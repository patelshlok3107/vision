from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed

from .auth import verify_admin_token


class IsAdminAuthenticated(BasePermission):
    """
    Requires valid admin JWT in Authorization: Bearer <admin_token>
    Does NOT accept normal user JWT.
    """
    def has_permission(self, request, view):
        auth = request.headers.get("Authorization", "") or request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            raise AuthenticationFailed("Admin authentication required. Please log in at /admin/login")
        token = auth.split(" ", 1)[1].strip()
        payload = verify_admin_token(token)
        if not payload:
            raise AuthenticationFailed("Invalid or expired admin token")
        # Attach admin identity
        request.admin_username = payload.get("sub", "admin")
        request.admin_jti = payload.get("jti")
        return True
