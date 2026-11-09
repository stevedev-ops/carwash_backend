from decimal import Decimal
from datetime import datetime
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Sum
from core.permissions import IsAdminUser, IsAdminOrReadOnly
from carwash.models import CarWash
from .models import WorkerPayment, Expense, DailyClosing
from .serializers import (
    WorkerPaymentSerializer, WorkerPaymentCreateSerializer, 
    ExpenseSerializer, DailyClosingSerializer
)

class WorkerPaymentViewSet(viewsets.ModelViewSet):
    queryset = WorkerPayment.objects.all().select_related('worker__user', 'processed_by')
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.action == 'create':
            return WorkerPaymentCreateSerializer
        return WorkerPaymentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        worker_id = self.request.query_params.get('worker_id')
        if worker_id:
            qs = qs.filter(worker_id=worker_id)
        method = self.request.query_params.get('payment_method')
        if method:
            qs = qs.filter(payment_method=method)
        return qs

class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().select_related('logged_by')
    serializer_class = ExpenseSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from and date_to:
            qs = qs.filter(date__gte=date_from, date__lte=date_to)
        return qs

class WorkerPayoutHistoryView(APIView):
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
            return Response({'error': 'No worker profile found'}, status=status.HTTP_404_NOT_FOUND)

        payments = WorkerPayment.objects.filter(worker=worker).order_by('-paid_at')
        serializer = WorkerPaymentSerializer(payments, many=True)
        return Response(serializer.data)

class DailyClosingViewSet(viewsets.ModelViewSet):
    queryset = DailyClosing.objects.all().select_related('closed_by')
    serializer_class = DailyClosingSerializer
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['get'])
    def preview(self, request):
        date_str = request.query_params.get('date')
        date_val = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()

        completed_washes = CarWash.objects.filter(created_at__date=date_val, status=CarWash.Status.COMPLETED)
        total_cars = completed_washes.count()
        total_revenue = completed_washes.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')
        cash_rev = completed_washes.aggregate(s=Sum('cash_amount'))['s'] or Decimal('0.00')
        mpesa_rev = completed_washes.aggregate(s=Sum('mpesa_amount'))['s'] or Decimal('0.00')
        commissions = completed_washes.aggregate(s=Sum('total_commission'))['s'] or Decimal('0.00')

        # Payouts disbursed today
        payouts_qs = WorkerPayment.objects.filter(paid_at__date=date_val)
        total_payouts = payouts_qs.aggregate(s=Sum('amount_paid'))['s'] or Decimal('0.00')
        cash_payouts = payouts_qs.filter(payment_method=WorkerPayment.PaymentMethod.CASH).aggregate(s=Sum('amount_paid'))['s'] or Decimal('0.00')

        # Expenses logged today
        expenses_qs = Expense.objects.filter(date=date_val)
        total_expenses = expenses_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        expected_cash = cash_rev - cash_payouts - total_expenses
        existing_closing = DailyClosing.objects.filter(date=date_val).first()

        return Response({
            'date': str(date_val),
            'total_cars_washed': total_cars,
            'total_revenue': float(total_revenue),
            'total_cash_revenue': float(cash_rev),
            'total_mpesa_revenue': float(mpesa_rev),
            'total_commissions': float(commissions),
            'total_payouts': float(total_payouts),
            'total_expenses': float(total_expenses),
            'expected_cash_in_drawer': float(expected_cash),
            'is_already_closed': bool(existing_closing),
            'existing_closing': DailyClosingSerializer(existing_closing).data if existing_closing else None
        })

    def perform_create(self, serializer):
        expected = serializer.validated_data.get('expected_cash_in_drawer', Decimal('0.00'))
        actual = serializer.validated_data.get('actual_cash_counted', Decimal('0.00'))
        variance = actual - expected
        serializer.save(closed_by=self.request.user, cash_variance=variance)
