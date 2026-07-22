from django.urls import path
from . import views

app_name = 'core'



urlpatterns = [
    # =========================================================
    # 0. AUTH / INDEX / SYSTEM SETTINGS
    # =========================================================
    path("", views.IndexView.as_view(), name="index"),
    path('site/settings/', views.SiteSettingsUpdateView.as_view(), name='site_settings'),

    # =========================================================
    # 1. CATEGORY & CATEGORY POST VIEWS
    # =========================================================
    path('category/lists/', views.CategoryListView.as_view(), name='category_list'),
    path('category/create/', views.CategoryCreateView.as_view(), name='category_create'),
    path('category/update/<slug:slug>/', views.CategoryEditView.as_view(), name='category_update'),
    path('category/delete/<slug:slug>/', views.CategoryDeleteView.as_view(), name='category_delete'),

    # --- Widgets ---
    path('widget/lists/', views.WidgetListView.as_view(), name='widget_list'),
    path('widget/create/', views.WidgetCreateView.as_view(), name='widget_create'),
    path('widget/update/<slug:slug>/', views.WidgetEditView.as_view(), name='widget_update'),
    path('widget/delete/<slug:slug>/', views.WidgetDeleteView.as_view(), name='widget_delete'),

    # =========================================================
    # 2. Pages / PageSection 
    # =========================================================
    path('pages/', views.PageListView.as_view(), name='page_list'),
    path('pages/create/', views.PageCreateView.as_view(), name='page_create'),
    path('pages/<int:pk>/edit/', views.PageUpdateView.as_view(), name='page_update'),
    path('pages/<int:pk>/delete/', views.PageDeleteView.as_view(), name='page_delete'),

    # =========================================================
    # STANDALONE PAGE SECTION MANAGEMENT
    # =========================================================
    path('pages/<int:page_pk>/sections/', views.PageSectionListView.as_view(), name='section_list'),
    path('pages/<int:page_pk>/sections/create/', views.PageSectionCreateView.as_view(), name='section_create'),
    path('sections/<int:pk>/edit/', views.PageSectionUpdateView.as_view(), name='section_update'),
    path('sections/<int:pk>/delete/', views.PageSectionDeleteView.as_view(), name='section_delete'),
    path('ajax/load-posts-checkboxes/', views.load_posts_checkboxes, name='ajax_load_posts_checkboxes'),

    # path('pages/', views.PageListView.as_view(), name='page_list'),
    # path('pages/create/', views.PageCreateView.as_view(), name='page_create'),
    # path('p/<slug:slug>/', views.PageDetailView.as_view(), name='page_detail'),
    # path('pages/<slug:slug>/update/', views.PageUpdateView.as_view(), name='page_update'),
    # path('pages/<slug:slug>/delete/', views.PageDeleteView.as_view(), name='page_delete'),

    # # Section management endpoints 
    # path('pagesection/<slug:page_slug>', views.PageSectionListView.as_view(), name='section_list'),
    # path('pages/<slug:page_slug>/sections/add/', views.PageSectionCreateView.as_view(), name='section_create'),
    # path('sections/<int:pk>/update/', views.PageSectionUpdateView.as_view(), name='section_update'),
    # path('sections/<int:pk>/delete/', views.PageSectionDeleteView.as_view(), name='section_delete'),

    # =========================================================
    # 3. CHILD POSTS (CATEGORY POSTS & WIDGET POSTS)
    # =========================================================

    # --- Category Post CRUD ---
    path('category/<slug:category_slug>/posts/', views.PostListByCategoryView.as_view(), name='post_list_by_category'), 
    path('category/<slug:category_slug>/create/', views.PostCreateView.as_view(), name='post_create'),
    path('category/<slug:category_slug>/edit/<slug:post_slug>/', views.PostEditView.as_view(), name='post_edit'),
    path('category/<slug:category_slug>/delete/<slug:post_slug>/', views.PostDeleteView.as_view(), name='category_post_delete'), 

    # --- Widget Post CRUD ---
    path('widget/<slug:widget_slug>/posts/', views.PostListByWidgetView.as_view(), name='post_list_by_widget'), 
    path('widget/<slug:widget_slug>/create/', views.WidgetPostCreateView.as_view(), name='widget_post_create'),
    path('widget/<slug:widget_slug>/edit/<slug:post_slug>/', views.WidgetPostEditView.as_view(), name='widget_post_edit'),
    path('widget/<slug:widget_slug>/delete/<slug:post_slug>/', views.WidgetPostDeleteView.as_view(), name='widget_post_delete'),

    # =========================================================
    # 3. BROADCAST & SUBSCRIBER HUB
    # =========================================================
    # --- Subscribers ---
    path('subscribers/', views.SubcribersHubView.as_view(), name='subscriber_list'),
    path('subscriber/delete/<int:pk>/', views.SubscriberDeleteView.as_view(), name='delete_subscriber'),
    path('subscribers/download-csv/', views.DownloadCSVTemplateView.as_view(), name='download_subscribers_csv'),
    
    # Subscription Actions
    path('external-subscribe/', views.ExternalSubscribers.as_view(), name='ExternalSub'),

    # --- Broadcast ---
    path('broadcast/dashboard/', views.BroadcastDashboardView.as_view(), name='broadcast_dashboard'),
    path('broadcast/create/', views.BroadcastCreateView.as_view(), name='broadcast_create'),
    path('broadcast/edit/<int:pk>/', views.BroadcastUpdateView.as_view(), name='broadcast_edit'),
    path('broadcast/delete/<int:pk>/', views.BroadcastDeleteView.as_view(), name='broadcast_delete'),

    # =========================================================
    # 4. CONTACT US & SYSTEM LOGS
    # =========================================================
    path("contact-us/", views.ContactUs.as_view(), name="contactus"),
    path('logs/', views.ActivityLogListView.as_view(), name='activity_logs'),
    path('logs/clear/', views.ClearLogsView.as_view(), name='clear_logs'),
    path('security/', views.SecurityAuditView.as_view(), name='security_audit'),

    # =========================================================
    # 5. MEDIA LIBRARY & ASSETS
    # =========================================================
    path('media/', views.MediaLibraryListView.as_view(), name='media_library'),
    path('media/upload/', views.MediaUploadView.as_view(), name='media_upload'),
    path('media/delete/<int:pk>/', views.MediaDeleteView.as_view(), name='media_delete'),
    path('admin/media-explorer/', views.admin_media_explorer, name='admin_media_explorer'),
    # path('media-modal/', views.MediaPopUp.as_view(), name='mediamodal'),
    path('media-picker/', views.MediaPickerView.as_view(), name='media_picker'),

    # --- Media Category ---
    path('media-categories/', views.MediaCategoryListView.as_view(), name='media_categories'),
    path('media-categories/add/', views.MediaCategoryCreateView.as_view(), name='media_category_add'),
    path('media-categories/edit/<int:pk>/', views.MediaCategoryUpdateView.as_view(), name='media_category_edit'),
    path('media-categories/delete/<int:pk>/', views.MediaCategoryDeleteView.as_view(), name='media_category_delete'),

    #======================================================
    #  COMPLAIN / ENQUIRE SYSTEM ROUTS
    #======================================================
    # Customer chat client endpoint
    path('support/chat/', views.LiveChatEngineView.as_view(), name='live_chat'),
    
    path('support-deck/', views.SupportMonitoringDeckView.as_view(), name='support_deck'),
    path('support-deck/data/', views.AdminChatMetricsQueueEndpoint.as_view(), name='queue_endpoint'),
    path('chat-dashboard/reply/<uuid:session_id>/', views.AdminChatActionReplyEndpoint.as_view(), name='action_reply_endpoint'),    
]