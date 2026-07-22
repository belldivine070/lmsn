from datetime import timedelta
import random
from urllib import request

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

# Core / Shared Layout App Imports
from core.mixins import PublicOrRolePermissionRequiredMixin, RolePermissionRequiredMixin, get_client_ip
from core.models import ActivityLog, AppVariable, PasswordResetOTP, SecurityAuditLog
from core.sms import send_sms_otp, validate_email_deliverability

# Accounts App Internal Imports
from .forms import DepartmentForm, LoginForm, PermissionForm, PositionForm, UserEditForm, UserSignupForm, AddressFormSet
from .models import CustomUser, Department, Position, RolePermission, Address

User = get_user_model()




# =========================================================
# 1. AUTHENTICATION VIEWS
# =========================================================
class CustomPasswordResetView(View):
    template_name = 'accounts/password_reset_form.html'

    def get(self, request):
        # Always start at Stage 1
        return render(request, self.template_name, {'stage': 1})

    def post(self, request):
        action = request.POST.get('action')
        identifier = request.POST.get('identifier', '').strip()

        # Phase-wide user lookup helper
        user = User.objects.filter(Q(email__iexact=identifier) | Q(mobile=identifier)).first() if identifier else None

        # =====================================================================
        # STAGE 1: GENERATE & DISPATCH OTP
        # =====================================================================
        if action == "send_otp":
            if not user:
                messages.error(request, "No account discovered with that identity detail.")
                return render(request, self.template_name, {'stage': 1, 'identifier': identifier})

            # FIX: Clean evaluation lookup to differentiate email vs mobile numbers correctly
            if "@" in identifier or identifier.endswith(".com"):
                method = 'email'
            else:
                method = 'mobile'
            
            # Generate DB record via your classmethod wrapper
            otp_record = PasswordResetOTP.generate_otp(user=user, method=method)

            # -----------------------------------------------------------------
            # PATH A: LIVE EMAIL VALIDATION & DELIVERY
            # -----------------------------------------------------------------
            if method == 'email':
                # 1. Run the APILayer Live Deliverability Check
                is_valid_email, email_message = validate_email_deliverability(user.email)
                
                if not is_valid_email:
                    messages.error(request, email_message)
                    return render(request, self.template_name, {'stage': 1, 'identifier': identifier})
                    
                # 2. If it passes validation, proceed to send the actual OTP email
                try:
                    send_mail(
                        subject="Your Security Reset OTP Code",
                        message=f"Your security validation token is: {otp_record.otp_code}. Valid for 10 minutes.",
                        from_email=settings.EMAIL_HOST_USER,
                        recipient_list=[user.email],
                        fail_silently=False,
                    )
                    messages.success(request, f"A fresh verification token has dropped into your email inbox: {user.email}")
                except Exception:
                    print(f"\n[DEV FALLBACK] SMTP Failed! Reset OTP Code: {otp_record.otp_code}\n")
                    messages.warning(request, "Mail server offline. Code printed to terminal.")

            # -----------------------------------------------------------------
            # PATH B: LIVE MOBILE VALIDATION & DELIVERY
            # -----------------------------------------------------------------
            else:
                # Trigger the combined validation and dispatch sequence
                sms_success, response_message = send_sms_otp(phone_number=user.mobile, otp_code=otp_record.otp_code)
                
                if sms_success:
                    messages.success(request, response_message)
                else:
                    # If APILayer says it's an invalid number, alert them instantly and halt progress
                    messages.error(request, response_message)
                    return render(request, self.template_name, {'stage': 1, 'identifier': identifier})

            # If it passes validation, advance into the Stage 2 input window smoothly
            return render(request, self.template_name, {'stage': 2, 'identifier': identifier})

        # =====================================================================
        # STAGE 2: VERIFY EXPLICIT OTP CODE MATCHING
        # =====================================================================
        elif action == "verify_otp":
            otp_input = request.POST.get('otp_code', '').strip()
            
            # Look up the active unverified token entry sequence
            otp_record = PasswordResetOTP.objects.filter(user=user, is_verified=False).last()

            if not otp_record or otp_record.is_expired():
                messages.error(request, "The security token session has expired. Please request a new code.")
                return render(request, self.template_name, {'stage': 1, 'identifier': identifier})

            if otp_input != otp_record.otp_code:
                messages.error(request, "The code you entered is invalid. Please double check and try again.")
                return render(request, self.template_name, {'stage': 2, 'identifier': identifier})

            # Mark token as spent in database record securely
            otp_record.is_verified = True
            otp_record.save()

            messages.success(request, "Identity token confirmed! Provide your new password below.")
            
            # Progress into stage 3 and supply the verified record token id to sign the payload
            return render(request, self.template_name, {
                'stage': 3, 
                'identifier': identifier, 
                'otp_record_id': otp_record.id
            })

        # =====================================================================
        # STAGE 3: ACCOUNT VALIDATION & CREATION UPDATE
        # =====================================================================
        elif action == "commit_new_password":
            otp_record_id = request.POST.get('otp_record_id')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            # Crucial verification guard: Confirm token was marked verified in Stage 2
            verified_token = PasswordResetOTP.objects.filter(id=otp_record_id, user=user, is_verified=True).first()
            if not verified_token:
                messages.error(request, "Unauthorized access sequence detected. Restart token authentication.")
                return render(request, self.template_name, {'stage': 1})

            if new_password != confirm_password:
                messages.error(request, "Your fresh new passwords do not match.")
                return render(request, self.template_name, {'stage': 3, 'identifier': identifier, 'otp_record_id': otp_record_id})

            try:
                validate_password(new_password, user=user)
            except ValidationError as e:
                for error in e.messages:
                    messages.error(request, error)
                return render(request, self.template_name, {'stage': 3, 'identifier': identifier, 'otp_record_id': otp_record_id})

            # Commit changes
            user.set_password(new_password)
            user.save()

            # Clean up the token asset so it cannot be parsed again
            verified_token.delete()

            messages.success(request, "Account update successful! Log into your profile below.")
            return redirect('accounts:login')  # Using proper explicit namespace pairing

        return render(request, self.template_name, {'stage': 1})

        
