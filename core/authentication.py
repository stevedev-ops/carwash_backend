import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

def generate_jwt_token(user):
    payload = {
        'user_id': user.id,
        'username': user.username,
        'role': getattr(user, 'role', 'WORKER'),
        'exp': datetime.now(timezone.utc) + timedelta(days=14),
        'iat': datetime.now(timezone.utc)
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    return token

class CustomJWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            # Fall back to query param for exports (PDF / Excel downloads)
            token = request.query_params.get('token')
            if not token:
                return None
        else:
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                return None
            token = parts[1]

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Token has expired. Please log in again.')
        except (jwt.InvalidTokenError, Exception) as e:
            raise exceptions.AuthenticationFailed(f'Invalid token: {str(e)}')

        User = get_user_model()
        try:
            user = User.objects.get(id=payload['user_id'], is_active=True)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('User not found or inactive.')

        return (user, token)

