import os
import uuid
import random

from datetime import timedelta
from django.utils.timezone import now

from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField # Use if on PostgreSQL, otherwise a JSONField/TextField works for raw embeddings
from django.core.exceptions import ValidationError

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.core.files.images import get_image_dimensions
from mutagen import File as MutagenFile



POST_FIELD_CHOICES = {
    'title': 'Title', 
    'slug': 'Slug', 
    'excerpt': 'Excerpt', 
    'content': 'Content',    
    'author': 'Author', 
    'btn_url': 'btn_URL',
    'btn_text': 'btn_Text', 
    'is_published': 'Publish Now (Toggle)',
    'featured_image': 'Feature Image (from Library)', 
    'featured_video': 'Feature Video (from Library)', 
    'featured_audio': 'Feature Audio (from Library)', 
    'icon': 'Icon',
    'image_align': 'Image Align', 
    'tags': 'Tags',
    'event_date': 'Event Date', 
    'address': 'Address', 
    'addfield1': 'Add Field 1',
    'addfield2': 'Add Field 2', 
    'addfield3': 'Add Field 3', 
    'addfield4': 'Add Field 4',
    'subtitle': 'Subtitle', 
    'shortcodes': 'Shortcodes', 
    'progress': 'Progress',
}



# ----------------------------------------------------
# 1. HELPERS & PATHS
# ----------------------------------------------------

def media_library_path(instance, filename):
    # 1. Determine the category folder
    if instance.mediacat:
        folder_name = slugify(instance.mediacat.name)
    else:
        folder_name = 'general'
    
    # # 2. Get the date structure
    # date_path = timezone.now().strftime('%Y/%m')
    
    # 3. Join them all
    # This results in: media_library/electronics/2026/04/yourfile.jpg
    return os.path.join('media_library', folder_name, filename)


class MediaAlbum(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=150, unique=True, blank=True)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    

class MediaAsset(models.Model):
    FILE_TYPES = (
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
    )
    
    mediacat = models.ForeignKey('MediaAlbum', on_delete=models.SET_NULL, null=True, blank=True, related_name='assets')
    file = models.FileField(upload_to=media_library_path, max_length=500)
    title = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=10, choices=FILE_TYPES, default='image')
    file_size = models.PositiveIntegerField(help_text="Size in bytes", editable=False, null=True)
    
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    duration = models.FloatField(null=True, blank=True, editable=False, help_text="Duration in seconds")
    extension = models.CharField(max_length=10, blank=True, editable=False)

    replace_existing = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file:
            # 1. Set Title and Extension
            if not self.title:
                self.title = os.path.basename(self.file.name)
            
            self.extension = os.path.splitext(self.file.name)[1].lower()
            self.file_size = self.file.size

            # 2. Type Detection
            ext = self.extension
            if ext in ['.mp4', '.webm', '.mov', '.mkv', '.avi']: 
                self.file_type = 'video'
            elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']: 
                self.file_type = 'image'
            elif ext in ['.mp3', '.wav', '.ogg']: 
                self.file_type = 'audio'
            else: 
                self.file_type = 'document'

            # 3. Physical File Replacement Logic
            if self.replace_existing:
                full_path = os.path.join(settings.MEDIA_ROOT, 'media_library', self.file.name)
                if os.path.exists(full_path):
                    os.remove(full_path)

            # 4. Extract Metadata (Dimensions/Duration)
            try:
                if self.file_type == 'image':
                    self.width, self.height = get_image_dimensions(self.file)
                elif self.file_type in ['video', 'audio']:
                    audio_info = MutagenFile(self.file)
                    if audio_info and audio_info.info:
                        self.duration = audio_info.info.length
            except Exception as e:
                print(f"Metadata error: {e}")

        super().save(*args, **kwargs)

    @property
    def formatted_duration(self):
        if self.duration:
            mins, secs = divmod(int(self.duration), 60)
            return f"{mins:02d}:{secs:02d}"
        return "00:00"

    def __str__(self):
        return f"[{self.file_type.upper()}] {self.title}"

    class Meta:
        verbose_name = "Media Asset"
        verbose_name_plural = "Media Library"
        ordering = ['-uploaded_at']

# --- PHYSICAL FILE CLEANUP ---

@receiver(post_delete, sender=MediaAsset)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """Deletes physical file when record is deleted from DB"""
    if instance.file:
        if os.path.isfile(instance.file.path):
            os.remove(instance.file.path)

