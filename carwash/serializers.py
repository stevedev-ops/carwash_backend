from decimal import Decimal
from rest_framework import serializers
from accounts.models import WorkerProfile
from services.models import Service
from .models import Vehicle, CarWash, CarWashService, WorkerAssignment
from .services import calculate_worker_commission

class VehicleSerializer(serializers.ModelSerializer):
    washes_count = serializers.IntegerField(source='washes.count', read_only=True)

    class Meta:
        model = Vehicle
        fields = ['id', 'plate_number', 'vehicle_type', 'make_model', 'customer_name', 'customer_phone', 'washes_count', 'created_at']
        read_only_fields = ['id', 'created_at']

class WorkerAssignmentSerializer(serializers.ModelSerializer):
    worker_id = serializers.ReadOnlyField(source='worker.id')
    worker_name = serializers.ReadOnlyField(source='worker.user.get_full_name')
    worker_username = serializers.ReadOnlyField(source='worker.user.username')

    class Meta:
        model = WorkerAssignment
        fields = ['id', 'worker_id', 'worker_name', 'worker_username', 'commission_earned', 'rate_applied_snapshot', 'is_credited', 'created_at']

class CarWashServiceSerializer(serializers.ModelSerializer):
    assignments = WorkerAssignmentSerializer(many=True, read_only=True)
    service_id = serializers.ReadOnlyField(source='service.id')

    class Meta:
        model = CarWashService
        fields = ['id', 'service_id', 'service_name_snapshot', 'price_charged', 'assignments']

class CarWashSerializer(serializers.ModelSerializer):
    vehicle = VehicleSerializer(read_only=True)
    services = CarWashServiceSerializer(many=True, read_only=True)
    logged_by_name = serializers.ReadOnlyField(source='logged_by.get_full_name')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.get_full_name')

    class Meta:
        model = CarWash
        fields = [
            'id', 'vehicle', 'status', 'bay_number', 'total_amount', 'cash_amount', 'mpesa_amount',
            'total_commission', 'net_business_revenue', 'payment_method', 'payment_reference', 'is_paid',
            'logged_by_name', 'approved_by_name', 'created_at', 'completed_at', 'notes',
            'services'
        ]

class ServiceItemInputSerializer(serializers.Serializer):
    service_id = serializers.IntegerField()
    price_charged = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    worker_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

class CarWashCreateSerializer(serializers.Serializer):
    plate_number = serializers.CharField(max_length=20)
    vehicle_type = serializers.ChoiceField(choices=Vehicle.VehicleType.choices, default=Vehicle.VehicleType.SALOON_SEDAN)
    make_model = serializers.CharField(max_length=100, required=False, allow_blank=True)
    customer_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    customer_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    bay_number = serializers.IntegerField(default=1, required=False)
    payment_method = serializers.ChoiceField(choices=CarWash.PaymentMethod.choices, default=CarWash.PaymentMethod.CASH)
    cash_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal('0.00'))
    mpesa_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal('0.00'))
    payment_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    is_paid = serializers.BooleanField(default=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = ServiceItemInputSerializer(many=True)

    def create(self, validated_data):
        user = self.context['request'].user
        plate_number = validated_data['plate_number'].strip().upper()
        
        # Get or create Vehicle
        vehicle, _ = Vehicle.objects.get_or_create(
            plate_number=plate_number,
            defaults={
                'vehicle_type': validated_data.get('vehicle_type', Vehicle.VehicleType.SALOON_SEDAN),
                'make_model': validated_data.get('make_model', ''),
                'customer_name': validated_data.get('customer_name', ''),
                'customer_phone': validated_data.get('customer_phone', ''),
            }
        )

        is_worker = getattr(user, 'role', '') == 'WORKER'
        # Workers create jobs with PENDING_APPROVAL; Admins create COMPLETED
        initial_status = CarWash.Status.PENDING_APPROVAL if is_worker else CarWash.Status.COMPLETED

        is_paid = validated_data.get('is_paid', True)
        payment_method = validated_data.get('payment_method', CarWash.PaymentMethod.CASH)
        if payment_method == CarWash.PaymentMethod.UNPAID or is_paid is False:
            is_paid = False
            payment_method = CarWash.PaymentMethod.UNPAID

        car_wash = CarWash.objects.create(
            vehicle=vehicle,
            status=initial_status,
            bay_number=validated_data.get('bay_number', 1),
            payment_method=payment_method,
            payment_reference=validated_data.get('payment_reference', '') if is_paid else '',
            is_paid=is_paid,
            logged_by=user,
            approved_by=user if not is_worker else None,
            notes=validated_data.get('notes', '')
        )

        total_amount = Decimal('0.00')
        total_commission = Decimal('0.00')

        items_data = validated_data['items']
        for item in items_data:
            service = Service.objects.get(id=item['service_id'])
            price = Decimal(str(item.get('price_charged') or service.default_price))
            total_amount += price

            cws = CarWashService.objects.create(
                car_wash=car_wash,
                service=service,
                service_name_snapshot=service.name,
                price_charged=price
            )

            # Assign workers
            workers = WorkerProfile.objects.filter(id__in=item['worker_ids'])
            num_workers = len(workers)
            for w in workers:
                comm, snapshot = calculate_worker_commission(w, service, price)
                # If multiple workers share a single service, split commission evenly
                if num_workers > 1:
                    comm = (comm / Decimal(num_workers)).quantize(Decimal('0.01'))
                    snapshot = f"{snapshot} (Split 1/{num_workers})"

                is_credited = (car_wash.status == CarWash.Status.COMPLETED)
                WorkerAssignment.objects.create(
                    car_wash_service=cws,
                    worker=w,
                    commission_earned=comm,
                    rate_applied_snapshot=snapshot,
                    is_credited=is_credited
                )
                total_commission += comm

        car_wash.total_amount = total_amount
        car_wash.total_commission = total_commission
        car_wash.net_business_revenue = total_amount - total_commission

        # Set cash and mpesa amounts based on payment method
        method = car_wash.payment_method
        raw_cash = Decimal(str(validated_data.get('cash_amount') or '0.00'))
        raw_mpesa = Decimal(str(validated_data.get('mpesa_amount') or '0.00'))

        if not car_wash.is_paid or method == CarWash.PaymentMethod.UNPAID:
            car_wash.cash_amount = Decimal('0.00')
            car_wash.mpesa_amount = Decimal('0.00')
        elif method == CarWash.PaymentMethod.CASH:
            car_wash.cash_amount = total_amount
            car_wash.mpesa_amount = Decimal('0.00')
        elif method == CarWash.PaymentMethod.MPESA:
            car_wash.cash_amount = Decimal('0.00')
            car_wash.mpesa_amount = total_amount
        elif method == CarWash.PaymentMethod.SPLIT:
            car_wash.cash_amount = raw_cash
            car_wash.mpesa_amount = raw_mpesa if raw_mpesa > 0 else (total_amount - raw_cash)
        else:
            car_wash.cash_amount = raw_cash
            car_wash.mpesa_amount = raw_mpesa

        car_wash.save()

        return car_wash

