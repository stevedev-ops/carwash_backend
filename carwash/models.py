from django.db import models
from accounts.models import User, WorkerProfile
from services.models import Service

class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        SALOON_SEDAN = 'SEDAN', 'Saloon / Sedan'
        SUV_4X4 = 'SUV', 'SUV / 4x4'
        VAN_PICKUP = 'VAN', 'Van / Pickup'
        MOTORBIKE = 'BODA', 'Motorbike / Boda'
        TRUCK_BUS = 'TRUCK', 'Truck / Bus'

    plate_number = models.CharField(max_length=20, unique=True, db_index=True)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.SALOON_SEDAN)
    make_model = models.CharField(max_length=100, blank=True)
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.plate_number.upper()} ({self.get_vehicle_type_display()})"

class CarWash(models.Model):
    class Status(models.TextChoices):
        PENDING_APPROVAL = 'PENDING', 'Pending Approval'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed & Approved'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class PaymentMethod(models.TextChoices):
        MPESA = 'MPESA', 'M-Pesa'
        CASH = 'CASH', 'Cash'
        SPLIT = 'SPLIT', 'Split (Cash + M-Pesa)'
        CARD = 'CARD', 'Credit / Debit Card'
        CREDIT = 'CREDIT', 'Customer Account / Credit'
        UNPAID = 'UNPAID', 'Pay on Collection (Unpaid)'

    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='washes')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    bay_number = models.IntegerField(default=1, null=True, blank=True)

    # Financial snapshots
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mpesa_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_commission = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_business_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    payment_reference = models.CharField(max_length=100, blank=True)
    is_paid = models.BooleanField(default=True)

    logged_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='recorded_washes')
    approved_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='approved_washes')
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Wash #{self.id} - {self.vehicle.plate_number} ({self.status})"

class CarWashService(models.Model):
    car_wash = models.ForeignKey(CarWash, on_delete=models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    service_name_snapshot = models.CharField(max_length=120)
    price_charged = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.service_name_snapshot} - KSh {self.price_charged}"

class WorkerAssignment(models.Model):
    car_wash_service = models.ForeignKey(CarWashService, on_delete=models.CASCADE, related_name='assignments')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.PROTECT, related_name='assignments')
    commission_earned = models.DecimalField(max_digits=10, decimal_places=2)
    rate_applied_snapshot = models.CharField(max_length=100)
    is_credited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.worker.user.username} on {self.car_wash_service.service_name_snapshot}: KSh {self.commission_earned}"
