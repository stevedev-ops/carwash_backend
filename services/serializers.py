from rest_framework import serializers
from .models import Service, WorkerCommissionRate

class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = [
            'id', 'name', 'description', 'default_price', 
            'default_commission_type', 'default_commission_value', 
            'estimated_minutes', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class WorkerCommissionRateSerializer(serializers.ModelSerializer):
    worker_name = serializers.ReadOnlyField(source='worker.user.get_full_name')
    service_name = serializers.ReadOnlyField(source='service.name')

    class Meta:
        model = WorkerCommissionRate
        fields = [
            'id', 'worker', 'worker_name', 'service', 'service_name', 
            'commission_type', 'commission_value', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']

