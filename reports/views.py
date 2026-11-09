import io
import csv
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Sum, Count, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from core.permissions import IsAdminUser
from carwash.models import CarWash, CarWashService, WorkerAssignment, Vehicle
from payments.models import WorkerPayment, Expense, DailyClosing
from accounts.models import WorkerProfile, Attendance
from services.models import Service

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


# ==============================================================================
# DATA AGGREGATION HELPERS
# ==============================================================================

def get_today_payouts_data(target_date=None):
    """
    Computes today's worker earnings, payouts disbursed, and balance needed to be paid.
    Fulfills: "todays payout steve earned this and he need to be paid this much"
    """
    if not target_date:
        target_date = timezone.now().date()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    workers = WorkerProfile.objects.all().select_related('user').order_by('user__first_name', 'user__username')
    worker_rows = []
    
    total_earned_today = Decimal('0.00')
    total_paid_today = Decimal('0.00')
    total_need_to_be_paid = Decimal('0.00')

    for w in workers:
        assignments_today = WorkerAssignment.objects.filter(
            worker=w,
            created_at__date=target_date,
            car_wash_service__car_wash__status=CarWash.Status.COMPLETED
        )
        jobs_count_today = assignments_today.count()
        earned_today = assignments_today.aggregate(s=Sum('commission_earned'))['s'] or Decimal('0.00')

        payouts_today = WorkerPayment.objects.filter(
            worker=w,
            paid_at__date=target_date
        )
        paid_today = payouts_today.aggregate(s=Sum('amount_paid'))['s'] or Decimal('0.00')

        net_earned_today = earned_today - paid_today
        outstanding_balance = Decimal(str(w.outstanding_balance))

        srv_counts = assignments_today.values('car_wash_service__service_name_snapshot').annotate(c=Count('id'))
        srv_summary = ", ".join([f"{sc['car_wash_service__service_name_snapshot']} ({sc['c']})" for sc in srv_counts]) or "No washes today"

        name = w.user.get_full_name() or w.user.username
        phone = w.mpesa_number or w.user.phone_number or '-'

        total_earned_today += earned_today
        total_paid_today += paid_today
        total_need_to_be_paid += outstanding_balance

        worker_rows.append({
            'worker_id': w.id,
            'name': name,
            'username': w.user.username,
            'phone': phone,
            'jobs_count_today': jobs_count_today,
            'earned_today': float(earned_today),
            'paid_today': float(paid_today),
            'net_earned_today': float(net_earned_today),
            'outstanding_balance': float(outstanding_balance),
            'needs_to_be_paid': float(outstanding_balance),
            'services_summary': srv_summary,
            'is_settled': bool(outstanding_balance <= 0)
        })

    return {
        'date': str(target_date),
        'workers': worker_rows,
        'total_earned_today': float(total_earned_today),
        'total_paid_today': float(total_paid_today),
        'total_need_to_be_paid': float(total_need_to_be_paid)
    }


def get_today_revenue_data(target_date=None):
    """
    Computes today's gross revenue, cash/mpesa splits, expenses, and net profit.
    Fulfills: "this is what was made today"
    """
    if not target_date:
        target_date = timezone.now().date()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    washes_today = CarWash.objects.filter(
        created_at__date=target_date,
        status=CarWash.Status.COMPLETED
    ).select_related('vehicle').prefetch_related('services__assignments__worker__user')

    total_cars = washes_today.count()
    total_revenue = washes_today.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')
    cash_revenue = washes_today.aggregate(s=Sum('cash_amount'))['s'] or Decimal('0.00')
    mpesa_revenue = washes_today.aggregate(s=Sum('mpesa_amount'))['s'] or Decimal('0.00')
    total_commissions = washes_today.aggregate(s=Sum('total_commission'))['s'] or Decimal('0.00')

    expenses_today = Expense.objects.filter(date=target_date)
    total_expenses = expenses_today.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    net_profit = total_revenue - total_commissions - total_expenses

    payouts_today = WorkerPayment.objects.filter(paid_at__date=target_date)
    total_payouts = payouts_today.aggregate(s=Sum('amount_paid'))['s'] or Decimal('0.00')

    washes_list = []
    for w in washes_today.order_by('-created_at'):
        srv_names = ", ".join([s.service_name_snapshot for s in w.services.all()])
        worker_set = set()
        for s in w.services.all():
            for a in s.assignments.all():
                worker_set.add(a.worker.user.get_full_name() or a.worker.user.username)
        workers_str = ", ".join(worker_set) or '-'

        washes_list.append({
            'id': w.id,
            'time': w.created_at.strftime('%H:%M'),
            'plate_number': w.vehicle.plate_number,
            'vehicle_type': w.vehicle.get_vehicle_type_display(),
            'customer_name': w.vehicle.customer_name or '-',
            'customer_phone': w.vehicle.customer_phone or '-',
            'bay_number': w.bay_number or 1,
            'services': srv_names,
            'workers': workers_str,
            'total_amount': float(w.total_amount),
            'payment_method': w.get_payment_method_display(),
            'cash_amount': float(w.cash_amount),
            'mpesa_amount': float(w.mpesa_amount),
            'payment_reference': w.payment_reference or '-',
            'commission': float(w.total_commission),
            'net_revenue': float(w.net_business_revenue),
            'is_paid': w.is_paid
        })

    unpaid_qs = washes_today.filter(is_paid=False)
    total_unpaid = unpaid_qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')

    return {
        'date': str(target_date),
        'total_cars': total_cars,
        'total_revenue': float(total_revenue),
        'total_unpaid_revenue': float(total_unpaid),
        'unpaid_count': unpaid_qs.count(),
        'cash_revenue': float(cash_revenue),
        'mpesa_revenue': float(mpesa_revenue),
        'total_commissions': float(total_commissions),
        'total_expenses': float(total_expenses),
        'total_payouts': float(total_payouts),
        'net_profit': float(net_profit),
        'washes': washes_list
    }


