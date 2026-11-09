from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """Allows access only to Admin users or Django superusers."""
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (getattr(request.user, 'role', '') == 'ADMIN' or request.user.is_superuser)
        )

class IsAdminOrCashier(permissions.BasePermission):
    """Allows access to Admin and Cashier roles."""
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (getattr(request.user, 'role', '') in ['ADMIN', 'CASHIER'] or request.user.is_superuser)
        )

class IsWorkerUser(permissions.BasePermission):
    """Allows access to Workers."""
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            getattr(request.user, 'role', '') == 'WORKER'
        )

class IsAdminOrReadOnly(permissions.BasePermission):
    """Allows safe methods to all authenticated users, modifications to Admin only."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(request.user, 'role', '') == 'ADMIN' or request.user.is_superuser

