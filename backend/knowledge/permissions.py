from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed

from .auth import verify_admin_token


class IsAdminAuthenticated(BasePermission):
    """
    Accepts either:
    1) Admin JWT (is_admin) from /api/admin/login  OR
    2) Normal user JWT where user.is_staff / is_superuser (merged login)
    """
    def has_permission(self, request, view):
        auth = request.headers.get("Authorization", "") or request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            raise AuthenticationFailed("Admin authentication required. Please log in with admin account")
        token = auth.split(" ", 1)[1].strip()
        # Try admin JWT first
        payload = verify_admin_token(token)
        if payload:
            request.admin_username = payload.get("sub", "admin")
            request.admin_jti = payload.get("jti")
            request.is_admin_via_jwt = True
            return True
        # Fallback: try normal user JWT and check is_staff
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
            auth_obj = JWTAuthentication()
            # Need to make a fake request with token for authenticate
            # Manually validate
            validated = auth_obj.get_validated_token(token)
            user = auth_obj.get_user(validated)
            if user and (user.is_staff or user.is_superuser):
                request.user = user
                request.admin_username = user.email or user.username
                request.is_admin_via_jwt = False
                return True
        except Exception:
            pass
        raise AuthenticationFailed("Invalid or expired admin token — use admin login")
