from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path('', views.CartDetailView.as_view(), name='cart_detail'),
    path('add/', views.AddToCartView.as_view(), name='add_to_cart'),
    # path('update/<int:item_id>/', views.UpdateCartView.as_view(), name='update_cart'),
    path('remove/<int:item_id>/', views.RemoveFromCartView.as_view(), name='remove_from_cart'),
    path('summary/', views.CartSummaryView.as_view(), name='cart_summary'),

    # cart/urls.py
    path('wishlist/', views.WishlistView.as_view(), name='wishlist'), # GET only
    path('wishlist/add/', views.AddToWishlistView.as_view(), name='add_to_wishlist'), # POST only
    path('wishlist/remove/<int:item_id>/', views.RemoveFromWishlistView.as_view(), name='remove_from_wishlist'),
]

