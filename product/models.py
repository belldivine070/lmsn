import os
import barcode
import qrcode
from io import BytesIO
from django.db import models
from django.conf import settings
from django.core.files import File
from django.utils.text import slugify
from django.db.models import Sum, Avg
from decimal import Decimal
from barcode.writer import ImageWriter
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db.models.signals import post_delete
from core.models import MediaAsset




class Color(models.Model):
    name = models.CharField(max_length=50, unique=True) # e.g., "Midnight Black"
    hex_code = models.CharField(max_length=7, blank=True, help_text="Hex code for UI (e.g. #000000)")

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField(max_length=20, unique=True) # e.g., "XL", "42", "2kg"
    
    def __str__(self):
        return self.name
    

class Supplier(models.Model):
    """Companies or individuals who supply products/brands."""
    name = models.CharField(max_length=255, help_text="Official company name")
    slug = models.SlugField(unique=True, blank=True, max_length=120)
    mobile = models.CharField(unique=True, max_length=20)
    email = models.EmailField(unique=True, help_text="Primary contact email")
    website = models.URLField(blank=True, null=True, help_text="Supplier's website (optional)")
    image = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='suppliers')
    address = models.TextField(help_text="Physical office or warehouse address")
    description = models.TextField(blank=True, help_text="Internal notes about this supplier")
    is_active = models.BooleanField(default=True, help_text="Uncheck this instead of deleting the supplier")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('products:supplier_detail', kwargs={'pk': self.pk})


class Brand(models.Model):
    """Product Brands linked to a specific Supplier."""
    name = models.CharField(max_length=100, unique=True, help_text="Common name of the brand (e.g., Coca-Cola)")
    slug = models.SlugField(unique=True, blank=True, max_length=120)
    supplier = models.ForeignKey('Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='brands',help_text="The primary company providing this brand's products")
    description = models.TextField(blank=True, null=True)
    image = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='brands')
    is_active = models.BooleanField(default=True, help_text="Disable this brand if they stop producing items")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('products:brand_detail', kwargs={'slug': self.slug})

    @property
    def product_count(self):
        """Quickly see how many products are under this brand."""
        return self.products.count() # Assumes your Product model has a ForeignKey to Brand


class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    image = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='product_cat_image')
    is_featured = models.BooleanField(default=False, help_text="Featured categories get highlighted on the storefront")
    is_active = models.BooleanField(default=True, help_text="Hide this category from the storefront")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Product Categories"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def product_count(self):
        return self.products.count()

    def get_absolute_url(self):
        return reverse('lmsn:category_product_list', kwargs={'slug': self.slug})
    

class Product(models.Model):
    PRODUCT_TYPE_CHOICES = [
        ('simple', 'Simple'), 
        ('variable', 'Variable'), 
        ('digital', 'Digital'), 
        ('service', 'Service')
    ]
    UOM_CHOICES = [
        ('pcs', 'Pieces'), 
        ('kg', 'Kilograms'), 
        ('g', 'Grams'), 
        ('ltr', 'Liters'), 
        ('pkt', 'Pack'), 
        ('crt', 'Carton')
    ]

    # --- Relationships ---
    category = models.ForeignKey('ProductCategory', on_delete=models.CASCADE, related_name='products')
    brand = models.ForeignKey('Brand', on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    supplier = models.ForeignKey('Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    # --- Basic Info ---
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, max_length=250)
    uom = models.CharField(max_length=10, choices=UOM_CHOICES, default='pcs')
    short_description = models.TextField()
    description = models.TextField(blank=True)
    warranty_text = models.CharField(max_length=255, blank=True, null=True)

    # --- Pricing (The Hybrid Engine) ---
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    old_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    discount = models.IntegerField(blank=True, null=True, help_text="Enter % to auto-calc price, or leave blank to auto-calc % from prices")

    # --- Media Assets ---
    is_primary = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='primary_products')
    is_secondary = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='secondary_products')
    gallery = models.ManyToManyField(MediaAsset, blank=True, related_name='product_galleries')
    
    # Structural Attributes# MASTER LISTS: What colors/sizes are possible for this item?
    colors = models.ManyToManyField(Color, related_name='products', blank=True)
    sizes = models.ManyToManyField(Size, related_name='products', blank=True)
    
    # --- Status Flags ---
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE_CHOICES, default='simple')
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)    
    is_sales = models.BooleanField(default=False)    

    # --- Promotion Control ---
    sale_start = models.DateTimeField(null=True, blank=True)
    sale_end = models.DateTimeField(null=True, blank=True)

    # --- SEO Metadata ---
    tags = models.CharField(max_length=255, blank=True)
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    meta_keywords = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        
        # --- HYBRID DISCOUNT ENGINE ---
        
        # CASE 1: We have a discount % but NO old_price
        # We assume the current selling_price is the intended SALE price, 
        # and we calculate what the original price was.
        if self.discount and self.discount > 0 and not self.old_price:
            if self.selling_price > 0:
                # Formula: Original = Current / (1 - Discount%)
                # Example: $80 / (1 - 0.20) = $100
                factor = Decimal(1) - (Decimal(self.discount) / Decimal(100))
                self.old_price = self.selling_price / factor

        # CASE 2: We have an old_price and a discount %
        # Standard calculation: update selling_price to match the %
        elif self.old_price and self.discount and self.discount > 0:
            discount_decimal = Decimal(self.discount) / Decimal(100)
            self.selling_price = self.old_price * (Decimal(1) - discount_decimal)

        # CASE 3: No discount entered, but prices suggest one exists
        # Calculate the % for the badge based on price gap
        elif self.old_price and self.selling_price < self.old_price:
            diff = self.old_price - self.selling_price
            self.discount = round((diff / self.old_price) * 100)

        # --- FINAL STATUS CHECKS ---
        if self.old_price and self.selling_price < self.old_price:
            self.is_sales = True
        else:
            self.is_sales = False
            self.discount = 0 # Reset if prices don't reflect a sale

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        # Change 'lmsn:product_detail' to match your actual URL name
        return reverse('lmsn:product_detail', kwargs={'pk': self.id})

    # --- Display Properties ---
    @property
    def average_rating(self):
        avg = self.reviews.aggregate(avg=Avg("rating"))["avg"]
        return round(avg, 1) if avg else 0
    
    @property
    def rating_percentage(self):
        """Used for CSS width of star ratings"""
        return (self.average_rating / 5) * 100

    @property
    def total_stock(self):
        return self.inventory_records.aggregate(total=Sum('quantity'))['total'] or 0

    @property
    def savings_amount(self):
        """Calculates actual currency saved"""
        if self.old_price and self.old_price > self.selling_price:
            return self.old_price - self.selling_price
        return 0

    # @property
    # def price_with_tax(self):
    #     price = self.latest_price
    #     return round(price + (price * (self.tax_percentage / 100)), 2)
    
    
