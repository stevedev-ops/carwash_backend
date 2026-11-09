from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count, Q
from decimal import Decimal
from .models import WorkerAssignment, CarWash
from payments.models import WorkerPayment
from payments.serializers import WorkerPaymentSerializer
from .serializers import WorkerAssignmentSerializer

class WorkerSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        worker = getattr(user, 'worker_profile', None)
        
        # If admin testing worker portal, allow selecting worker_id
        if not worker and (user.is_superuser or user.role == 'ADMIN'):
            worker_id = request.query_params.get('worker_id')
            if worker_id:
                from accounts.models import WorkerProfile
                worker = WorkerProfile.objects.filter(id=worker_id).first()
        
        if not worker:
            return Response({'error': 'No worker profile attached to this account'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        today = now.date()
        start_of_week = today - timedelta(days=today.weekday())
        start_of_month = today.replace(day=1)

        base_assignments = WorkerAssignment.objects.filter(
            worker=worker,
            is_credited=True,
            car_wash_service__car_wash__status=CarWash.Status.COMPLETED
        )

        today_earnings = base_assignments.filter(
            created_at__date=today
        ).aggregate(s=Sum('commission_earned'))['s'] or Decimal('0.00')

        week_earnings = base_assignments.filter(
            created_at__date__gte=start_of_week
        ).aggregate(s=Sum('commission_earned'))['s'] or Decimal('0.00')

        month_earnings = base_assignments.filter(
            created_at__date__gte=start_of_month
        ).aggregate(s=Sum('commission_earned'))['s'] or Decimal('0.00')

        total_earned = worker.total_earned
        total_paid = worker.total_paid
        outstanding_balance = worker.outstanding_balance

        cars_worked_count = base_assignments.values('car_wash_service__car_wash').distinct().count()

        pending_count = WorkerAssignment.objects.filter(
            worker=worker,
            is_credited=False,
            car_wash_service__car_wash__status=CarWash.Status.PENDING_APPROVAL
        ).count()

        return Response({
            'worker_id': worker.id,
            'worker_name': worker.user.get_full_name() or worker.user.username,
            'phone_number': worker.user.phone_number or worker.mpesa_number,
            'today_earnings': today_earnings,
            'week_earnings': week_earnings,
            'month_earnings': month_earnings,
            'cars_worked_on': cars_worked_count,
            'pending_approval_jobs': pending_count,
            'total_earned': total_earned,
            'total_paid': total_paid,
            'outstanding_balance': outstanding_balance,
        })

class WorkerJobsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        worker = getattr(user, 'worker_profile', None)

        if not worker and (user.is_superuser or user.role == 'ADMIN'):
            worker_id = request.query_params.get('worker_id')
            if worker_id:
                from accounts.models import WorkerProfile
                worker = WorkerProfile.objects.filter(id=worker_id).first()

        if not worker:
            return Response({'error': 'No worker profile attached to this account'}, status=status.HTTP_404_NOT_FOUND)

        assignments = WorkerAssignment.objects.filter(worker=worker).select_related(
            'car_wash_service__car_wash__vehicle',
            'car_wash_service__service'
        ).order_by('-created_at')

        results = []
        for a in assignments:
            cw = a.car_wash_service.car_wash
            results.append({
                'assignment_id': a.id,
                'car_wash_id': cw.id,
                'plate_number': cw.vehicle.plate_number,
                'vehicle_type': cw.vehicle.get_vehicle_type_display(),
                'service_name': a.car_wash_service.service_name_snapshot,
                'price_charged': a.car_wash_service.price_charged,
                'commission_earned': a.commission_earned,
                'rate_applied': a.rate_applied_snapshot,
                'is_credited': a.is_credited,
                'status': cw.status,
                'date': a.created_at.strftime('%Y-%m-%d %H:%M'),
            })

        return Response(results)

