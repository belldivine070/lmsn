from django.urls import path, reverse_lazy
from . import views
from django.contrib.auth import views as auth_views

from .views import CustomPasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView


app_name = 'accounts'



urlpatterns = [
    # =========================================================
    # 1. AUTHENTICATION & PUBLIC SIGNUP
    # =========================================================
    path('', views.UserLoginView.as_view(), name='login'),
    path('logout/', views.UserLogoutView.as_view(), name='logout'),
    path('signup/', views.SignupView.as_view(), name='register'),

    path('password-reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    # path('password-reset/done/', PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    # path('password-reset/confirm/<uidb64>/<token>/', PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html', success_url=reverse_lazy('accounts:password_reset_complete')), name='password_reset_confirm'),
    # path('password-reset/complete/', PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),

    # ... other urls ...
    # path('password-reset/', auth_views.PasswordResetView.as_view(template_name='accounts/password_reset.html'), name='password_reset'),
    # path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    # path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'), name='password_reset_confirm'),
    # path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),

    # =========================================================
    # 2. USER MANAGEMENT (Staff/Admin)
    # =========================================================
    # This acts as the main Account List with Search/Filters
    path('users/', views.ManageUsersListView.as_view(), name='manage_users'),
    path('edit/<uuid:pk>/', views.EditSubordinateView.as_view(), name='edit_user'),
    path('detail/<uuid:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('assignments/', views.StaffAssignmentView.as_view(), name='staff_assignment'),

    path('profile/', views.ProfileView.as_view(), name='profile'),

    # =========================================================
    # 2. CUSTOMER MANAGEMENT
    # =========================================================
    # This acts as the main Account List with Search/Filters
    path('manage-customers/', views.ManageCustomersListView.as_view(), name='manage_customers'),
    path('customer/<uuid:pk>/edit/', views.CustomerEditView.as_view(), name='customer_edit'),
    path('customer/<uuid:pk>/delete/', views.CustomerDeleteView.as_view(), name='customer_delete'),

    # =========================================================
    # 3. ROLE MANAGEMENT (Superuser Only)
    # =========================================================
    path('roles/', views.PositionView.as_view(), name='manage_roles'),
    path('roles/add/', views.PositionCreateView.as_view(), name='add_role'),
    path('roles/edit/<int:pk>/', views.PositionUpdateView.as_view(), name='edit_role'),
    path('roles/delete/<int:pk>/', views.PositionDeleteView.as_view(), name='delete_role'),

    path('permissions/', views.PermissionListView.as_view(), name='manage_permissions'),
    path('permissions/add/', views.PermissionCreateView.as_view(), name='add_permission'),
    path('permissions/edit/<int:pk>/', views.PermissionUpdateView.as_view(), name='edit_permission'),
    path('permissions/delete/<int:pk>/', views.PermissionDeleteView.as_view(), name='delete_permission'),

    path('departments/', views.DepartmentListView.as_view(), name='manage_departments'),
    path('departments/add/', views.DepartmentCreateView.as_view(), name='add_department'),  
    path('departments/edit/<int:pk>/', views.DepartmentUpdateView.as_view(), name='edit_department'),
    path('departments/delete/<int:pk>/', views.DepartmentDeleteView.as_view(), name='delete_department'),

]