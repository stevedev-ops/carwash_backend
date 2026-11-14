from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from accounts.views import LoginView, CurrentUserView, WorkerProfileViewSet, AttendanceViewSet, UserViewSet
from services.views import ServiceViewSet, WorkerCommissionRateViewSet
from carwash.views import VehicleViewSet, CarWashViewSet
from carwash.receipt_views import CarWashCustomerReceiptView
from carwash.worker_views import WorkerSummaryView, WorkerJobsView
from payments.views import (
    WorkerPaymentViewSet, ExpenseViewSet, WorkerPayoutHistoryView, DailyClosingViewSet
)
from reports.views import (
    BusinessSummaryReportView, ExportExcelReportView, ExportPDFReportView,
    TodayPayoutsReportView, TodayRevenueReportView, ShiftClosingReportView,
    ExportTodayPayoutsExcelView, ExportTodayPayoutsPDFView,
    ExportTodayRevenueExcelView, ExportTodayRevenuePDFView,
    ExportShiftClosingExcelView, ExportShiftClosingPDFView,
    ExportCSVReportView
)
from core.views import SinglePageAppView, ServiceWorkerView, ManifestView

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='users')
router.register(r'workers', WorkerProfileViewSet, basename='workers')
router.register(r'attendance', AttendanceViewSet, basename='attendance')
router.register(r'services', ServiceViewSet, basename='services')
router.register(r'worker-rates', WorkerCommissionRateViewSet, basename='worker-rates')
router.register(r'vehicles', VehicleViewSet, basename='vehicles')
router.register(r'washes', CarWashViewSet, basename='washes')
router.register(r'worker-payments', WorkerPaymentViewSet, basename='worker-payments')
router.register(r'daily-closings', DailyClosingViewSet, basename='daily-closings')
router.register(r'expenses', ExpenseViewSet, basename='expenses')

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # PWA Service Worker & Manifest
    path('sw.js', ServiceWorkerView.as_view(), name='pwa-sw'),
    path('manifest.json', ManifestView.as_view(), name='pwa-manifest'),

    # Authentication
    path('api/auth/login/', LoginView.as_view(), name='auth-login'),
    path('api/auth/me/', CurrentUserView.as_view(), name='auth-me'),

    # Worker Self-Service Portal APIs
    path('api/worker-portal/summary/', WorkerSummaryView.as_view(), name='worker-summary'),
    path('api/worker-portal/jobs/', WorkerJobsView.as_view(), name='worker-jobs'),
    path('api/worker-portal/payouts/', WorkerPayoutHistoryView.as_view(), name='worker-payouts'),

    # Reports and File Exports
    path('api/reports/summary/', BusinessSummaryReportView.as_view(), name='reports-summary'),
    path('api/reports/today-payouts/', TodayPayoutsReportView.as_view(), name='reports-today-payouts'),
    path('api/reports/today-revenue/', TodayRevenueReportView.as_view(), name='reports-today-revenue'),
    path('api/reports/shift-closing/', ShiftClosingReportView.as_view(), name='reports-shift-closing'),

    # Master Exports
    path('api/reports/export/excel/', ExportExcelReportView.as_view(), name='reports-export-excel'),
    path('api/reports/export/pdf/', ExportPDFReportView.as_view(), name='reports-export-pdf'),
    
    # Specific Targeted Exports ("Steve earned this, needed to be paid this", "this was made today", "closing shift was this")
    path('api/reports/export/today-payouts/excel/', ExportTodayPayoutsExcelView.as_view(), name='reports-export-today-payouts-excel'),
    path('api/reports/export/today-payouts/pdf/', ExportTodayPayoutsPDFView.as_view(), name='reports-export-today-payouts-pdf'),
    path('api/reports/export/today-revenue/excel/', ExportTodayRevenueExcelView.as_view(), name='reports-export-today-revenue-excel'),
    path('api/reports/export/today-revenue/pdf/', ExportTodayRevenuePDFView.as_view(), name='reports-export-today-revenue-pdf'),
    path('api/reports/export/shift-closing/excel/', ExportShiftClosingExcelView.as_view(), name='reports-export-shift-closing-excel'),
    path('api/reports/export/shift-closing/pdf/', ExportShiftClosingPDFView.as_view(), name='reports-export-shift-closing-pdf'),

    # Universal CSV Download Engine
    path('api/reports/export/csv/', ExportCSVReportView.as_view(), name='reports-export-csv-default'),
    path('api/reports/export/csv/<str:entity>/', ExportCSVReportView.as_view(), name='reports-export-csv-entity'),

    # Receipts
    path('api/washes/<int:pk>/receipt/', CarWashCustomerReceiptView.as_view(), name='carwash-receipt'),

    # REST Router for CRUD
    path('api/', include(router.urls)),

    # Client-side SPA routing fallback
    re_path(r'^(?!api/|admin/|static/|media/|sw\.js|manifest\.json).*$', SinglePageAppView.as_view(), name='spa'),
]
