import uuid
from datetime import datetime, timedelta
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.conf import settings
from django.apps import apps
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.contrib.auth.signals import user_logged_out, user_logged_in
from django.dispatch import receiver



from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver


# =========================
# ROLE PERMISSION MODEL
# =========================
class RolePermission(models.Model):
    name = models.CharField(max_length=100)  # Human readable
    codename = models.CharField(max_length=100, unique=True)  # System key

    def __str__(self):
        return self.name


# =========================
# POSITION / ROLE MODEL
# =========================
class Position(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(RolePermission, blank=True)

    class Meta:
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# =========================
# DEPARTMENT MODEL
# =========================
class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    permissions = models.ManyToManyField(RolePermission, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)

        if not self.contact_email:
            self.contact_email = getattr(settings, 'OFFICIAL_EMAIL', None)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# =========================
# USER MANAGER
# =========================
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)

        if 'position' not in extra_fields:
            PositionModel = apps.get_model('accounts', 'Position')
            position_instance, _ = PositionModel.objects.get_or_create(
                slug='client',
                defaults={'name': 'Client'}
            )
            extra_fields['position'] = position_instance

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        PositionModel = apps.get_model('accounts', 'Position')
        DeptModel = apps.get_model('accounts', 'Department')

        admin_position, _ = PositionModel.objects.get_or_create(
            slug='super_admin',
            defaults={'name': 'Super Admin'}
        )

        admin_dept, _ = DeptModel.objects.get_or_create(
            slug='administration',
            defaults={'name': 'Administration'}
        )

        extra_fields['position'] = admin_position
        extra_fields['department'] = admin_dept

        return self.create_user(email, password, **extra_fields)


# =========================
# USER MODEL
# =========================
class CustomUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    full_name = models.CharField(max_length=60, blank=True, null=True, editable=False)
    mobile = models.CharField(max_length=20, blank=True, null=True)

    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    permission = models.ManyToManyField(RolePermission, blank=True, related_name='users')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    assigned_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_client = models.BooleanField(default=False)
    is_subscribed = models.BooleanField(default=True)
    is_online = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)

    ip_address = models.GenericIPAddressField(blank=True, null=True)
    region = models.CharField(max_length=50, blank=True, null=True)
    image = models.ImageField(upload_to='profile_images/', null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    def save(self, *args, **kwargs):
        # Ensure only one role flag is true
        if self.is_staff and self.is_client:
            self.is_client = False

        if not self.is_staff and not self.is_client:
            self.is_client = True

        self.full_name = f"{self.first_name} {self.last_name}".strip()

        super().save(*args, **kwargs)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def update_online_status(self):
        """Auto turn user offline after inactivity"""
        if self.is_online and self.last_login:
            if timezone.now() > self.last_login + timedelta(minutes=30):
                self.is_online = False
                self.save(update_fields=['is_online'])
        return self.is_online

    def has_role_perm(self, perm_key):
        """
        Checks permission from:
        - Superuser
        - User permissions
        - Position permissions
        - Department permissions
        """
        if self.is_superuser:
            return True

        if self.permissions.filter(codename=perm_key).exists():
            return True
        if self.position and self.position.permissions.filter(codename=perm_key).exists():
            return True
        if self.department and self.department.permissions.filter(codename=perm_key).exists():
            return True
        return False

    def __str__(self):
        return self.email
    
    @property
    def profile_url(self):
        if self.profile_image and hasattr(self.profile_image, 'url'):
            return self.profile_image.url
        return "/static/assets/images/default-user.png" 


# =========================
# ADDRESS MODEL
# =========================
class Address(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="addresses")
    country = models.CharField(max_length=255)
    address_line_1 = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.full_name} - {self.city}"
    
