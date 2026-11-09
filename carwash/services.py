from decimal import Decimal
from django.utils import timezone
from services.models import WorkerCommissionRate

def calculate_worker_commission(worker, service, price_charged):
    """
    Computes commission based on hierarchical model:
    1. Checks worker-specific custom override
    2. Fallbacks to service's default commission
    3. Calculates fixed or percentage
    """
    override = WorkerCommissionRate.objects.filter(worker=worker, service=service).first()
    
    if override:
        comm_type = override.commission_type
        comm_value = Decimal(str(override.commission_value))
        snapshot = f"Custom ({comm_value}% if % else KSh {comm_value})"
    else:
        comm_type = service.default_commission_type
        comm_value = Decimal(str(service.default_commission_value))
        snapshot = f"Default ({comm_value}% if % else KSh {comm_value})"

    if comm_type == 'PERCENTAGE':
        commission = (Decimal(str(price_charged)) * comm_value) / Decimal('100.0')
    else:
        commission = comm_value

    return commission.quantize(Decimal('0.01')), snapshot

def approve_car_wash(car_wash, approved_by_user):
    """
    Approves a car wash record, marks assignments as credited to unlock worker earnings.
    """
    car_wash.status = 'COMPLETED'
    car_wash.approved_by = approved_by_user
    car_wash.completed_at = timezone.now()

    # Calculate total commission and credit assignments
    total_commission = Decimal('0.00')
    for cws in car_wash.services.all():
        for assignment in cws.assignments.all():
            assignment.is_credited = True
            assignment.save()
            total_commission += assignment.commission_earned

    car_wash.total_commission = total_commission
    car_wash.net_business_revenue = Decimal(str(car_wash.total_amount)) - total_commission
    car_wash.save()
    return car_wash

