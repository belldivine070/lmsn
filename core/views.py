# Standard Library Imports
import csv
import io
import json
import logging
import mimetypes
import os
import re
from datetime import timedelta

# Third-Party Imports
from zoneinfo import ZoneInfo

# Google AI / Google GenAI SDK Import structures
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Django Core
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.core.files.base import ContentFile
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.gis.geoip2 import GeoIP2
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.utils.timezone import is_naive, make_aware, now as timezone_now, now
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Prefetch

# Models
from accounts.models import CustomUser, Position
from product.models import Product

# Forms
from .forms import BroadcastForm, CategoryForm, CSVUploadForm, ContactForm, DynamicCategoryPostForm, DynamicWidgetPostForm, MediaAlbumForm, PageForm, PageSectionForm, SiteSettingsKeyForm, SubcribersForm, UniversalMediaForm, WidgetForm

# Models
from .models import POST_FIELD_CHOICES, ChatSession, ChatMessageImage, ChatMessage, ActivityLog, AppVariable, Category, CategoryPost, ExternalSubscriber, MediaAsset, MediaAlbum, NewsPost, Page, PageSection, SecurityAuditLog, Widget, WidgetPost, ComplaintResolution

# Mixins & Tasks
from .mixins import get_client_ip
from .tasks import send_broadcast_task
from .utils import optimize_chat_image_bytes, get_semantically_matching_resolutions

# Utility functions
from .ai_tools import lookup_product_inventory, manage_customer_order, check_site_knowledge_base, query_order_tracking_pipeline, modify_order_shipping_destination, file_formal_complaint

# Logger Setup
logger = logging.getLogger(__name__)






# =========================================================
# 1. PUBLIC & DASHBOARD VIEWS
# =========================================================

class IndexView(LoginRequiredMixin, TemplateView):
    template_name = 'home.html'


# =========================================================
# PAGE BUILDER VIEWS
# =========================================================
class PageListView(LoginRequiredMixin, ListView):
    model = Page
    template_name = 'pages/page_list.html'
    context_object_name = 'pages'
    ordering = ['-created_at']


class PageBaseView(LoginRequiredMixin):
    """Shared configuration properties for standalone Page operations."""
    model = Page
    form_class = PageForm
    template_name = 'pages/page_form.html'
    success_url = reverse_lazy('core:page_list')


class PageCreateView(PageBaseView, CreateView):
    """Creates a clean standalone Page model instance on its own."""
    pass


class PageUpdateView(PageBaseView, UpdateView):
    """Updates parent page layout rules or metadata independently."""
    pass


class PageDeleteView(LoginRequiredMixin, DeleteView):
    model = Page
    success_url = reverse_lazy('core:page_list')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return redirect(self.success_url)


# # =========================================================
# # STANDALONE PAGE SECTION VIEWS
# # =========================================================
class PageSectionListView(LoginRequiredMixin, ListView):
    model = PageSection
    template_name = 'pages/section_list.html'
    context_object_name = 'sections'

    def get_queryset(self):
        self.page_obj = get_object_or_404(Page, pk=self.kwargs.get('page_pk'))
        return PageSection.objects.filter(page=self.page_obj).select_related('category', 'widget')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page'] = self.page_obj
        return context
    

