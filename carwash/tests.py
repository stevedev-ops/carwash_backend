from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from accounts.models import User, WorkerProfile
from services.models import Service, WorkerCommissionRate
from carwash.models import Vehicle, CarWash, CarWashService, WorkerAssignment
from carwash.services import calculate_worker_commission, approve_car_wash

class CommissionAndApprovalTests(TestCase):
    def setUp(self):
        # 1. Setup Admin & Workers
        self.admin = User.objects.create_superuser('admin_test', 'admin@test.com', 'pass123', role=User.Role.ADMIN)
        self.worker_user1 = User.objects.create_user('john_test', 'john@test.com', 'pass123', role=User.Role.WORKER)
        self.worker1 = WorkerProfile.objects.create(user=self.worker_user1, mpesa_number='0712345671')

        self.worker_user2 = User.objects.create_user('peter_test', 'peter@test.com', 'pass123', role=User.Role.WORKER)
        self.worker2 = WorkerProfile.objects.create(user=self.worker_user2, mpesa_number='0712345672')

        # 2. Setup Services
        self.exterior_service = Service.objects.create(
            name='Exterior Wash',
            default_price=Decimal('200.00'),
            default_commission_type=Service.CommissionType.FIXED,
            default_commission_value=Decimal('50.00')
        )

        self.engine_service = Service.objects.create(
            name='Engine Steam',
            default_price=Decimal('400.00'),
            default_commission_type=Service.CommissionType.FIXED,
            default_commission_value=Decimal('100.00')
        )

        self.custom_percent_service = Service.objects.create(
            name='Ceramic Coating',
            default_price=Decimal('2000.00'),
            default_commission_type=Service.CommissionType.PERCENTAGE,
            default_commission_value=Decimal('20.00') # 20%
        )

        # 3. Setup Custom Override for John on Exterior Wash (Senior rate KSh 70 instead of 50)
        WorkerCommissionRate.objects.create(
            worker=self.worker1,
            service=self.exterior_service,
            commission_type=Service.CommissionType.FIXED,
            commission_value=Decimal('70.00')
        )

        # 4. Setup Vehicle
        self.vehicle = Vehicle.objects.create(
            plate_number='KDA 999Z',
            vehicle_type=Vehicle.VehicleType.SALOON_SEDAN
        )

    def test_hierarchical_commission_calculation(self):
        """Worker with custom override gets custom rate; worker without gets default rate."""
        # John has override (KSh 70)
        comm_john, snap_john = calculate_worker_commission(self.worker1, self.exterior_service, Decimal('200.00'))
        self.assertEqual(comm_john, Decimal('70.00'))

        # Peter has NO override on Exterior (fallback to service default KSh 50)
        comm_peter, snap_peter = calculate_worker_commission(self.worker2, self.exterior_service, Decimal('200.00'))
        self.assertEqual(comm_peter, Decimal('50.00'))

        # Percentage commission test (20% of 2000 = 400)
        comm_percent, _ = calculate_worker_commission(self.worker2, self.custom_percent_service, Decimal('2000.00'))
        self.assertEqual(comm_percent, Decimal('400.00'))

    def test_multi_worker_car_wash_approval_flow(self):
        """Worker logs job -> status PENDING -> commissions uncredited -> Admin approves -> credited."""
        car_wash = CarWash.objects.create(
            vehicle=self.vehicle,
            status=CarWash.Status.PENDING_APPROVAL,
            bay_number=1,
            total_amount=Decimal('600.00'),
            logged_by=self.worker_user1
        )

        # Service 1: Exterior Wash performed by John (KSh 70 custom comm)
        cws1 = CarWashService.objects.create(
            car_wash=car_wash,
            service=self.exterior_service,
            service_name_snapshot='Exterior Wash',
            price_charged=Decimal('200.00')
        )
        assign1 = WorkerAssignment.objects.create(
            car_wash_service=cws1,
            worker=self.worker1,
            commission_earned=Decimal('70.00'),
            rate_applied_snapshot='Custom Override KSh 70.00',
            is_credited=False
        )

        # Service 2: Engine Steam performed by Peter (KSh 100 default comm)
        cws2 = CarWashService.objects.create(
            car_wash=car_wash,
            service=self.engine_service,
            service_name_snapshot='Engine Steam',
            price_charged=Decimal('400.00')
        )
        assign2 = WorkerAssignment.objects.create(
            car_wash_service=cws2,
            worker=self.worker2,
            commission_earned=Decimal('100.00'),
            rate_applied_snapshot='Default KSh 100.00',
            is_credited=False
        )

        # Before approval, worker outstanding balance should be 0 (uncredited)
        self.assertEqual(self.worker1.total_earned, Decimal('0.00'))
        self.assertEqual(self.worker2.total_earned, Decimal('0.00'))

        # Admin approves the job
        approved_wash = approve_car_wash(car_wash, self.admin)

        self.assertEqual(approved_wash.status, CarWash.Status.COMPLETED)
        self.assertEqual(approved_wash.total_commission, Decimal('170.00'))
        self.assertEqual(approved_wash.net_business_revenue, Decimal('430.00'))

        # Verify worker ledger credited
        assign1.refresh_from_db()
        assign2.refresh_from_db()
        self.assertTrue(assign1.is_credited)
        self.assertTrue(assign2.is_credited)
        self.assertEqual(self.worker1.total_earned, Decimal('70.00'))
        self.assertEqual(self.worker2.total_earned, Decimal('100.00'))
