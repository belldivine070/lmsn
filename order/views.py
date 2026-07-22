from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, DetailView, View
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import FormView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic.edit import FormMixin
from django.shortcuts import redirect, render, get_object_or_404
from .models import Order, OrderItem, OrderTracking, TrackingStatus
from .forms import OrderCreateForm, TrackingForm, AddTrackingForm
from django.db.models import Q, Q as FilterQ, Count
from django.db import transaction
from cart.models import Cart, CartItem
from django.contrib import messages
from accounts.models import Address





class CheckoutView(LoginRequiredMixin, View):
    template_name = 'lmsn/checkout.html'
    login_url = 'accounts:register' or 'accounts:login'

    def get_cart(self, request):
        # Ensure we get the DB-backed cart for the logged-in user
        return Cart.objects.filter(user=request.user).first()

    def get(self, request, pk=None, *args, **kwargs):
        # --- 1. Restore Order Logic ---
        if pk:
            # Check for existing unpaid order
            order = get_object_or_404(Order, id=pk, user=request.user, is_paid=False)
            cart, _ = Cart.objects.get_or_create(user=request.user)

            try:
                with transaction.atomic():
                    for item in order.order_items.all():
                        # FIX: Logic to handle product access safely
                        product_obj = item.variant.product if item.variant else None
                        
                        if product_obj:
                            cart_item, created = CartItem.objects.get_or_create(
                                cart=cart,
                                product=product_obj,
                                variant=item.variant,
                                defaults={
                                    'quantity': item.quantity,
                                    'price_at_addition': item.price_at_purchase
                                }
                            )
                            if not created:
                                cart_item.quantity += item.quantity
                                cart_item.save()

                    # Important: Delete the old order so we don't have duplicates
                    order.delete()

                     # FORCE CACHE CLEAR
                    request.session['cart_modified'] = True
                    request.session.modified = True

                    messages.info(request, "Items restored to checkout. Please confirm your details.")
                    
                # Redirect to the standard checkout URL (WITHOUT the pk)
                return redirect('orders:checkout')
            except Exception as e:
                messages.error(request, f"Restore failed: {str(e)}")
                return redirect('orders:order_list')

        # --- 2. Standard GET Logic ---
        cart = self.get_cart(request)
        
        # FIX: Check if the cart has items. 
        # If we just redirected from the 'restore' logic, cart.items.exists() must be True.
        if not cart or not cart.items.exists():
            messages.info(request, "Your cart is empty.")
            return redirect('lmsn:index')
        
        # Pre-filling logic
        user_address = Address.objects.filter(user=request.user, is_default=True).first()
        if not user_address:
            user_address = Address.objects.filter(user=request.user).first()
        
        context = {
            'cart': cart,
            'items': cart.items.select_related('product', 'variant', 'variant__size', 'variant__color'),
            'default_name': request.user.full_name,
            'default_email': request.user.email,
            'default_phone': request.user.mobile or '',
            # Prefilling from the separate Address model instance
            'saved_address': user_address.address_line_1 if user_address else '',
            'saved_city': user_address.city if user_address else '',
            'saved_state': user_address.state if user_address else '',
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        cart = self.get_cart(request)
        
        selected_item_ids = request.POST.getlist('selected_items')
        if not selected_item_ids:
            messages.error(request, "Please select at least one item to order.")
            return redirect('orders:checkout')

        items_to_order = cart.items.filter(id__in=selected_item_ids)
        
        order_subtotal = sum(item.quantity * item.price_at_addition for item in items_to_order)
        shipping_fee = 0 
        total_amount = order_subtotal + shipping_fee

        try:
            with transaction.atomic():
                # Construct shipping address
                address = request.POST.get('address', '')
                city = request.POST.get('city', '')
                state = request.POST.get('state', '')
                full_address = f"{address}, {city}, {state}"
                
                order = Order.objects.create(
                    user=request.user,
                    recipient_name=request.POST.get('full_name') or request.user.full_name,
                    recipient_email=request.POST.get('email') or request.user.email,
                    shipping_phone=request.POST.get('phone') or (request.user.mobile or ''),
                    shipping_address=full_address,
                    subtotal=order_subtotal,
                    shipping_fee=shipping_fee,
                    total_amount=total_amount,
                    status='pending',
                    order_notes=request.POST.get('order_notes', '')
                )

                for item in items_to_order:
                    OrderItem.objects.create(
                        order=order,
                        variant=item.variant,
                        product_name_snapshot=item.product.name,
                        price_at_purchase=item.price_at_addition, 
                        quantity=item.quantity
                    )

                # Step 5: CLEAR CART (This makes the cart empty)
                items_to_order.delete()

                # Step 6: ACTIVATE PAYMENT
                # This is the "Pay Now" trigger. It redirects the browser to the payment app.
                # print(f"--- REDIRECTING TO ORDER {order.id} ---") # Add this line to confirm we're hitting this point
                return redirect('payments:initiate', pk=order.id)

        except Exception as e:
            messages.error(request, f"Checkout failed: {str(e)}")
            return redirect('orders:checkout')


class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = "orders/order_list.html"
    context_object_name = "orders"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        """Redirects non-staff customers to their profile order anchor point."""
        if not request.user.is_staff:
            return redirect(reverse('lmsn:profile') + '#orders')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """Fetches, filters, and searches all dashboard orders efficiently."""
        queryset = Order.objects.filter(status__in=['pending', 'processing', 'shipped'], is_paid=True).select_related('user').prefetch_related('order_items').order_by('-created_at')
        
        query = self.request.GET.get('q', '').strip().lower()
        if not query:
            return queryset

        # Base text field search logic
        search_filter = Q(
            Q(user__email__icontains=query) |
            Q(order_number__icontains=query) |
            Q(status__icontains=query) |
            Q(shipping_address__icontains=query)
        )

        # Safeguard boolean checks against raw search text
        if query in ['paid', 'true', 'yes', '1']:
            search_filter |= Q(is_paid=True)
        elif query in ['unpaid', 'false', 'no', '0']:
            search_filter |= Q(is_paid=False)
        elif 'paid' in query:
            search_filter |= Q(is_paid=True)
        elif 'unpaid' in query:
            search_filter |= Q(is_paid=False)

        return queryset.filter(search_filter)

    def get_context_data(self, **kwargs):
        """Injects highly optimized counter statistics into the admin dashboard context."""
        context = super().get_context_data(**kwargs)
        
        # Pull total and breakdown counts in ONE database trip
        stats = Order.objects.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            processing=Count('id', filter=Q(status='processing')),
            shipped=Count('id', filter=Q(status='shipped')),
            delivered=Count('id', filter=Q(status='delivered'))
        )
        
        context.update({
            'total_order': stats['total'],
            'pending_count': stats['pending'],
            'processing_count': stats['processing'],
            'shipped_count': stats['shipped'],
            'delivered_count': stats['delivered'],
            'current_search': self.request.GET.get('q', '').strip()
        })
        return context