def get_shift_closing_data(target_date=None):
    """
    Computes physical cash drawer balancing and shift status.
    Fulfills: "and the closing shift was this in shell carwash"
    """
    if not target_date:
        target_date = timezone.now().date()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    closing_obj = DailyClosing.objects.filter(date=target_date).first()

    if closing_obj:
        return {
            'date': str(target_date),
            'is_closed': True,
            'closed_by': closing_obj.closed_by.get_full_name() or closing_obj.closed_by.username,
            'closed_at': closing_obj.closed_at.strftime('%Y-%m-%d %H:%M:%S'),
            'total_cars_washed': closing_obj.total_cars_washed,
            'total_revenue': float(closing_obj.total_revenue),
            'total_cash_revenue': float(closing_obj.total_cash_revenue),
            'total_mpesa_revenue': float(closing_obj.total_mpesa_revenue),
            'total_commissions': float(closing_obj.total_commissions),
            'total_payouts': float(closing_obj.total_payouts),
            'total_expenses': float(closing_obj.total_expenses),
            'expected_cash_in_drawer': float(closing_obj.expected_cash_in_drawer),
            'actual_cash_counted': float(closing_obj.actual_cash_counted),
            'cash_variance': float(closing_obj.cash_variance),
            'notes': closing_obj.notes or 'Audit verified',
            'status': 'BALANCED' if closing_obj.cash_variance == 0 else ('OVERAGE' if closing_obj.cash_variance > 0 else 'SHORTAGE')
        }

    rev_data = get_today_revenue_data(target_date)
    payouts_qs = WorkerPayment.objects.filter(paid_at__date=target_date)
    cash_payouts = payouts_qs.filter(payment_method=WorkerPayment.PaymentMethod.CASH).aggregate(s=Sum('amount_paid'))['s'] or Decimal('0.00')
    expenses_qs = Expense.objects.filter(date=target_date)
    cash_expenses = expenses_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    expected_cash = Decimal(str(rev_data['cash_revenue'])) - cash_payouts - cash_expenses

    return {
        'date': str(target_date),
        'is_closed': False,
        'closed_by': 'Pending Shift Manager',
        'closed_at': 'Shift In Progress (Live Preview)',
        'total_cars_washed': rev_data['total_cars'],
        'total_revenue': rev_data['total_revenue'],
        'total_cash_revenue': rev_data['cash_revenue'],
        'total_mpesa_revenue': rev_data['mpesa_revenue'],
        'total_commissions': rev_data['total_commissions'],
        'total_payouts': float(payouts_qs.aggregate(s=Sum('amount_paid'))['s'] or 0),
        'total_expenses': rev_data['total_expenses'],
        'expected_cash_in_drawer': float(expected_cash),
        'actual_cash_counted': float(expected_cash),
        'cash_variance': 0.0,
        'notes': 'Live shift estimates pending final drawer count and audit',
        'status': 'ESTIMATED / OPEN'
    }


# ==============================================================================
# JSON API ENDPOINTS
# ==============================================================================

class BusinessSummaryReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filter_type = request.query_params.get('filter', 'today')
        now = timezone.now()
        today = now.date()

        if filter_type == 'yesterday':
            start_date = today - timedelta(days=1)
            end_date = start_date
        elif filter_type == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif filter_type == 'month':
            start_date = today.replace(day=1)
            end_date = today
        elif filter_type == 'custom':
            df = request.query_params.get('date_from')
            dt = request.query_params.get('date_to')
            start_date = datetime.strptime(df, '%Y-%m-%d').date() if df else today
            end_date = datetime.strptime(dt, '%Y-%m-%d').date() if dt else today
        else:
            start_date = today
            end_date = today

        washes_qs = CarWash.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status=CarWash.Status.COMPLETED
        )

        total_cars = washes_qs.count()
        total_revenue = washes_qs.aggregate(r=Sum('total_amount'))['r'] or Decimal('0.00')
        total_commissions = washes_qs.aggregate(c=Sum('total_commission'))['c'] or Decimal('0.00')
        profit_before_expenses = total_revenue - total_commissions

        expenses_qs = Expense.objects.filter(date__gte=start_date, date__lte=end_date)
        total_expenses = expenses_qs.aggregate(e=Sum('amount'))['e'] or Decimal('0.00')
        net_profit = profit_before_expenses - total_expenses

        total_cash_revenue = washes_qs.aggregate(s=Sum('cash_amount'))['s'] or Decimal('0.00')
        total_mpesa_revenue = washes_qs.aggregate(s=Sum('mpesa_amount'))['s'] or Decimal('0.00')

        workers = WorkerProfile.objects.filter(is_active=True)
        total_outstanding_balance = sum([w.outstanding_balance for w in workers])

        # Pending collection (Unpaid washes awaiting customer pickup)
        unpaid_qs = CarWash.objects.filter(is_paid=False).exclude(status=CarWash.Status.CANCELLED)
        unpaid_washes_count = unpaid_qs.count()
        unpaid_amount_total = unpaid_qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')

        services_breakdown = list(CarWashService.objects.filter(
            car_wash__in=washes_qs
        ).values('service_name_snapshot').annotate(
            count=Count('id'),
            revenue=Sum('price_charged')
        ).order_by('-count'))

        most_popular_service = services_breakdown[0] if services_breakdown else None

        workers_agg = list(WorkerAssignment.objects.filter(
            car_wash_service__car_wash__in=washes_qs
        ).values(
            'worker__id',
            'worker__user__first_name',
            'worker__user__last_name',
            'worker__user__username'
        ).annotate(
            jobs_count=Count('id'),
            total_commissions=Sum('commission_earned')
        ).order_by('-jobs_count'))

        top_worker = None
        if workers_agg:
            tw = workers_agg[0]
            w_name = f"{tw['worker__user__first_name']} {tw['worker__user__last_name']}".strip() or tw['worker__user__username']
            top_worker = {
                'worker_id': tw['worker__id'],
                'name': w_name,
                'jobs_count': tw['jobs_count'],
                'total_commissions': float(tw['total_commissions'] or 0)
            }

        trend_days = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_washes = CarWash.objects.filter(created_at__date=day, status=CarWash.Status.COMPLETED)
            rev = day_washes.aggregate(r=Sum('total_amount'))['r'] or Decimal('0.00')
            comm = day_washes.aggregate(c=Sum('total_commission'))['c'] or Decimal('0.00')
            trend_days.append({
                'date': day.strftime('%a %d'),
                'revenue': float(rev),
                'commissions': float(comm),
                'profit': float(rev - comm),
                'cars': day_washes.count()
            })

        return Response({
            'filter_type': filter_type,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'total_cars': total_cars,
            'total_revenue': float(total_revenue),
            'total_cash_revenue': float(total_cash_revenue),
            'total_mpesa_revenue': float(total_mpesa_revenue),
            'total_commissions': float(total_commissions),
            'profit_before_expenses': float(profit_before_expenses),
            'total_expenses': float(total_expenses),
            'net_profit': float(net_profit),
            'total_outstanding_balance': float(total_outstanding_balance),
            'unpaid_washes_count': unpaid_washes_count,
            'unpaid_amount_total': float(unpaid_amount_total),
            'total_workers': workers.count(),
            'most_popular_service': most_popular_service,
            'top_worker': top_worker,
            'services_breakdown': services_breakdown,
            'workers_breakdown': workers_agg,
            'daily_trend': trend_days
        })


class TodayPayoutsReportView(APIView):
    """
    API endpoint returning today's worker earnings & payouts to be paid.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_today_payouts_data(date_str)
        return Response(data)


class TodayRevenueReportView(APIView):
    """
    API endpoint returning today's revenue and completed washes.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_today_revenue_data(date_str)
        return Response(data)


