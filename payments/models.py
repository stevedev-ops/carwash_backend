from django.db import models
from accounts.models import User, WorkerProfile

class WorkerPayment(models.Model):
    class PaymentMethod(models.TextChoices):
        MPESA = 'MPESA', 'M-Pesa Payout'
        CASH = 'CASH', 'Cash Payout'
        BANK = 'BANK', 'Bank Transfer'

    worker = models.ForeignKey(WorkerProfile, on_delete=models.PROTECT, related_name='payments')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    transaction_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='processed_worker_payments')
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_at']

    def __str__(self):
        return f"Payout #{self.id} to {self.worker.user.username}: KSh {self.amount_paid} ({self.payment_method})"

class Expense(models.Model):
    class Category(models.TextChoices):
        RENT = 'RENT', 'Premise Rent'
        WATER = 'WATER', 'Water Bill / Tanker'
        ELECTRICITY = 'POWER', 'Electricity'
        CHEMICALS = 'CHEMICALS', 'Soaps, Shampoos & Polishes'
        EQUIPMENT = 'EQUIPMENT', 'Machine & Pressure Washer Repairs'
        SALARY = 'SALARY', 'Fixed Base Staff / Security'
        OTHER = 'OTHER', 'Miscellaneous'

    category = models.CharField(max_length=25, choices=Category.choices, default=Category.OTHER)
    title = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    notes = models.TextField(blank=True)
    logged_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='logged_expenses')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} - KSh {self.amount} ({self.date})"

class DailyClosing(models.Model):
    date = models.DateField(unique=True, db_index=True)
    closed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='daily_closings')
    total_cars_washed = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cash_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_mpesa_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_commissions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_payouts = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_expenses = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_cash_in_drawer = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    actual_cash_counted = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_variance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Daily Closing {self.date}: KSh {self.total_revenue} Revenue (Variance: KSh {self.cash_variance})"
