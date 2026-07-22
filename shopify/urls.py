from django.urls import path
from . import views


app_name = 'lmsn'



urlpatterns = [
    path('', views.Index.as_view(), name='index'),
    path('product/<int:pk>/', views.ProductDetailView.as_view(), name='product_detail'),
    path("quickview/<int:pk>/", views.QuickViewAjax.as_view(), name="quickview"),

    path('category/<slug:slug>/', views.CategoryProductListView.as_view(), name='category_product_list'),

    path("contact-us/", views.Contact.as_view(), name="contact-us"),
    path("about-us/", views.AboutUs.as_view(), name="about-us"),
    path("shop/", views.Shop.as_view(), name="shop"),
    path("privacy-policy/", views.PrivacyPolicy.as_view(), name="privacypolicy"),
    path("terms-of-use/", views.TermsOfUse.as_view(), name="termsofuse"),
    path("faq/", views.FAQView.as_view(), name="faq"),

    path('shop/search/', views.GlobalProductSearchView.as_view(), name='global_search_cbv'),
    path("shop/", views.ShopListView.as_view(), name="shop_list"),

    path("profile/", views.ProfileView.as_view(), name="profile"),

    path('<slug:slug>/', views.PublicPageView.as_view(), name='dynamic_page'),


    # path("subcriber/", views.ExternalSubscribers.as_view(), name="subscriber"),

    path("uregister", views.PublicSignupView.as_view(), name="usersignup"),
]