class ShiftClosingReportView(APIView):
    """
    API endpoint returning closing shift details & drawer reconciliation.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_shift_closing_data(date_str)
        return Response(data)


# ==============================================================================
# EXCEL EXPORTS (.XLSX)
# ==============================================================================

class ExportTodayPayoutsExcelView(APIView):
    """
    Excel export for Today's Worker Earnings & Payouts Sheet:
    Steve earned X today, was paid Y today, needs to be paid Z.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_today_payouts_data(date_str)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Today Worker Payouts"

        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=16, bold=True, color="1E3A8A")
        sub_font = Font(name="Calibri", size=10, italic=True, color="64748B")
        total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        total_font = Font(name="Calibri", size=11, bold=True, color="0F172A")

        ws["A1"] = "SHELL CAR WASH - DAILY WORKER EARNINGS & PAYOUT SHEET"
        ws["A1"].font = title_font
        ws["A2"] = f"Shift Date: {data['date']} | Generated On: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        ws["A2"].font = sub_font

        headers = [
            "#", "Staff Name", "Phone / M-Pesa", "Jobs Done Today",
            "Earned Today (KSh)", "Paid Today (KSh)", "Net Earned Today (KSh)",
            "Total Needs To Be Paid (KSh)", "Status", "Services Performed Today", "Worker Signature / M-Pesa Ref"
        ]

        ws.append([]) # Row 3 blank
        ws.append(headers) # Row 4
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=4, column=c)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center" if c in [1, 4, 9] else "left")

        for idx, w in enumerate(data['workers'], start=1):
            status_text = "Fully Settled" if w['outstanding_balance'] <= 0 else f"Owed KSh {w['outstanding_balance']:,.2f}"
            ws.append([
                idx,
                w['name'],
                w['phone'],
                w['jobs_count_today'],
                w['earned_today'],
                w['paid_today'],
                w['net_earned_today'],
                w['needs_to_be_paid'],
                status_text,
                w['services_summary'],
                "" # Signature blank
            ])

        last_row = len(data['workers']) + 4
        # Total Summary Row
        summary_row = [
            "TOTALS", "", "",
            sum(w['jobs_count_today'] for w in data['workers']),
            data['total_earned_today'],
            data['total_paid_today'],
            data['total_earned_today'] - data['total_paid_today'],
            data['total_need_to_be_paid'],
            "", "", ""
        ]
        ws.append(summary_row)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=last_row + 1, column=c)
            cell.fill = total_fill
            cell.font = total_font

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="shell_carwash_today_payouts_{data["date"]}.xlsx"'
        return response


