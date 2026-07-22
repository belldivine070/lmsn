from django import template
from django.utils.safestring import mark_safe
from django.forms.widgets import ClearableFileInput
import builtins
from core.models import POST_FIELD_CHOICES
import os

register = template.Library()


@register.filter
def split_path(value):
    return os.path.basename(value)

# --- Dictionary/Object Utilities ---

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Safely get a value from a dictionary."""
    return dictionary.get(key)

@register.filter(name='get_attr')
def get_attr(obj, attr_name):
    """Get an attribute from an object dynamically."""
    return getattr(obj, attr_name, None)

@register.filter(name='in_list')
def in_list(value, list_string):
    """Check if a value exists in a comma-separated string."""
    return str(value) in [x.strip() for x in list_string.split(',')]

@register.filter
def split(value, key):
    """Split a string into a list using the given separator."""
    if not isinstance(value, str):
        return []
    return value.split(key)

@register.filter
def join_pks(queryset, separator=','):
    """Join primary keys of a queryset into a string."""
    try:
        return separator.join(str(obj.pk) for obj in queryset)
    except (TypeError, AttributeError):
        return ''

# --- URL / Context Utilities ---

@register.simple_tag(takes_context=True)
def url_name(context):
    """Return the current URL pattern name."""
    return context.request.resolver_match.url_name

@register.simple_tag(takes_context=True)
def get_category_slug_from_url(context):
    """Get 'slug' or 'category_slug' from URL kwargs if present."""
    match = context.request.resolver_match
    return match.kwargs.get('category_slug') or match.kwargs.get('slug')

# --- Post/Category Utilities ---

@register.filter
def should_display(post, field_name):
    """Check if a field should be displayed for a post's category."""
    if not getattr(post, 'category', None):
        return False
    return field_name in getattr(post.category, 'child_fields', [])

@register.filter
def get_field_verbose_name(field_name):
    """Translate a field slug into a readable name using POST_FIELD_CHOICES."""
    return POST_FIELD_CHOICES.get(field_name, field_name.replace('_', ' ').title())

@register.simple_tag
def get_gallery_images(post):
    """Return post's gallery images excluding the primary image (order > 0)."""
    if hasattr(post, 'images'):
        return post.images.filter(order__gt=0).order_by('order')
    return []

# --- Media Utilities ---

@register.filter
def is_video(filename_url):
    """Check if a file URL ends with a video extension."""
    if not filename_url:
        return False
    return str(filename_url).lower().endswith(('.mp4', '.webm', '.ogg', '.mov', '.avi'))

@register.filter
def is_image(filename_url):
    """Check if a file URL ends with an image extension."""
    if not filename_url:
        return False
    return str(filename_url).lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))

# --- Widget Utilities ---

@register.filter
def render_checkbox_with_class(bound_widget_subitem, css_class):
    """
    Add a CSS class to a single checkbox widget from CheckboxSelectMultiple.
    Usage: {{ checkbox|render_checkbox_with_class:"form-check-input" }}
    """
    tag_html = str(bound_widget_subitem.tag)

    # If class already exists, return as is
    if f'class="{css_class}"' in tag_html or f"class='{css_class}'" in tag_html:
        return mark_safe(tag_html)

    # Insert class before the closing '>'
    closing_bracket_index = tag_html.rfind('>')
    if closing_bracket_index != -1:
        modified_tag = tag_html[:closing_bracket_index] + f' class="{css_class}"' + tag_html[closing_bracket_index:]
        return mark_safe(modified_tag)

    return mark_safe(tag_html)

@register.filter
def getattr_filter(obj, attr):
    """
    Safely retrieves the value of a dynamic attribute (string) from an object.
    Equivalent to Python's built-in getattr(obj, attr, None).
    Renamed to avoid conflict with the built-in.
    """
    return builtins.getattr(obj, attr, None)

@register.simple_tag
def render_file_field(field, css_class=None, multiple=None, **kwargs):
    """
    Custom tag to render a file field with added classes and attributes.
    Safely handles cases where the field might not have as_widget (e.g., model fields).
    """
    if hasattr(field, 'as_widget'):
        # It's a proper form field; use its widget
        widget = field.widget
        if css_class:
            widget.attrs['class'] = css_class
        if multiple:
            widget.attrs['multiple'] = multiple
        for key, value in kwargs.items():
            widget.attrs[key] = value
        return field.as_widget()
    else:
        # Fallback for model fields or non-form fields: generate HTML manually
        attrs = {
            'type': 'file',
            'name': getattr(field, 'name', 'file'),
            'id': f"id_{getattr(field, 'name', 'file')}"
        }
        if css_class:
            attrs['class'] = css_class
        if multiple:
            attrs['multiple'] = multiple
        for key, value in kwargs.items():
            attrs[key] = value
        
        # Build the HTML string
        attr_string = ' '.join(f'{key}="{value}"' for key, value in attrs.items())
        return mark_safe(f'<input {attr_string} />')

@register.filter
def get_item(dictionary, key):
    # Check if 'dictionary' is actually a dict before calling .get()
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None 