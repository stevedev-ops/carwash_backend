from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets
from rest_framework.decorators import action
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db.models import ProtectedError
from core.authentication import generate_jwt_token
from core.permissions import IsAdminUser
from .models import User, WorkerProfile, Attendance
from .serializers import UserSerializer, WorkerProfileSerializer, AttendanceSerializer

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({'error': 'Please provide both username and password'}, status=status.HTTP_400_BAD_REQUEST)

        # Allow logging in with phone number as username too
        user = authenticate(username=username, password=password)
        if not user:
            # Try finding user by phone number
            user_by_phone = User.objects.filter(phone_number=username).first()
            if user_by_phone:
                user = authenticate(username=user_by_phone.username, password=password)

        if not user:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({'error': 'Account is inactive. Contact administration.'}, status=status.HTTP_403_FORBIDDEN)

        token = generate_jwt_token(user)
        worker_profile_id = None
        if hasattr(user, 'worker_profile'):
            worker_profile_id = user.worker_profile.id

        return Response({
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'phone_number': user.phone_number,
                'worker_profile_id': worker_profile_id,
            }
        })

class CurrentUserView(APIView):
    def get(self, request):
        user = request.user
        worker_profile_id = None
        if hasattr(user, 'worker_profile'):
            worker_profile_id = user.worker_profile.id
        return Response({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role,
            'phone_number': user.phone_number,
            'worker_profile_id': worker_profile_id,
        })

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance == request.user:
            return Response({'error': 'You cannot delete your own logged-in admin account.'}, status=status.HTTP_400_BAD_REQUEST)
        user_name = instance.get_full_name() or instance.username
        try:
            instance.delete()
            return Response({'status': 'deleted', 'message': f'User "{user_name}" permanently deleted.'}, status=status.HTTP_200_OK)
        except ProtectedError:
            instance.is_active = False
            instance.save()
            return Response({
                'status': 'deactivated',
                'message': f'User "{user_name}" has recorded historical system data. Account has been deactivated and blocked from login to preserve audit trails.'
            }, status=status.HTTP_200_OK)

class WorkerProfileViewSet(viewsets.ModelViewSet):
    queryset = WorkerProfile.objects.all().select_related('user').order_by('id')
    serializer_class = WorkerProfileSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = super().get_queryset()
        active_only = self.request.query_params.get('active_only')
        if active_only == 'true':
            qs = qs.filter(is_active=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = instance.user
        worker_name = user.get_full_name() or user.username if user else f"Worker #{instance.id}"
        try:
            user_to_delete = user
            instance.delete()
            if user_to_delete:
                user_to_delete.delete()
            return Response({'status': 'deleted', 'message': f'Worker "{worker_name}" permanently deleted.'}, status=status.HTTP_200_OK)
        except ProtectedError:
            instance.is_active = False
            instance.save()
            if user:
                user.is_active = False
                user.save()
            return Response({
                'status': 'deactivated',
                'message': f'Worker "{worker_name}" has historical wash or payout records. Profile was deactivated and removed from active roster to preserve audit integrity.'
            }, status=status.HTTP_200_OK)

class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.all().select_related('worker__user', 'marked_by')
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        date_param = self.request.query_params.get('date') or timezone.now().date()
        return qs.filter(date=date_param)

    def perform_create(self, serializer):
        serializer.save(marked_by=self.request.user)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def batch_update(self, request):
        date_val = request.data.get('date') or timezone.now().date()
        records = request.data.get('records', [])
        saved = []
        for r in records:
            att, _ = Attendance.objects.update_or_create(
                worker_id=r['worker_id'],
                date=date_val,
                defaults={
                    'status': r.get('status', 'PRESENT'),
                    'notes': r.get('notes', ''),
                    'marked_by': request.user
                }
            )
            saved.append(att)
        return Response(AttendanceSerializer(saved, many=True).data)