class ExportTodayRevenueExcelView(APIView):
    """
    Excel export for Today's Revenue and Completed Washes:
    "this is what was made today"
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_today_revenue_data(date_str)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Today Revenue & Washes"

        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=15, bold=True, color="1E3A8A")

        ws["A1"] = f"SHELL CAR WASH - DAILY REVENUE & PERFORMANCE REPORT ({data['date']})"
        ws["A1"].font = title_font
        ws["A2"] = f"Generated On: {timezone.now().strftime('%Y-%m-%d %H:%M')} | Nairobi, KE"

        # Summary KPIs block
        ws["A4"] = "Total Completed Washes"
        ws["B4"] = data['total_cars']
        ws["A5"] = "Total Gross Revenue (KSh)"
        ws["B5"] = data['total_revenue']
        ws["A6"] = "Cash Revenue Collected (KSh)"
        ws["B6"] = data['cash_revenue']
        ws["A7"] = "M-Pesa Revenue Collected (KSh)"
        ws["B7"] = data['mpesa_revenue']
        ws["A8"] = "Worker Commissions Credited (KSh)"
        ws["B8"] = data['total_commissions']
        ws["A9"] = "Operating Expenses (KSh)"
        ws["B9"] = data['total_expenses']
        ws["A10"] = "Net Operating Profit (KSh)"
        ws["B10"] = data['net_profit']

        for r in range(4, 11):
            ws.cell(row=r, column=1).font = Font(bold=True)

        # Washes table
        ws.cell(row=12, column=1, value="DETAILED WASHES CONDUCTED TODAY").font = Font(bold=True, size=12, color="1E3A8A")
        headers = [
            "Wash ID", "Time", "Plate Number", "Vehicle Type", "Customer Name", "Customer Phone",
            "Bay #", "Services Performed", "Workers Assigned", "Total Bill (KSh)", "Payment Method",
            "Cash (KSh)", "M-Pesa (KSh)", "Payment Reference", "Commission (KSh)", "Net Profit (KSh)"
        ]
        ws.append([]) # 13
        ws.append(headers) # 14
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=14, column=c)
            cell.fill = header_fill
            cell.font = header_font

        for w in data['washes']:
            ws.append([
                w['id'],
                w['time'],
                w['plate_number'],
                w['vehicle_type'],
                w['customer_name'],
                w['customer_phone'],
                w['bay_number'],
                w['services'],
                w['workers'],
                w['total_amount'],
                w['payment_method'],
                w['cash_amount'],
                w['mpesa_amount'],
                w['payment_reference'],
                w['commission'],
                w['net_revenue']
            ])

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="shell_carwash_today_revenue_{data["date"]}.xlsx"'
        return response


class ExportShiftClosingExcelView(APIView):
    """
    Excel export for the Closing Shift register and cash drawer balancing.
    "the closing shift was this in shell carwash"
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_shift_closing_data(date_str)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Shift Closing Register"

        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=16, bold=True, color="1E3A8A")

        ws["A1"] = "SHELL CAR WASH - DAILY SHIFT CLOSING & REGISTER RECONCILIATION"
        ws["A1"].font = title_font
        ws["A2"] = f"Shift Date: {data['date']} | Status: {data['status']} | Closed By: {data['closed_by']}"

        rows = [
            ["Shift Audit Metric", "Amount (KSh / Count)"],
            ["Total Cars Washed in Shift", data['total_cars_washed']],
            ["Total Gross Shift Revenue", data['total_revenue']],
            ["Cash Revenue Collected (+)", data['total_cash_revenue']],
            ["M-Pesa Revenue Collected", data['total_mpesa_revenue']],
            ["Worker Commission Obligations", data['total_commissions']],
            ["Worker Cash Payouts Disbursed (-)", data['total_payouts']],
            ["Operating Expenses Paid From Drawer (-)", data['total_expenses']],
            ["Expected Physical Cash in Drawer (=)", data['expected_cash_in_drawer']],
            ["Actual Physical Cash Counted in Drawer", data['actual_cash_counted']],
            ["Cash Drawer Discrepancy / Variance", data['cash_variance']],
            ["Shift Reconciliation Status", data['status']],
            ["Shift Closing Notes & Handover", data['notes']]
        ]

        ws.append([]) # Row 3
        for r_idx, row in enumerate(rows, start=4):
            for c_idx, val in enumerate(row, start=1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                if r_idx == 4:
                    cell.fill = header_fill
                    cell.font = header_font
                elif r_idx in [12, 13]:
                    cell.font = Font(bold=True)

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="shell_carwash_shift_closing_{data["date"]}.xlsx"'
        return response


# ==============================================================================
# PDF EXPORTS (.PDF)
# ==============================================================================

class ExportTodayPayoutsPDFView(APIView):
    """
    Print-ready PDF statement for Today's Worker Earnings & Payouts.
    Fulfills: "todays payout steve earned this and he need to be paid this much"
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_today_payouts_data(date_str)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1E3A8A'),
            spaceAfter=4
        )
        sub_style = ParagraphStyle(
            'DocSub',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#475569'),
            spaceAfter=12
        )
        section_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=11,
            textColor=colors.HexColor('#0F172A'),
            spaceBefore=10,
            spaceAfter=6
        )

        elements.append(Paragraph("SHELL CAR WASH - DAILY WORKER EARNINGS & PAYOUT SHEET", title_style))
        elements.append(Paragraph(
            f"Shift Date: <b>{data['date']}</b> | Generated: {timezone.now().strftime('%d %B %Y, %I:%M %p')} | Shell Service Station",
            sub_style
        ))

        # Overall Day Totals Table
        totals_data = [
            ["Metric", "Total Amount (KSh)"],
            ["Total Worker Commissions Earned Today", f"KSh {data['total_earned_today']:,.2f}"],
            ["Total Worker Payouts Disbursed Today", f"KSh {data['total_paid_today']:,.2f}"],
            ["Total Balance Needed To Be Paid Out", f"KSh {data['total_need_to_be_paid']:,.2f}"]
        ]
        t_totals = Table(totals_data, colWidths=[340, 210])
        t_totals.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#DC2626')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        elements.append(t_totals)

        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Individual Worker Earnings & Cashout Ledger", section_style))

        # Workers Table
        headers = ["Staff Name", "Phone / M-Pesa", "Cars", "Earned Today", "Paid Today", "Needs To Be Paid", "Signature / Ref"]
        table_rows = [headers]

        for w in data['workers']:
            table_rows.append([
                w['name'],
                w['phone'],
                str(w['jobs_count_today']),
                f"KSh {w['earned_today']:,.0f}",
                f"KSh {w['paid_today']:,.0f}",
                f"KSh {w['needs_to_be_paid']:,.0f}",
                ""
            ])

        t_workers = Table(table_rows, colWidths=[115, 95, 35, 75, 70, 85, 75])
        t_workers.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('ALIGN', (2, 0), (5, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('TEXTCOLOR', (5, 1), (5, -1), colors.HexColor('#B91C1C')),
            ('FONTNAME', (5, 1), (5, -1), 'Helvetica-Bold'),
        ]))
        elements.append(t_workers)

        elements.append(Spacer(1, 20))
        # Manager Sign-off Block
        sign_data = [
            ["Prepared By (Cashier): ____________________", "Approved By (Manager): ____________________"],
            ["Date & Timestamp: ________________________", "Disbursed Via: [ ] Cash  [ ] M-Pesa Bulk"]
        ]
        t_sign = Table(sign_data, colWidths=[275, 275])
        t_sign.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#475569')),
        ]))
        elements.append(t_sign)

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="shell_carwash_today_payouts_{data["date"]}.pdf"'
        return response


class ExportShiftClosingPDFView(APIView):
    """
    Official PDF Shift Closing Statement and Cash Drawer Reconciliation Voucher.
    Fulfills: "and the closing shift was this in shell carwash"
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_shift_closing_data(date_str)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#1E3A8A'), spaceAfter=4
        )
        sub_style = ParagraphStyle(
            'DocSub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), spaceAfter=14
        )
        section_style = ParagraphStyle(
            'SectionTitle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#0F172A'), spaceBefore=8, spaceAfter=4
        )

        elements.append(Paragraph("SHELL CAR WASH - SHIFT CLOSING & REGISTER RECONCILIATION", title_style))
        elements.append(Paragraph(
            f"Shift Date: <b>{data['date']}</b> | Closed By: <b>{data['closed_by']}</b> | Status: <b>{data['status']}</b>",
            sub_style
        ))

        # Shift Volume & Revenue Table
        elements.append(Paragraph("1. Shift Volume & Revenue Collection", section_style))
        vol_data = [
            ["Revenue Metric", "Amount (KSh / Count)"],
            ["Total Completed Vehicles Washed", f"{data['total_cars_washed']} vehicles"],
            ["Total Gross Shift Revenue", f"KSh {data['total_revenue']:,.2f}"],
            ["Cash Revenue Collected", f"KSh {data['total_cash_revenue']:,.2f}"],
            ["M-Pesa Revenue Collected", f"KSh {data['total_mpesa_revenue']:,.2f}"],
            ["Worker Commission Obligations", f"KSh {data['total_commissions']:,.2f}"]
        ]
        t_vol = Table(vol_data, colWidths=[330, 210])
        t_vol.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
        ]))
        elements.append(t_vol)

        elements.append(Spacer(1, 10))
        # Cash Drawer Reconciliation Table
        elements.append(Paragraph("2. Physical Cash Drawer Balancing & Audit", section_style))
        var_color = colors.HexColor('#15803D') if data['cash_variance'] == 0 else colors.HexColor('#DC2626')
        reconcile_data = [
            ["Cash Drawer Reconciliation Step", "Amount (KSh)"],
            ["(+) Cash Revenue Collected from Customers", f"KSh {data['total_cash_revenue']:,.2f}"],
            ["(-) Cash Worker Payouts Disbursed During Shift", f"- KSh {data['total_payouts']:,.2f}"],
            ["(-) Operating Expenses Paid from Drawer", f"- KSh {data['total_expenses']:,.2f}"],
            ["(=) Expected Cash in Physical Drawer", f"KSh {data['expected_cash_in_drawer']:,.2f}"],
            ["Physical Cash Counted in Drawer", f"KSh {data['actual_cash_counted']:,.2f}"],
            ["Cash Variance (Discrepancy)", f"KSh {data['cash_variance']:,.2f} ({data['status']})"]
        ]
        t_rec = Table(reconcile_data, colWidths=[330, 210])
        t_rec.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#0F172A')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('FONTNAME', (0, 4), (-1, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (1, -1), (1, -1), var_color),
        ]))
        elements.append(t_rec)

        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"<b>Audit & Handover Notes:</b> {data['notes']}", sub_style))

        elements.append(Spacer(1, 15))
        # Handover Signatures
        sign_data = [
            ["Cashier Handover Signature:", "Manager Acceptance Signature:"],
            ["Name: _______________________________", "Name: _______________________________"],
            ["Signature: __________________________", "Signature: __________________________"],
            ["Date: _______________________________", "Date: _______________________________"]
        ]
        t_sign = Table(sign_data, colWidths=[270, 270])
        t_sign.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_sign)

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="shell_carwash_shift_closing_{data["date"]}.pdf"'
        return response


