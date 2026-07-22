import uuid
from django.db import models
from django.conf import settings
from product.models import ProductVariant



class TrackingStatus(models.Model):
    """The Library of predefined messages (e.g., 'Package at Airport')"""
    message = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.message

class Order(models.Model):
    STATUS_CHOICES = (
    ('pending', 'Pending'),
    # ('paid', 'Paid'), # We can infer payment status from the 'is_paid' boolean field, so we don't need a separate 'paid' status in the workflow.
    ('processing', 'Processing'),
    ('shipped', 'Shipped'),
    ('in_transit', 'In Transit'),
    ('out_for_delivery', 'Out for Delivery'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
    ('returned', 'Returned'),
    ('refunded', 'Refunded'),
    )
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    
    recipient_name = models.CharField(max_length=100)
    recipient_email = models.EmailField(blank=True)
    shipping_address = models.TextField()
    shipping_phone = models.CharField(max_length=20, blank=True)
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    order_notes = models.TextField(blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Instead of a ForeignKey here, we use a property to get the latest update
    @property
    def current_update(self):
        return self.tracking_history.first()

    @property
    def total_items(self):
        """Calculates total individual quantities across all items in this order"""
        # Sums up the 'quantity' field of all related OrderItems
        return self.order_items.aggregate(models.Sum('quantity'))['quantity__sum'] or 0

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if not self.order_number:
            self.order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        
        super().save(*args, **kwargs)

        if is_new:
            initial_status, created = TrackingStatus.objects.get_or_create(message="Processing your order...")
            OrderTracking.objects.create(order=self, status_message=initial_status)

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='order_items', on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True)
    product_name_snapshot = models.CharField(max_length=255, editable=False)
    price_at_purchase = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    quantity = models.PositiveIntegerField(default=1)

    def save(self, *args, **kwargs):
        if not self.product_name_snapshot:
            self.product_name_snapshot = self.variant.product.name
        else:
            pass  # We keep the snapshot consistent with the variant's product name at the time of saving
        if not self.price_at_purchase:
            self.price_at_purchase = self.variant.price
        super().save(*args, **kwargs)


class OrderTracking(models.Model):
    """The 'Log' that connects an Order to a Status"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='tracking_history')
    status_message = models.ForeignKey(TrackingStatus, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order.order_number} - {self.status_message.message}"