from django.urls import path
from . import views

app_name = 'products'


urlpatterns = [
    # --- Dashboard & Global Search ---
    path('search/', views.GlobalSearchAjaxView.as_view(), name='global_search_ajax'),

    # --- Supplier Management ---
    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/add/', views.SupplierCreateView.as_view(), name='supplier_create'),
    # Add '/edit/' and '/delete/' suffixes to make them unique
    path('suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.SupplierDeleteView.as_view(), name='supplier_delete'),
    
    # --- Brand Management ---
    path('brands/', views.BrandListView.as_view(), name='brand_list'),
    path('brands/add/', views.BrandCreateView.as_view(), name='brand_create'),
    path('brands/<int:pk>/edit/', views.BrandUpdateView.as_view(), name='brand_edit'),
    path('brands/<int:pk>/delete/', views.BrandDeleteView.as_view(), name='brand_delete'),

    # --- Category Management ---
    path('procat/', views.ProductCategoryListView.as_view(), name='category_list'),
    path('procat/add/', views.ProcatCreateView.as_view(), name='category_create'),
    path('procat/<int:pk>/edit/', views.ProcatUpdateView.as_view(), name='category_update'),
    path('procat/<int:pk>/delete/', views.ProductCategoryDeleteView.as_view(), name='category_delete'),

    # --- Product Management ---
    path('products/', views.ProductListView.as_view(), name='all_products'),
    path('procat/<int:pk>/', views.ProductListView.as_view(), name='product_list_by_category'),
    path('products/add/', views.ProductCreateView.as_view(), name='product_create'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product_update'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),

    # --- Inventory Management ---
    path('inventory/', views.InventoryListView.as_view(), name='inventory'),
    # path('inventory/<int:pk>/', views.InventoryUpdateView.as_view(), name='update_inventory'),
    # path('inventory/ajax/update/', views.quick_stock_update, name='quick_stock_update'),
    path('inventory/update/', views.QuickStockUpdateView.as_view(), name='quick_stock_update'),
]