class ExportTodayRevenuePDFView(APIView):
    """
    Print-ready PDF report for Today's Revenue and Vehicle Washes.
    Fulfills: "this is what was made today"
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date')
        data = get_today_revenue_data(date_str)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#1E3A8A'), spaceAfter=4
        )
        sub_style = ParagraphStyle(
            'DocSub', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), spaceAfter=12
        )
        section_style = ParagraphStyle(
            'SectionTitle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#0F172A'), spaceBefore=8, spaceAfter=4
        )

        elements.append(Paragraph(f"SHELL CAR WASH - DAILY REVENUE & OPERATIONS REPORT", title_style))
        elements.append(Paragraph(f"Date: <b>{data['date']}</b> | Generated: {timezone.now().strftime('%d %B %Y, %I:%M %p')}", sub_style))

        kpi_data = [
            ["Financial KPI", "Amount"],
            ["Total Vehicles Washed Today", f"{data['total_cars']} cars"],
            ["Total Gross Revenue Made Today", f"KSh {data['total_revenue']:,.2f}"],
            ["Cash Revenue Collected", f"KSh {data['cash_revenue']:,.2f}"],
            ["M-Pesa Revenue Collected", f"KSh {data['mpesa_revenue']:,.2f}"],
            ["Worker Commissions Credited Today", f"KSh {data['total_commissions']:,.2f}"],
            ["Operating Expenses Incurred Today", f"KSh {data['total_expenses']:,.2f}"],
            ["Net Profit Kept Today", f"KSh {data['net_profit']:,.2f}"]
        ]
        t_kpi = Table(kpi_data, colWidths=[330, 220])
        t_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#15803D')),
        ]))
        elements.append(t_kpi)

        elements.append(Spacer(1, 10))
        elements.append(Paragraph("Vehicles Washed Today", section_style))

        headers = ["Time", "Plate", "Type", "Services", "Workers", "Bill (KSh)", "Pay Method"]
        rows = [headers]
        for w in data['washes'][:30]: # First 30
            rows.append([
                w['time'],
                w['plate_number'],
                w['vehicle_type'][:10],
                w['services'][:25],
                w['workers'][:20],
                f"KSh {w['total_amount']:,.0f}",
                w['payment_method']
            ])

        t_washes = Table(rows, colWidths=[40, 65, 60, 150, 100, 65, 70])
        t_washes.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ]))
        elements.append(t_washes)

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="shell_carwash_today_revenue_{data["date"]}.pdf"'
        return response


# ==============================================================================
# MASTER COMPREHENSIVE EXCEL WORKBOOK (ALL 11 SHEETS)
# ==============================================================================

class ExportExcelReportView(APIView):
    """
    Master 11-Sheet Excel Workbook covering everything in the system.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        today = now.date()
        wb = openpyxl.Workbook()

        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=15, bold=True, color="1E3A8A")
        sub_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        # -------------------------------------------------------------
        # Sheet 1: Executive KPI Summary
        # -------------------------------------------------------------
        ws_summary = wb.active
        ws_summary.title = "Executive Summary"

        ws_summary["A1"] = "SHELL CAR WASH - MASTER EXECUTIVE PERFORMANCE REPORT"
        ws_summary["A1"].font = title_font
        ws_summary["A2"] = f"Generated On: {now.strftime('%Y-%m-%d %H:%M')} | Nairobi, KE"

        washes = CarWash.objects.filter(status=CarWash.Status.COMPLETED)
        total_rev = washes.aggregate(s=Sum('total_amount'))['s'] or 0
        total_cash = washes.aggregate(s=Sum('cash_amount'))['s'] or 0
        total_mpesa = washes.aggregate(s=Sum('mpesa_amount'))['s'] or 0
        total_comm = washes.aggregate(s=Sum('total_commission'))['s'] or 0
        total_exp = Expense.objects.aggregate(s=Sum('amount'))['s'] or 0

        summary_data = [
            ["Business Metric", "Value (KSh / Count)"],
            ["Total Completed Car Washes (All-time)", washes.count()],
            ["Total Gross Revenue Collected", total_rev],
            ["Total Cash Collected", total_cash],
            ["Total M-Pesa Collected", total_mpesa],
            ["Total Worker Commissions Credited", total_comm],
            ["Gross Profit (Rev - Comm)", total_rev - total_comm],
            ["Total Operating Expenses", total_exp],
            ["Net Business Operating Profit", total_rev - total_comm - total_exp],
            ["Active Bay Workers", WorkerProfile.objects.filter(is_active=True).count()]
        ]

        for r_idx, row in enumerate(summary_data, start=4):
            for c_idx, val in enumerate(row, start=1):
                cell = ws_summary.cell(row=r_idx, column=c_idx, value=val)
                if r_idx == 4:
                    cell.fill = header_fill
                    cell.font = header_font
                elif r_idx % 2 == 1:
                    cell.fill = sub_fill

        # -------------------------------------------------------------
        # Sheet 2: Today's Worker Earnings & Payouts (Steve earned X...)
        # -------------------------------------------------------------
        ws_today_payouts = wb.create_sheet(title="Today Worker Payouts")
        payouts_data = get_today_payouts_data(today)
        tp_headers = [
            "#", "Staff Name", "Phone / M-Pesa", "Jobs Done Today",
            "Earned Today (KSh)", "Paid Today (KSh)", "Net Earned Today (KSh)",
            "Total Needs To Be Paid (KSh)", "Status", "Services Summary"
        ]
        ws_today_payouts.append(tp_headers)
        for c in range(1, len(tp_headers) + 1):
            ws_today_payouts.cell(row=1, column=c).fill = header_fill
            ws_today_payouts.cell(row=1, column=c).font = header_font

        for idx, w in enumerate(payouts_data['workers'], start=1):
            ws_today_payouts.append([
                idx, w['name'], w['phone'], w['jobs_count_today'],
                w['earned_today'], w['paid_today'], w['net_earned_today'],
                w['needs_to_be_paid'], "Settled" if w['outstanding_balance'] <= 0 else "Pending",
                w['services_summary']
            ])

        # -------------------------------------------------------------
        # Sheet 3: Today's Revenue & Completed Washes
        # -------------------------------------------------------------
        ws_today_rev = wb.create_sheet(title="Today Revenue & Washes")
        today_rev_data = get_today_revenue_data(today)
        tr_headers = [
            "Wash ID", "Time", "Plate Number", "Type", "Customer", "Phone",
            "Bay", "Services", "Workers", "Total (KSh)", "Payment Method",
            "Cash (KSh)", "M-Pesa (KSh)", "Commission (KSh)", "Net Profit (KSh)"
        ]
        ws_today_rev.append(tr_headers)
        for c in range(1, len(tr_headers) + 1):
            ws_today_rev.cell(row=1, column=c).fill = header_fill
            ws_today_rev.cell(row=1, column=c).font = header_font

        for w in today_rev_data['washes']:
            ws_today_rev.append([
                w['id'], w['time'], w['plate_number'], w['vehicle_type'],
                w['customer_name'], w['customer_phone'], w['bay_number'],
                w['services'], w['workers'], w['total_amount'], w['payment_method'],
                w['cash_amount'], w['mpesa_amount'], w['commission'], w['net_revenue']
            ])

        # -------------------------------------------------------------
        # Sheet 4: Shift Closings History
        # -------------------------------------------------------------
        ws_closings = wb.create_sheet(title="Shift Closings")
        sc_headers = [
            "Date", "Closed By", "Cars Washed", "Gross Revenue (KSh)", "Cash Rev (KSh)",
            "M-Pesa Rev (KSh)", "Commissions (KSh)", "Payouts (KSh)", "Expenses (KSh)",
            "Expected Cash (KSh)", "Actual Cash (KSh)", "Variance (KSh)", "Audit Notes"
        ]
        ws_closings.append(sc_headers)
        for c in range(1, len(sc_headers) + 1):
            ws_closings.cell(row=1, column=c).fill = header_fill
            ws_closings.cell(row=1, column=c).font = header_font

        for cl in DailyClosing.objects.all().select_related('closed_by').order_by('-date'):
            ws_closings.append([
                str(cl.date), cl.closed_by.get_full_name() or cl.closed_by.username,
                cl.total_cars_washed, float(cl.total_revenue), float(cl.total_cash_revenue),
                float(cl.total_mpesa_revenue), float(cl.total_commissions), float(cl.total_payouts),
                float(cl.total_expenses), float(cl.expected_cash_in_drawer),
                float(cl.actual_cash_counted), float(cl.cash_variance), cl.notes or '-'
            ])

        # -------------------------------------------------------------
        # Sheet 5: All Car Washes (Full Historical Ledger)
        # -------------------------------------------------------------
        ws_washes = wb.create_sheet(title="All Car Washes")
        wash_headers = [
            "ID", "Date & Time", "Plate Number", "Vehicle Type", "Customer Name", "Customer Phone",
            "Bay #", "Services Performed", "Workers Assigned", "Total Bill (KSh)", "Payment Method",
            "Cash (KSh)", "M-Pesa (KSh)", "M-Pesa Reference", "Commission (KSh)", "Net Profit (KSh)", "Status"
        ]
        ws_washes.append(wash_headers)
        for c in range(1, len(wash_headers) + 1):
            ws_washes.cell(row=1, column=c).fill = header_fill
            ws_washes.cell(row=1, column=c).font = header_font

        for w in CarWash.objects.all().select_related('vehicle').prefetch_related('services__assignments__worker__user').order_by('-created_at')[:1000]:
            srv_names = ", ".join([s.service_name_snapshot for s in w.services.all()])
            worker_set = set()
            for s in w.services.all():
                for a in s.assignments.all():
                    worker_set.add(a.worker.user.get_full_name() or a.worker.user.username)
            workers_str = ", ".join(worker_set)

            ws_washes.append([
                w.id, w.created_at.strftime('%Y-%m-%d %H:%M'), w.vehicle.plate_number,
                w.vehicle.get_vehicle_type_display(), w.vehicle.customer_name or '-',
                w.vehicle.customer_phone or '-', w.bay_number or 1, srv_names, workers_str,
                float(w.total_amount), w.get_payment_method_display(), float(w.cash_amount),
                float(w.mpesa_amount), w.payment_reference or '-', float(w.total_commission),
                float(w.net_business_revenue), w.get_status_display()
            ])

        # -------------------------------------------------------------
        # Sheet 6: Worker Performance & Balances (Lifetime)
        # -------------------------------------------------------------
        ws_workers = wb.create_sheet(title="Workers Lifetime")
        worker_headers = [
            "Worker ID", "Staff Name", "Phone / M-Pesa", "Jobs / Cars Done",
            "Total Commissions Earned (KSh)", "Total Paid Out (KSh)", "Outstanding Balance (KSh)",
            "Services Breakdown Summary"
        ]
        ws_workers.append(worker_headers)
        for c in range(1, len(worker_headers) + 1):
            ws_workers.cell(row=1, column=c).fill = header_fill
            ws_workers.cell(row=1, column=c).font = header_font

        for wp in WorkerProfile.objects.all().select_related('user'):
            assignments = WorkerAssignment.objects.filter(worker=wp, car_wash_service__car_wash__status=CarWash.Status.COMPLETED)
            jobs_count = assignments.count()
            srv_counts = assignments.values('car_wash_service__service_name_snapshot').annotate(c=Count('id')).order_by('-c')
            srv_str = "; ".join([f"{sc['car_wash_service__service_name_snapshot']} ({sc['c']})" for sc in srv_counts]) or "None"

            ws_workers.append([
                wp.id, wp.user.get_full_name() or wp.user.username,
                wp.mpesa_number or wp.user.phone_number or '', jobs_count,
                float(wp.total_earned), float(wp.total_paid), float(wp.outstanding_balance), srv_str
            ])

        # -------------------------------------------------------------
        # Sheet 7: Worker Payouts History (Disbursements)
        # -------------------------------------------------------------
        ws_payouts_hist = wb.create_sheet(title="Payouts Disbursements")
        ph_headers = ["Payout ID", "Date & Time", "Worker Name", "Amount (KSh)", "Method", "Reference", "Processed By", "Notes"]
        ws_payouts_hist.append(ph_headers)
        for c in range(1, len(ph_headers) + 1):
            ws_payouts_hist.cell(row=1, column=c).fill = header_fill
            ws_payouts_hist.cell(row=1, column=c).font = header_font

        for p in WorkerPayment.objects.all().select_related('worker__user', 'processed_by').order_by('-paid_at'):
            ws_payouts_hist.append([
                p.id, p.paid_at.strftime('%Y-%m-%d %H:%M'),
                p.worker.user.get_full_name() or p.worker.user.username,
                float(p.amount_paid), p.get_payment_method_display(),
                p.transaction_reference or '-', p.processed_by.username, p.notes or '-'
            ])

        # -------------------------------------------------------------
        # Sheet 8: Services Catalog & Margins
        # -------------------------------------------------------------
        ws_srv = wb.create_sheet(title="Services Catalog")
        srv_headers = ["Service Name", "Total Washes Done", "Total Revenue Collected (KSh)", "Average Ticket (KSh)", "Commissions Distributed (KSh)"]
        ws_srv.append(srv_headers)
        for c in range(1, len(srv_headers) + 1):
            ws_srv.cell(row=1, column=c).fill = header_fill
            ws_srv.cell(row=1, column=c).font = header_font

        for s in Service.objects.all():
            cws_qs = CarWashService.objects.filter(service=s, car_wash__status=CarWash.Status.COMPLETED)
            cnt = cws_qs.count()
            rev = cws_qs.aggregate(s=Sum('price_charged'))['s'] or Decimal('0.00')
            avg_p = (rev / cnt) if cnt > 0 else Decimal('0.00')
            comm_dist = WorkerAssignment.objects.filter(car_wash_service__service=s, is_credited=True).aggregate(s=Sum('commission_earned'))['s'] or Decimal('0.00')

            ws_srv.append([s.name, cnt, float(rev), float(avg_p), float(comm_dist)])

        # -------------------------------------------------------------
        # Sheet 9: Operating Expenses
        # -------------------------------------------------------------
        ws_exp = wb.create_sheet(title="Operating Expenses")
        exp_headers = ["ID", "Date", "Category", "Expense Title", "Amount (KSh)", "Logged By", "Notes"]
        ws_exp.append(exp_headers)
        for c in range(1, len(exp_headers) + 1):
            ws_exp.cell(row=1, column=c).fill = header_fill
            ws_exp.cell(row=1, column=c).font = header_font

        for e in Expense.objects.all().select_related('logged_by').order_by('-date'):
            ws_exp.append([
                e.id, e.date.strftime('%Y-%m-%d'), e.get_category_display(),
                e.title, float(e.amount), e.logged_by.get_full_name() or e.logged_by.username, e.notes or '-'
            ])

        # -------------------------------------------------------------
        # Sheet 10: Bay Attendance History
        # -------------------------------------------------------------
        ws_att = wb.create_sheet(title="Bay Attendance")
        att_headers = ["Date", "Worker Name", "Status", "Clock In", "Clock Out", "Marked By", "Notes"]
        ws_att.append(att_headers)
        for c in range(1, len(att_headers) + 1):
            ws_att.cell(row=1, column=c).fill = header_fill
            ws_att.cell(row=1, column=c).font = header_font

        for a in Attendance.objects.all().select_related('worker__user', 'marked_by').order_by('-date'):
            ws_att.append([
                str(a.date), a.worker.user.get_full_name() or a.worker.user.username,
                a.get_status_display(), str(a.clock_in or '-'), str(a.clock_out or '-'),
                a.marked_by.username, a.notes or '-'
            ])

        # -------------------------------------------------------------
        # Sheet 11: Customers & Vehicles
        # -------------------------------------------------------------
        ws_veh = wb.create_sheet(title="Customer Vehicles")
        veh_headers = ["Plate Number", "Type", "Make & Model", "Customer Name", "Customer Phone", "Registered Date"]
        ws_veh.append(veh_headers)
        for c in range(1, len(veh_headers) + 1):
            ws_veh.cell(row=1, column=c).fill = header_fill
            ws_veh.cell(row=1, column=c).font = header_font

        for v in Vehicle.objects.all().order_by('-created_at'):
            ws_veh.append([
                v.plate_number, v.get_vehicle_type_display(), v.make_model or '-',
                v.customer_name or '-', v.customer_phone or '-', v.created_at.strftime('%Y-%m-%d')
            ])

        # Auto-adjust column widths across all sheets
        for ws in wb.worksheets:
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="shell_carwash_master_audit_{now.strftime("%Y%m%d_%H%M")}.xlsx"'
        return response


