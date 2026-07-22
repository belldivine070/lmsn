from django.db import models
from django.conf import settings
from product.models import Product, ProductVariant  # Ensure both are imported
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.contrib.auth import get_user_model




class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)    
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart: {self.user.email if self.user else 'Guest ' + str(self.session_key)}"

    @transaction.atomic
    def merge_with_user_cart(self, user):
        user_cart, _ = Cart.objects.get_or_create(user=user)
        for item in self.items.all():
            user_item, created = CartItem.objects.get_or_create(
                cart=user_cart, 
                product=item.product, # Added product check
                variant=item.variant,
                defaults={'quantity': item.quantity, 'price_at_addition': item.price_at_addition}
            )
            if not created:
                user_item.quantity += item.quantity
                user_item.save()
        self.delete()

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    # Link directly to Product so Simple Products work
    product = models.ForeignKey(Product, on_delete=models.CASCADE) 
    # Variant remains optional (null=True) for Variable Products
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    
    quantity = models.PositiveIntegerField(default=1)
    price_at_addition = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    added_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Always pull the price from the main product model
        if not self.price_at_addition:
            self.price_at_addition = self.product.selling_price
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return self.price_at_addition * self.quantity

    def clean(self):
        # Validation logic: Check variant stock if it exists, otherwise check product stock
        stock = self.variant.quantity if self.variant else self.product.total_stock
        if self.quantity > stock:
            raise ValidationError(f"Only {stock} units available.")


class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.user.email} -> {self.product.name}"
    


@receiver(user_logged_in)
def merge_carts(sender, user, request, **kwargs):
    # 1. Get the session key
    session_key = request.session.session_key
    if not session_key:
        return

    # 2. Look for an anonymous cart linked to this session
    anonymous_cart = Cart.objects.filter(session_key=session_key, user__isnull=True).first()
    
    if anonymous_cart:
        # 3. Get or create the user's actual cart
        user_cart, _ = Cart.objects.get_or_create(user=user)

        # 4. Move items from anonymous cart to user cart
        anon_items = anonymous_cart.items.all()
        for item in anon_items:
            # Check if this exact product/variant already exists in the user's cart
            existing_item = CartItem.objects.filter(
                cart=user_cart, 
                product=item.product, 
                variant=item.variant
            ).first()

            if existing_item:
                # If it exists, just update the quantity
                existing_item.quantity += item.quantity
                existing_item.save()
                item.delete()
            else:
                # If it doesn't exist, reassign the item to the user's cart
                item.cart = user_cart
                item.save()

        # 5. Delete the now-empty anonymous cart
        anonymous_cart.delete()
