from django.contrib import admin
from django.utils.html import format_html
from .models import Page, PageSection
from .forms import PageForm, PageSectionForm

class PageSectionInline(admin.StackedInline):
    """
    Allows editing and ordering sections directly inside the Page detailed view.
    Using StackedInline since sections contain multiple rich fields like body, links, and media.
    """
    model = PageSection
    form = PageSectionForm
    extra = 1
    classes = ['collapse']  # Keeps the page tidy by letting administrators collapse sections
    ordering = ['order']
    fieldsets = (
        (None, {
            'fields': (('layout_type', 'order', 'is_active'),)
        }),
        ('Content Sources', {
            'description': 'Choose one source of truth for this section block.',
            'fields': ('category', 'widget', 'body_content'),
        }),
        ('Media Assets & Interactivity', {
            'fields': (('image', 'video_url'), ('cta_text', 'cta_url')),
        }),
        ('Styling & Dev Meta', {
            'fields': ('custom_classes', 'internal_notes'),
        }),
    )


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    form = PageForm
    list_display = ('title', 'slug', 'template', 'status_badge', 'is_active', 'updated_at')
    list_filter = ('template', 'status', 'is_active', 'created_at')
    search_fields = ('title', 'slug', 'excerpt')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [PageSectionInline]
    
    fieldsets = (
        (None, {
            'fields': (('title', 'slug'), ('template', 'status', 'is_active'))
        }),
        ('Media & Context Overview', {
            'fields': ('image', 'excerpt'),
        }),
        ('System Timestamps', {
            'fields': ('published_at',),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('published_at',)

    @admin.display(description='Status')
    def status_badge(self, obj):
        colors = {
            'draft': '#cca300',      # Amber
            'published': '#28a745',  # Green
            'archived': '#6c757d',   # Muted Gray
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; '
            'border-radius: 4px; font-weight: bold; text-transform: uppercase; font-size: 10px;">{}</span>',
            colors.get(obj.status, '#000'),
            obj.status
        )


@admin.register(PageSection)
class PageSectionAdmin(admin.ModelAdmin):
    form = PageSectionForm
    list_display = ('__str__', 'layout_type', 'order', 'is_active', 'content_source_summary')
    list_filter = ('layout_type', 'is_active', 'page')
    search_fields = ('body_content', 'internal_notes', 'page__title')
    ordering = ['page', 'order']

    @admin.display(description='Content Source')
    def content_source_summary(self, obj):
        if obj.category:
            return f"Category: {obj.category}"
        if obj.widget:
            return f"Widget: {obj.widget}"
        if obj.body_content.strip():
            return "HTML / Markdown Content"
        if obj.image:
            return "Standalone Media (Image)"
        if obj.video_url:
            return "Standalone Media (Video)"
        return "Empty Slot"