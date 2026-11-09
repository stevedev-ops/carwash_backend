from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, WorkerProfile

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role', 'phone_number', 'is_active']
        read_only_fields = ['id']

class WorkerProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    username = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False)
    first_name = serializers.CharField(write_only=True, required=False)
    last_name = serializers.CharField(write_only=True, required=False)
    phone_number = serializers.CharField(write_only=True, required=False)
    
    total_earned = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_paid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    outstanding_balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = WorkerProfile
        fields = [
            'id', 'user', 'username', 'password', 'first_name', 'last_name', 'phone_number',
            'national_id', 'mpesa_number', 'is_active', 'joined_at', 'emergency_contact', 'notes',
            'total_earned', 'total_paid', 'outstanding_balance'
        ]
        read_only_fields = ['id', 'joined_at']

    def create(self, validated_data):
        username = validated_data.pop('username', None)
        password = validated_data.pop('password', 'worker123')
        first_name = validated_data.pop('first_name', '')
        last_name = validated_data.pop('last_name', '')
        phone_number = validated_data.pop('phone_number', '')

        if not username:
            username = phone_number or f"worker_{first_name.lower() or 'staff'}"
            # Ensure unique username
            base = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}_{counter}"
                counter += 1

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            role=User.Role.WORKER
        )

        profile = WorkerProfile.objects.create(
            user=user,
            mpesa_number=validated_data.get('mpesa_number', phone_number),
            **validated_data
        )
        return profile

class AttendanceSerializer(serializers.ModelSerializer):
    worker_name = serializers.ReadOnlyField(source='worker.user.get_full_name')
    marked_by_name = serializers.ReadOnlyField(source='marked_by.get_full_name')

    class Meta:
        from .models import Attendance
        model = Attendance
        fields = ['id', 'worker', 'worker_name', 'date', 'status', 'clock_in', 'clock_out', 'notes', 'marked_by_name', 'created_at']
        read_only_fields = ['id', 'created_at', 'marked_by_name']

