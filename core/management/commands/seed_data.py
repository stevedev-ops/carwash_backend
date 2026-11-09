from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import User, WorkerProfile
from services.models import Service, WorkerCommissionRate
from carwash.models import Vehicle, CarWash, CarWashService, WorkerAssignment
from payments.models import WorkerPayment, Expense

class Command(BaseCommand):
    help = 'Seeds initial car wash business data, workers, services, and transactions'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Clearing old demo data..."))
        WorkerPayment.objects.all().delete()
        WorkerAssignment.objects.all().delete()
        CarWashService.objects.all().delete()
        CarWash.objects.all().delete()
        Vehicle.objects.all().delete()
        WorkerCommissionRate.objects.all().delete()
        Service.objects.all().delete()
        Expense.objects.all().delete()
        WorkerProfile.objects.all().delete()
        User.objects.exclude(is_superuser=True).delete()

        self.stdout.write(self.style.NOTICE("Creating Users & Workers..."))
        # 1. Admin
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'Manager',
                'last_name': 'Admin',
                'email': 'admin@shellcarwash.co.ke',
                'phone_number': '0700000000',
                'role': User.Role.ADMIN,
                'is_staff': True,
                'is_superuser': True
            }
        )
        admin_user.set_password('admin123')
        admin_user.save()

        # 2. Cashier
        cashier_user, _ = User.objects.get_or_create(
            username='cashier',
            defaults={
                'first_name': 'Grace',
                'last_name': 'Moraa',
                'email': 'cashier@shellcarwash.co.ke',
                'phone_number': '0711000111',
                'role': User.Role.CASHIER,
            }
        )
        cashier_user.set_password('cashier123')
        cashier_user.save()

        # 3. Workers
        workers_data = [
            ('steve', 'Steve', 'Mwangi', '0712345670', 'ID34567890', '0712345670'),
            ('john', 'John', 'Kariuki', '0712345671', 'ID29837411', '0712345671'),
            ('peter', 'Peter', 'Kamau', '0712345672', 'ID31849202', '0712345672'),
            ('james', 'James', 'Omondi', '0712345673', 'ID28471923', '0712345673'),
            ('mary', 'Mary', 'Wambui', '0712345674', 'ID33918274', '0712345674'),
        ]

        worker_objs = {}
        for username, fname, lname, phone, nid, mpesa in workers_data:
            u, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'phone_number': phone,
                    'role': User.Role.WORKER
                }
            )
            u.set_password('worker123')
            u.save()

            wp, _ = WorkerProfile.objects.get_or_create(
                user=u,
                defaults={
                    'national_id': nid,
                    'mpesa_number': mpesa,
                    'emergency_contact': f"Relative of {fname}: 0722000999"
                }
            )
            worker_objs[username] = wp

        self.stdout.write(self.style.NOTICE("Creating Services & Commission Rates..."))
        services_data = [
            ("Exterior wash", 200, Service.CommissionType.FIXED, 50, 15),
            ("Interior cleaning", 300, Service.CommissionType.FIXED, 80, 25),
            ("Full wash", 500, Service.CommissionType.FIXED, 140, 40),
            ("Engine wash", 400, Service.CommissionType.FIXED, 100, 20),
            ("Carpet cleaning", 300, Service.CommissionType.FIXED, 70, 20),
            ("Underwash", 200, Service.CommissionType.FIXED, 50, 15),
        ]

        service_objs = {}
        for name, price, comm_type, comm_val, mins in services_data:
            s, _ = Service.objects.get_or_create(
                name=name,
                defaults={
                    'default_price': Decimal(str(price)),
                    'default_commission_type': comm_type,
                    'default_commission_value': Decimal(str(comm_val)),
                    'estimated_minutes': mins
                }
            )
            service_objs[name] = s

        # Custom override: John gets KSh 60 on Exterior wash (Senior rate)
        WorkerCommissionRate.objects.get_or_create(
            worker=worker_objs['john'],
            service=service_objs['Exterior wash'],
            defaults={'commission_type': Service.CommissionType.FIXED, 'commission_value': Decimal('60.00')}
        )

        # Custom override: Peter gets 25% on Engine wash
        WorkerCommissionRate.objects.get_or_create(
            worker=worker_objs['peter'],
            service=service_objs['Engine wash'],
            defaults={'commission_type': Service.CommissionType.PERCENTAGE, 'commission_value': Decimal('25.00')}
        )

        self.stdout.write(self.style.NOTICE("Creating Sample Vehicles & Car Wash Transactions..."))
        vehicles_data = [
            ("KDA 124B", Vehicle.VehicleType.SALOON_SEDAN, "Toyota Probox", "David Ndirangu", "0722123456"),
            ("KDF 992P", Vehicle.VehicleType.SUV_4X4, "Toyota Prado TX", "Senator Mutua", "0733654321"),
            ("KDD 405X", Vehicle.VehicleType.VAN_PICKUP, "Isuzu D-Max", "Fast Cargo Ltd", "0711987654"),
            ("KDE 312M", Vehicle.VehicleType.SALOON_SEDAN, "Mazda CX-5", "Caroline Achieng", "0720554433"),
            ("KMDF 884L", Vehicle.VehicleType.MOTORBIKE, "Bajaj Boxer 150", "Boda Rider Kevin", "0701223344"),
            ("KDC 711T", Vehicle.VehicleType.SUV_4X4, "Subaru Forester", "Brian Otieno", "0719887766"),
        ]

        veh_objs = {}
        for plate, vtype, model, cname, cphone in vehicles_data:
            v, _ = Vehicle.objects.get_or_create(
                plate_number=plate,
                defaults={'vehicle_type': vtype, 'make_model': model, 'customer_name': cname, 'customer_phone': cphone}
            )
            veh_objs[plate] = v

        now = timezone.now()

        # Wash 1: Toyota Probox (Full wash split: Exterior John, Interior Peter, Engine James)
        cw1 = CarWash.objects.create(
            vehicle=veh_objs["KDA 124B"],
            status=CarWash.Status.COMPLETED,
            bay_number=1,
            total_amount=Decimal('900.00'),
            total_commission=Decimal('240.00'),
            net_business_revenue=Decimal('660.00'),
            payment_method=CarWash.PaymentMethod.MPESA,
            payment_reference="SDF7842NJK",
            is_paid=True,
            logged_by=admin_user,
            approved_by=admin_user,
            notes="Full package on Probox"
        )
        cw1.created_at = now - timedelta(hours=3)
        cw1.completed_at = now - timedelta(hours=2)
        cw1.save()

        # Services for cw1
        cws1 = CarWashService.objects.create(car_wash=cw1, service=service_objs['Exterior wash'], service_name_snapshot='Exterior wash', price_charged=Decimal('200.00'))
        WorkerAssignment.objects.create(car_wash_service=cws1, worker=worker_objs['john'], commission_earned=Decimal('60.00'), rate_applied_snapshot='Custom Override KSh 60.00', is_credited=True)

        cws2 = CarWashService.objects.create(car_wash=cw1, service=service_objs['Interior cleaning'], service_name_snapshot='Interior cleaning', price_charged=Decimal('300.00'))
        WorkerAssignment.objects.create(car_wash_service=cws2, worker=worker_objs['peter'], commission_earned=Decimal('80.00'), rate_applied_snapshot='Default KSh 80.00', is_credited=True)

        cws3 = CarWashService.objects.create(car_wash=cw1, service=service_objs['Engine wash'], service_name_snapshot='Engine wash', price_charged=Decimal('400.00'))
        WorkerAssignment.objects.create(car_wash_service=cws3, worker=worker_objs['james'], commission_earned=Decimal('100.00'), rate_applied_snapshot='Default KSh 100.00', is_credited=True)

        # Wash 2: Toyota Prado (Full Wash by Mary)
        cw2 = CarWash.objects.create(
            vehicle=veh_objs["KDF 992P"],
            status=CarWash.Status.COMPLETED,
            bay_number=2,
            total_amount=Decimal('1000.00'),
            total_commission=Decimal('280.00'),
            net_business_revenue=Decimal('720.00'),
            payment_method=CarWash.PaymentMethod.CASH,
            payment_reference="RECEIPT-0012",
            is_paid=True,
            logged_by=admin_user,
            approved_by=admin_user,
            notes="Underwash and Full wash"
        )
        cw2.created_at = now - timedelta(hours=1)
        cw2.completed_at = now - timedelta(minutes=20)
        cw2.save()

        cws4 = CarWashService.objects.create(car_wash=cw2, service=service_objs['Full wash'], service_name_snapshot='Full wash', price_charged=Decimal('800.00'))
        WorkerAssignment.objects.create(car_wash_service=cws4, worker=worker_objs['mary'], commission_earned=Decimal('230.00'), rate_applied_snapshot='Default KSh 230.00', is_credited=True)

        cws5 = CarWashService.objects.create(car_wash=cw2, service=service_objs['Underwash'], service_name_snapshot='Underwash', price_charged=Decimal('200.00'))
        WorkerAssignment.objects.create(car_wash_service=cws5, worker=worker_objs['john'], commission_earned=Decimal('50.00'), rate_applied_snapshot='Default KSh 50.00', is_credited=True)

        # Wash 3: Mazda CX-5 (Pending Approval - Logged by Worker Peter on Bay 3)
        cw3 = CarWash.objects.create(
            vehicle=veh_objs["KDE 312M"],
            status=CarWash.Status.PENDING_APPROVAL,
            bay_number=3,
            total_amount=Decimal('500.00'),
            total_commission=Decimal('140.00'),
            net_business_revenue=Decimal('360.00'),
            payment_method=CarWash.PaymentMethod.MPESA,
            payment_reference="PENDING-QW90",
            is_paid=True,
            logged_by=worker_objs['peter'].user,
            notes="Customer paid via cashier M-Pesa till. Awaiting admin signoff."
        )
        cws6 = CarWashService.objects.create(car_wash=cw3, service=service_objs['Full wash'], service_name_snapshot='Full wash', price_charged=Decimal('500.00'))
        WorkerAssignment.objects.create(car_wash_service=cws6, worker=worker_objs['peter'], commission_earned=Decimal('140.00'), rate_applied_snapshot='Default KSh 140.00', is_credited=False)

        # Additional historical washes to build realistic ledger balances
        for i in range(1, 15):
            day_offset = (i % 7) + 1
            h_wash = CarWash.objects.create(
                vehicle=veh_objs["KDC 711T"] if i % 2 == 0 else veh_objs["KDD 405X"],
                status=CarWash.Status.COMPLETED,
                bay_number=(i % 3) + 1,
                total_amount=Decimal('700.00'),
                total_commission=Decimal('200.00'),
                net_business_revenue=Decimal('500.00'),
                payment_method=CarWash.PaymentMethod.MPESA if i % 2 == 0 else CarWash.PaymentMethod.CASH,
                payment_reference=f"TXN-HIST-{i:03d}",
                is_paid=True,
                logged_by=admin_user,
                approved_by=admin_user,
            )
            h_wash.created_at = now - timedelta(days=day_offset, hours=i)
            h_wash.completed_at = h_wash.created_at + timedelta(minutes=45)
            h_wash.save()

            # Assign workers in turn
            target_worker = worker_objs[['john', 'peter', 'james', 'mary'][i % 4]]
            hcws = CarWashService.objects.create(car_wash=h_wash, service=service_objs['Exterior wash'], service_name_snapshot='Exterior wash', price_charged=Decimal('400.00'))
            WorkerAssignment.objects.create(car_wash_service=hcws, worker=target_worker, commission_earned=Decimal('100.00'), rate_applied_snapshot='Historical Shift Rate', is_credited=True)

            hcws2 = CarWashService.objects.create(car_wash=h_wash, service=service_objs['Interior cleaning'], service_name_snapshot='Interior cleaning', price_charged=Decimal('300.00'))
            second_worker = worker_objs[['mary', 'james', 'peter', 'john'][i % 4]]
            WorkerAssignment.objects.create(car_wash_service=hcws2, worker=second_worker, commission_earned=Decimal('100.00'), rate_applied_snapshot='Historical Shift Rate', is_credited=True)

        self.stdout.write(self.style.NOTICE("Creating Worker Payments & Payouts (Shell Carwash Ledger)..."))
        # Partial payout for John (e.g. KSh 500 via M-Pesa)
        WorkerPayment.objects.create(
            worker=worker_objs['john'],
            amount_paid=Decimal('350.00'),
            payment_method=WorkerPayment.PaymentMethod.MPESA,
            transaction_reference="MPESA-B2C-78392",
            notes="Midweek transport allowance advance",
            processed_by=admin_user
        )

        WorkerPayment.objects.create(
            worker=worker_objs['peter'],
            amount_paid=Decimal('400.00'),
            payment_method=WorkerPayment.PaymentMethod.CASH,
            transaction_reference="CASH-REC-109",
            notes="End of week cash payout",
            processed_by=admin_user
        )

        self.stdout.write(self.style.NOTICE("Creating Operating Expenses..."))
        expenses_data = [
            (Expense.Category.WATER, "Clean Water Tanker 10,000 Litres", 3500.00, 2),
            (Expense.Category.CHEMICALS, "Car Wash Foam Shampoo (20L Jerrycan)", 2800.00, 3),
            (Expense.Category.ELECTRICITY, "Kenya Power Token Token Purchase", 2000.00, 5),
            (Expense.Category.EQUIPMENT, "Pressure washer gun nozzle replacement", 1200.00, 6),
        ]
        for cat, title, amt, days_ago in expenses_data:
            Expense.objects.create(
                category=cat,
                title=title,
                amount=Decimal(str(amt)),
                date=(now - timedelta(days=days_ago)).date(),
                notes="Verified store invoice",
                logged_by=admin_user
            )

        self.stdout.write(self.style.SUCCESS("Demo database successfully seeded!"))
        self.stdout.write(self.style.SUCCESS("Admin: admin / admin123"))
        self.stdout.write(self.style.SUCCESS("Workers: john, peter, james, mary / worker123"))