@receiver(pre_save, sender=MediaAsset)
def auto_delete_file_on_change(sender, instance, **kwargs):
    """Deletes old physical file when a new file is uploaded to the same record"""
    if not instance.pk:
        return False

    try:
        old_file = MediaAsset.objects.get(pk=instance.pk).file
    except MediaAsset.DoesNotExist:
        return False

    new_file = instance.file
    if not old_file == new_file:
        if os.path.isfile(old_file.path):
            os.remove(old_file.path)


class PasswordResetOTP(models.Model):
    DELIVERY_CHOICES = [
        ('email', 'Email'),
        ('mobile', 'Mobile'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='password_otps')
    otp_code = models.CharField(max_length=6)
    delivery_method = models.CharField(max_length=6, choices=DELIVERY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        # OTP is valid for 10 minutes
        return timezone.now() > self.created_at + timedelta(minutes=10)

    @classmethod
    def generate_otp(cls, user, method):
        # Generate a secure-looking 6 digit random number
        code = f"{random.randint(100000, 999999)}"
        # Deactivate any previous unused OTPs for this user
        cls.objects.filter(user=user, is_verified=False).delete()
        
        return cls.objects.create(user=user, otp_code=code, delivery_method=method)


# ----------------------------------------------------
# 3. SYSTEM SETTINGS & AUDIT
# ----------------------------------------------------

class AppVariable(models.Model):
    var_name = models.CharField(max_length=100, unique=True)
    var_value = models.TextField(blank=True, null=True)
    description = models.CharField(max_length=250, blank=True, default="")
    isreadonly = models.BooleanField(default=False)
    lastupdated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return f"{self.var_name}: {self.var_value}"

    @staticmethod
    def get_setting(name, default=''):
        try:
            return AppVariable.objects.get(var_name=name).var_value
        except AppVariable.DoesNotExist:
            return default


class ActivityLog(models.Model):
    ACTIVITY_TYPES = (
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('purchase', 'Purchase'),
        ('refund', 'Refund'),
        ('cancel_Payment', 'Cancel Payment'),
        ('failed_login', 'Failed Login Attempt'),
        ('password_change', 'Password Change'),
        ('registered', 'Register'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['timestamp', 'activity_type']),
        ]
        ordering = ['-timestamp']


class SecurityAuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    event = models.CharField(max_length=100) 
    description = models.TextField()
    user_agent = models.TextField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)


# ----------------------------------------------------
# 7. MARKETING, COMMUNICATIONS & OTHER
# ----------------------------------------------------

class Banner(models.Model):
    title = models.CharField(max_length=100)
    image_asset = models.ForeignKey(MediaAsset, on_delete=models.CASCADE, related_name='banners', null=True, blank=True)
    link_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)


class ExternalSubscriber(models.Model):
    email = models.EmailField(unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    date_subscribed = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.ip_address:
            try:
                from .tasks import get_subscriber_location_task
                get_subscriber_location_task.delay(self.id)
            except Exception: pass


class ContactUs(models.Model):
    fullname = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)


# ==============================================================
# Email Brocasting system
# ==============================================================
class NewsPost(models.Model):
    AUDIENCE_CHOICES = [
        ('all', 'All Audience'), 
        ('staff_only', 'Staff Only'),
        ('external_only', 'External Subscribers Only'), 
        ('clients', 'Clients'),
    ]
    title = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    content = models.TextField()
    sender_email = models.EmailField(blank=True, null=True)
    target_audience = models.CharField(max_length=50, choices=AUDIENCE_CHOICES, default='all')
    
    # Keeps individual campaign targets local to the record context
    target_emails = models.JSONField(default=list, blank=True)
    
    scheduled_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # 1. Standard Fallback Syncs
        if not self.subject: 
            self.subject = self.title
        if not self.sender_email:
            self.sender_email = AppVariable.get_setting('official_email', 'noreply@bgtech.com')
            
        # 2. Collision-Free Slug Generator
        if not self.slug: 
            base_slug = slugify(self.title) or 'broadcast'
            slug = base_slug
            counter = 1
            Klass = self.__class__
            
            # Loop until a completely unique slug is established
            while Klass.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                if counter > 50:
                    slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
                    break
            self.slug = slug
        super().save(*args, **kwargs)

    def gather_emails(self):
        """
        Dynamically yields target distribution profiles based on the selected
        audience parameters, filtering out dead or missing records.
        """
        CustomUser = get_user_model()
        emails = set()
        
        if self.target_audience in ['all', 'external_only']:
            emails.update(ExternalSubscriber.objects.values_list('email', flat=True))
        if self.target_audience in ['all', 'staff_only']:
            emails.update(CustomUser.objects.filter(is_staff=True, is_active=True).values_list('email', flat=True))
        if self.target_audience == 'clients':
            emails.update(CustomUser.objects.filter(is_client=True, is_active=True).values_list('email', flat=True))
        return list(filter(None, emails))

    def __str__(self):
        return f"{self.title} ({self.status})"