class PageSectionBaseView(LoginRequiredMixin):
    """Shared structural configuration framework for independent Section records."""
    model = PageSection
    form_class = PageSectionForm
    template_name = 'pages/section_form.html'

    def get_success_url(self):
        return reverse_lazy('core:section_list', kwargs={'page_pk': self.object.page.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if hasattr(self, 'object') and getattr(self, 'object', None):
            context['page'] = self.object.page
        else:
            context['page'] = get_object_or_404(Page, pk=self.kwargs.get('page_pk'))
        return context


class PageSectionCreateView(PageSectionBaseView, CreateView):
    def form_valid(self, form):
        # Explicitly assign parent page to the section instance before committing to DB
        form.instance.page = get_object_or_404(Page, pk=self.kwargs.get('page_pk'))
        return super().form_valid(form)


class PageSectionUpdateView(PageSectionBaseView, UpdateView):
    def form_valid(self, form):
        # Secure safety fallback: ensure the parent link is intact during modifications
        if not hasattr(form.instance, 'page') or not form.instance.page:
            form.instance.page = get_object_or_404(Page, pk=self.kwargs.get('page_pk'))
        return super().form_valid(form)
    

class PageSectionDeleteView(LoginRequiredMixin, DeleteView):
    model = PageSection

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Capture the parent page's ID before deleting the record from the database
        page_pk = self.object.page.pk
        self.object.delete()
        return redirect('core:section_list', page_pk=page_pk)
    

# =========================================================================
# AJAX FORM HELPER ENDPOINT
# =========================================================================
def load_posts_checkboxes(request):
    """
    Called asynchronously when an admin changes the category or widget dropdown 
    in pages/section_form.html. Returns checked HTML list blocks.
    """
    category_id = request.GET.get('category')
    widget_id = request.GET.get('widget')
    choices = []

    if category_id:
        posts = CategoryPost.objects.filter(category_id=category_id, is_published=True)
        choices = [(f"cat_{p.id}", p.title) for p in posts]
    elif widget_id:
        posts = WidgetPost.objects.filter(widget_id=widget_id, is_published=True)
        choices = [(f"wid_{p.id}", p.title) for p in posts]

    html_output = ""
    for value, label in choices:
        html_output += f"""
        <div class="form-check my-2">
            <input type="checkbox" name="visible_posts" value="{value}" class="form-check-input" id="id_visible_posts_{value}" checked>
            <label class="form-check-label text-dark ms-2" for="id_visible_posts_{value}">{label}</label>
        </div>
        """
    
    if not html_output:
        html_output = '<p class="text-muted small my-1">No dynamic entries found under this option selection.</p>'
        
    return HttpResponse(html_output)
    

# =========================================================
# 3. CONTACT & FEEDBACK VIEWS
# =========================================================
class ContactUs(FormView):
    form_class = ContactForm
    template_name = "lmsn/contact-us.html"
    success_url = reverse_lazy("lmsn:contact-us")

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Your message has been sent successfully!")
        return super().form_valid(form)
    
    def form_invalid(self, form):
        print(form.errors) # This will print the errors to your terminal/console
        return super().form_invalid(form)


# =========================================================
# 2. ALBUM / MEDIA LIBRARY & ASSETS
# =========================================================
# --- DYNAMIC MEDIA AJAX ---

class MediaCategoryListView(LoginRequiredMixin, ListView):
    model = MediaAlbum
    template_name ='media/media_cat.html'
    context_object_name = 'albums'
    ordering = ['-id']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['album_form'] = MediaAlbumForm()
        return context


class MediaCategoryCreateView(LoginRequiredMixin, CreateView):
    model = MediaAlbum
    form_class = MediaAlbumForm
    success_url = reverse_lazy('core:media_categories')

    def form_valid(self, form):
        messages.success(self.request, "Album created successfully!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Failed to create album. Check if the name is unique.")
        return redirect('core:media_categories')
    

class MediaCategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = MediaAlbum
    form_class = MediaAlbumForm
    template_name = 'media/media_cat.html'
    success_url = reverse_lazy('core:media_categories')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['albums'] = MediaAlbum.objects.all().order_by('-id')
        context['album_form'] = context['form']
        context['is_edit'] = True
        return context


class MediaCategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = MediaAlbum
    
    def get(self, request, *args, **kwargs):
        # We fetch the object and delete it directly
        self.object = self.get_object()
        success_url = reverse_lazy('core:media_categories')
        
        self.object.delete()
        messages.warning(request, "Album deleted successfully.")
        return HttpResponseRedirect(success_url)

    # We override post just in case a POST request hits this URL
    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


class MediaLibraryListView(LoginRequiredMixin, ListView):
    model = MediaAsset
    template_name = 'media/media_library.html'
    context_object_name = 'assets'
    paginate_by = 10 

    def get_paginate_by(self, queryset):
        return self.request.GET.get('entries', self.paginate_by)
    
    def get_queryset(self):
        qs = MediaAsset.objects.all().order_by('-uploaded_at')
        query = self.request.GET.get('q')
        cat_id = self.request.GET.get('cat')
        
        if query:
            qs = qs.filter(Q(title__icontains=query) | Q(file__icontains=query))
        if cat_id:
            qs = qs.filter(mediacat_id=cat_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['albums'] = MediaAlbum.objects.all() 
        context['base_template'] = 'layout.html'
        context['is_picker'] = False
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('bulk_action')
        asset_ids = request.POST.getlist('asset_ids')

        if not asset_ids:
            messages.warning(request, "No items selected.")
        elif action == 'delete':
            deleted_count, _ = MediaAsset.objects.filter(id__in=asset_ids).delete()
            messages.success(request, f"Successfully deleted {deleted_count} items.")
        return redirect('core:media_library')
    

class MediaPickerView(LoginRequiredMixin, ListView):
    model = MediaAsset
    template_name = 'media/media_modal.html'
    context_object_name = 'assets'
    paginate_by = 30  # Larger grid for the popup

    def get_queryset(self):
        qs = MediaAsset.objects.all().order_by('-uploaded_at')
        query = self.request.GET.get('q')
        cat_id = self.request.GET.get('cat')
        
        if query:
            qs = qs.filter(Q(title__icontains=query) | Q(file__icontains=query))
        if cat_id:
            qs = qs.filter(mediacat_id=cat_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['albums'] = MediaAlbum.objects.all() 
        # Capture picker-specific data from URL
        context['target'] = self.request.GET.get('target', '') # 'primary', 'secondary', 'gallery'
        context['mode'] = self.request.GET.get('mode', 'single') # 'bulk' for gallery
        context['is_picker'] = True
        return context
    

class MediaUploadView(LoginRequiredMixin, FormView):
    """Handles multiple file uploads and logging"""
    template_name = 'media/media_popup.html'
    form_class = UniversalMediaForm
    success_url = reverse_lazy('core:media_library')

    def form_valid(self, form):
        results = form.save_multiple()
        messages.success(self.request, f"Processed: {results['created']} new, {results['replaced']} updated.")
        return super().form_valid(form)


class MediaDeleteView(LoginRequiredMixin, DeleteView):
    model = MediaAsset
    success_url = reverse_lazy('core:media_library')

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        log_description = f"Permanently deleted media asset: {obj.title}"
        
        # LOG THE ACTION
        ActivityLog.objects.create(
            user=request.user, 
            activity_type='delete', 
            description=log_description, 
            ip_address=get_client_ip(request)
        )
        
        messages.warning(request, f"Media '{obj.title}' deleted.")
        return super().post(request, *args, **kwargs)

def admin_media_explorer(request):
    """View for the popup/modal media picker"""
    assets = MediaAsset.objects.all().order_by('-uploaded_at')
    return render(request, 'core/media/upload_media.html', {'assets': assets})


# =========================================================
# 6. SYSTEM LOGS & MONITORING
# =========================================================

class ActivityLogListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = ActivityLog
    template_name = 'activity-logs.html'
    context_object_name = 'logs'
    paginate_by = 50
    ordering = ['-timestamp']

    def test_func(self):
        """Only allow staff/superusers to view logs"""
        return self.request.user.is_staff


class SecurityAuditView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = SecurityAuditLog
    template_name = 'security-audit.html'    
    context_object_name = 'logs'
    paginate_by = 100  # Fixed typo: was 'pagination'
    ordering = ['-timestamp']

    def test_func(self):
        return self.request.user.is_staff


class ClearLogsView(LoginRequiredMixin, View):
    """Allows admins to wipe the logs"""
    def post(self, request):
        count = ActivityLog.objects.count()
        ActivityLog.objects.all().delete()
        
        # Log the clearing of logs (so there is at least one record of who did it)
        ActivityLog.objects.create(
            user=request.user,
            activity_type='delete',
            description=f"Cleared all activity logs ({count} entries removed).",
            ip_address=get_client_ip(request)
        )
        
        messages.success(request, "Activity logs cleared successfully.")
        return redirect('core:activity_logs')
    

# =========================================================
#             1. CATEGORY & CATEGORY POST VIEWS
# =========================================================

class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'categories/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return Category.objects.annotate(post_count=Count('posts')).order_by('title')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Convert the tuple of tuples into a dictionary so get_item can work
        context['POST_FIELD_CHOICES'] = dict(POST_FIELD_CHOICES)
        return context
    
class CategoryBaseView(LoginRequiredMixin):
    model = Category
    form_class = CategoryForm
    template_name = 'categories/category_form.html'
    success_url = reverse_lazy('core:category_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fix: Using 'mediacat' to avoid FieldError
        context['available_media_cats'] = MediaAsset.objects.values_list(
            'mediacat', flat=True
        ).distinct().order_by('mediacat')
        return context
    
    def form_valid(self, form):
        # 1. Capture the ID from the hidden input field (sent by the popup)
        # Ensure the 'name' in HTML matches 'library_asset_id'
        selected_asset_id = self.request.POST.get('library_asset_id')
        
        if selected_asset_id:
            # Assign the ID directly to the Foreign Key field
            # Replace 'media_asset_id' with your actual field name + _id
            form.instance.media_asset_id = selected_asset_id

        # 2. Save the instance
        response = super().form_valid(form)
        
        # 3. Enhanced Logging
        is_update = 'update' if self.object.pk else 'create'
        media_info = f"Asset ID: {selected_asset_id}" if selected_asset_id else "No Asset"
        
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=is_update,
            description=f"{'Updated' if is_update == 'update' else 'Created'} category: {self.object.title} ({media_info})",
            ip_address=get_client_ip(self.request)
        )
        
        messages.success(self.request, f"Category '{self.object.title}' saved successfully.")
        return response


class CategoryCreateView(CategoryBaseView, CreateView):
    pass

class CategoryEditView(CategoryBaseView, UpdateView):
    slug_url_kwarg = 'slug'

class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    slug_url_kwarg = 'slug'
    success_url = reverse_lazy('core:category_list') 

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.success(request, "Category and posts deleted.")
        return redirect(self.success_url)


class PostListByCategoryView(LoginRequiredMixin, ListView):
    model = CategoryPost
    template_name = 'categories/post_list.html'
    context_object_name = 'posts'

    def get_queryset(self):
        self.category = get_object_or_404(Category, slug=self.kwargs['category_slug'])
        return CategoryPost.objects.filter(category=self.category).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context

class CatPostBaseView(LoginRequiredMixin):
    model = CategoryPost
    form_class = DynamicCategoryPostForm
    template_name = 'categories/post_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Fetch and store category once
        self.category = get_object_or_404(Category, slug=self.kwargs['category_slug'])
        kwargs['category_id'] = self.category.id
        return kwargs
        
    def form_valid(self, form):
        # 1. Attach the stored category and author
        form.instance.category = self.category
        form.instance.author = self.request.user

        # 2. MEDIA LIBRARY PICKER FIX:
        # Capture the ID from the hidden 'library_asset_id' input in your HTML
        selected_asset_id = self.request.POST.get('library_asset_id')
        
        if selected_asset_id:
            # Manually link the Foreign Key using the ID from the picker
            form.instance.featured_image_id = selected_asset_id
        elif selected_asset_id == "":
            # Handle clearing the image
            form.instance.featured_image = None

        # 3. Save the main Post instance
        response = super().form_valid(form)
        
        # 4. Handle Multiple Gallery Image Uploads (Legacy File Upload)
        # Note: Replace 'PostImage' with your actual Gallery Model name
        images = self.request.FILES.getlist('gallery_images')
        for f in images:
            # Assuming you have a PostImage model that links to CategoryPost
            # PostImage.objects.create(post=self.object, image=f)
            pass
            
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context
    
    def get_success_url(self):
        # FIX: Changed namespace from 'users' to 'core' based on your previous logs
        # If your namespace is actually 'accounts', use that instead.
        return reverse('core:post_list_by_category', kwargs={'category_slug': self.kwargs['category_slug']})
    

class PostCreateView(CatPostBaseView, CreateView):
    pass

class PostEditView(CatPostBaseView, UpdateView):
    slug_url_kwarg = 'post_slug'
    

class PostDeleteView(LoginRequiredMixin, DeleteView):
    model = CategoryPost
    slug_url_kwarg = 'post_slug'
    success_url = reverse_lazy('core:post_list_by_category')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        slug = self.kwargs['category_slug']
        self.object.delete()
        return redirect(reverse('core:post_list_by_category', kwargs={'category_slug': slug}))
    
    def get_success_url(self):
        return reverse('core:post_list_by_category', kwargs={'category_slug': self.kwargs['category_slug']})
    

# =========================================================
#             2. WIDGET & WIDGET POST VIEWS
# =========================================================

class WidgetListView(LoginRequiredMixin, ListView):
    model = Widget
    template_name = 'widgets/widget_list.html'
    context_object_name = 'widgets'

    def get_queryset(self):
        return Widget.objects.annotate(post_count=Count('widget_posts')).order_by('title')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['POST_FIELD_CHOICES'] = dict(POST_FIELD_CHOICES)
        return super().get_context_data(**kwargs)

class WidgetBaseView(LoginRequiredMixin):
    model = Widget
    form_class = WidgetForm
    template_name = 'widgets/widget_form.html'
    success_url = reverse_lazy('core:widget_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['available_media_cats'] = MediaAsset.objects.values_list(
            'mediacat', flat=True
        ).distinct().order_by('mediacat')
        return context
    
    def form_valid(self, form):
        selected_asset_id = self.request.POST.get('library_asset_id')
        
        if selected_asset_id:
            form.instance.media_asset_id = selected_asset_id

        response = super().form_valid(form)
        
        # 3. Enhanced Logging
        is_update = 'update' if self.object.pk else 'create'
        media_info = f"Asset ID: {selected_asset_id}" if selected_asset_id else "No Asset"
        
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=is_update,
            description=f"{'Updated' if is_update == 'update' else 'Created'} widget: {self.object.title} ({media_info})",
            ip_address=get_client_ip(self.request)
        )
        
        messages.success(self.request, f"Widget '{self.object.title}' saved successfully.")
        return response


class WidgetCreateView(WidgetBaseView, CreateView):
    pass

class WidgetEditView(WidgetBaseView, UpdateView):
    slug_url_kwarg = 'slug'

class WidgetDeleteView(LoginRequiredMixin, DeleteView):
    model = Widget
    slug_url_kwarg = 'slug'
    success_url = reverse_lazy('core:widget_list')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return redirect(self.success_url)

class PostListByWidgetView(LoginRequiredMixin, ListView):
    model = WidgetPost
    template_name = 'widgets/wid_post_list.html'
    context_object_name = 'posts'

    def get_queryset(self):
        self.widget = get_object_or_404(Widget, slug=self.kwargs['widget_slug'])
        return WidgetPost.objects.filter(widget=self.widget).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['widget'] = self.widget
        return context


class WidPostBaseView(LoginRequiredMixin):
    model = WidgetPost
    form_class = DynamicWidgetPostForm
    template_name = 'widgets/wid_postcreate.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Fetch and store category once
        self.widget = get_object_or_404(Widget, slug=self.kwargs['widget_slug'])
        kwargs['widget_id'] = self.widget.id
        return kwargs
        
    def form_valid(self, form):
        # 1. Attach the stored category and author
        form.instance.widget = self.widget
        form.instance.author = self.request.user

        # 2. MEDIA LIBRARY PICKER FIX:
        selected_asset_id = self.request.POST.get('library_asset_id')
        
        if selected_asset_id:
            # Manually link the Foreign Key using the ID from the picker
            form.instance.featured_image_id = selected_asset_id
        elif selected_asset_id == "":
            # Handle clearing the image
            form.instance.featured_image = None

        # 3. Save the main Post instance
        response = super().form_valid(form)
        
        # 4. Handle Multiple Gallery Image Uploads (Legacy File Upload)
        # Note: Replace 'PostImage' with your actual Gallery Model name
        images = self.request.FILES.getlist('gallery_images')
        for f in images:
            # Assuming you have a PostImage model that links to CategoryPost
            # PostImage.objects.create(post=self.object, image=f)
            pass
            
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['widget'] = self.widget
        return context
    
    def get_success_url(self):
        return reverse('core:post_list_by_widget', kwargs={'widget_slug': self.kwargs['widget_slug']})
    

class WidgetPostCreateView(WidPostBaseView, CreateView):
    pass

class WidgetPostEditView(WidPostBaseView, UpdateView):
    slug_url_kwarg = 'post_slug'

class WidgetPostDeleteView(LoginRequiredMixin, DeleteView):
    model = WidgetPost
    slug_url_kwarg = 'post_slug'

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        widget_slug = self.object.widget.slug
        self.object.delete()
        return redirect('core:post_list_by_widget', widget_slug=widget_slug)


# =========================================================
# 4. BROADCAST & SUBSCRIBER HUB
# =========================================================

class SubcribersHubView(LoginRequiredMixin, FormView):
    template_name = 'subscribers_list.html'
    form_class = SubcribersForm
    success_url = reverse_lazy('core:subscriber_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['subscribers'] = ExternalSubscriber.objects.all().order_by('-id')
        context['bulk_form'] = CSVUploadForm()
        return context

    def post(self, request, *args, **kwargs):
        if 'csv_file' in request.FILES:
            return self.handle_bulk_upload(request)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        subscriber = form.save(commit=False)
        subscriber.ip_address = get_client_ip(self.request)
        subscriber.save()
        messages.success(self.request, "Subscriber added successfully!")
        return redirect(self.success_url)

    def handle_bulk_upload(self, request):
        bulk_form = CSVUploadForm(request.POST, request.FILES)
        if bulk_form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                data_set = csv_file.read().decode('UTF-8')
                io_string = io.StringIO(data_set)
                reader = csv.reader(io_string, delimiter=',', quotechar="|")
                next(reader) 
                created_count = 0
                for row in reader:
                    if not row: continue
                    email = row[0].strip()
                    if email and not ExternalSubscriber.objects.filter(email=email).exists():
                        ExternalSubscriber.objects.create(email=email, ip_address=get_client_ip(request))
                        created_count += 1
                messages.success(request, f"Imported {created_count} new subscribers.")
            except Exception as e:
                messages.error(request, f"Error processing file: {e}")
        return redirect(self.success_url)
    

class SubscriberDeleteView(LoginRequiredMixin, DeleteView):
    model = ExternalSubscriber
    success_url = reverse_lazy('core:subscriber_list')
    
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        messages.warning(request, "Subscriber removed.")
        return super().delete(request, *args, **kwargs)
    

class ExternalSubscribers(FormView):
    """
    A single, robust view for all subscription forms.
    Handles duplicates, tracks client IPs via custom get_client_ip utility,
    and runs Django GeoIP2 lookups.
    """
    form_class = SubcribersForm

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', '/')

    def form_valid(self, form):
        email = form.cleaned_data.get("email")

        # 1. DUPLICATE PREVENTION
        if ExternalSubscriber.objects.filter(email=email).exists():
            messages.warning(self.request, "This email is already subscribed.")
            return HttpResponseRedirect(self.get_success_url())
            
        # 2. RUN YOUR CUSTOM IP UTILITY
        ip = get_client_ip(self.request)

        # Set default values for geolocation variables
        city = 'Unknown'
        country = 'Unknown'
        region = 'Unknown'

        # 3. NATIVE DJANGO GEOIP2 LOOKUP
        lookup_ip = ip
        if ip in ['127.0.0.1', '::1', None, ''] and settings.DEBUG:
            lookup_ip = '102.89.1.1'  # Safe fallback for local testing

        # Only run GeoIP lookup if we actually extracted a valid string
        if lookup_ip:
            try:
                g = GeoIP2()
                location_data = g.city(lookup_ip)
                
                city = location_data.get('city') or 'Unknown'
                country = location_data.get('country_name') or 'Unknown'
                region = location_data.get('region') or 'Unknown'
            except Exception as e:
                logger.error(f"Django GeoIP2 lookup exception encountered for IP {lookup_ip}: {str(e)}")

        # 4. SAVE ENHANCED SUBSCRIBER MODEL
        subscriber = form.save(commit=False)
        subscriber.ip_address = ip or 'Unknown'
        subscriber.city = city
        subscriber.region = region
        subscriber.country = country
        subscriber.save()

        # 5. SUCCESS FEEDBACK & DYNAMIC REDIRECT
        messages.success(self.request, "Thank you for subscribing!")
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Please provide a valid email address.")
        return HttpResponseRedirect(self.get_success_url())
    
# =========================================================
# 5. BROADCAST CREATION & MANAGEMENT
# =========================================================

class BroadcastDashboardView(LoginRequiredMixin, ListView):
    model = NewsPost
    template_name = 'broadcast_dashboard.html'
    context_object_name = 'broadcasts'
    ordering = ['-created_at']




class BroadcastMixin(LoginRequiredMixin):
    """
    Shared orchestration logic for live audience filtering, clone actions,
    validation hooks, and recipient extraction.
    """
    model = NewsPost
    form_class = BroadcastForm
    template_name = 'send_email.html'
    success_url = reverse_lazy('core:broadcast_dashboard')

    def get(self, request, *args, **kwargs):
        """
        Safely isolates AJAX operations (live dropdown lookups and historical template cloning) 
        from core worker connection bottlenecks.
        """
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            
            # --- 1. CLONE / REUSE SYSTEM ACTION ---
            clone_id = request.GET.get('clone_id')
            if clone_id:
                try:
                    past_post = NewsPost.objects.get(pk=clone_id)
                    return JsonResponse({
                        'success': True,
                        'title': past_post.title,
                        'subject': past_post.subject,
                        'content': past_post.content,
                        'target_audience': past_post.target_audience,
                    })
                except NewsPost.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Mailing template not found.'}, status=404)

            # --- 2. DYNAMIC LIVE AUDIENCE FILTERS ---
            audience = request.GET.get('audience')
            emails = set()
            
            filters = {
                'is_manager': {'is_manager': True},
                'super_admin': {'is_superuser': True},
                'staffs': {'is_staff': True},
                'clients': {'is_client': True},
            }
            
            try:
                if audience == 'all':
                    emails.update(CustomUser.objects.filter(is_active=True).values_list('email', flat=True))
                    emails.update(ExternalSubscriber.objects.values_list('email', flat=True))
                    
                elif audience == 'department':
                    dept_id = request.GET.get('department_id')
                    if dept_id:
                        emails.update(CustomUser.objects.filter(department_id=dept_id, is_active=True).values_list('email', flat=True))
                        
                elif audience == 'individual':
                    ind_email = request.GET.get('individual_email')
                    if ind_email:
                        emails.add(ind_email.strip())
                
                elif audience == 'is_staff':
                    emails.update(CustomUser.objects.filter(is_staff=True, is_active=True).values_list('email', flat=True))
                        
                elif audience == 'external_only':
                    emails.update(ExternalSubscriber.objects.values_list('email', flat=True))
                    
                elif audience in filters:
                    emails.update(CustomUser.objects.filter(**filters[audience], is_active=True).values_list('email', flat=True))
                
                clean_emails = sorted(list({e for e in emails if e}))
                return JsonResponse({'emails': clean_emails})
                
            except Exception as e:
                return JsonResponse({'emails': [], 'error': str(e)}, status=400)
                
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recent_posts'] = NewsPost.objects.all().order_by('-created_at')[:10]
        return context

    def post(self, request, *args, **kwargs):
        """
        Intercepts execution to validate unique title slugs without database crashes.
        """
        if isinstance(self, UpdateView):
            self.object = self.get_object()
        else:
            self.object = None 
        
        form = self.get_form()
        title = request.POST.get('title', '')
        derived_slug = slugify(title)

        slug_query = NewsPost.objects.filter(slug=derived_slug)
        if self.object:
            slug_query = slug_query.exclude(pk=self.object.pk)

        if derived_slug and slug_query.exists():
            form.add_error('title', "A broadcast with this precise title already exists. Please modify your title slightly to keep it unique.")
            return self.form_invalid(form)

        return super().post(request, *args, **kwargs)


class BroadcastCreateView(BroadcastMixin, CreateView):
    """Handles creating a new broadcast and saving it as an initial draft."""
    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.status = 'draft'

        audience = form.cleaned_data.get('target_audience')
        individual_target = form.cleaned_data.get('target_individual_email')
        department_target = form.cleaned_data.get('target_department_select')
        recipient_list = self.request.POST.getlist('final_recipients')

        if not recipient_list:
            emails_set = set()
            if audience == 'individual' and individual_target:
                emails_set.add(individual_target)
            elif audience == 'department' and department_target:
                emails_set.update(CustomUser.objects.filter(department_id=department_target, is_active=True).values_list('email', flat=True))
            else:
                emails_set.update(self.object.gather_emails())
            
            recipient_list = list({e for e in emails_set if e})

        if not recipient_list:
            messages.error(self.request, "Aborted: Could not extract any valid target recipient destination accounts.")
            return redirect(self.success_url)

        self.object.target_emails = recipient_list
        self.object.save()

        messages.success(self.request, f"📢 Campaign draft saved successfully with {len(recipient_list)} target subscribers!")
        return redirect(self.success_url)


class BroadcastUpdateView(BroadcastMixin, UpdateView):
    """Handles updating a draft broadcast and processes either 'Save Draft' or 'Broadcast Now'."""
    def form_valid(self, form):
        campaign = form.save(commit=False)
        
        recipient_list = self.request.POST.getlist('final_recipients')
        if not recipient_list:
            recipient_list = campaign.target_emails

        campaign.target_emails = recipient_list

        # --- PIPELINE 1: ADMIN CLICKED "BROADCAST NOW" ---
        if 'action_broadcast' in self.request.POST:
            if not recipient_list:
                messages.error(self.request, "Aborted: Cannot execute a live broadcast with zero target users.")
                return self.form_invalid(form)

            user_tz = ZoneInfo(self.request.POST.get('user_timezone', 'UTC'))
            scheduled_time = campaign.scheduled_time

            if scheduled_time:
                if is_naive(scheduled_time):
                    scheduled_time = make_aware(scheduled_time, user_tz)
                scheduled_time_utc = scheduled_time.astimezone(ZoneInfo('UTC'))
            else:
                scheduled_time_utc = None

            # Fall back to AppVariable official email context if sender_email fields are empty
            resolved_sender = campaign.sender_email or AppVariable.get_setting('official_email', 'noreply@bgtech.com')
            target_status = 'scheduled' if (scheduled_time_utc and scheduled_time_utc > timezone_now()) else 'sending'

            try:
                # Local import to prevent circular dependency structures
                from .tasks import send_broadcast_task 

                if target_status == 'scheduled':
                    send_broadcast_task.apply_async(
                        kwargs={'post_id': campaign.id, 'recipient_list': recipient_list, 'from_email': resolved_sender},
                        eta=scheduled_time_utc
                    )
                    messages.success(self.request, f"📅 Broadcast successfully scheduled for {scheduled_time.strftime('%Y-%m-%d %H:%M')}")
                else:
                    send_broadcast_task.delay(
                        post_id=campaign.id,
                        recipient_list=recipient_list,
                        from_email=resolved_sender
                    )
                    messages.success(self.request, "🚀 Dispatch sequence engaged! Outbound transmission running in background.")
                
                campaign.status = target_status
                campaign.save()

            except Exception as broker_error:
                messages.error(
                    self.request, 
                    f"⚠️ Connection Error: Draft parameters updated locally, but dispatch failed because the Celery task broker is unreachable. Detail: {str(broker_error)}"
                )
                campaign.status = 'draft'
                campaign.save()

        # --- PIPELINE 2: ADMIN CLICKED "SAVE DRAFT" (Default) ---
        else:
            campaign.status = 'draft'
            campaign.save()
            messages.info(self.request, "💾 Campaign draft parameters updated successfully.")

        return redirect(self.success_url)


class BroadcastDeleteView(LoginRequiredMixin, DeleteView):
    model = NewsPost
    success_url = reverse_lazy('core:broadcast_dashboard')
    
    def get(self, request, *args, **kwargs): 
        return self.post(request, *args, **kwargs)
    

class DownloadCSVTemplateView(LoginRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="all_subscribers.csv"'
        writer = csv.writer(response)
        writer.writerow(['Email', 'Date Subscribed', 'IP Address', 'Region'])
        subscribers = ExternalSubscriber.objects.all().values_list('email', 'date_subscribed', 'ip_address', 'region')
        for sub in subscribers: 
            writer.writerow(sub)
        return response


class SubscriberDeleteView(LoginRequiredMixin, DeleteView):
    model = ExternalSubscriber
    success_url = reverse_lazy('core:subscriber_list')
    def get(self, request, *args, **kwargs): 
        return self.post(request, *args, **kwargs)
        
        
# =========================================================
# 6. SITE SETTINGS & CONFIGURATION
# =========================================================

class SiteSettingsUpdateView(UserPassesTestMixin, FormView):
    form_class = SiteSettingsKeyForm
    template_name = 'settings/site_settings.html' 
    success_url = reverse_lazy('core:site_settings') 
    
    def test_func(self): return self.request.user.is_superuser
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        combined = []
        for setting in context['form'].settings:
            combined.append({
                'value_field': context['form'][setting.var_name],
                'description_field': context['form'][f'desc_{setting.var_name}'],
                'var_name': setting.var_name,
                'label': context['form'][setting.var_name].label
            })
        context['combined_settings_list'] = combined
        return context
        
    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Settings updated.")
        return super().form_valid(form)


import logging
import mimetypes
import os
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.utils.timezone import now as timezone_now
from django.views import View
from django.views.decorators.csrf import csrf_protect

# Google GenAI SDK imports
from google import genai
from google.genai import types
from google.genai.errors import ServerError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Presumed project imports
# from core.models import ChatSession, ChatMessage, ChatMessageImage, AppVariable
# from core.utils import get_semantically_matching_resolutions, lookup_product_inventory, ...

logger = logging.getLogger(__name__)

@method_decorator(csrf_protect, name='dispatch')
class LiveChatEngineView(View):
    """
    Asynchronous architecture driving both customer and admin support chat boxes.
    Features: Semantic RAG retrieval, image scaling, and session recovery tools.
    """

    def _get_or_create_session(self, request):
        """Ensures a valid tracking environment is extracted regardless of auth state."""
        if not request.session.session_key:
            request.session.create()
            request.session.modified = True
        browser_key = request.session.session_key

        if request.user.is_authenticated:
            user_session, _ = ChatSession.objects.get_or_create(
                user=request.user, 
                defaults={'is_active': True, 'is_ai_active': True}
            )
            if not user_session.is_active:
                user_session.is_active = True
                user_session.save(update_fields=['is_active'])

            # Transition anonymous guest threads cleanly to verified profiles atomically
            guest_tracking_key = request.session.get('pre_login_guest_key', browser_key)
            anonymous_session = ChatSession.objects.filter(
                anonymous_session_key=guest_tracking_key, 
                user__isnull=True, 
                is_active=True
            ).first()
            
            if anonymous_session:
                with transaction.atomic():
                    # Batch migrate relationships efficiently
                    anonymous_session.messages.update(session=user_session)
                    user_session.messages.filter(sender_name="Guest Visitor").update(sender_name=request.user.email)
                    anonymous_session.delete()

                if 'pre_login_guest_key' in request.session:
                    del request.session['pre_login_guest_key']
                    request.session.modified = True
                
            return user_session
        
        guest_session, created = ChatSession.objects.get_or_create(
            anonymous_session_key=browser_key, 
            user__isnull=True,
            defaults={'is_active': True, 'is_ai_active': True}
        )
        
        if not created and not guest_session.is_active:
            request.session.create()
            request.session.modified = True
            new_browser_key = request.session.session_key
            
            guest_session = ChatSession.objects.create(
                anonymous_session_key=new_browser_key,
                user=None, is_active=True, is_ai_active=True
            )
            browser_key = new_browser_key

        if request.session.get('pre_login_guest_key') != browser_key:
            request.session['pre_login_guest_key'] = browser_key
            request.session.modified = True

        return guest_session

    def _check_session_expiry(self, session):
        """Flags old unauthenticated conversations inactive after a 6-hour period."""
        if session.user is not None:
            return False
        last_msg = session.messages.order_by('-timestamp').first()
        if last_msg and (timezone_now() - last_msg.timestamp > timedelta(hours=6)):
            session.is_active = False  
            session.is_ai_active = False
            session.save(update_fields=['is_active', 'is_ai_active'])
            return True 
        return False

    def _verify_and_restore_ai_control(self, session):
        """Automatically re-engages AI controls if no human supervisor message occurred in 1 hour."""
        last_msg = session.messages.order_by('-timestamp').first()
        if last_msg and last_msg.is_from_admin and (last_msg.sender_name != "AI Assistant"):
            if timezone_now() - last_msg.timestamp > timedelta(hours=1):
                session.is_ai_active = True
                session.save(update_fields=['is_ai_active'])

    def _generate_ai_response(self, session, user_text, current_msg_id, attached_images_records=None):
        """Dispatches continuous text/image metrics directly through the Gemini API Client."""
        text = user_text.lower().strip() if user_text else ""
        explicit_agent_request = any(word in text for word in ['agent', 'operator', 'talk to someone', 'human staff'])
        
        if explicit_agent_request:
            session.is_ai_active = False
            session.save(update_fields=['is_ai_active'])
            return "🔄 Handing you over to a human assistant immediately. Please hold on...", None

        try:
            try:
                GEMINI_API_KEY = AppVariable.get_setting('API_3')
            except Exception:
                GEMINI_API_KEY = getattr(settings, "GEMINI_API_KEY", "")

            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # Safe RAG Wrapper Setup
            knowledge_context = ""
            primary_matched_kb = None
            try:
                matching_resolutions = get_semantically_matching_resolutions(user_text, limit=2)
                if matching_resolutions:
                    primary_matched_kb = matching_resolutions[0]
                    knowledge_context = "\n=== COMPLAINT RESOLUTION PROCEDURES ===\n"
                    for entry in matching_resolutions:
                        knowledge_context += f"- Match Pattern: {entry.complaint_summary}\n"  
                        knowledge_context += f"  Target Response: {entry.resolution_script or entry.successful_resolution}\n"
            except Exception as embedding_err:
                logger.warning(f"RAG embedding skipped due to model error: {str(embedding_err)}")

            # Exclude current message from history payload to avoid duplications or dropping attachments
            db_messages = session.messages.exclude(id=current_msg_id).order_by('timestamp').prefetch_related('images')
            gemini_history = []
            
            for msg in db_messages:
                role = "model" if msg.is_from_admin else "user"
                historical_parts = [types.Part.from_text(text=msg.message_text or "")]
                
                # Abstracted file retrieval supporting local file system and remote cloud buckets (S3)
                for hist_img in msg.images.all():
                    if hist_img.file:
                        try:
                            mime_type, _ = mimetypes.guess_type(hist_img.file.name)
                            mime_type = mime_type or "image/webp"
                            with hist_img.file.open('rb') as f:
                                historical_parts.append(types.Part.from_bytes(data=f.read(), mime_type=mime_type))
                        except Exception as img_err:
                            logger.error(f"Failed parsing historical image file payload: {str(img_err)}")
                            
                gemini_history.append(types.Content(role=role, parts=historical_parts))

            # Locate this block inside your view:
            current_user_parts = []
            if user_text:
                current_user_parts.append(types.Part.from_text(text=user_text))
                
            # Assemble incoming prompt elements
            if attached_images_records:
                # FIX: If images exist but user text is missing, inject an explicit visual analysis instruction
                if not user_text:
                    current_user_parts.append(types.Part.from_text(
                        text="The user has provided an image attachment without commentary. "
                            "Analyze this image carefully, extract any visible text or code, "
                            "and ask the user how you can help them regarding its contents."
                    ))
                    
                for img_rec in attached_images_records:
                    if img_rec.file:
                        try:
                            mime_type, _ = mimetypes.guess_type(img_rec.file.name)
                            mime_type = mime_type or "image/webp"
                            with img_rec.file.open('rb') as f:
                                current_user_parts.append(types.Part.from_bytes(data=f.read(), mime_type=mime_type))
                        except Exception as img_err:
                            logger.error(f"Failed parsing active image file chunk: {str(img_err)}")

            if not current_user_parts:
                current_user_parts.append(types.Part.from_text(text="[Reviewing context attachments]"))

            gemini_history.append(types.Content(role="user", parts=current_user_parts))
            
            user_identity = session.user.email if session.user else None
            identity_string = f"Logged-In Customer: '{user_identity}'" if user_identity else "Guest Visitor (Unauthenticated)."
            
            system_instruction = (
                "You are an elite automated support assistant for Jumia.\n"
                "make sure the user is logged in before canceling his order.\n"
                f"Customer Context: {identity_string}\n"
                f"{knowledge_context}\n"
                "Keep responses concise (under 3 sentences) and prioritize executing available tools if requested."
            )
            
            # Local Execution Wrappers
            available_tools_map = {
                "tool_lookup_product_inventory": lambda search_query: lookup_product_inventory(search_query=search_query),
                "tool_manage_customer_order": lambda action_type, order_id: manage_customer_order(action_type=action_type, order_id=order_id, customer_email=user_identity),
                "tool_check_site_knowledge_base": lambda category: check_site_knowledge_base(category=category),
                "tool_query_order_tracking_pipeline": lambda order_id: query_order_tracking_pipeline(order_id=order_id, context_user_email=user_identity),
                "tool_modify_order_shipping_destination": lambda order_id, clean_new_address: modify_order_shipping_destination(order_id=order_id, clean_new_address=clean_new_address, context_user_email=user_identity),
                "tool_file_formal_complaint": lambda issue_description: file_formal_complaint(issue_description=issue_description, customer_email=user_identity),
            }

            # Explicit Tool Declarations for Google-GenAI SDK
            sdk_tools_declaration = [
                types.Tool(function_declarations=[
                    types.FunctionDeclaration(
                        name="tool_lookup_product_inventory",
                        description="Look up item configurations, stock availability status, and general price points from store database lines.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={"search_query": types.Schema(type=types.Type.STRING, description="The name or category keyword of the product to search for.")},
                            required=["search_query"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="tool_manage_customer_order",
                        description="Process action mutations over customer invoice records like initiating order cancellations or return queries.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "action_type": types.Schema(type=types.Type.STRING, description="The action to perform, e.g., 'CANCEL' or 'RETURN'."),
                                "order_id": types.Schema(type=types.Type.STRING, description="The identification number of the target order transaction.")
                            },
                            required=["action_type", "order_id"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="tool_check_site_knowledge_base",
                        description="Retrieve general documentation details regarding core corporate model categories such as refund, privacy policies, or terms.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={"category": types.Schema(type=types.Type.STRING, description="The information category to search, e.g., 'refunds', 'privacy', 'shipping'.")},
                            required=["category"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="tool_query_order_tracking_pipeline",
                        description="Check shipping delivery progress tracking context timelines for an active order tracking invoice reference.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={"order_id": types.Schema(type=types.Type.STRING, description="The string identifier code of the customer order package.")},
                            required=["order_id"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="tool_modify_order_shipping_destination",
                        description="Update delivery address details for an order before processing fulfillment workflows.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "order_id": types.Schema(type=types.Type.STRING, description="The target order identifier code string."),
                                "clean_new_address": types.Schema(type=types.Type.STRING, description="The verified full update address text string mapping destination targets.")
                            },
                            required=["order_id", "clean_new_address"]
                        )
                    ),
                    types.FunctionDeclaration(
                        name="tool_file_formal_complaint",
                        description="File a structured customer complaint statement record to log system customer grievances.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={"issue_description": types.Schema(type=types.Type.STRING, description="The detailed description summary detailing customer issue events.")},
                            required=["issue_description"]
                        )
                    )
                ])
            ]

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=6),
                retry=retry_if_exception_type(ServerError),
                reraise=True
            )
            def _execute_generation_with_backoff(history_payload, current_config):
                return client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=history_payload,
                    config=current_config
                )

            initial_config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=sdk_tools_declaration,
                temperature=0.3,
            )

            response = _execute_generation_with_backoff(gemini_history, initial_config)
            
            if response.function_calls:
                tool_history = list(gemini_history)
                tool_history.append(response.candidates[0].content)
                tool_parts_responses = []
                
                for call in response.function_calls:
                    if call.name in available_tools_map:
                        tool_result = available_tools_map[call.name](**call.args)
                    else:
                        tool_result = {"error": "Unsupported backend tool instruction."}
                        
                    tool_parts_responses.append(types.Part.from_function_response(name=call.name, response=tool_result))
                
                tool_history.append(types.Content(role="user", parts=tool_parts_responses))
                
                final_config = types.GenerateContentConfig(system_instruction=system_instruction)
                final_response = _execute_generation_with_backoff(tool_history, final_config)
                ai_final_text = final_response.text
            else:
                ai_final_text = response.text

            return ai_final_text, primary_matched_kb
            
        except Exception as e:
            SITE_NAME = AppVariable.get_setting('APP_NAME')
            logger.error(f"Gemini execution layer error: {str(e)}", exc_info=True)
            return f"🤖 {SITE_NAME} is currently experiencing high server volume. Please try sending your request once more in a brief moment!", None

    def get(self, request, *args, **kwargs):
        """Fetches conversation history dataset logs for the customer widget interface."""
        session = self._get_or_create_session(request)

        if not session or self._check_session_expiry(session):
            return JsonResponse({'success': False, 'message': 'Chat session context unavailable.'}, status=404)

        self._verify_and_restore_ai_control(session)

        if not session.messages.exists():
            if request.user.is_authenticated:
                user_name = request.user.get_full_name() or request.user.email or request.user.username
                greeting_text = f"Hello {user_name}! 👋 Welcome to Customer Support. How can I help you check your order, tracking status, or file a complaint today?"
            else:
                greeting_text = "Hello! 👋 Welcome to Customer Support. How can I help you check your order, tracking status, or file a complaint today?"
            
            ChatMessage.objects.create(
                session=session,
                is_from_admin=True,
                sender_name="AI Assistant",
                message_text=greeting_text
            )

        messages_query = session.messages.order_by('timestamp').prefetch_related('images')
        history = [{
            'id': msg.id,
            'is_admin': msg.is_from_admin,
            'sender': msg.sender_name,
            'text': msg.message_text or "",
            'time': msg.timestamp.strftime('%H:%M'),
            'image_urls': [img.file.url for img in msg.images.all() if img.file]
        } for msg in messages_query]
        
        return JsonResponse({'success': True, 'history': history, 'is_ai_active': session.is_ai_active})

    def post(self, request, *args, **kwargs):
        """Accepts incoming customer requests and handles automatic AI reactions."""
        raw_text = request.POST.get('message', '').strip()
        attached_images_list = request.FILES.getlist('images')

        if not raw_text and not attached_images_list:
            return JsonResponse({'success': False, 'message': 'Payload cannot be blank.'}, status=400)

        session = self._get_or_create_session(request)
        if self._check_session_expiry(session):
            return JsonResponse({'success': False, 'message': 'Session expired. Please start a new chat.'}, status=410)

        name_identity = request.user.email if request.user.is_authenticated else "Guest Visitor"
        
        # Open transaction block only for immediate database instantiation operations
        with transaction.atomic():
            new_msg = ChatMessage.objects.create(
                session=session, is_from_admin=False, sender_name=name_identity, message_text=raw_text
            )

            saved_image_urls = []
            saved_image_records = []
            for uploaded_img in attached_images_list:
                try:
                    optimized_webp_bytes = optimize_chat_image_bytes(uploaded_img)
                    img_file = ContentFile(optimized_webp_bytes, name=f"{timezone_now().strftime('%Y%m%d%H%M%S')}.webp")
                    img_obj = ChatMessageImage.objects.create(message=new_msg, file=img_file)
                    saved_image_records.append(img_obj)
                    saved_image_urls.append(img_obj.file.url)
                except Exception as e:
                    logger.error(f"Failed processing compressed image attachment: {str(e)}")

        ai_message_payload = None
        if session.is_ai_active:
            # Pass new_msg.id into AI generation loop to properly partition payload building pipelines
            ai_reply_text, matched_kb = self._generate_ai_response(
                session, raw_text, current_msg_id=new_msg.id, attached_images_records=saved_image_records
            )
            
            ai_msg = ChatMessage.objects.create(
                session=session, is_from_admin=True, sender_name="AI Assistant", message_text=ai_reply_text, matched_resolution=matched_kb
            )
            ai_message_payload = {
                'is_admin': True, 
                'sender': 'AI Assistant', 
                'text': ai_msg.message_text, 
                'time': ai_msg.timestamp.strftime('%H:%M'), 
                'image_urls': []
            }

        return JsonResponse({
            'success': True,
            'message': {
                'is_admin': False, 
                'sender': name_identity, 
                'text': new_msg.message_text or "", 
                'time': new_msg.timestamp.strftime('%H:%M'), 
                'image_urls': saved_image_urls
            },
            'ai_response': ai_message_payload
        })


@method_decorator(csrf_protect, name='dispatch')
class AdminChatActionReplyEndpoint(LoginRequiredMixin, UserPassesTestMixin, View):
    """Handles manual interventions, overrides, and session states within the agent pool."""
    
    def test_func(self):
        return self.request.user.is_staff

    def post(self, request, session_id, *args, **kwargs):
        session = ChatSession.objects.filter(id=session_id).first()
        if not session:
            return JsonResponse({'success': False, 'message': 'Target conversation window missing.'}, status=404)

        # Normalize data parsing regardless of content transmission format (JSON or Multi-part FormData)
        if request.content_type == 'application/json':
            try:
                body_data = json.loads(request.body.decode('utf-8'))
            except Exception:
                body_data = {}
        else:
            body_data = request.POST

        action = body_data.get('action')

        # 1. AI Handover Engine Core Commands
        if action == 'hijack_chat':
            session.is_ai_active = False
            session.save(update_fields=['is_ai_active'])
            return JsonResponse({'success': True, 'is_ai_active': False})

        if action == 'activate_ai':
            session.is_ai_active = True
            session.save(update_fields=['is_ai_active'])
            return JsonResponse({'success': True, 'is_ai_active': True})

        # 2. Match with Javascript structural action: logResolutionAndClose()
        if action in ['close_and_log', 'log_resolution_close']:
            category = body_data.get('category', 'other')
            summary = body_data.get('summary', '').strip()
            # Falls back to frontend variable named template key: 'action_taken'
            resolution = body_data.get('resolution', body_data.get('action_taken', '')).strip()
            
            if summary and resolution:
                try:
                    from core.models import ComplaintResolution
                    ComplaintResolution.objects.create(
                        category=category,
                        complaint_summary=summary,
                        successful_resolution=resolution,
                        resolution_script=resolution
                    )
                except Exception as e:
                    # Fallback log recording pattern if logger isn't initialized 
                    print(f"Error logging dynamic knowledge expansion record: {str(e)}")

            session.is_active = False
            session.is_ai_active = False
            session.save(update_fields=['is_active', 'is_ai_active'])
            return JsonResponse({'success': True})

        # 3. Match with Javascript structural action: closeSessionOnly()
        if action in ['close_only', 'close_session_only']:
            session.is_active = False
            session.is_ai_active = False
            session.save(update_fields=['is_active', 'is_ai_active'])
            return JsonResponse({'success': True})

        # 4. Standard Text Message Flow fallback loop
        raw_text = request.POST.get('message', '').strip()
        attached_images_list = request.FILES.getlist('images')

        if not raw_text and not attached_images_list:
            return JsonResponse({'success': False, 'message': 'Payload cannot be blank.'}, status=400)

        admin_msg = ChatMessage.objects.create(
            session=session,
            is_from_admin=True,
            sender_name=request.user.email,
            message_text=raw_text
        )

        for uploaded_img in attached_images_list:
            try:
                # Ensure your processing utils function matches your root layout signature
                from .utils import optimize_chat_image_bytes 
                optimized_webp_bytes = optimize_chat_image_bytes(uploaded_img)
                img_file = ContentFile(optimized_webp_bytes, name=f"admin_{timezone.now().strftime('%Y%m%d%H%M%S')}.webp")
                ChatMessageImage.objects.create(message=admin_msg, file=img_file)
            except Exception as e:
                print(f"Failed processing administrative attachment matrix: {str(e)}")

        session.is_ai_active = False
        session.save(update_fields=['is_ai_active'])

        return JsonResponse({'success': True})


class SupportMonitoringDeckView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Renders the main single-page Support UI workspace dashboard."""
    template_name = "chat_dashboard.html"

    def test_func(self):
        return self.request.user.is_staff


@method_decorator(csrf_protect, name='dispatch')
class AdminChatMetricsQueueEndpoint(LoginRequiredMixin, UserPassesTestMixin, View):
    """Provides background live data streams and processes structural agent updates."""
    
    def test_func(self):
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs):
        target_session_id = request.GET.get('session_id')

        # --- STREAM A: FETCH SINGLE SESSION DETAILED HISTORY ---
        if target_session_id:
            session = ChatSession.objects.filter(id=target_session_id).first()
            if not session:
                return JsonResponse({'success': False, 'message': 'Chat session missing.'}, status=404)
            
            messages_query = session.messages.all().order_by('timestamp').prefetch_related('images')
            history = [{
                'id': msg.id,
                'is_admin': msg.is_from_admin,
                'sender': msg.sender_name or ("Admin" if msg.is_from_admin else "Customer"),
                'text': msg.message_text or "",
                'time': msg.timestamp.strftime('%H:%M'),
                'image_urls': [img.file.url for img in msg.images.all() if img.file]
            } for msg in messages_query]

            customer_identity = session.user.email if session.user else "Guest Visitor"

            return JsonResponse({
                'success': True,
                'session_id': str(session.id),
                'customer_identity': customer_identity,
                'is_ai_active': session.is_ai_active,
                'history': history
            })

        # --- STREAM B: FETCH TICKETS QUEUE & STATUS BADGE METRICS ---
        active_sessions = ChatSession.objects.filter(is_active=True).prefetch_related('messages').order_by('-created_at')
        
        pending_complaints = 0
        awaiting_reply = 0
        replied = 0
        active_tickets_payload = []

        for s in active_sessions:
            last_msg = s.messages.all().order_by('-timestamp').first()
            status = 'Replied'
            last_snippet = "No messages in this channel yet."
            last_time = s.created_at.strftime('%H:%M')

            if last_msg:
                last_snippet = last_msg.message_text or "[Image Attachment]"
                last_time = last_msg.timestamp.strftime('%H:%M')
                
                if not last_msg.is_from_admin:
                    text_lower = (last_msg.message_text or "").lower()
                    is_complaint = any(w in text_lower for w in ['wrong', 'broken', 'refund', 'damage', 'missing', 'fake', 'fail'])
                    if is_complaint:
                        status = 'Pending Complaint'
                        pending_complaints += 1
                    else:
                        status = 'Customer Waiting'
                        awaiting_reply += 1
                else:
                    status = 'Replied'
                    replied += 1
            else:
                awaiting_reply += 1

            customer_display = s.user.email if s.user else f"Guest ({str(s.id)[:8]})"

            active_tickets_payload.append({
                'session_id': str(s.id),
                'customer': customer_display,
                'status': status,
                'last_active_time': last_time,
                'last_snippet': last_snippet
            })

        return JsonResponse({
            'success': True,
            'metrics': {
                'pending_complaints': pending_complaints,
                'awaiting_reply': awaiting_reply,
                'replied': replied
            },
            'active_tickets': active_tickets_payload
        })

    def post(self, request, *args, **kwargs):
        """Processes outbound agent communication overrides and handles closing/logging actions."""
        session_id = request.GET.get('session_id')
        session = ChatSession.objects.filter(id=session_id).first()
        if not session:
            return JsonResponse({'success': False, 'message': 'Active workspace window missing.'}, status=404)

        # Normalize incoming request data
        if request.content_type == 'application/json':
            try:
                body_data = json.loads(request.body.decode('utf-8'))
            except Exception:
                body_data = {}
        else:
            body_data = request.POST

        action = body_data.get('action')

        # --- BOT OVERRIDE INTERVENE ACTIONS ---
        if action == 'hijack_chat':
            session.is_ai_active = False
            session.save(update_fields=['is_ai_active'])
            return JsonResponse({'success': True, 'is_ai_active': False})

        if action == 'activate_ai':
            session.is_ai_active = True
            session.save(update_fields=['is_ai_active'])
            return JsonResponse({'success': True, 'is_ai_active': True})

        # --- TERMINATION / RESOLUTION SAVING OPERATIONS ---
        if action == 'close_and_log':
            category = body_data.get('category', 'other')
            summary = body_data.get('summary', '').strip()
            action_taken = body_data.get('action_taken', '').strip()
            
            if summary and action_taken:
                try:
                    ComplaintResolution.objects.create(
                        category=category,
                        complaint_summary=summary,
                        successful_resolution=action_taken,
                        resolution_script=action_taken
                    )
                except Exception as e:
                    logger.error(f"Could not log resolution database values: {str(e)}")

            session.is_active = False
            session.is_ai_active = False
            session.save(update_fields=['is_active', 'is_ai_active'])
            return JsonResponse({'success': True})

        if action == 'close_only':
            session.is_active = False
            session.is_ai_active = False
            session.save(update_fields=['is_active', 'is_ai_active'])
            return JsonResponse({'success': True})

        # --- STANDARD AGENT MESSAGE DISPATCH WITH IMAGES ---
        raw_text = request.POST.get('message', '').strip()
        attached_images_list = request.FILES.getlist('images')

        if not raw_text and not attached_images_list:
            return JsonResponse({'success': False, 'message': 'Cannot send an empty outbound reply.'}, status=400)

        admin_msg = ChatMessage.objects.create(
            session=session,
            is_from_admin=True,
            sender_name=request.user.email,
            message_text=raw_text
        )

        for uploaded_img in attached_images_list:
            try:
                optimized_webp_bytes = optimize_chat_image_bytes(uploaded_img)
                img_file = ContentFile(optimized_webp_bytes, name=f"admin_{timezone.now().strftime('%Y%m%d%H%M%S')}.webp")
                ChatMessageImage.objects.create(message=admin_msg, file=img_file)
            except Exception as e:
                logger.error(f"Image compression upload failed: {str(e)}")

        # Whenever a human types, turn off AI automatically
        session.is_ai_active = False
        session.save(update_fields=['is_ai_active'])

        return JsonResponse({'success': True})

        
# @method_decorator(csrf_protect, name='dispatch')
# class AdminChatMetricsQueueEndpoint(LoginRequiredMixin, UserPassesTestMixin, View):
#     """Provides background live data streams for active tickets and specific session histories."""
    
#     def test_func(self):
#         return self.request.user.is_staff

#     def get(self, request, *args, **kwargs):
#         target_session_id = request.GET.get('session_id')

#         # --- STREAM A: FETCH SINGLE SESSION DETAILED HISTORY ---
#         if target_session_id:
#             session = ChatSession.objects.filter(id=target_session_id).first()
#             if not session:
#                 return JsonResponse({'success': False, 'message': 'Chat session missing.'}, status=404)
            
#             messages_query = session.messages.all().order_by('timestamp').prefetch_related('images')
#             history = [{
#                 'id': msg.id,
#                 'is_admin': msg.is_from_admin,
#                 'sender': msg.sender_name or ("Admin" if msg.is_from_admin else "Customer"),
#                 'text': msg.message_text or "",
#                 'time': msg.timestamp.strftime('%H:%M'),
#                 'image_urls': [img.file.url for img in msg.images.all() if img.file]
#             } for msg in messages_query]

#             customer_identity = session.user.email if session.user else "Guest Visitor"

#             return JsonResponse({
#                 'success': True,
#                 'session_id': str(session.id),
#                 'customer_identity': customer_identity,
#                 'is_ai_active': session.is_ai_active,
#                 'history': history
#             })

#         # --- STREAM B: FETCH TICKETS QUEUE & STATUS BADGE METRICS ---
#         # Fixed to use 'created_at' as confirmed by your model schema
#         active_sessions = ChatSession.objects.filter(is_active=True).prefetch_related('messages').order_by('-created_at')
        
#         pending_complaints = 0
#         awaiting_reply = 0
#         replied = 0
#         active_tickets_payload = []

#         for s in active_sessions:
#             last_msg = s.messages.all().order_by('-timestamp').first()
#             status = 'Replied'
#             last_snippet = "No messages in this channel yet."
#             last_time = s.created_at.strftime('%H:%M')

#             if last_msg:
#                 last_snippet = last_msg.message_text or "[Image Attachment]"
#                 last_time = last_msg.timestamp.strftime('%H:%M')
                
#                 if not last_msg.is_from_admin:
#                     text_lower = (last_msg.message_text or "").lower()
#                     # Pattern matching to guess flag urgency rules
#                     is_complaint = any(w in text_lower for w in ['wrong', 'broken', 'refund', 'damage', 'missing', 'fake', 'fail'])
#                     if is_complaint:
#                         status = 'Pending Complaint'
#                         pending_complaints += 1
#                     else:
#                         status = 'Customer Waiting'
#                         awaiting_reply += 1
#                 else:
#                     status = 'Replied'
#                     replied += 1
#             else:
#                 awaiting_reply += 1

#             customer_display = s.user.email if s.user else f"Guest ({str(s.id)[:8]})"

#             active_tickets_payload.append({
#                 'session_id': str(s.id),
#                 'customer': customer_display,
#                 'status': status,
#                 'last_active_time': last_time,
#                 'last_snippet': last_snippet
#             })

#         return JsonResponse({
#             'success': True,
#             'metrics': {
#                 'pending_complaints': pending_complaints,
#                 'awaiting_reply': awaiting_reply,
#                 'replied': replied
#             },
#             'active_tickets': active_tickets_payload
#         })


@method_decorator(csrf_protect, name='dispatch')
class AdminChatActionReplyEndpoint(LoginRequiredMixin, UserPassesTestMixin, View):
    """Processes outbound agent communication overrides and handles closing/logging actions."""
    
    def test_func(self):
        return self.request.user.is_staff

    def post(self, request, session_id, *args, **kwargs):
        session = ChatSession.objects.filter(id=session_id).first()
        if not session:
            return JsonResponse({'success': False, 'message': 'Active workspace window missing.'}, status=404)

        # Normalize incoming request types (payload JSON data vs classic FormData uploads)
        if request.content_type == 'application/json':
            try:
                body_data = json.loads(request.body.decode('utf-8'))
            except Exception:
                body_data = {}
        else:
            body_data = request.POST

        action = body_data.get('action')

        # --- BOT OVERRIDE INTERVENE ACTIONS ---
        if action == 'hijack_chat':
            session.is_ai_active = False
            session.save(update_fields=['is_ai_active'])
            return JsonResponse({'success': True, 'is_ai_active': False})

        if action == 'activate_ai':
            session.is_ai_active = True
            session.save(update_fields=['is_ai_active'])
            return JsonResponse({'success': True, 'is_ai_active': True})

        # --- TERMINATION / RESOLUTION SAVING OPERATIONS ---
        if action == 'close_and_log':
            category = body_data.get('category', 'other')
            summary = body_data.get('summary', '').strip()
            action_taken = body_data.get('action_taken', '').strip()
            
            if summary and action_taken:
                try:
                    ComplaintResolution.objects.create(
                        category=category,
                        complaint_summary=summary,
                        successful_resolution=action_taken,
                        resolution_script=action_taken
                    )
                except Exception as e:
                    logger.error(f"Could not log resolution database values: {str(e)}")

            session.is_active = False
            session.is_ai_active = False
            session.save(update_fields=['is_active', 'is_ai_active'])
            return JsonResponse({'success': True})

        if action == 'close_only':
            session.is_active = False
            session.is_ai_active = False
            session.save(update_fields=['is_active', 'is_ai_active'])
            return JsonResponse({'success': True})

        # --- STANDARD AGENT MESSAGE DISPATCH WITH IMAGES ---
        raw_text = request.POST.get('message', '').strip()
        attached_images_list = request.FILES.getlist('images')

        if not raw_text and not attached_images_list:
            return JsonResponse({'success': False, 'message': 'Cannot send an empty outbound reply.'}, status=400)

        admin_msg = ChatMessage.objects.create(
            session=session,
            is_from_admin=True,
            sender_name=request.user.email,
            message_text=raw_text
        )

        for uploaded_img in attached_images_list:
            try:
                optimized_webp_bytes = optimize_chat_image_bytes(uploaded_img)
                img_file = ContentFile(optimized_webp_bytes, name=f"admin_{timezone.now().strftime('%Y%m%d%H%M%S')}.webp")
                ChatMessageImage.objects.create(message=admin_msg, file=img_file)
            except Exception as e:
                logger.error(f"Image compression upload failed: {str(e)}")

        # Whenever a human types, turn off AI automatically
        session.is_ai_active = False
        session.save(update_fields=['is_ai_active'])

        return JsonResponse({'success': True})

