import uuid
from django.db import models
from django.conf import settings
from order.models import Order



class Payment(models.Model):
    PAYMENT_METHODS = (
        ('card', 'Credit/Debit Card'),
        ('transfer', 'Bank Transfer'),
        ('wallet', 'In-App Wallet'),
        ('cod', 'Cash on Delivery'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('successful', 'Successful'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    transaction_reference = models.CharField(max_length=100, unique=True)
    gateway_response = models.JSONField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.transaction_reference} ({self.status})"


class Refund(models.Model):
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name='refund')
    reason = models.TextField()
    amount_refunded = models.DecimalField(max_digits=12, decimal_places=2)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,)
    status = models.CharField(max_length=20, default='completed')
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE)
    product = models.CharField(max_length=255) # Increased length for safety
    purchase_status = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Payment Histories"