class UserLoginView(LoginView):
    form_class = LoginForm
    template_name = "lmsn/login.html"

    def get_success_url(self):
        user = self.request.user
        next_url = self.request.GET.get('next')

        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()}
        ):
            return next_url

        if user.is_staff or user.is_superuser:
            return reverse("core:index")
        return reverse("lmsn:index")

    def form_valid(self, form):
        """Runs only when login is successful"""
        user = form.get_user()
        
        SecurityAuditLog.objects.create(
            user=user,
            event='login',
            description=f"User {user.username} logged in successfully.",
            ip_address=get_client_ip(self.request),
            user_agent=self.request.headers.get('User-Agent')
        )
        messages.success(self.request, f"Welcome back, {user.full_name}!")
        return super().form_valid(form)

    def form_invalid(self, form):
        """Runs when login fails (wrong password/username)"""
        username = form.data.get('username') # Get the name they tried to use
        
        SecurityAuditLog.objects.create(
            # No user linked because login failed
            event='failed_login',
            description=f"Failed login attempt for username: {username}",
            ip_address=get_client_ip(self.request),
            user_agent=self.request.headers.get('User-Agent')
        )
        # Check for the "50 attempts" here
        self.check_brute_force(username)
        return super().form_invalid(form)

    def check_brute_force(self, username):
        """Simple manual check for too many failed attempts"""
        one_hour_ago = timezone.now() - timedelta(hours=1)
        attempts = SecurityAuditLog.objects.filter(
            event='failed_login',
            description__contains=username,
            timestamp__gte=one_hour_ago
        ).count()

        if attempts >= 5: # Low threshold for testing
             # You could trigger an email alert or a SecurityAuditLog here
             SecurityAuditLog.objects.create(
                event="Potential Brute Force",
                description=f"User {username} failed login {attempts} times in 1 hour.",
                ip_address=get_client_ip(self.request),
                # user_agent=self.request.headers.get('User-Agent'),
             )


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("lmsn:index")

    def dispatch(self, request, *args, **kwargs):
        user=self.request.user
        if request.user.is_authenticated:
            SecurityAuditLog.objects.create(
                user=user,
                event="logout",
                description=f"User {user.username} logged out successfully.",
                ip_address=get_client_ip(self.request),
                user_agent=self.request.headers.get('User-Agent')
            )
            messages.info(request, "You have been logged out successfully.")
        return super().dispatch(request, *args, **kwargs)


