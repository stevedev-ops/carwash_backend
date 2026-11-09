from decimal import Decimal
from rest_framework import serializers
from accounts.models import WorkerProfile
from .models import WorkerPayment, Expense, DailyClosing

class WorkerPaymentSerializer(serializers.ModelSerializer):
    worker_name = serializers.ReadOnlyField(source='worker.user.get_full_name')
    worker_username = serializers.ReadOnlyField(source='worker.user.username')
    worker_phone = serializers.ReadOnlyField(source='worker.mpesa_number')
    processed_by_name = serializers.ReadOnlyField(source='processed_by.get_full_name')

    class Meta:
        model = WorkerPayment
        fields = [
            'id', 'worker', 'worker_name', 'worker_username', 'worker_phone',
            'amount_paid', 'payment_method', 'transaction_reference', 'notes',
            'processed_by_name', 'paid_at'
        ]
        read_only_fields = ['id', 'paid_at', 'processed_by_name']

class WorkerPaymentCreateSerializer(serializers.ModelSerializer):
    worker_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = WorkerPayment
        fields = ['worker_id', 'amount_paid', 'payment_method', 'transaction_reference', 'notes']

    def validate_amount_paid(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value

    def create(self, validated_data):
        worker_id = validated_data.pop('worker_id')
        worker = WorkerProfile.objects.get(id=worker_id)
        user = self.context['request'].user
        payment = WorkerPayment.objects.create(
            worker=worker,
            processed_by=user,
            **validated_data
        )
        return payment

class ExpenseSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    logged_by_name = serializers.ReadOnlyField(source='logged_by.get_full_name')

    class Meta:
        model = Expense
        fields = ['id', 'category', 'category_display', 'title', 'amount', 'date', 'notes', 'logged_by_name', 'created_at']
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        return Expense.objects.create(logged_by=user, **validated_data)

class DailyClosingSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.ReadOnlyField(source='closed_by.get_full_name')

    class Meta:
        model = DailyClosing
        fields = [
            'id', 'date', 'closed_by_name', 'total_cars_washed', 'total_revenue',
            'total_cash_revenue', 'total_mpesa_revenue', 'total_commissions',
            'total_payouts', 'total_expenses', 'expected_cash_in_drawer',
            'actual_cash_counted', 'cash_variance', 'notes', 'closed_at'
        ]
        read_only_fields = ['id', 'closed_by_name', 'closed_at']

