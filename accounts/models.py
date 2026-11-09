from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Sum

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin / Manager'
        CASHIER = 'CASHIER', 'Cashier'
        WORKER = 'WORKER', 'Car Wash Worker'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.WORKER)
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True)

    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def is_worker(self):
        return self.role == self.Role.WORKER

class WorkerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='worker_profile')
    national_id = models.CharField(max_length=50, blank=True, null=True)
    mpesa_number = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateField(auto_now_add=True)
    emergency_contact = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.mpesa_number or self.user.phone_number or 'No Phone'})"

    @property
    def total_earned(self):
        from carwash.models import WorkerAssignment
        # Only count approved/credited car wash jobs
        val = WorkerAssignment.objects.filter(
            worker=self, 
            is_credited=True,
            car_wash_service__car_wash__status='COMPLETED'
        ).aggregate(total=Sum('commission_earned'))['total']
        return val or 0

    @property
    def total_paid(self):
        from payments.models import WorkerPayment
        val = WorkerPayment.objects.filter(worker=self).aggregate(total=Sum('amount_paid'))['total']
        return val or 0

    @property
    def outstanding_balance(self):
        return self.total_earned - self.total_paid

class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'PRESENT', 'Present on Bay'
        ABSENT = 'ABSENT', 'Absent'
        HALF_DAY = 'HALF_DAY', 'Half Day'
        ON_LEAVE = 'ON_LEAVE', 'On Leave'

    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    clock_in = models.TimeField(null=True, blank=True)
    clock_out = models.TimeField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    marked_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='marked_attendances')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('worker', 'date')
        ordering = ['-date', 'worker__user__first_name']

    def __str__(self):
        return f"{self.worker.user.first_name} - {self.date}: {self.status}"
