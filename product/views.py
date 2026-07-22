import os
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum, Count, Avg, F, Case, When, Value, IntegerField, Max

from django.http import JsonResponse
from django.template.loader import render_to_string
from httpx import request

from .models import Product, Brand, Supplier, ProductCategory, ProductVariant, ProductInventory
from .forms import SupplierForm, BrandForm, VariantInventoryFormSet, ProductForm, InventoryFormSet, ProductInventoryForm, ProCatForm

from django.views.decorators.http import require_POST



###########################################
# ------ Search Logic ----------
###########################################

class GlobalSearchAjaxView(LoginRequiredMixin, TemplateView):
    template_name = 'products/search.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get('q', '').strip()
        results = {'products': [], 'brands': [], 'suppliers': []}

        if len(query) > 1:
            results['products'] = Product.objects.filter(
                Q(name__icontains=query) | Q(barcode__icontains=query) | Q(sku__icontains=query)
            )[:5]
            results['brands'] = Brand.objects.filter(name__icontains=query)[:3]
            results['suppliers'] = Supplier.objects.filter(name__icontains=query)[:3]
        
        context['results'] = results
        context['query'] = query
        return context


###########################################
# --- Supplier Management ---
###########################################

class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier
    template_name = 'products/supplier/supplier_list.html'
    context_object_name = 'suppliers'

class SupplierBaseView(LoginRequiredMixin):
    model = Supplier
    form_class = SupplierForm
    template_name = 'products/supplier/supplier_form.html'
    success_url = reverse_lazy('products:supplier_list')

    
    # This allows the same view to work for "Create" (no PK)
    def get_object(self, queryset=None):
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def form_valid(self, form):
        # 1. Get the Media ID from the AJAX picker hidden input
        asset_id = self.request.POST.get('library_asset_id')

        try:
            with transaction.atomic():
                self.object = form.save(commit=False)
                
                # 2. Assign the Media Foreign Key
                if asset_id:
                    self.object.image_id = asset_id # Direct ID assignment is faster
                elif asset_id == "": # If user clicked "Remove"
                    self.object.image = None
                
                self.object.save()
                return redirect(self.success_url)
                
        except Exception as e:
            form.add_error(None, f"Database Error: {str(e)}")
            return self.render_to_response(self.get_context_data(form=form))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))
    

class SupplierCreateView(SupplierBaseView, CreateView):
    pass

class SupplierUpdateView(SupplierBaseView, UpdateView):
    pass

class SupplierDeleteView(LoginRequiredMixin, DeleteView):
    model = Supplier
    success_url = reverse_lazy('products:supplier_list')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.error(request, "Supplier deleted.")
        return redirect(self.success_url)

###########################################
# --- Brand Management ---
###########################################

class BrandListView(LoginRequiredMixin, ListView):
    model = Brand
    template_name = 'products/brand/brand_list.html'
    context_object_name = 'brands'

class BrandBaseView(LoginRequiredMixin):
    model = Brand
    form_class = BrandForm
    template_name = 'products/brand/brand_form.html'
    success_url = reverse_lazy('products:brand_list')

    # This allows the same view to work for "Create" (no PK)
    def get_object(self, queryset=None):
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def form_valid(self, form):
        # 1. Get the Media ID from the AJAX picker hidden input
        asset_id = self.request.POST.get('library_asset_id')

        try:
            with transaction.atomic():
                self.object = form.save(commit=False)
                
                # 2. Assign the Media Foreign Key
                if asset_id:
                    self.object.image_id = asset_id # Direct ID assignment is faster
                elif asset_id == "": # If user clicked "Remove"
                    self.object.image = None
                
                self.object.save()
                return redirect(self.success_url)
                
        except Exception as e:
            form.add_error(None, f"Database Error: {str(e)}")
            return self.render_to_response(self.get_context_data(form=form))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

class BrandCreateView(BrandBaseView, CreateView):
    pass

class BrandUpdateView(BrandBaseView, UpdateView):
    pass

class BrandDeleteView(LoginRequiredMixin, DeleteView):
    model = Brand
    success_url = reverse_lazy('products:brand_list')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.error(request, "Brand deleted.")
        return redirect(self.success_url)

###########################################
# ----- Product Category -------------
###########################################

class ProductCategoryListView(LoginRequiredMixin, ListView):
    model = ProductCategory
    template_name = 'products/product_cat_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        queryset = ProductCategory.objects.annotate(total_products=Count('products')).order_by('name')

        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            )
        return queryset.order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get('q', '')
        return context


