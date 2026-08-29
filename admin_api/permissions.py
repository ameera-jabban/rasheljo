from rest_framework.permissions import BasePermission


class IsStaffUser(BasePermission):
    """Every admin_api endpoint requires is_staff — enforced at the API layer,
    not just hidden behind a frontend route guard, per Part 3's access-control note."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