class OrderDetailView(LoginRequiredMixin, FormMixin, DetailView):
    """
    Handles both customer viewing and admin status updating.
    Acts as a single source of truth for order detailed management.
    """
    model = Order
    context_object_name = "order"
    form_class = AddTrackingForm
    slug_field = 'order_number'
    slug_url_kwarg = 'order_number'

    def get_template_names(self):
        if self.request.user.is_staff:
            return ["orders/order_details.html"] 
        return ["lmsn/order_detail.html"]       

    def get_queryset(self):
        base_queryset = Order.objects.prefetch_related(
            'order_items', 
            'tracking_history__status_message'
        ).order_by('-id')
        if self.request.user.is_staff:
            return base_queryset
        return base_queryset.filter(user=self.request.user)

    def get_initial(self):
        """Pre-populates the admin status field with the order's current state."""
        initial = super().get_initial()
        initial['order_status'] = self.object.status
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_staff:
            context['form'] = self.get_form()
            
        context['tracking_history'] = self.object.tracking_history.all()
        return context

    def post(self, request, *args, **kwargs):
        """Processes tracking updates if submitted by authorized staff."""
        if not request.user.is_staff:
            return redirect('lmsn:profile')
            
        self.object = self.get_object()
        form = self.get_form()
        
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form):
        """Updates root order pipelines and registers tracking snapshot steps."""
        order = self.object
        order.status = form.cleaned_data['order_status']
        order.save()

        new_log = form.save(commit=False)
        new_log.order = order
        new_log.save()

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('orders:order_detail', kwargs={'order_number': self.object.order_number})



class AdminOrderListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Dedicated view listing all system consumer orders within custom admin panel dashboards."""
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    ordering = ['-created_at']

    def test_func(self):
        return self.request.user.is_staff


class DeliveredOrderListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Dedicated view listing all system consumer orders within custom admin panel dashboards."""
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    ordering = ['-created_at']

    def test_func(self):
        return self.request.user.is_staff

    def get_queryset(self):
        return Order.objects.filter(status__in=['delivered', 'cancelled', 'refunded'], is_paid=True).select_related('user').prefetch_related('order_items').order_by('-created_at')


class TrackingListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """View listing all distinct master tracking status message profiles."""
    model = TrackingStatus
    template_name = 'orders/tracking_list.html'
    context_object_name = 'tracking_info'
    paginate_by = 20

    def test_func(self):
        return self.request.user.is_staff

    def get_queryset(self):
        return TrackingStatus.objects.all().order_by('-id')


class TrackingUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Simple view that edits a template if pk is in URL, otherwise creates a new one."""
    model = TrackingStatus
    form_class = TrackingForm
    template_name = 'orders/tracking_form.html'
    success_url = reverse_lazy('orders:tracking_list')

    def test_func(self):
        return self.request.user.is_staff

    def get_object(self, queryset=None):
        """If 'pk' isn't in the URL path, return None to trigger a new creation."""
        if 'pk' not in self.kwargs:
            return None
        return super().get_object(queryset)

    def form_valid(self, form):
        if self.object:
            messages.success(self.request, "Tracking template updated successfully.")
        else:
            messages.success(self.request, "New tracking milestone created successfully.")
        return super().form_valid(form)


class TrackingDeleteView(LoginRequiredMixin, DeleteView):
    model = TrackingStatus
    success_url = reverse_lazy('orders:tracking_list')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return redirect(self.success_url)