from django.db import models
from accounts.models import WorkerProfile

class Service(models.Model):
    class CommissionType(models.TextChoices):
        FIXED = 'FIXED', 'Fixed Amount (KSh)'
        PERCENTAGE = 'PERCENTAGE', 'Percentage of Price (%)'

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    default_price = models.DecimalField(max_digits=10, decimal_places=2)
    default_commission_type = models.CharField(
        max_length=15, 
        choices=CommissionType.choices, 
        default=CommissionType.FIXED
    )
    default_commission_value = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="KSh amount if FIXED, or percentage (e.g. 20.00 for 20%) if PERCENTAGE"
    )
    estimated_minutes = models.IntegerField(default=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - KSh {self.default_price}"

class WorkerCommissionRate(models.Model):
    """Custom commission override for an individual worker on a specific service."""
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='custom_rates')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='worker_rates')
    commission_type = models.CharField(max_length=15, choices=Service.CommissionType.choices)
    commission_value = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('worker', 'service')

    def __str__(self):
        return f"{self.worker.user.username} @ {self.service.name}: {self.commission_value} ({self.commission_type})"
