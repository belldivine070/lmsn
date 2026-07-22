from email import message
from ipaddress import ip_address
from ipaddress import ip_address
import json
import hmac
import hashlib
import requests
import logging

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView, DetailView, RedirectView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.db.models import Sum, Q
from core.models import ActivityLog, AppVariable
from core.views import get_client_ip
from order.models import Order, OrderTracking, TrackingStatus
from .models import Payment, PaymentHistory, Refund


logger = logging.getLogger(__name__)





# --- Shared Logic ---
def process_payment_success(pk, reference, gateway_data, request=None):
    data = gateway_data.get('data', gateway_data)
    payment_channel = data.get('channel', 'card')

    with transaction.atomic():
        # Use select_for_update to lock the row during this transaction
        order = Order.objects.select_for_update().get(id=pk)
        
        payment, created = Payment.objects.get_or_create(
            transaction_reference=reference,
            defaults={
                'order': order,
                'user': order.user,
                'amount': order.total_amount,
                'payment_method': payment_channel,
                'status': 'successful',
                'gateway_response': gateway_data
            }
        )
        
        if created:
            order.is_paid = True
            order.status = 'processing' 
            order.save()

            # 1. Paid / Processing Stage (Your Original Block)
            paid_status, _ = TrackingStatus.objects.get_or_create(
                message="Your payment was successfully processed. We are now preparing your items.",
                defaults={
                    'description': 'Payment verified. Items are being picked from stock shelves, checked, and securely boxed.'
                }
            )
            
            # Record in timeline
            OrderTracking.objects.create(order=order, status_message=paid_status)

            # --- DYNAMIC METADATA EXTRACTION ---
            if request:
                # 1. Active User Browser Track
                user_ip = get_client_ip(request)
                user_agent = request.headers.get('User-Agent', 'unknown')
            else:
                # 2. Automated Webhook Track (Extracting user footprints saved by Paystack)
                user_ip = data.get('ip_address') or '0.0.0.0'
                
                history = data.get('history', [])
                if history and isinstance(history, list):
                    user_agent = history[0].get('user_agent', 'Paystack-Gateway/2.0')
                else:
                    user_agent = 'Paystack-Webhook/2.0'

            #  THE REFINED AND SECURE CODE:
            ActivityLog.objects.create(
                user=order.user,  # Safe and reliable extraction directly from the order
                activity_type='purchase',
                description=f"Order #{order.order_number} confirmed: {order.total_items} items for ₦{order.total_amount}",
                user_agent=user_agent, # Webhook context fallback safe
                ip_address=user_ip # Standard loopback or gateway origin
            )

            # Record in payment history (Only once)
            PaymentHistory.objects.create(
                user=order.user,
                payment=payment,
                product=f"Payment for Order {order.order_number}",
                purchase_status='successful'
            )
            
    return payment


class PaymentListView(LoginRequiredMixin, ListView):
    model = Payment
    context_object_name = "payments"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        # If the user isn't staff, they don't belong here.
        # Send them to their actual Orders list.
        if not request.user.is_staff:
            return redirect('orders:order_list') # Adjust name to your actual orders URL name
        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        # Since dispatch handles users, this will now only ever be for staff
        return ["payments/payment_list.html"]

    def get_queryset(self):
        # Staff only queryset
        queryset = Payment.objects.all().select_related('user', 'order')
        
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(transaction_reference__icontains=query) |
                Q(user__email__icontains=query) |
                Q(order__id__icontains=query)
            )
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Summary Stats for Admin
        context['total_revenue'] = Payment.objects.filter(status='successful').aggregate(Sum('amount'))['amount__sum'] or 0
        context['refunded_total'] = Refund.objects.aggregate(Sum('amount_refunded'))['amount_refunded__sum'] or 0
        return context
    

class PaymentDetailView(LoginRequiredMixin, DetailView):
    """
    A detailed view of a single payment. 
    Useful for generating receipts or for staff to inspect gateway logs.
    """
    model = Payment
    template_name = "payments/payment_detail.html"
    context_object_name = "payment"

    def get_queryset(self):
        # Ensure users can't 'ID-hop' to see other people's payments
        if self.request.user.is_staff:
            return Payment.objects.all()
        return Payment.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Check if a refund exists for this payment to show in the UI
        context['refund'] = Refund.objects.filter(payment=self.object).first()
        return context
    

