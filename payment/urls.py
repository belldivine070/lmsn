from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    # --- User Facing Views ---
    # List all payments for the logged-in user
    path("", views.PaymentListView.as_view(), name="index"),
    
    # Detailed view of a specific transaction/receipt
    # Note: Using <int:pk> because Payment usually follows Order's ID type
    path("<int:pk>/", views.PaymentDetailView.as_view(), name="detail"),

    # --- Paystack Transaction Flow ---
    # 1. Initialize the transaction and redirect to Paystack
    path('initiate/<int:pk>/', views.PaystackInitiateView.as_view(), name='initiate'),
    
    # 2. Redirect destination after user pays on Paystack
    path('verify/', views.VerifyPaymentView.as_view(), name='verify'),
    
    # 3. Background listener for Paystack events
    path('webhook/', views.PaystackWebhookView.as_view(), name='webhook'),

    # --- Administrative Actions ---
    path('<int:payment_id>/refund/', views.ProcessRefundView.as_view(), name='process_refund'),
]