class ProcatBase(LoginRequiredMixin):
    model = ProductCategory
    form_class = ProCatForm
    template_name = 'products/product_cat_form.html'
    success_url = reverse_lazy('products:category_list')

    # This allows the same view to work for "Create" (no PK)
    def get_object(self, queryset=None):
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def form_valid(self, form):
        # 1. Get the Media ID from the AJAX picker hidden input
        asset_id = self.request.POST.get('library_asset_id')

        try:
            with transaction.atomic():
                self.object = form.save(commit=False)
                
                # 2. Assign the Media Foreign Key
                if asset_id:
                    self.object.image_id = asset_id # Direct ID assignment is faster
                elif asset_id == "": # If user clicked "Remove"
                    self.object.image = None
                
                self.object.save()
                return redirect(self.success_url)
                
        except Exception as e:
            form.add_error(None, f"Database Error: {str(e)}")
            return self.render_to_response(self.get_context_data(form=form))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))
    

class ProcatCreateView(ProcatBase, CreateView):
    def form_valid(self, form):
        messages.success(self.request, "New category created successfully.")
        return super().form_valid(form)

class ProcatUpdateView(ProcatBase, UpdateView):
    def form_valid(self, form):
        messages.info(self.request, f"Category '{self.object.name}' updated.")
        return super().form_valid(form)

class ProductCategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = ProductCategory
    success_url = reverse_lazy('products:category_list')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.error(request, "Category deleted.")
        return redirect(self.success_url)


#######################################################
# --- Product Management ---
#######################################################
class ProductListView(LoginRequiredMixin, ListView):
    model = Product
    template_name = "products/products.html"
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        # 1. ALWAYS initialize self.category to avoid AttributeError in get_context_data
        self.category = None
        
        # 2. Start with an optimized queryset
        # Use select_related for ForeignKeys (category, is_primary)
        # Use prefetch_related for Reverse ForeignKeys (inventory_records)
        queryset = Product.objects.all().select_related('category', 'is_primary').prefetch_related('inventory_records')

        # 3. Filter by Category if the PK is in the URL
        category_pk = self.kwargs.get('pk')
        if category_pk:
            self.category = get_object_or_404(ProductCategory, pk=category_pk)
            queryset = queryset.filter(category=self.category)

        # 4. Handle Search Query
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | 
                Q(inventory_records__sku__icontains=query) | 
                Q(inventory_records__barcode__icontains=query)
            ).distinct()
            
        return queryset.order_by('name')

    def get(self, request, *args, **kwargs):
        # Handle AJAX search requests
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # This calls get_queryset() which now safely sets self.category
            queryset = self.get_queryset()
            data = []
            
            for p in queryset:
                inv = p.inventory_records.first()
                
                # Build JSON response
                data.append({
                    'id': p.id,
                    'name': p.name,
                    'uom': p.get_uom_display(),
                    'sku': inv.sku if inv else "N/A",
                    'barcode': inv.barcode if inv else "No Barcode",
                    # current_status should be a @property on your ProductInventory model
                    'status': inv.current_status if inv else 'out',
                    'quantity': inv.quantity if inv else 0,
                    'image_url': p.is_primary.file.url if p.is_primary else None,
                    'update_url': reverse('products:product_update', args=[p.id]),
                    'delete_url': reverse('products:product_delete', args=[p.id]),
                })
            return JsonResponse({'products': data})
        
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # This will no longer crash because self.category is initialized in get_queryset
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context
  