class ExportPDFReportView(APIView):
    """
    Executive PDF Business Statement.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E3A8A'), spaceAfter=6
        )
        subtitle_style = ParagraphStyle(
            'DocSub', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#4B5563'), spaceAfter=15
        )
        section_style = ParagraphStyle(
            'SectionTitle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#111827'), spaceBefore=12, spaceAfter=6
        )

        elements.append(Paragraph("SHELL CAR WASH - EXECUTIVE BUSINESS REPORT", title_style))
        elements.append(Paragraph(f"Generated at: {timezone.now().strftime('%d %B %Y, %I:%M %p')} | Nairobi, Kenya", subtitle_style))
        elements.append(Spacer(1, 10))

        washes = CarWash.objects.filter(status=CarWash.Status.COMPLETED)
        total_rev = washes.aggregate(s=Sum('total_amount'))['s'] or 0
        total_comm = washes.aggregate(s=Sum('total_commission'))['s'] or 0
        total_exp = Expense.objects.aggregate(s=Sum('amount'))['s'] or 0
        gross_profit = total_rev - total_comm
        net_profit = gross_profit - total_exp

        kpi_data = [
            ["Key Performance Indicator", "Amount"],
            ["Total Completed Washes", f"{washes.count()} vehicles"],
            ["Total Business Revenue", f"KSh {total_rev:,.2f}"],
            ["Total Worker Commissions Paid/Credited", f"KSh {total_comm:,.2f}"],
            ["Gross Profit (Revenue - Commissions)", f"KSh {gross_profit:,.2f}"],
            ["Operating Expenses", f"KSh {total_exp:,.2f}"],
            ["Net Business Operating Profit", f"KSh {net_profit:,.2f}"],
        ]

        t_kpi = Table(kpi_data, colWidths=[340, 200])
        t_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F9FAFB')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#059669')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        elements.append(t_kpi)

        elements.append(Spacer(1, 15))
        elements.append(Paragraph("Worker Commission & Payout Status", section_style))

        workers_data = [["Worker", "Phone / M-Pesa", "Commissions Earned", "Disbursed Paid", "Balance Owed"]]
        for w in WorkerProfile.objects.all():
            workers_data.append([
                w.user.get_full_name() or w.user.username,
                w.mpesa_number or w.user.phone_number or '-',
                f"KSh {w.total_earned:,.2f}",
                f"KSh {w.total_paid:,.2f}",
                f"KSh {w.outstanding_balance:,.2f}"
            ])

        t_workers = Table(workers_data, colWidths=[120, 110, 100, 100, 110])
        t_workers.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(t_workers)

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="shell_carwash_report_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf"'
        return response


# ==============================================================================
# UNIVERSAL CSV EXPORT VIEW
# ==============================================================================

class ExportCSVReportView(APIView):
    """
    Universal CSV Exporter for almost everything in the system:
    - washes
    - today-washes
    - today-payouts (Steve earned X, needs to be paid Y...)
    - today-revenue (what was made today...)
    - shift-closings (closing shift was this...)
    - worker-payouts
    - expenses
    - attendance
    - workers
    - services
    - vehicles
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, entity=None):
        if not entity:
            entity = request.query_params.get('entity', 'washes')

        today = timezone.now().date()
        date_param = request.query_params.get('date')
        target_date = datetime.strptime(date_param, '%Y-%m-%d').date() if date_param else today

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        writer = csv.writer(response)

        if entity in ['today-payouts', 'payouts-today']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_today_payouts_{target_date}.csv"'
            p_data = get_today_payouts_data(target_date)
            writer.writerow([
                "Worker ID", "Staff Name", "Username", "Phone / M-Pesa",
                "Jobs Done Today", "Earned Today (KSh)", "Paid Today (KSh)",
                "Net Earned Today (KSh)", "Total Needs To Be Paid (KSh)", "Services Breakdown"
            ])
            for w in p_data['workers']:
                writer.writerow([
                    w['worker_id'], w['name'], w['username'], w['phone'],
                    w['jobs_count_today'], w['earned_today'], w['paid_today'],
                    w['net_earned_today'], w['needs_to_be_paid'], w['services_summary']
                ])

        elif entity in ['today-revenue', 'today-washes']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_today_revenue_{target_date}.csv"'
            r_data = get_today_revenue_data(target_date)
            writer.writerow([
                "Wash ID", "Time", "Plate Number", "Vehicle Type", "Customer Name", "Customer Phone",
                "Bay #", "Services", "Workers", "Total Bill (KSh)", "Payment Method",
                "Cash (KSh)", "M-Pesa (KSh)", "M-Pesa Ref", "Commission (KSh)", "Net Profit (KSh)"
            ])
            for w in r_data['washes']:
                writer.writerow([
                    w['id'], w['time'], w['plate_number'], w['vehicle_type'],
                    w['customer_name'], w['customer_phone'], w['bay_number'],
                    w['services'], w['workers'], w['total_amount'], w['payment_method'],
                    w['cash_amount'], w['mpesa_amount'], w['payment_reference'],
                    w['commission'], w['net_revenue']
                ])

        elif entity in ['shift-closings', 'closings']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_shift_closings_{today}.csv"'
            writer.writerow([
                "Date", "Closed By", "Cars Washed", "Gross Revenue (KSh)", "Cash Revenue (KSh)",
                "M-Pesa Revenue (KSh)", "Commissions (KSh)", "Payouts (KSh)", "Expenses (KSh)",
                "Expected Cash in Drawer (KSh)", "Actual Cash Counted (KSh)", "Cash Variance (KSh)", "Notes"
            ])
            for cl in DailyClosing.objects.all().select_related('closed_by').order_by('-date'):
                writer.writerow([
                    cl.date, cl.closed_by.get_full_name() or cl.closed_by.username,
                    cl.total_cars_washed, cl.total_revenue, cl.total_cash_revenue,
                    cl.total_mpesa_revenue, cl.total_commissions, cl.total_payouts,
                    cl.total_expenses, cl.expected_cash_in_drawer, cl.actual_cash_counted,
                    cl.cash_variance, cl.notes or ''
                ])

        elif entity in ['worker-payouts', 'payouts']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_all_payouts_{today}.csv"'
            writer.writerow([
                "Payout ID", "Date & Time", "Worker Name", "Amount Paid (KSh)",
                "Payment Method", "Transaction Reference", "Processed By", "Notes"
            ])
            for p in WorkerPayment.objects.all().select_related('worker__user', 'processed_by').order_by('-paid_at'):
                writer.writerow([
                    p.id, p.paid_at.strftime('%Y-%m-%d %H:%M:%S'),
                    p.worker.user.get_full_name() or p.worker.user.username,
                    p.amount_paid, p.get_payment_method_display(),
                    p.transaction_reference or '', p.processed_by.username, p.notes or ''
                ])

        elif entity in ['expenses']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_expenses_{today}.csv"'
            writer.writerow(["ID", "Date", "Category", "Title", "Amount (KSh)", "Logged By", "Notes"])
            for e in Expense.objects.all().select_related('logged_by').order_by('-date'):
                writer.writerow([
                    e.id, e.date, e.get_category_display(), e.title,
                    e.amount, e.logged_by.get_full_name() or e.logged_by.username, e.notes or ''
                ])

        elif entity in ['attendance']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_attendance_{today}.csv"'
            writer.writerow(["Date", "Worker Name", "Status", "Clock In", "Clock Out", "Marked By", "Notes"])
            for a in Attendance.objects.all().select_related('worker__user', 'marked_by').order_by('-date'):
                writer.writerow([
                    a.date, a.worker.user.get_full_name() or a.worker.user.username,
                    a.get_status_display(), a.clock_in or '', a.clock_out or '',
                    a.marked_by.username, a.notes or ''
                ])

        elif entity in ['workers']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_staff_roster_{today}.csv"'
            writer.writerow([
                "Worker ID", "Name", "Username", "Role", "Phone", "M-Pesa Number",
                "National ID", "Lifetime Earned (KSh)", "Lifetime Paid (KSh)", "Balance Owed (KSh)", "Active"
            ])
            for w in WorkerProfile.objects.all().select_related('user'):
                writer.writerow([
                    w.id, w.user.get_full_name() or w.user.username, w.user.username,
                    w.user.get_role_display(), w.user.phone_number or '', w.mpesa_number or '',
                    w.national_id or '', w.total_earned, w.total_paid, w.outstanding_balance,
                    "Yes" if w.is_active else "No"
                ])

        elif entity in ['services']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_services_catalog_{today}.csv"'
            writer.writerow(["Service ID", "Name", "Default Price (KSh)", "Commission Type", "Default Commission Value", "Active"])
            for s in Service.objects.all():
                writer.writerow([s.id, s.name, s.default_price, s.get_default_commission_type_display(), s.default_commission_value, "Yes" if s.is_active else "No"])

        elif entity in ['vehicles', 'customers']:
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_customer_vehicles_{today}.csv"'
            writer.writerow(["ID", "Plate Number", "Vehicle Type", "Make & Model", "Customer Name", "Customer Phone", "Registration Date"])
            for v in Vehicle.objects.all().order_by('-created_at'):
                writer.writerow([v.id, v.plate_number, v.get_vehicle_type_display(), v.make_model or '', v.customer_name or '', v.customer_phone or '', v.created_at.strftime('%Y-%m-%d')])

        else: # Default: all washes
            response['Content-Disposition'] = f'attachment; filename="shell_carwash_all_washes_{today}.csv"'
            writer.writerow([
                "ID", "Date & Time", "Plate Number", "Vehicle Type", "Customer Name", "Customer Phone",
                "Bay #", "Services", "Workers", "Total Bill (KSh)", "Payment Method",
                "Cash (KSh)", "M-Pesa (KSh)", "Payment Ref", "Commission (KSh)", "Net Profit (KSh)", "Status"
            ])
            for w in CarWash.objects.all().select_related('vehicle').prefetch_related('services__assignments__worker__user').order_by('-created_at'):
                srv_names = ", ".join([s.service_name_snapshot for s in w.services.all()])
                worker_set = set()
                for s in w.services.all():
                    for a in s.assignments.all():
                        worker_set.add(a.worker.user.get_full_name() or a.worker.user.username)
                writer.writerow([
                    w.id, w.created_at.strftime('%Y-%m-%d %H:%M:%S'), w.vehicle.plate_number,
                    w.vehicle.get_vehicle_type_display(), w.vehicle.customer_name or '',
                    w.vehicle.customer_phone or '', w.bay_number or 1, srv_names, ", ".join(worker_set),
                    w.total_amount, w.get_payment_method_display(), w.cash_amount, w.mpesa_amount,
                    w.payment_reference or '', w.total_commission, w.net_business_revenue, w.get_status_display()
                ])

        return response
