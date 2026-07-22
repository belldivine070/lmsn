from django import forms
from django.contrib.auth.forms import UserCreationForm
from accounts.models import CustomUser, Address
from django.forms import inlineformset_factory
from core.models import ExternalSubscriber




class PublicUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        # Django's UserCreationForm handles password fields internally.
        # You only list the NON-password fields here.
        fields = ("first_name", "last_name", "email", "mobile", "username") 

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email
    

class ProfileEdit(forms.ModelForm):

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'mobile']


AddressFormSet = inlineformset_factory(
    CustomUser, 
    Address, 
    fields=['address_line_1', 'city', 'state', 'country'],
    extra=1,  # 🔥 important
    max_num=1,
    can_delete=True
)


class ExternalSubcriberForm(forms.ModelForm):
    class Meta:
        model = ExternalSubscriber
        fields = ['email']

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if ExternalSubscriber.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already subscribed.")
        return email