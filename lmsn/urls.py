from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static 
from django.views.static import serve
from django.urls import re_path


urlpatterns = [
    path('admin/', admin.site.urls),    
    path('orders/', include('order.urls')),
    path('login/', include('accounts.urls')),
    path('products/', include('product.urls')),
    path('payments/', include('payment.urls')),
    path('cart/', include('cart.urls')),
    path('core/', include('core.urls')),
    path('', include('shopify.urls')),
    path('summernote/', include('django_summernote.urls')),
    path('paystack/', include(('django_paystack.urls', 'paystack'), namespace='paystack')),
]
if not settings.DEBUG:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
else:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