class PaystackInitiateView(LoginRequiredMixin, RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        order = get_object_or_404(Order, id=kwargs['pk'], user=self.request.user)
        
        url = "https://api.paystack.co/transaction/initialize"

        headers = {
            "Authorization": f"Bearer {AppVariable.get_setting('PAYSTACK_SK')}",
            "Content-Type": "application/json",
        }
        # Note: pk is sent as metadata to be retrieved in webhook/verify
        payload = {
            "email": self.request.user.email,
            "amount": int(order.total_amount * 100), 
            "callback_url": self.request.build_absolute_uri(reverse('payments:verify')),
            "metadata": {"pk": str(order.id)}
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            data = response.json()
            if data.get('status'):
                return data['data']['authorization_url']
        except Exception as e:
            logger.error(f"Paystack Init Error: {e}")
            messages.error(self.request, "Payment gateway is currently unreachable.")
            
            # url = reverse('lmsn:profile') + '#orders'
        # return reverse(url, kwargs={'pk': order.id})
        return reverse('lmsn:profile') + '#orders'


class VerifyPaymentView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        reference = request.GET.get('reference')
        if not reference:
            return redirect('orders:history')

        # Check if already processed by Webhook
        payment = Payment.objects.filter(transaction_reference=reference).first()
        if payment and payment.status == 'successful':
            messages.success(request, "Payment confirmed!")
            return redirect(reverse('orders:order_detail', kwargs={'pk': payment.order.id}))

        # Manual Verify Fallback
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {"Authorization": f"Bearer {AppVariable.get_setting('PAYSTACK_SK')}"}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()

            if data.get('status') and data['data'].get('status') == "success":
                pk = data['data']['metadata'].get('pk')
                process_payment_success(pk, reference, data)
                messages.success(request, "Payment verified successfully.")
                return redirect(reverse('orders:order_detail', kwargs={'pk': pk}))
        except Exception as e:
            logger.error(f"Verification Error: {e}")

        messages.info(request, "Transaction is being processed. Please check back in a moment.")
        url = reverse('lmsn:profile') + '#orders'
        return redirect(url)


@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(View):
    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.headers.get('x-paystack-signature')

        if not sig_header:
            return HttpResponse(status=400)

        # SECURITY: Paystack uses SHA512 for webhooks
        hash_val = hmac.new(
            AppVariable.get_setting('PAYSTACK_SK').encode('utf-8'),
            payload,
            digestmod=hashlib.sha512
        ).hexdigest()

        if hash_val != sig_header:
            logger.warning("Invalid Webhook Signature detected.")
            return HttpResponse(status=400)

        event_data = json.loads(payload)
        if event_data['event'] == 'charge.success':
            data = event_data['data']
            reference = data['reference']
            pk = data['metadata'].get('pk')
            
            try:
                process_payment_success(pk, reference, event_data)
            except Exception as e:
                logger.error(f"Webhook Processing Error: {e}")

        return HttpResponse(status=200)


class ProcessRefundView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Staff-only view to trigger a refund.
    """
    def test_func(self):
        return self.request.user.has_role_perm('can_process_refund')

    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id, status='successful')
        reason = request.POST.get('reason', 'No reason provided')
        
        # 1. Logic to call Paystack Refund API would go here
        # 2. If API success, create Refund record
        with transaction.atomic():
            Refund.objects.create(
                payment=payment,
                reason=reason,
                amount_refunded=payment.amount,
                processed_by=request.user
            )
            payment.status = 'refunded'
            if request.user.is_staff:
                ActivityLog.objects.create(
                    user=request.user, # Use the request directly
                    activity_type='refund', # Make sure this matches your ACTIVITY_TYPES choices
                    description=f"User {request.user.username} successfully initiated a refund for User: {payment.user.username}, Order: #{payment.order.order_number}, Amount: ₦{payment.amount}",
                    ip_address=get_client_ip(request),
                    user_agent=request.headers.get('User-Agent')
                )
            payment.save()
            
            # Update PaymentHistory
            PaymentHistory.objects.filter(payment=payment).update(purchase_status='refunded')

        messages.success(request, "Refund processed successfully.")
        return redirect('payments:detail', pk=payment.id)