# =========================================================
# Profile
# =========================================================
class ProfileView(LoginRequiredMixin, UpdateView):
    model = CustomUser
    template_name = "accounts/profile.html"
    context_object_name = "profile"
    form_class = UserEditForm

    # def get_object(self, queryset=None):
    #     """Directly returns the logged-in user instance for the form layout."""
    #     return self.request.user

    def get_object(self):
        return self.request.user
    
    def get_success_url(self):
        return reverse('accounts:profile')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        
        if self.request.POST:
            data['address_form'] = AddressFormSet(self.request.POST, instance=self.request.user)
        else:
            data['address_form'] = AddressFormSet(instance=self.request.user)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        address_form = context['address_form']
        
        if form.is_valid() and address_form.is_valid():
            # Save the User first
            self.object = form.save()
            
            # Explicitly bind the formset to the saved user and save
            address_form.instance = self.object
            address_form.save()
            
            return redirect(self.get_success_url())
        else:
            # If the address form isn't valid, show errors
            return self.render_to_response(self.get_context_data(form=form))


# =========================================================
# 2. USER REGISTRATION & MANAGEMENT
# =========================================================

class SignupView(PublicOrRolePermissionRequiredMixin, CreateView):
    """
    Handles both Public Signup and Admin-created users seamlessly.
    """
    required_permission = 'can_create_user'  # Checked via your custom mixin rules
    form_class = UserSignupForm
    success_url = reverse_lazy('accounts:manage_users')

    def get_template_names(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return ["accounts/signup.html"]  # Staff management template
        return ["lmsn/register.html"]        # Public guest signup template

    def form_valid(self, form):
        """
        Processes form fields completely in memory first, handles security tagging, 
        and performs a single transaction commit to eliminate post-save crash loops.
        """
        # 1. Initialize user instance completely in memory (commit=False)
        # This prevents Django from saving the row to the database yet!
        user = form.save(commit=False)

        is_authenticated = self.request.user.is_authenticated
        is_staff = self.request.user.is_staff if is_authenticated else False
        is_admin_creating = is_authenticated and is_staff

        # 2. Safely apply boundary logic properties directly to the memory instance
        if is_admin_creating and not self.request.user.is_superuser:
            user.assigned_to = self.request.user

        if not is_admin_creating:
            user.is_client = True

        # 3. NOW it is 100% configured and safe to commit to the database
        user.save()
        
        # 4. Save form ManyToMany data (like user groups or roles if attached to the form)
        form.save_m2m()

        # 5. Execute downstream logging safely after a guaranteed database save
        SecurityAuditLog.objects.create(
            user=user,
            event='register',
            description=f"User account {user.username} created. Context: {'Admin Panel' if is_admin_creating else 'Public Form'}.",
            ip_address=get_client_ip(self.request),
            user_agent=self.request.headers.get('User-Agent', 'Unknown')
        )

        messages.success(self.request, f"User {user.username} created successfully.")

        if is_admin_creating:
            return redirect("accounts:manage_users")

        # Fallback parameters redirection logic
        next_url = self.request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()}
        ):
            return redirect(next_url)

        return redirect("lmsn:index")
    

class ManageUsersListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CustomUser
    permission_required = ['accounts.can_create_user', 'accounts.can_edit_user']
    template_name = 'accounts/manage_users.html'
    context_object_name = 'users'
    paginate_by = 10
    
    def get_queryset(self):
        # 1. Get the actual user object
        request_user = self.request.user
        
        # 2. Corrected Base Queryset logic
        if request_user.is_superuser:
            # Show everyone EXCEPT the current superuser and clients
            queryset = CustomUser.objects.all().exclude(pk=request_user.pk)
        else:
            # Show only users assigned to this staff member
            queryset = CustomUser.objects.filter(assigned_to=request_user)
        
        queryset = queryset.select_related('position', 'assigned_to').order_by("-date_joined")

        # 3. Search and Filters (Cleaned variable names)
        search = self.request.GET.get("search")
        position_slug = self.request.GET.get("Position")
        region = self.request.GET.get("region")

        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(username__icontains=search) |
                Q(email__icontains=search)
            )
        
        if position_slug:
            # Assuming 'position' is the field name on CustomUser
            queryset = queryset.filter(position__slug=position_slug)
            
        if region:
            queryset = queryset.filter(region__icontains=region)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "search": self.request.GET.get("search", ""),
            "Position_filter": self.request.GET.get("Position", ""),
            "region_filter": self.request.GET.get("region", "")
        })
        return context

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "search": self.request.GET.get("search", ""),
            "Position_filter": self.request.GET.get("Position", ""),
            "region_filter": self.request.GET.get("region", "")
        })
        return context