class ProductBase(LoginRequiredMixin):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('products:all_products')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['inventory_formset'] = InventoryFormSet(self.request.POST, instance=self.object, prefix='inv')
            data['variant_formset'] = VariantInventoryFormSet(self.request.POST, instance=self.object, prefix='var')
        else:
            data['inventory_formset'] = InventoryFormSet(instance=self.object, prefix='inv')
            data['variant_formset'] = VariantInventoryFormSet(instance=self.object, prefix='var')
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        inventory_fs = context['inventory_formset']
        variant_fs = context['variant_formset']
        print(self.request.POST)

        if not (inventory_fs.is_valid() and variant_fs.is_valid()):
            return self.form_invalid(form)

        try:
            with transaction.atomic():
                # 1. Save the Product Core (commit=False)
                self.object = form.save(commit=False)
                self.object.is_primary_id = self.request.POST.get('is_primary_id')
                self.object.is_secondary_id = self.request.POST.get('is_secondary_id')
                self.object.save() 
                
                # --- CRITICAL FIX: SAVE THE MASTER LIST ---
                # This handles the 'colors' and 'sizes' Many-to-Many fields
                form.save_m2m() 
                # ------------------------------------------

                # Re-assign the saved object to formsets
                inventory_fs.instance = self.object
                variant_fs.instance = self.object
                
                # Handle Gallery
                gallery_ids = self.request.POST.getlist('gallery_asset_ids')
                if gallery_ids:
                    self.object.gallery.set([gid for gid in gallery_ids if gid])

                product_type = form.cleaned_data.get('product_type')

                if product_type == 'variable':
                    variant_fs.save() 
                    for v_form in variant_fs:
                        if v_form.cleaned_data and not v_form.cleaned_data.get('DELETE'):
                            variant_instance = v_form.instance
                            variant_instance.color = v_form.cleaned_data.get('color')
                            variant_instance.size = v_form.cleaned_data.get('size')
                            variant_instance.is_active = v_form.cleaned_data.get('is_active', False)
                            variant_instance.save()
                            
                            inv, _ = ProductInventory.objects.get_or_create(
                                product=self.object, 
                                variant=variant_instance
                            )
                            self.apply_inventory_data(inv, v_form.cleaned_data)
                else:
                    # Simple product logic...
                    inv, _ = ProductInventory.objects.get_or_create(
                        product=self.object, 
                        variant=None
                    )
                    if inventory_fs.forms:
                        self.apply_inventory_data(inv, inventory_fs.forms[0].cleaned_data)

                return redirect(self.success_url)

        except Exception as e:
            form.add_error(None, f"Critical Save Error: {str(e)}")
            return self.form_invalid(form)
    
    def apply_inventory_data(self, inventory_instance, data):
        """Helper to map form fields to the inventory model."""
        inventory_instance.sku = data.get('sku')
        inventory_instance.barcode = data.get('barcode')
        inventory_instance.barcode_type = data.get('barcode_type', 'code128')
        inventory_instance.quantity = data.get('quantity', 0)
        # inventory_instance.cost_price = data.get('cost_price', 0)
        # inventory_instance.selling_price = data.get('selling_price', 0)
        inventory_instance.low_stock_threshold = data.get('low_stock_threshold', 10)
        
        # Sales/Promotions logic
        inventory_instance.is_sales = data.get('is_sales', False)
        inventory_instance.old_price = data.get('old_price')
        inventory_instance.sale_start = data.get('sale_start')
        inventory_instance.sale_end = data.get('sale_end')
        
        inventory_instance.save()


class ProductCreateView(ProductBase, CreateView):
    def get(self, request, *args, **kwargs):
        self.object = None
        return super().get(request, *args, **kwargs)

class ProductUpdateView(ProductBase, UpdateView):
    def get_object(self, queryset=None):
        return get_object_or_404(Product, pk=self.kwargs.get('pk'))
    

class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    success_url = reverse_lazy('products:product_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        product_name = self.object.name
        self.object.delete()
        
        # Check if the request is AJAX
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'message': f"Product '{product_name}' was deleted."
            })
            
        return super().post(request, *args, **kwargs)

    # If you still want to support the GET-to-delete shortcut (not recommended but works)
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


#############################################
# ------ Inventory Management ----------
#############################################

# class InventoryView(LoginRequiredMixin, ListView):
#     model = ProductInventory
#     template_name = 'products/inventory.html'
#     context_object_name = 'inventory'
#     paginate_by = 25  # Recommended for large inventories

#     def get_queryset(self):
#         # Optimization: select_related joins tables (Product, Variant) 
#         # prefetch_related handles many-to-many or reverse lookups
#         return ProductInventory.objects.select_related(
#             'product', 
#             'variant', 
#             'product__is_primary' # Fetch primary image so list loads fast
#         ).all().order_by('product__name', 'variant__sku')

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         qs = self.get_queryset()
        
#         # Dashboard Stats for the top of the inventory page
#         context['total_batches'] = qs.count()
#         context['oos_count'] = qs.filter(quantity__lte=0).count()
        
#         # Added: Low Stock Warning (where quantity is less than or equal to threshold)
#         context['low_stock_count'] = qs.filter(
#             quantity__gt=0, 
#             quantity__lte=F('low_stock_threshold')
#         ).count()
        
#         return context


# class InventoryListView(LoginRequiredMixin, ListView):
#     model = ProductInventory
#     template_name = 'products/inventory/inventory.html'
#     context_object_name = 'inventory_items'
#     paginated_by = 25

