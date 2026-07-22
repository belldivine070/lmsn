from .models import AppVariable, Category
from product.models import ProductCategory
from cart.models import Cart, Wishlist




def extras(request):
    return {
        'categories': ProductCategory.objects.all()
    }


def wish_list(request):
    wishlist_items = []
    wishlist_count = 0

    if request.user.is_authenticated:
        # Get all wishlist objects for the user
        wishlist_items = Wishlist.objects.filter(user=request.user)
        wishlist_count = wishlist_items.count()
    
    return {
        'wishlist_items': wishlist_items,
        'wishlist_count': wishlist_count
    }



def cart_context(request):
    cart = None
    item_count = 0
    total_price = 0
    
    # 1. Retrieve the cart based on User or Session
    if request.user.is_authenticated:
        # Optimization: prefetch items and select related products/variants for the mini-cart
        cart = Cart.objects.filter(user=request.user).prefetch_related(
            'items__product', 
            'items__variant'
        ).first()
    elif request.session.session_key:
        cart = Cart.objects.filter(
            session_key=request.session.session_key, 
            user__isnull=True
        ).prefetch_related(
            'items__product', 
            'items__variant'
        ).first()
    
    # 2. Calculate values if cart exists
    if cart:
        # Using getattr to safely check for properties or fields
        item_count = getattr(cart, 'item_count', 0)
        total_price = getattr(cart, 'total_price', 0)

    return {
        'global_cart': cart,
        'cart_item_count': item_count,
        'cart_total_price': total_price,
    }


def app_settings_processor(request):
    settings_dict = {}
    try:
        # Fetch only the var_name and var_value columns
        variables = AppVariable.objects.all().values('var_name', 'var_value')
        
        for var in variables:
            # Add the setting directly to the dictionary
            settings_dict[var['var_name']] = var['var_value']
            
        # Optional print statements for debugging (remove in production)
        # print("\n--- APP VARIABLE KEYS LOADED ---")
        # print(settings_dict.keys())
        # print("--------------------------------\n")
            
    except Exception as e:
        print(f"Error loading AppVariables: {e}")
        # Return an empty dictionary if loading fails
        settings_dict = {}

    # CRITICAL FIX: Return the dictionary directly, not nested
    return settings_dict