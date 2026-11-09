from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets
from rest_framework.decorators import action
from django.contrib.auth import authenticate
from django.utils import timezone
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
