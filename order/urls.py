from django.urls import path
from .import views


app_name = 'orders'



urlpatterns = [
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('checkout/<int:pk>/', views.CheckoutView.as_view(), name='checkout_retry'),

    path('orders/', views.AdminOrderListView.as_view(), name='orders_list'),
    path('my-orders/', views.OrderListView.as_view(), name='order_list'),    
    path('delivered&cancelled/', views.DeliveredOrderListView.as_view(), name='delivered_order_list'),

    path("tracking/", views.TrackingListView.as_view(), name="tracking_list"),
    path("tkc/add/", views.TrackingUpdateView.as_view(), name='tracking_create'),    
    path('tkc/<int:pk>/edit/', views.TrackingUpdateView.as_view(), name='tracking_edit'),
    path('tkc/<int:pk>/delete/', views.TrackingDeleteView.as_view(), name='tracking_delete'),


    path('<str:order_number>/', views.OrderDetailView.as_view(), name='order_detail'),
]