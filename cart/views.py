from django.views import View
from django.http import JsonResponse 
from django.shortcuts import get_object_or_404, render
from cart.models import Cart, CartItem, Wishlist 
from product.models import ProductInventory
from django.contrib.auth.mixins import LoginRequiredMixin
import json
from django.db.models import Prefetch, Q
from django.views.generic import ListView





class AddToCartView(View):
    """Handles adding items via SKU for both Simple and Variable products."""
    
    def post(self, request, *args, **kwargs):
        # 1. Robust Data Capture
        sku = None
        raw_qty = 1

        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                sku = data.get('sku')
                raw_qty = data.get('quantity', 1)
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        else:
            # This handles standard jQuery $.ajax POST data
            sku = request.POST.get('sku')
            raw_qty = request.POST.get('quantity', 1)

        # 2. Safety Parse Quantity
        try:
            qty = int(raw_qty) if raw_qty else 1
        except (ValueError, TypeError):
            qty = 1

        # 3. Final SKU Check
        if not sku:
            return JsonResponse({'success': False, 'error': 'SKU is missing. Please select a variant.'}, status=400)

        # 2. Get Inventory by SKU
        inventory = get_object_or_404(ProductInventory, sku=sku)
        
        # 3. Stock Validation
        if inventory.quantity < qty:
            return JsonResponse({'success': False, 'error': f'Only {inventory.quantity} units available'}, status=400)

        # 4. Get or Create Cart (Unified Logic)
        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
        else:
            if not request.session.session_key:
                request.session.create()
            
            session_key = request.session.session_key
            cart, _ = Cart.objects.get_or_create(session_key=session_key, user__isnull=True)
            
            # Store the Cart ID in the session as a "hard link"
            request.session['anon_cart_id'] = cart.id 
            request.session.modified = True

        # 5. Price Logic (Calculate price before adding)
        price = inventory.product.selling_price
        if inventory.variant and inventory.variant.price_override:
            price = inventory.variant.price_override

        # 6. Add/Update Item
        # We use the 'cart' variable defined in Step 4
        item, created = CartItem.objects.get_or_create(
            cart=cart, 
            product=inventory.product,
            variant=inventory.variant,
            defaults={
                'quantity': qty, 
                'price_at_addition': price
            }
        )
        
        if not created:
            # Check if total requested exceeds stock
            if item.quantity + qty > inventory.quantity:
                return JsonResponse({
                    'success': False, 
                    'error': f'Cannot add more. Max stock is {inventory.quantity}'
                }, status=400)
            item.quantity += qty
            item.save()

        # 7. Prepare raw data for dropdown (Fixed AttributeError)
        cart_items_data = []
        for c_item in cart.items.all():
            img_url = ""
            if c_item.product.is_primary and hasattr(c_item.product.is_primary, 'file'):
                img_url = c_item.product.is_primary.file.url

            cart_items_data.append({
                'id': c_item.id,
                'name': c_item.product.name,
                'qty': c_item.quantity,
                'price': str(c_item.price_at_addition),
                'url': c_item.product.get_absolute_url(),
                'image': img_url
            })

        return JsonResponse({
            'success': True,
            'message': 'Product added to cart',
            'cart_count': cart.item_count,
            'total_price': format(cart.total_price, ".2f"),
            'cart_items': cart_items_data
        })
    

class UpdateCartView(View):
    """Updates quantity directly from the Cart Page."""
    
    def post(self, request, item_id):
        new_qty = int(request.POST.get('quantity', 1))
        item = get_object_or_404(CartItem, id=item_id)
        
        # Ownership check
        is_owner = (request.user.is_authenticated and item.cart.user == request.user) or \
                   (item.cart.session_key == request.session.session_key)
        
        if not is_owner:
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

        if new_qty > 0:
            # Check stock for the specific variant/sku
            inventory = ProductInventory.objects.filter(product=item.product, variant=item.variant).first()
            if inventory and new_qty <= inventory.quantity:
                item.quantity = new_qty
                item.save()
                return JsonResponse({
                    'success': True, 
                    'total': format(item.cart.total_price, ".2f"),
                    'subtotal': format(item.subtotal, ".2f"),
                    'count': item.cart.item_count
                })
            return JsonResponse({'success': False, 'error': 'Stock limit exceeded'}, status=400)
        else:
            item.delete()
            return JsonResponse({'success': True, 'message': 'Removed'})


class RemoveFromCartView(View):
    """Removes item from cart and returns updated totals for the mini-cart badge."""
    
    def post(self, request, item_id):
        item = get_object_or_404(CartItem, id=item_id)
        cart = item.cart
        item.delete()
        return JsonResponse({
            'success': True,
            'total': format(cart.total_price, ".2f"),
            'count': cart.item_count
        })


class CartDetailView(View):
    """Renders the full cart page."""
    
    def get(self, request):
        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
        else:
            if not request.session.session_key:
                request.session.create()
            cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key, user__isnull=True)

        items = cart.items.all().select_related('product', 'variant', 'variant__color', 'variant__size').prefetch_related('product__inventory_records')
        return render(request, 'lmsn/cart.html', {'cart': cart, 'items': items})


class CartSummaryView(View):
    """View to display the full cart page or sidebar data."""
    
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            cart = Cart.objects.filter(user=request.user).first()
        else:
            cart = Cart.objects.filter(session_key=request.session.session_key).first()
            
        # You can return a TemplateResponse or JSON if building a side-drawer
        return JsonResponse({
            'total': cart.total_price if cart else 0,
            'count': cart.item_count if cart else 0,
            'items': list(cart.items.values('variant__sku', 'quantity')) if cart else []
        })



class WishlistView(LoginRequiredMixin, ListView): # Renamed the class to WishlistView
    template_name = "lmsn/wishlist.html"
    context_object_name = "wishlist"

    def get_queryset(self):
        # We use the Model (WishlistModel) to fetch data for the specific user
        return Wishlist.objects.filter(user=self.request.user).order_by('-id')
    

class AddToWishlistView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            product_id = data.get('product_id')
            
            if not product_id:
                return JsonResponse({'status': 'error', 'message': 'Invalid Product ID'}, status=400)

            # Get or create ensures we don't have duplicates
            obj, created = Wishlist.objects.get_or_create(
                user=request.user, 
                product_id=product_id
            )

            # Get updated count for the user
            # This matches the logic in your wish_list context processor
            wishlist_count = Wishlist.objects.filter(user=request.user).count()

            if created:
                return JsonResponse({
                    'status': 'success', 
                    'message': 'Added to wishlist!',
                    'wishlist_count': wishlist_count # Return new count
                })
            else:
                return JsonResponse({
                    'status': 'exists', 
                    'message': 'Already in your wishlist.',
                    'wishlist_count': wishlist_count
                })
        
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class RemoveFromWishlistView(LoginRequiredMixin, View):
    def post(self, request, item_id):
        # Ensure we only delete items belonging to the current user
        item = get_object_or_404(Wishlist, id=item_id, user=request.user)
        item.delete()
        
        # Get the new count to update the UI badge
        new_count = Wishlist.objects.filter(user=request.user).count()
        
        return JsonResponse({
            'success': True,
            'message': 'Item removed from wishlist',
            'wishlist_count': new_count
        })