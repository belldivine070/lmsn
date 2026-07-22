from django import forms
from .models import Order, TrackingStatus, OrderTracking




class AddTrackingForm(forms.ModelForm):
    # Field to update the parent order status simultaneously
    order_status = forms.ChoiceField(
        choices=Order.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = OrderTracking
        fields = ['status_message']
        widgets = {
            'status_message': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'status_message': 'Select Predefined Status Message',
        }

        
class OrderCreateForm(forms.ModelForm):

    class Meta:
        model = Order
        fields = ['recipient_name', 'recipient_email', 'shipping_phone', 'shipping_address']
        labels = {
            'recipient_name': 'Recipient Full Name',
            'recipient_email': 'Recipient Email (Optional)',
            'shipping_phone': 'Delivery Phone Number',
            'shipping_address': 'Delivery Address'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class TrackingForm(forms.ModelForm):
    class Meta:
        model = TrackingStatus
        fields = ['message', 'description']
        widgets = {
            'message': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Package arrived at local hub'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Internal staff note...'}),
        }