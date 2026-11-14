from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from django.db.models import ProtectedError
from core.permissions import IsAdminOrReadOnly
from .models import Service, WorkerCommissionRate
from .serializers import ServiceSerializer, WorkerCommissionRateSerializer

class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all().order_by('id')
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        active_only = self.request.query_params.get('active_only')
        if active_only == 'true':
            qs = qs.filter(is_active=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        service_name = instance.name
        try:
            instance.delete()
            return Response({'status': 'deleted', 'message': f'Service "{service_name}" was permanently deleted.'}, status=status.HTTP_200_OK)
        except ProtectedError:
            instance.is_active = False
            instance.save()
            return Response({
                'status': 'deactivated',
                'message': f'Service "{service_name}" has past customer wash receipts. It has been deactivated and removed from active booking menu to preserve financial records.'
            }, status=status.HTTP_200_OK)

class WorkerCommissionRateViewSet(viewsets.ModelViewSet):
    queryset = WorkerCommissionRate.objects.all().select_related('worker__user', 'service')
    serializer_class = WorkerCommissionRateSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        worker_id = self.request.query_params.get('worker_id')
        service_id = self.request.query_params.get('service_id')
        if worker_id:
            qs = qs.filter(worker_id=worker_id)
        if service_id:
            qs = qs.filter(service_id=service_id)
        return qs