class EditSubordinateView(RolePermissionRequiredMixin, UpdateView):
    model = CustomUser
    form_class = UserEditForm
    template_name = 'accounts/user_edit.html'
    required_permission = ['can_assign_staff', 'can_create_user' ] 
    success_url = reverse_lazy('accounts:manage_users')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return CustomUser.objects.all()
        return CustomUser.objects.filter(assigned_to=self.request.user)


class UserDetailView(LoginRequiredMixin, DetailView):
    model = CustomUser
    template_name = "users/user_detail.html"
    context_object_name = "target_user"

    def get_object(self, queryset=None):
        obj = super().get_object()
        # Security: Only staff or the user themselves can view the profile
        if not self.request.user.is_staff and obj != self.request.user:
            raise PermissionDenied("You are not allowed to view this profile.")
        return obj
    

###########################################################
# Customer
###########################################################
class ManageCustomersListView(LoginRequiredMixin, ListView):
    """Unified View for listing accounts with Search and Filtering."""
    model = CustomUser
    template_name = 'accounts/manage_customers.html'
    required_permission = ['can_assign_staff', 'can_create_user', 'can_edit_user' ] 
    context_object_name = 'users'
    paginate_by = 10
    
    def get_queryset(self):
        # Correctly exclude staff/superusers to only show 'customers'
        queryset = CustomUser.objects.filter(is_staff=False, is_superuser=False).order_by("-date_joined")

        # Capture filter values
        search = self.request.GET.get("search")
        region = self.request.GET.get("region")

        # Apply Search logic
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(username__icontains=search) |
                Q(email__icontains=search)
            )

        # Apply Position Filter (Checking by slug)
        if region:
            queryset = queryset.filter(region__icontains=region)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass filters back to template to persist in search fields
        context.update({
            "search": self.request.GET.get("search", ""),
            "position_filter": self.request.GET.get("position", ""),
            "region_filter": self.request.GET.get("region", "")
        })
        return context
    

class CustomerEditView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = CustomUser
    form_class = UserEditForm
    template_name = 'accounts/user_edit.html'
    permission_required = ['can_assign_staff', 'can_create_user']
    success_url = reverse_lazy('accounts:manage_users')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return CustomUser.objects.all()
        return CustomUser.objects.filter(is_client=self.request.user)