class BroadcastLog(models.Model):
    news_post = models.ForeignKey(NewsPost, on_delete=models.CASCADE, related_name='logs')
    recipient_email = models.EmailField()
    status = models.CharField(max_length=20, default='Sent')  # e.g., 'Sent', 'Failed'
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.recipient_email} - {self.status} ({self.sent_at.strftime('%Y-%m-%d')})"
    

class Page(models.Model):
    TEMPLATE_CHOICES = (
        ('default', 'Default Page'),
        ('about', 'About Page'),
        ('contact', 'Contact Page'),
        ('legal', 'Legal Page'),
        ('landing', 'Landing Page'),
        ('homepage', 'Homepage'),
    )

    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    )

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    title = models.CharField(max_length=150)
    slug = models.SlugField(unique=True, blank=True)
    template = models.CharField(max_length=30, choices=TEMPLATE_CHOICES, default='default')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    image = models.ImageField(upload_to='pages/', blank=True, null=True)
    excerpt = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['title']
        verbose_name = 'Page'
        verbose_name_plural = 'Pages'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Auto-generate slug if missing
        if not self.slug:    
            self.slug = slugify(self.title)
        
        # Auto-manage published_at timestamp
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        elif self.status != 'published':
            self.published_at = None

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('page_detail', kwargs={'slug': self.slug})

    @property
    def active_sections(self):
        # Assumes a ForeignKey or GenericRelation exists on the Section model with related_name='sections'
        return self.sections.filter(is_active=True).order_by('order')


# ----------------------------------------------------
# 6. WIDGETS & WIDGET POSTS
# ----------------------------------------------------

class Widget(models.Model):
    title = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    excerpt = models.TextField(blank=True, null=True)
    # Linked to Media Library
    media_asset = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='widget_covers')
    child_fields = models.JSONField(default=list, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug: self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self): return self.title


class WidgetPost(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    widget = models.ForeignKey(Widget, on_delete=models.CASCADE, related_name='widget_posts')          
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    excerpt = models.TextField(blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    tags = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    subtitle = models.CharField(max_length=255, blank=True, null=True)
    shortcodes = models.TextField(blank=True, null=True)
    
    # Linked to Media Library
    featured_image = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='wid_post_images')
    featured_video = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='wid_post_videos')
    featured_audio = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='wid_post_audios')
    
    icon = models.CharField(max_length=70, blank=True, null=True)
    image_align = models.CharField(max_length=50, blank=True, null=True)
    btn_text = models.CharField(max_length=100, blank=True, null=True, default="Read More")
    btn_url = models.URLField(blank=True, null=True)
    event_date = models.DateTimeField(blank=True, null=True)
    progress = models.IntegerField(blank=True, null=True)
    addfield1 = models.CharField(max_length=255, blank=True, null=True)
    addfield2 = models.CharField(max_length=255, blank=True, null=True)
    addfield3 = models.CharField(max_length=255, blank=True, null=True)
    addfield4 = models.CharField(max_length=255, blank=True, null=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def primary_image_url(self):
        if self.featured_image and self.featured_image.file:
            return self.featured_image.file.url
        return None

    def save(self, *args, **kwargs):
        if not self.slug: self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['widget', '-created_at']   


# ----------------------------------------------------
# 5. CATEGORIES & POSTS (Content Types)
# ----------------------------------------------------

class Category(models.Model):
    title = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    excerpt = models.TextField(blank=True, null=True)
    # Linked to Media Library
    media_asset = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='category_covers')
    child_fields = models.JSONField(default=list, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug: self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Content Type (Category)"
        verbose_name_plural = "Content Types (Categories)"

    def __str__(self): return self.title


class CategoryPost(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='posts')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    excerpt = models.TextField(blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    tags = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    subtitle = models.CharField(max_length=255, blank=True, null=True)
    shortcodes = models.TextField(blank=True, null=True)
    
    # Linked to Media Library (Single files as requested)
    featured_image = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='cat_post_images')
    featured_video = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='cat_post_videos')
    featured_audio = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name='cat_post_audios')
    
    icon = models.CharField(max_length=70, blank=True, null=True)
    image_align = models.CharField(max_length=50, blank=True, null=True)
    btn_text = models.CharField(max_length=100, blank=True, null=True, default="Read More")
    btn_url = models.URLField(blank=True, null=True)
    event_date = models.DateTimeField(blank=True, null=True)
    progress = models.IntegerField(blank=True, null=True)
    addfield1 = models.CharField(max_length=255, blank=True, null=True)
    addfield2 = models.CharField(max_length=255, blank=True, null=True)
    addfield3 = models.CharField(max_length=255, blank=True, null=True)
    addfield4 = models.CharField(max_length=255, blank=True, null=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)       

    def save(self, *args, **kwargs):
        if not self.slug: self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def primary_image_url(self):
        if self.featured_image and self.featured_image.file:
            return self.featured_image.file.url
        return None

    class Meta:
        ordering = ['category', '-created_at']