#     def get_queryset(self):
#         # Prefetch related data to avoid N+1 query issues
#         return ProductInventory.objects.select_related('product', 'variant', 'product__is_primary').all().order_by('product__name','sku', '-id', 'date_added')



class InventoryListView(ListView):
    model = Product
    template_name = 'products/inventory/inventory.html'
    context_object_name = 'products'
    paginate_by = 100

    def get_queryset(self):
        queryset = Product.objects.prefetch_related('inventory_records', 'inventory_records__variant', 'category')
        
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | 
                Q(inventory_records__sku__icontains=query) |
                Q(category__name__icontains=query)
            ).distinct()

        queryset = queryset.annotate(
            is_any_variant_low=Max(
                Case(
                    When(inventory_records__quantity__lte=F('inventory_records__low_stock_threshold'), then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
        )
        return queryset.order_by('-created_at')

    def get(self, request, *args, **kwargs):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            queryset = self.get_queryset()

            data = []
            for product in queryset[:50]:
                image = getattr(product, 'is_primary', None)

                data.append({
                    "id": product.id,
                    "name": product.name or "",
                    "category": product.category.name if product.category else "",
                    "image_url": image.file.url if image else "",
                    "total_stock": getattr(product, 'total_stock', 0),
                    "uom": product.get_uom_display(),
                    "latest_price": str(getattr(product, 'latest_price', 0)),
                    "is_any_variant_low": bool(product.is_any_variant_low),
                    "inventory": [
                        {
                            "id": inv.id,
                            "sku": inv.sku or "NO-SKU",
                            "variant_details": inv.variant.variant_details if inv.variant else "Base",
                            "quantity": inv.quantity,
                            "selling_price": str(inv.selling_price),
                            "low_stock_threshold": inv.low_stock_threshold,
                        } for inv in product.inventory_records.all()
                    ]
                })

            return JsonResponse({'products': data})

        # NORMAL PAGE LOAD → HTML
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        return context


# class InventoryUpdateView(LoginRequiredMixin, UpdateView):
#     model = ProductInventory
#     form_class = ProductInventoryForm
#     template_name = "products/update_inventory.html"
#     success_url = reverse_lazy('products:inventory')

#     def get_form_kwargs(self):
#         """Passes the current product to the form for variant filtering."""
#         kwargs = super().get_form_kwargs()
#         # Ensure 'product' is passed so the form's __init__ can filter variants
#         kwargs['product'] = self.get_object().product
#         return kwargs

#     def form_valid(self, form):
#         """Add a success message after updating stock."""
#         response = super().form_valid(form)
#         messages.success(
#             self.request, 
#             f"Inventory for {self.object.product.name} updated successfully!"
#         )
#         return response


class QuickStockUpdateView(View):
    def post(self, request, *args, **kwargs):
        # Extract data from POST
        inventory_id = request.POST.get('inventory_id')
        quantity = request.POST.get('quantity')
        price = request.POST.get('selling_price')
        threshold = request.POST.get('low_stock_threshold')
        sku = request.POST.get('sku')
        barcode = request.POST.get('barcode')

        # Basic Validation
        if not inventory_id:
            return JsonResponse({'success': False, 'error': 'Missing inventory ID.'}, status=400)

        try:
            # Update the record
            # Note: Ensure the model name matches (ProductInventory vs InventoryRecord)
            inventory = ProductInventory.objects.get(id=inventory_id)
            
            if quantity is not None:
                inventory.quantity = quantity
            if price is not None:
                inventory.selling_price = price
            if threshold is not None:
                inventory.low_stock_threshold = threshold
            
            inventory.sku = sku
            inventory.barcode = barcode
            
            inventory.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Inventory updated successfully.'
            })

        except ProductInventory.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Inventory record not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        
# @require_POST
# def quick_stock_update(request):
#     inventory_id = request.POST.get('inventory_id')
#     quantity = request.POST.get('quantity')
#     price = request.POST.get('selling_price')
#     low_stock_threshold = request.POST.get('low_stock_threshold')

#     try:
#         inventory = ProductInventory.objects.get(id=inventory_id)
#         inventory.quantity = quantity
#         inventory.selling_price = price
#         inventory.low_stock_threshold = low_stock_threshold
#         inventory.sku = request.POST.get('sku')
#         inventory.barcode = request.POST.get('barcode')

#         inventory.save()
#         return JsonResponse({'success': True})
#     except Exception as e:
#         return JsonResponse({'success': False, 'error': str(e)})