class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    color = models.ForeignKey(Color, on_delete=models.CASCADE, null=True, blank=True)
    size = models.ForeignKey(Size, on_delete=models.CASCADE, null=True, blank=True)  
    # sizes = models.ManyToManyField(Size, related_name='variant_sizes')
    
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, null=True, blank=True)
    price_override = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        unique_together = ('product', 'color', 'size') # Prevent duplicate variants with same color and size

    def __str__(self):
        # size_list = ", ".join([s.name for s in self.sizes.all()]) # this line loops through while using many to many field, which is not ideal for performance. We should consider a different approach if we want to display sizes here. 
        return f"{self.product.name} - {self.color.name} - {self.size.name}" # - (Sizes: {size_list})"



class ProductInventory(models.Model):
    BARCODE_TYPES = [('ean13', 'EAN-13'), ('upc', 'UPC-A'), ('code128', 'Code 128'), ('qr', 'QR Code')]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_records')
    variant = models.OneToOneField(ProductVariant, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory')

    sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
   
    barcode = models.CharField(max_length=50, unique=True, null=True, blank=True)
    barcode_type = models.CharField(max_length=20, choices=BARCODE_TYPES, default='code128')
    barcode_image = models.ImageField(upload_to='barcodes/', blank=True, null=True)

    is_active = models.BooleanField(default=True)

    quantity = models.PositiveIntegerField(default=0, null=True, blank=True)
    low_stock_threshold = models.PositiveIntegerField(default=10)

    date_added = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.barcode and not self.barcode_image:
            self.barcode_image = self.generate_barcode_file(self.barcode, self.barcode_type)
        super().save(*args, **kwargs)

    def generate_barcode_file(self, code, b_type):
        buf = BytesIO()
        if b_type == 'qr':
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(code)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(buf, format='PNG')
        else:
            CODE_CLASS = barcode.get_barcode_class(b_type)
            my_barcode = CODE_CLASS(code, writer=ImageWriter())
            my_barcode.write(buf)
        return File(buf, name=f'bc-{code}.png')

    @property
    def current_status(self):
        if self.quantity <= 0:
            return 'out'
        if self.quantity <= self.low_stock_threshold:
            return 'low'
        return 'in_stock'
    
    class Meta:
        ordering = ['-date_added']


class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user')



# --- Signals for Auto-Inventory ---
@receiver(post_save, sender=Product)
def create_product_inventory(sender, instance, created, **kwargs):
    if created and instance.product_type != 'variable':
        ProductInventory.objects.get_or_create(product=instance, variant=None)

@receiver(post_save, sender=ProductVariant)
def create_variant_inventory(sender, instance, created, **kwargs):
    if created:
        ProductInventory.objects.get_or_create(product=instance.product, variant=instance)