class PageSection(models.Model):
    LAYOUT_CHOICES = (
        ('hero', 'Hero Section'),
        ('standard', 'Standard Content'),
        ('grid', 'Grid Layout'),
        ('icons', 'Icon Features'),
        ('testimonial', 'Testimonials'),
        ('info', 'Info Strip'),
        ('products', 'Products Section'),
        ('categories', 'Category Section'),
        ('widget', 'Custom Widget'),
        ('gallery', 'Gallery Section'),
        ('faq', 'FAQ Section'),
        ('video', 'Video Section'),
        ('team', 'Team Section'),
        ('cta', 'Call To Action'),
    )

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='sections')
    category = models.ForeignKey('core.Category', on_delete=models.SET_NULL, null=True, blank=True)
    widget = models.ForeignKey('Widget', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Store unchecked post IDs: e.g., [12, 45, 89] to manage custom selections on the fly
    excluded_posts = models.JSONField(default=list, blank=True, help_text='IDs of child posts unchecked by an admin.')
    
    layout_type = models.CharField(max_length=30, choices=LAYOUT_CHOICES, default='standard')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    body_content = models.TextField(blank=True)
    image = models.ImageField(upload_to='sections/', blank=True, null=True)
    video_url = models.URLField(blank=True)
    cta_text = models.CharField(max_length=100, blank=True)
    cta_url = models.CharField(max_length=255, blank=True)
    classes = models.JSONField(default=list, blank=True, help_text='Example: ["hero-section", "overlay-dark", "text-center"]')
    internal_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Page Section'
        verbose_name_plural = 'Page Sections'

    def __str__(self):
        return f'{self.page.title} -> Section {self.order} ({self.get_layout_type_display()})'

    def clean(self):
        super().clean()
        errors = {}

        # Prevent category + widget structural configuration conflict
        if self.category and self.widget:
            conflict_msg = 'A section cannot contain both a category and a widget.'
            errors['category'] = conflict_msg
            errors['widget'] = conflict_msg

        # Relaxed Validation: Allows sections to exist with purely custom static block content assets
        if not any([
            self.category,
            self.widget,
            self.body_content,
            self.image,
            self.video_url
        ]):
            errors['__all__'] = 'Section must contain at least one content engine source or static layout asset (Category, Widget, Text Content, Image, Video).'

        if errors:
            raise ValidationError(errors)

    @property
    def css_classes(self):
        return ' '.join(self.classes) if isinstance(self.classes, list) else ''

    @property
    def template_path(self):
        return f'pages/pagelayout/{self.layout_type}.html'
        # return f'lmsn/dynamic.html'
    
    def get_assigned_posts(self):
        """
        Fetches all published dynamic child posts, automatically omitting 
        any item IDs that the administrator unchecked inside the workspace panel loop.
        """
        exclusions = self.excluded_posts if isinstance(self.excluded_posts, list) else []
        
        if self.category:
            return self.category.posts.filter(is_published=True).exclude(id__in=exclusions)
        if self.widget:
            return self.widget.widget_posts.filter(is_published=True).exclude(id__in=exclusions)
        return []
    

# ==============================================================================
# CHAT SESSION
# ==============================================================================
class ChatSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="chat_sessions",
    )
    anonymous_session_key = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    is_ai_active = models.BooleanField(default=True, help_text="True = AI handles replies. False = human agent is in control.")
    ai_fail_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.user:
            return f"Chat with {self.user.email}"
        return f"Guest Chat #{self.id} ({self.anonymous_session_key[:8] if self.anonymous_session_key else 'N/A'})"


