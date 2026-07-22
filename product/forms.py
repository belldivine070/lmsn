from django import forms
from django.forms import inlineformset_factory

from product.models import Product
from .models import Product, Brand, ProductCategory, Supplier, ProductReview, ProductVariant, ProductInventory, Color, Size





class BaseBootstrapForm(forms.ModelForm):
    """Base class to avoid repeating the Bootstrap class loop."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
                field.widget.attrs.update({'class': 'form-check-input'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

class SupplierForm(BaseBootstrapForm):
    class Meta:
        model = Supplier
        fields = ['name', 'mobile', 'email', 'image', 'address', 'website', 'description']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'description': forms.Textarea(attrs={'rows': 2}),
        }

class BrandForm(BaseBootstrapForm):
    class Meta:
        model = Brand
        fields = ['name', 'supplier', 'description', 'image']
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

class ProCatForm(BaseBootstrapForm):
    class Meta:
        model = ProductCategory
        fields = ['name', 'description', 'image', 'is_featured']
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

class ProductForm(BaseBootstrapForm):
    class Meta:
        model = Product
        fields = [
            'name', 'product_type', 'uom', 'category', 'brand', 'supplier',
            'short_description', 'description', 'warranty_text',
            'is_active', 'is_featured', 'is_sales', 'sale_start', 'sale_end',
            'tags', 'meta_title', 'meta_description', 'meta_keywords', 'cost_price', 
            'selling_price', 'old_price', 'discount', 'colors', 'sizes'
        ]
        widgets = {
            'short_description': forms.Textarea(attrs={'rows': 2}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'sale_start': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'sale_end': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'colors': forms.CheckboxSelectMultiple(),
            'sizes': forms.CheckboxSelectMultiple(),
        }

class ProductInventoryForm(BaseBootstrapForm):
    """Used for Simple Products."""
    class Meta:
        model = ProductInventory
        fields = [
            'sku', 'barcode', 'barcode_type', 'quantity', 
            'low_stock_threshold'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FIX: Ensure barcode_type and threshold don't block simple product creation
        self.fields['barcode_type'].initial = 'code128'
        self.fields['low_stock_threshold'].initial = 10
        self.fields['low_stock_threshold'].required = False

class VariantInventoryForm(BaseBootstrapForm):
    """Used for Variable Products. Includes manual fields for the related Inventory."""
    sku = forms.CharField(max_length=100, required=False)
    barcode = forms.CharField(max_length=50, required=False)
    barcode_type = forms.ChoiceField(choices=ProductInventory.BARCODE_TYPES, initial='code128', required=False)
    quantity = forms.IntegerField(min_value=0, initial=0, required=False)
    low_stock_threshold = forms.IntegerField(min_value=0, initial=10, required=False)

    class Meta:
        model = ProductVariant
        fields = ['color', 'size', 'weight', 'price_override', 'is_active'] 
        widgets = {
                'color': forms.Select(attrs={'class': 'form-select'}),
                'size': forms.Select(attrs={'class': 'form-select'}),
                'price_override': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to use base price'}),
                'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            }

    def __init__(self, *args, **kwargs):
        # product = kwargs.pop('product', None)
        super().__init__(*args, **kwargs)
        self.fields['color'].queryset = Color.objects.all()
        self.fields['size'].queryset = Size.objects.all()
        # if product and product.pk:
        #     self.fields['color'].queryset = product.colors.all()
        #     self.fields['size'].queryset = product.sizes.all()
        # else:
        #     self.fields['color'].queryset = Color.objects.all()
        #     self.fields['size'].queryset = Size.objects.all()

        if self.instance.pk and hasattr(self.instance, 'inventory'):
            inv = self.instance.inventory
            self.initial.update({
                'sku': inv.sku,
                'barcode': inv.barcode,
                'barcode_type': inv.barcode_type,
                'quantity': inv.quantity,
                'low_stock_threshold': inv.low_stock_threshold,
            })
            

# --- Formsets ---

InventoryFormSet = inlineformset_factory(
    Product, 
    ProductInventory, 
    form=ProductInventoryForm, 
    extra=1, 
    max_num=1, 
    can_delete=False
)

VariantInventoryFormSet = inlineformset_factory(
    Product, 
    ProductVariant, 
    form=VariantInventoryForm, 
    extra=0,
    can_delete=True
)