from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import datetime, time
from django.db.models import Sum, Q, Count
from core.permissions import IsAdminUser, IsAdminOrReadOnly
from .models import Vehicle, CarWash, WorkerAssignment
from .serializers import (
    VehicleSerializer, CarWashSerializer, CarWashCreateSerializer, WorkerAssignmentSerializer
)
from .services import approve_car_wash

class VehicleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vehicle.objects.all().order_by('-created_at')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        query = self.request.query_params.get('search')
        if query:
            qs = qs.filter(Q(plate_number__icontains=query) | Q(customer_phone__icontains=query))
        return qs

    @action(detail=False, methods=['get'])
    def lookup(self, request):
        plate = request.query_params.get('plate', '').strip().upper()
        if not plate:
            return Response({'exists': False})
        
        # Match exact or with spaces removed (e.g. KDA124B vs KDA 124B)
        clean_input = plate.replace(' ', '')
        from django.db.models.functions import Replace
        from django.db.models import Value
        veh = Vehicle.objects.annotate(
            no_space=Replace('plate_number', Value(' '), Value(''))
        ).filter(Q(no_space__iexact=clean_input) | Q(plate_number__icontains=plate)).first()

        if not veh:
            return Response({'exists': False})
        
        last_wash = veh.washes.filter(status='COMPLETED').order_by('-created_at').first()
        wash_count = veh.washes.filter(status='COMPLETED').count()
        total_spent = veh.washes.filter(status='COMPLETED').aggregate(s=Sum('total_amount'))['s'] or 0

        return Response({
            'exists': True,
            'id': veh.id,
            'plate_number': veh.plate_number,
            'vehicle_type': veh.vehicle_type,
            'make_model': veh.make_model,
            'customer_name': veh.customer_name,
            'customer_phone': veh.customer_phone,
            'total_washes': wash_count,
            'total_spent': float(total_spent),
            'last_wash_date': last_wash.created_at.strftime('%Y-%m-%d %H:%M') if last_wash else None
        })

class CarWashViewSet(viewsets.ModelViewSet):
    queryset = CarWash.objects.all().select_related('vehicle', 'logged_by', 'approved_by').prefetch_related('services__assignments__worker__user')
    serializer_class = CarWashSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return CarWashCreateSerializer
        return CarWashSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        filter_date = self.request.query_params.get('date') # YYYY-MM-DD
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        plate = self.request.query_params.get('plate')
        worker_id = self.request.query_params.get('worker_id')

        if status_param:
            qs = qs.filter(status=status_param)

        if filter_date:
            qs = qs.filter(created_at__date=filter_date)
        elif date_from and date_to:
            qs = qs.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)

        if plate:
            qs = qs.filter(vehicle__plate_number__icontains=plate)

        is_paid = self.request.query_params.get('is_paid')
        if is_paid is not None:
            if str(is_paid).lower() in ['true', '1']:
                qs = qs.filter(is_paid=True)
            elif str(is_paid).lower() in ['false', '0']:
                qs = qs.filter(is_paid=False)

        if worker_id:
            qs = qs.filter(services__assignments__worker_id=worker_id).distinct()

        # If user is a worker, allow filtering to see only their logged jobs or jobs they worked on
        if getattr(self.request.user, 'role', '') == 'WORKER' and self.action == 'list':
            worker_profile = getattr(self.request.user, 'worker_profile', None)
            if worker_profile:
                qs = qs.filter(Q(logged_by=self.request.user) | Q(services__assignments__worker=worker_profile)).distinct()

        return qs

    def create(self, request, *args, **kwargs):
        serializer = CarWashCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        car_wash = serializer.save()
        output_serializer = CarWashSerializer(car_wash)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        car_wash = self.get_object()
        if car_wash.status == CarWash.Status.COMPLETED:
            return Response({'message': 'Already approved and completed'}, status=status.HTTP_200_OK)

        car_wash = approve_car_wash(car_wash, request.user)
        return Response(CarWashSerializer(car_wash).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def cancel(self, request, pk=None):
        car_wash = self.get_object()
        car_wash.status = CarWash.Status.CANCELLED
        # Uncredit assignments
        for s in car_wash.services.all():
            s.assignments.update(is_credited=False)
        car_wash.save()
        return Response(CarWashSerializer(car_wash).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def collect_payment(self, request, pk=None):
        from decimal import Decimal
        car_wash = self.get_object()
        method = request.data.get('payment_method', CarWash.PaymentMethod.CASH)
        raw_cash = Decimal(str(request.data.get('cash_amount') or '0.00'))
        raw_mpesa = Decimal(str(request.data.get('mpesa_amount') or '0.00'))
        ref = request.data.get('payment_reference', '').strip()

        car_wash.payment_method = method
        car_wash.payment_reference = ref
        car_wash.is_paid = True
        car_wash.completed_at = car_wash.completed_at or timezone.now()

        if method == CarWash.PaymentMethod.CASH:
            car_wash.cash_amount = car_wash.total_amount
            car_wash.mpesa_amount = Decimal('0.00')
        elif method == CarWash.PaymentMethod.MPESA:
            car_wash.cash_amount = Decimal('0.00')
            car_wash.mpesa_amount = car_wash.total_amount
        elif method == CarWash.PaymentMethod.SPLIT:
            car_wash.cash_amount = raw_cash
            car_wash.mpesa_amount = raw_mpesa if raw_mpesa > 0 else (car_wash.total_amount - raw_cash)
        else:
            car_wash.cash_amount = raw_cash
            car_wash.mpesa_amount = raw_mpesa

        car_wash.save()
        return Response(CarWashSerializer(car_wash).data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def unpaid(self, request):
        unpaid_washes = self.get_queryset().filter(is_paid=False).exclude(status=CarWash.Status.CANCELLED)
        serializer = CarWashSerializer(unpaid_washes, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def pending(self, request):
        pending_washes = self.get_queryset().filter(status=CarWash.Status.PENDING_APPROVAL)
        serializer = CarWashSerializer(pending_washes, many=True)
        return Response(serializer.data)
