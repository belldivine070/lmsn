from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AuthenticationForm
from django.contrib.auth import get_user_model, authenticate
from .models import Department, Position, CustomUser, RolePermission, Address
from django.forms import inlineformset_factory

User = get_user_model()



# =========================================================
# 1. AUTHENTICATION (LOGIN)
# =========================================================

class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Email, Username or Mobile",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter Email, Username or Mobile'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(username=username, password=password)
            if self.user_cache is None:
                raise forms.ValidationError("Invalid login credentials")
            if not self.user_cache.is_active:
                raise forms.ValidationError("This account has been suspended or inactive.")
        return self.cleaned_data

        
class UserSignupForm(forms.ModelForm):
    """Handles both public and admin-initiated registration via SignupView."""
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'first_name', 'last_name', 'mobile', 'is_active', 'is_staff', ''
        'image', 'position', 'department', 'assigned_to']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ['username', 'email', 'first_name', 'last_name', 'mobile', 'image', 'is_active', 'is_staff', 'assigned_to']:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
        self.fields['position'].queryset = Position.objects.all()
        self.fields['department'].queryset = Department.objects.all()

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("confirm_password"):
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    """Handles updating existing user profiles."""    
    class Meta:
        model = CustomUser
        fields = [
            'username', 'email', 'first_name', 'last_name', 'mobile', 
            'is_active', 'is_staff', 'image', 'position', 
            'department', 'assigned_to'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply form-control class to all fields
        for field_name, field in self.fields.items():
            if field_name not in ['is_active', 'is_staff']:  # Switches use different classes
                field.widget.attrs.update({'class': 'form-control'})
        
        # Ensure QuerySets are loaded
        self.fields['position'].queryset = Position.objects.all()
        self.fields['department'].queryset = Department.objects.all()

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        # Check if email is taken by SOMEONE ELSE (exclude current user)
        if CustomUser.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

AddressFormSet = inlineformset_factory(
    CustomUser, 
    Address, 
    fields=['address_line_1', 'city', 'state', 'country'],
    extra=1,  # 🔥 important
    max_num=1,
    can_delete=True
)


class CustomUserChangeForm(UserChangeForm):
    """Used by admins to update existing users."""
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), required=False)
    
    role = forms.ModelChoiceField(
        queryset=Position.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'username', 'mobile', 'position', 'is_active', 'is_staff')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


# =========================================================
# 4. ROLE MANAGEMENT & Permissions
# =========================================================

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'contact_email', 'permissions']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'permissions': forms.CheckboxSelectMultiple()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional: Add Bootstrap class to the checkbox container
        self.fields['permissions'].queryset = RolePermission.objects.all()


class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ['name', 'description', 'permissions']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'permissions': forms.CheckboxSelectMultiple()
        }
        
class PermissionForm(forms.ModelForm):
    class Meta:
        model = RolePermission
        fields = ['name', 'codename']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'codename': forms.TextInput(attrs={'class': 'form-control'}),
        }