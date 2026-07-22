# core/mixins.py
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect



def get_client_ip(request):
    """Utility to extract IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class RolePermissionRequiredMixin(UserPassesTestMixin):
    required_permission = None

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if hasattr(user, 'role') and user.role:
            return user.role.permissions.filter(codename=self.required_permission).exists()
        return False

    def handle_no_permission(self):
        if self.request.user.is_authenticated and self.request.user.is_staff == True:
            messages.error(self.request, "You do not have permission to access this page.")
            return redirect('accounts:index')
        elif self.request.user.is_authenticated and self.request.user.is_staff == False:
            return redirect('lmsn:index')
        return super().handle_no_permission()


# =========================================================
# NEW: COMBINED PUBLIC / STAFF PERMISSION MIXIN
# =========================================================
class PublicOrRolePermissionRequiredMixin(RolePermissionRequiredMixin):
    """
    Allows anonymous public access completely unhindered.
    However, if an authenticated user accesses the view, it strictly enforces
    your custom role/permission rules matching 'required_permission'.
    """
    def test_func(self):
        # 1. If the browser visitor is a public guest, let them through immediately
        if not self.request.user.is_authenticated:
            return True
            
        # 2. If they are logged in, reuse your exact parent mixin permission logic!
        return super().test_func()