class CustomerDeleteView(LoginRequiredMixin, View):
    def delete(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        customer = get_object_or_404(CustomUser, pk=pk, is_staff=False)
        customer.delete()
        
        return HttpResponse("")
    

# =========================================================
# 3. ROLE MANAGEMENT (Superuser Only)
# =========================================================

class PositionView(UserPassesTestMixin, ListView):
    model = Position
    template_name = 'accounts/manage_roles.html'
    context_object_name = 'roles'
    
    def test_func(self): 
        return self.request.user.is_superuser
        
    def get_queryset(self): 
        return Position.objects.annotate(user_count=Count('users'))


class PositionBaseView(UserPassesTestMixin):
    model = Position
    form_class = PositionForm
    template_name = 'accounts/role_form.html' 
    success_url = reverse_lazy('accounts:manage_roles')

    def test_func(self): 
        return self.request.user.is_superuser


class PositionCreateView(PositionBaseView, CreateView):
    pass

class PositionUpdateView(PositionBaseView, UpdateView):
    pass


class PositionDeleteView(UserPassesTestMixin, DeleteView):
    model = Position
    success_url = reverse_lazy('accounts:manage_roles')
    
    def test_func(self): 
        return self.request.user.is_superuser

    def post(self, request, *args, **kwargs):
        role = self.get_object()
        if role.users.exists():
            messages.error(
                request, 
                f"Cannot delete '{role.name}' because it is assigned to {role.users.count()} users."
            )
            return redirect(self.success_url)
        
        messages.success(request, f"Position '{role.name}' deleted successfully.")
        return super().post(request, *args, **kwargs)


# =================================================
# Department Views (Superuser Only)
# =================================================

class DepartmentListView(UserPassesTestMixin, ListView):
    model = Department
    template_name = 'accounts/manage_departments.html'
    context_object_name = 'departments'
    
    def test_func(self): 
        return self.request.user.is_superuser


class DepartmentBaseView(UserPassesTestMixin):
    """Abstract structural helper providing base configuration settings"""
    model = Department
    form_class = DepartmentForm
    template_name = 'accounts/department_form.html'  # Shared Form Template
    success_url = reverse_lazy('accounts:manage_departments')
    
    def test_func(self): 
        return self.request.user.is_superuser


class DepartmentCreateView(DepartmentBaseView, CreateView):
    pass  # Automatically uses settings and templates from DepartmentBaseView


class DepartmentUpdateView(DepartmentBaseView, UpdateView):
    pass  # Automatically uses settings and templates from DepartmentBaseView


class DepartmentDeleteView(UserPassesTestMixin, DeleteView):
    model = Department
    success_url = reverse_lazy('accounts:manage_departments')
    
    def test_func(self): 
        return self.request.user.is_superuser

    def post(self, request, *args, **kwargs):
        department = self.get_object()
        if hasattr(department, 'users') and department.users.exists():
            messages.error(
                request, 
                f"Cannot delete '{department.name}' while it contains active staff profiles."
            )
            return redirect(self.success_url)
            
        messages.warning(request, f"Department '{department.name}' has been removed.")
        return super().post(request, *args, **kwargs)


# =================================================
# Permission Views (Superuser Only)
# =================================================

class PermissionListView(UserPassesTestMixin, ListView):
    model = RolePermission
    template_name = 'accounts/manage_permissions.html'
    context_object_name = 'permissions'

    def test_func(self):
        return self.request.user.is_superuser

class PermissionBaseView(UserPassesTestMixin):
    model = RolePermission
    form_class = PermissionForm
    template_name = 'accounts/permission_form.html'  # Shared Form Template
    success_url = reverse_lazy('accounts:manage_permissions')
    
    def test_func(self): 
        return self.request.user.is_superuser


class PermissionCreateView(PermissionBaseView, CreateView):
    pass  # Automatically uses settings and templates from PermissionBaseView


class PermissionUpdateView(PermissionBaseView, UpdateView):
    pass  # Automatically uses settings and templates from PermissionBaseView


class PermissionDeleteView(UserPassesTestMixin, DeleteView):
    model = RolePermission
    success_url = reverse_lazy('accounts:manage_permissions')

    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request, *args, **kwargs):
        permission = self.get_object()
        if hasattr(permission, 'users') and permission.users.exists():
            messages.error(
                request, 
                f"Cannot delete '{permission.name}' while it contains active staff profiles."
            )
            return redirect(self.success_url)
            
        messages.warning(request, f"Permission '{permission.name}' has been removed.")
        return super().post(request, *args, **kwargs)


# =================================================
# 4. Assign Staffs
# =================================================

class StaffAssignmentView(RolePermissionRequiredMixin, ListView):
    """
    Dedicated view for managers to see only the staff assigned to them.
    Uses a different template if you want a dashboard-style layout.
    """
    required_permission = 'can_assign_staff' 
    model = CustomUser
    template_name = 'dashboard/staff_assignment.html'
    context_object_name = 'subordinates'

    def get_queryset(self):
        # Only show users assigned to the logged-in user
        return CustomUser.objects.filter(assigned_to=self.request.user).select_related('Position')
    

class CustomPasswordChangeView(LoginRequiredMixin, FormView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('users:login')
    def get_form_class(self):
        from django.contrib.auth.forms import PasswordChangeForm
        return PasswordChangeForm
        
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        user = form.get_user()
        SecurityAuditLog.objects.create(
            user=user,
            event='password_change',
            description=f"User {user.username} created an account successfully.",
            ip_address=get_client_ip(self.request),
            user_agent=self.request.headers.get('User-Agent')

        )
        user = form.save()
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Password updated.")
        return super().form_valid(form)