# ==============================================================================
# COMPLAINT RESOLUTION (The AI's Evolving Knowledge Base)
# ==============================================================================
class ComplaintResolution(models.Model):
    CATEGORY_CHOICES = [
        ("order", "Order Issue"),
        ("refund", "Refund Request"),
        ("delivery", "Delivery Problem"),
        ("product", "Product / Quality Issue"),
        ("account", "Account / Login"),
        ("other", "Other"),
    ]

    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="other", db_index=True)
    complaint_summary = models.TextField(help_text="Brief description of the complaint pattern (e.g. 'Customer received wrong item').")
    successful_resolution = models.TextField(help_text="What action or explanation resolved this type of complaint.")
    resolution_script = models.TextField(blank=True, help_text="Optional exact wording the AI should use.")
    
    # NEW: Vector Embedding field for Semantic RAG Lookup
    # If you aren't using PostgreSQL + pgvector, use text/JSONField to store the vector float list.
    # embedding = ArrayField(models.FloatField(), blank=True, null=True, help_text="1536 or 768 dimension vector representation of the complaint_summary.")
    embedding = models.JSONField(blank=True, null=True, help_text="Vector representation list of floats for the complaint_summary.")

    times_used = models.IntegerField(default=0)
    effectiveness_score = models.FloatField(default=0.5, help_text="Rolling average score between 0.0 and 1.0.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="resolutions_created")
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effectiveness_score", "-times_used"]

    def __str__(self):
        return f"[{self.get_category_display()}] {self.complaint_summary[:50]} ({int(self.effectiveness_score * 100)}% effective)"


# ==============================================================================
# CHAT MESSAGE
# ==============================================================================
class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    is_from_admin = models.BooleanField(default=False, help_text="True = AI or human agent. False = customer.")
    sender_name = models.CharField(max_length=100, default="Visitor")
    message_text = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(default=now)
    
    # NEW: Move the dynamic AI matching connection down to the individual message layer
    matched_resolution = models.ForeignKey(
        ComplaintResolution,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="messages_applied",
        help_text="The knowledge base entry used by the AI to answer this specific message."
    )

    class Meta:
        ordering = ["timestamp"]


# ==============================================================================
# CHAT MESSAGE IMAGE (Multimodal Storage)
# ==============================================================================
class ChatMessageImage(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="images")
    file = models.ImageField(upload_to="chat_uploads/")
    uploaded_at = models.DateTimeField(default=now)


# ==============================================================================
# GRANULAR CHAT FEEDBACK (NEW CONCEPT)
# ==============================================================================
class ChatFeedback(models.Model):
    """
    Allows customers to rate either a whole session or a specific turning point message.
    """
    RATING_CHOICES = [(i, f"{i} Star") for i in range(1, 6)]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="feedbacks")
    
    # NEW: Link feedback to the specific message that contained the AI's resolution
    target_message = models.ForeignKey(
        ChatMessage, 
        on_delete=models.CASCADE, 
        null=True, blank=True, 
        related_name="message_feedback",
        help_text="Links feedback directly to the response where the tool/resolution was offered."
    )
    
    rating = models.IntegerField(choices=RATING_CHOICES)
    resolved = models.BooleanField(help_text="Did this fix the specific issue?")
    feedback_text = models.TextField(blank=True, default="", help_text="Optional comments.")
    submitted_at = models.DateTimeField(default=now)

    class Meta:
        verbose_name_plural = "Chat Feedback Entries"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Propagate changes directly to the correct resolution item if linked via the target message
        if self.target_message and self.target_message.matched_resolution:
            resolution = self.target_message.matched_resolution
            resolution.times_used += 1
            
            # Simple rolling average recalculation
            new_score = (1.0 if self.resolved else 0.0) * (self.rating / 5.0)
            resolution.effectiveness_score = (
                (resolution.effectiveness_score * (resolution.times_used - 1) + new_score) 
                / resolution.times_used
            )
            resolution.save(update_fields=["times_used", "effectiveness_score"])