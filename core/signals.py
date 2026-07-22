import math
import logging
import google.genai as genai
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone

from cart.models import Cart, CartItem
from .models import ChatSession, ComplaintResolution

User = get_user_model()
logger = logging.getLogger(__name__)




# ==============================================================================
# 1. KNOWLEDGE BASE EMBEDDINGS (AI LEARNING SIGNAL)
# ==============================================================================

@receiver(post_save, sender=ComplaintResolution)
def generate_complaint_resolution_embedding(sender, instance, created, **kwargs):
    """
    Automated signal interceptor that hooks into ComplaintResolution updates
    to keep vector coordinates in sync with text modifications.
    """
    # Prevent infinite recursion loops when saving the instance inside its own signal
    if hasattr(instance, '_skip_signal'):
        return

    # Fallback credential resolution paths
    try:
        from core.models import AppVariable
        api_key = AppVariable.get_setting('API_3')
    except Exception:
        api_key = getattr(settings, "GEMINI_API_KEY", "")

    if not api_key:
        logger.error("Skipping vector calculation: Missing valid GEMINI_API_KEY tokens.")
        return

    text_to_embed = instance.complaint_summary.strip()
    if not text_to_embed:
        return
    
    try:
        client = genai.Client(api_key=api_key)
        
        # Hit Gemini's optimized feature embedding engine
        response = client.models.embed_content(
            model="text-embedding-004",
            contents=text_to_embed,
        )
        
        vector_values = response.embeddings[0].values
        
        # Explicitly update the record without triggering the signal again
        instance._skip_signal = True
        instance.embedding = vector_values
        instance.save(update_fields=['embedding'])
        del instance._skip_signal
        
        logger.info(f"Successfully generated {len(vector_values)}-dimension vector coordinates for Resolution ID #{instance.id}")

    except Exception as e:
        logger.error(f"Vector pipeline generation broken for Resolution #{instance.id}: {str(e)}", exc_info=True)


# ==============================================================================
# 2. CHAT HISTORY OWNERSHIP HANDOVER
# ==============================================================================

@receiver(user_logged_in)
def transfer_anonymous_chat_history(sender, request, user, **kwargs):
    """
    Transfers active anonymous guest chat history to the user upon logging in.
    """
    session_key = request.session.session_key
    if session_key:
        # Find any unassigned chat sessions created under this browser session key
        guest_sessions = ChatSession.objects.filter(user__isnull=True, anonymous_session_key=session_key)
        
        if guest_sessions.exists():
            # Transfer ownership and clean up the temporary key reference
            guest_sessions.update(user=user, anonymous_session_key=None)
            logger.info(f"Transferred anonymous chat sessions to logged-in user: {user.email}")


# ==============================================================================
# 3. E-COMMERCE CART MERGING PIPELINE
# ==============================================================================

@receiver(user_logged_in)
def merge_carts(sender, user, request, **kwargs):
    """
    Moves items from an anonymous cart to a user's cart.
    Uses 'anon_cart_id' for a more reliable link than session_key.
    """
    cart_id = request.session.get('anon_cart_id')
    anonymous_cart = None

    if cart_id:
        anonymous_cart = Cart.objects.filter(id=cart_id, user__isnull=True).first()
    
    # Fallback: Try the session key if ID isn't found
    if not anonymous_cart:
        session_key = request.session.session_key
        anonymous_cart = Cart.objects.filter(session_key=session_key, user__isnull=True).first()

    if anonymous_cart:
        user_cart, _ = Cart.objects.get_or_create(user=user)

        for item in anonymous_cart.items.all():
            existing_item = CartItem.objects.filter(
                cart=user_cart, 
                product=item.product, 
                variant=item.variant
            ).first()

            if existing_item:
                existing_item.quantity += item.quantity
                existing_item.save()
                item.delete()
            else:
                item.cart = user_cart
                item.save()

        # Cleanup anonymous cart resource
        anonymous_cart.delete()
        
        if 'anon_cart_id' in request.session:
            del request.session['anon_cart_id']
            request.session.modified = True


# ==============================================================================
# 4. USER SESSION METRICS & USER STATUS TRACKING
# ==============================================================================

@receiver(user_logged_in)
def safe_update_last_login(sender, request, user, **kwargs):
    """Updates user presence metrics seamlessly upon entering the platform."""
    User.objects.filter(pk=user.pk).update(last_login=timezone.now(), is_online=True)


@receiver(user_logged_out)
def handle_user_logout(sender, request, user, **kwargs):
    """Cleans up live presence statuses when a user leaves the application."""
    if user:
        User.objects.filter(pk=user.pk).update(is_online=False)







# def _get_or_create_session(self, request):
#     """Ensures a valid tracking environment is extracted regardless of auth state."""
#     if request.user.is_authenticated:
#         # If logged in, prioritize fetching their newly attached user session profile
#         session, _ = ChatSession.objects.get_or_create(user=request.user, is_active=True)
#         return session
    
#     if not request.session.session_key:
#         request.session.create()
#         request.session.modified = True
    
#     browser_key = request.session.session_key
#     session, _ = ChatSession.objects.get_or_create(anonymous_session_key=browser_key, is_active=True)
#     return session
