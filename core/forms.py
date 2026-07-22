import os
import json
from django import forms
from django_summernote.widgets import SummernoteWidget
from django.forms.widgets import CheckboxSelectMultiple
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError

from accounts.models import Department
from .models import AppVariable, Category, CategoryPost, POST_FIELD_CHOICES, PageSection, Widget, WidgetPost, NewsPost, ExternalSubscriber, ContactUs, Page, MediaAsset, MediaAlbum



######################################################################################
# --- Helper Functions ---
######################################################################################

def get_field_label(field_name):
    return POST_FIELD_CHOICES.get(field_name, field_name.replace('_', ' ').title())

# Mappings for dynamic fields
WIDGET_MAPPING = {
    'excerpt': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
    'content': SummernoteWidget(),
    'shortcodes': forms.TextInput(attrs={'class': 'form-control'}),
    'address': forms.TextInput(attrs={'rows': 3, 'class': 'form-control'}),
    'event_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
}

class UniversalMediaForm(forms.ModelForm):
    # Standard file field that we will enhance with 'multiple' and 'dropify'
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={
        'class': 'dropify', 
        'data-height': '300',
    }))

    class Meta:
        model = MediaAsset
        fields = ['mediacat', 'file', 'title', 'replace_existing']
        widgets = {
            'mediacat': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional: Manual Title'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Inject multiple attribute for bulk uploading
        self.fields['file'].widget.attrs.update({'multiple': True})
        # Make title optional since we often want to use the filename
        self.fields['title'].required = False

    def save_multiple(self):
        """
        Processes each file and assigns them to the selected category.
        """
        files = self.files.getlist('file')
        selected_cat = self.cleaned_data.get('mediacat')
        results = {"created": 0, "replaced": 0}
        
        for f in files:
            filename = f.name
            # Check for existing record to determine log status
            exists = MediaAsset.objects.filter(title=filename).exists()
            
            # Create instance but don't commit yet to set the category
            asset = MediaAsset(
                file=f, 
                title=filename, 
                mediacat=selected_cat
            )
            # The .save() method in your model handles the replacement/file cleanup logic
            asset.save() 
            
            if exists:
                results["replaced"] += 1
            else:
                results["created"] += 1
                
        return results

# --- FORM FOR CREATING NEW ALBUMS ---

class MediaAlbumForm(forms.ModelForm):
    class Meta:
        model = MediaAlbum
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Album Name', 'autofocus': 'autofocus'}),
        }

class MediaAlbumForm(forms.ModelForm):
    class Meta:
        model = MediaAlbum
        fields = ['name', 'slug']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control form-control-line', 
                'placeholder': 'Cat or Album name', 
                'id': 'album_name',
                'autofocus': 'autofocus'
            }),
        }


######################################################################################
# --- Mixins ---
######################################################################################

class DynamicPostFormMixin:
    """Mixin to handle dynamic field enabling and Media Library selection."""

    def dynamic_init_logic(self, parent_instance_id, parent_model, parent_field_name):
        enabled_fields = set()
    
        if parent_instance_id:
            try:
                parent_instance = parent_model.objects.get(pk=parent_instance_id)
                # List of keys (e.g., ['featured_image', 'content']) enabled in Category
                enabled_fields = set(parent_instance.child_fields or [])
            except parent_model.DoesNotExist:
                pass

        # CORE_FIELDS are always visible/rendered
        CORE_FIELDS = ['title', 'slug', 'is_published', 'featured_image', parent_field_name]

        # Map the field names to the 'file_type' choices in your MediaAsset model
        # Adjust 'IMAGE', 'VIDEO', 'AUDIO' to match your actual MediaAsset constants
        MEDIA_MAP = {
            'featured_image': 'IMAGE',
            'featured_video': 'VIDEO',
            'featured_audio': 'AUDIO'
        }

        for field_name in list(self.fields.keys()):
            # 1. Handle Title/Slug (Required)
            if field_name in ['title', 'slug']:
                self.fields[field_name].required = True
                self.fields[field_name].widget.attrs.update({'class': 'form-control', 'required': 'required'})
                continue

            # 2. Handle Media Asset ForeignKeys
            if field_name in MEDIA_MAP:
                # If it's not a core field AND not enabled in the category, remove it
                if field_name not in enabled_fields and field_name not in CORE_FIELDS:
                    self.fields.pop(field_name, None)
                else:
                    # Filter the library choices by the correct file type
                    target_type = MEDIA_MAP[field_name]
                    if field_name in self.fields:
                        self.fields[field_name].queryset = MediaAsset.objects.filter(file_type=target_type)
                        
                        # Set pretty label and styling
                        clean_label = target_type.title()
                        self.fields[field_name].label = f"Select {clean_label} from Library"
                        self.fields[field_name].widget.attrs.update({
                            'class': 'form-control select2-media',
                            'data-type': target_type.lower()
                        })
                continue

            # 3. Handle Remaining Core Fields
            if field_name in CORE_FIELDS:
                if field_name in self.fields:
                    self.fields[field_name].widget.attrs.setdefault('class', 'form-control')
                continue
                
            # 4. Remove other fields NOT enabled in Category settings
            if field_name not in enabled_fields:
                self.fields.pop(field_name, None)
                continue

            # 5. Handle Dynamic Fields styling (Summernote, etc.)
            self.fields[field_name].label = get_field_label(field_name)
            if field_name in WIDGET_MAPPING:
                self.fields[field_name].widget = WIDGET_MAPPING[field_name]

            # Standard Styling for non-checkbox/non-editor fields
            widget_class = self.fields[field_name].widget.__class__.__name__
            if widget_class not in ('CheckboxInput', 'SummernoteWidget'):
                self.fields[field_name].widget.attrs.setdefault('class', 'form-control')


# =====================================================================
#                           Category Forms
# =====================================================================
   
class CategoryForm(forms.ModelForm):
    child_fields = forms.MultipleChoiceField(
        choices=[(k, v) for k, v in POST_FIELD_CHOICES.items()],
        required=False,
        widget=CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Enable fields for posts in this Category"
    )

    class Meta:
        model = Category
        fields = ['title', 'slug', 'excerpt', 'media_asset', 'child_fields']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'excerpt': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        # Get the selected fields from the form
        selected_fields = self.cleaned_data.get('child_fields', [])
        
        # 1. Manually add 'title' and 'slug' if they aren't there
        if 'title' not in selected_fields:
            selected_fields.append('title')
        if 'slug' not in selected_fields:
            selected_fields.append('slug')
            
        instance.child_fields = selected_fields
        
        if commit:
            instance.save()
        return instance

class DynamicCategoryPostForm(DynamicPostFormMixin, forms.ModelForm):
    class Meta:
        model = CategoryPost
        # Dynamically include all possible fields from your choices
        fields = list(POST_FIELD_CHOICES.keys()) + ['category']
        exclude = ['author', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        # 1. Pop the category_id passed from the Base View
        cat_id = kwargs.pop('category_id', None)
        kwargs.pop('category_instance', None) 

        super().__init__(*args, **kwargs)

        # 2. Determine the active Category ID for dynamic logic
        # Priority 1: The instance (if editing)
        # Priority 2: The ID passed from the URL (if creating)
        if self.instance and self.instance.pk and hasattr(self.instance, 'category'):
            cat_id = self.instance.category.id
        
        # 3. Trigger the Mixin logic (MediaAsset filtering + Dynamic fields)
        if cat_id:
            self.dynamic_init_logic(cat_id, Category, 'category')

        # 4. Handle Category Field Visibility
        if 'category' in self.fields:
            # We keep it as a Select box so users can change it
            self.fields['category'].required = True
            self.fields['category'].label = "Change Post Category"
            self.fields['category'].widget.attrs.update({
                'class': 'form-control select2',
                'id': 'id_category_selector'
            })
            
            # If creating a new post, we pre-select the category from the URL
            if cat_id and not self.instance.pk:
                self.fields['category'].initial = cat_id


# # =====================================================================
# #                           Widget Forms
# # =====================================================================
    
class WidgetForm(forms.ModelForm):
    child_fields = forms.MultipleChoiceField(
        choices=[(k, v) for k, v in POST_FIELD_CHOICES.items()],
        required=False,
        widget=CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Enable fields for posts in this Category"
    )

    class Meta:
        model = Widget
        fields = ['title', 'slug', 'excerpt', 'media_asset', 'child_fields']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'excerpt': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Get the selected fields from the form
        selected_fields = self.cleaned_data.get('child_fields', [])
        
        # 1. Manually add 'title' and 'slug' if they aren't there
        if 'title' not in selected_fields:
            selected_fields.append('title')
        if 'slug' not in selected_fields:
            selected_fields.append('slug')
        if 'featured_image' not in selected_fields:
            selected_fields.append('featured_image')
            
        instance.child_fields = selected_fields
        
        if commit:
            instance.save()
        return instance


class DynamicWidgetPostForm(DynamicPostFormMixin, forms.ModelForm):
    class Meta:
        model = WidgetPost
        fields = list(POST_FIELD_CHOICES.keys()) + ['widget']
        exclude = ['author', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        # 1. Pop custom arguments SAFELY
        # Use .pop(key, None) to ensure it doesn't crash if the key is missing
        wid_id = kwargs.pop('widget_id', None)
        kwargs.pop('widget_instance', None) # Remove this so super() doesn't see it

        super().__init__(*args, **kwargs)

        # 2. Determine the Widget ID for dynamic logic
        # If we are editing (instance exists), get ID from the instance
        if self.instance and self.instance.pk and hasattr(self.instance, 'widget'):
            wid_id = self.instance.widget.id
        
        # 3. Run dynamic logic
        self.dynamic_init_logic(wid_id, Widget, 'widget')

        # 4. Make widget optional (view handles it)
        if 'widget' in self.fields:
            self.fields['widget'].required = False


# =========================================================
# PAGE FORM
# =========================================================
class PageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = [
            'title', 'slug', 'template', 'status', 
            'image', 'excerpt', 'is_active'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'vTextField', 'placeholder': 'Enter page title...'}),
            'slug': forms.TextInput(attrs={'placeholder': 'Auto-generated from title if left blank'}),
            'excerpt': SummernoteWidget(),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        if slug:
            slug = slug.lower().strip()
        return slug


class PageSectionForm(forms.ModelForm):
    # Dynamic multiple choice checkboxes
    visible_posts = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="Select Posts to Display",
        help_text="By default, all dynamic child entries are checked and active. Uncheck specific items to hide them from the user view."
    )

    # Overlay a char field to make entering custom CSS classes easier than editing JSON strings directly
    custom_classes = forms.CharField(
        required=False,
        label="CSS Classes",
        help_text="Space-separated list of CSS classes. Example: hero-section overlay-dark text-center",
        widget=forms.TextInput(attrs={'class': 'vTextField', 'placeholder': 'class1 class2 class3'})
    )

    class Meta:
        model = PageSection
        fields = [
            'layout_type', 'order', 'is_active',
            'category', 'widget', 'visible_posts', 'body_content', 'image', 'video_url',
            'cta_text', 'cta_url', 'custom_classes', 'internal_notes'
        ]
        widgets = {
            'body_content': SummernoteWidget(),
            'internal_notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Internal staff notes...'}),
            'cta_url': forms.TextInput(attrs={'placeholder': '/shop/ or https://example.com'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate custom_classes from existing JSON list data if editing
        if self.instance and self.instance.pk and isinstance(self.instance.classes, list):
            self.initial['custom_classes'] = ' '.join(self.instance.classes)

        # Dynamic construction block for checkbox lists
        choices = []
        initial_selected = []
        exclusions = self.instance.excluded_posts if (self.instance and self.instance.excluded_posts) else []

        # Case A: Editing an entry that already maps directly to a Category Engine
        if self.instance and getattr(self.instance, 'category_id', None):
            posts = CategoryPost.objects.filter(category=self.instance.category, is_published=True)
            choices = [(f"cat_{p.id}", f"[Category: {self.instance.category.title}] - {p.title}") for p in posts]
            initial_selected = [f"cat_{p.id}" for p in posts if p.id not in exclusions]
            
        # Case B: Editing an entry that maps directly to a Widget Engine
        elif self.instance and getattr(self.instance, 'widget_id', None):
            posts = WidgetPost.objects.filter(widget=self.instance.widget, is_published=True)
            choices = [(f"wid_{p.id}", f"[Widget: {self.instance.widget.title}] - {p.title}") for p in posts]
            initial_selected = [f"wid_{p.id}" for p in posts if p.id not in exclusions]

        # Case C: Creating a completely new section. Preload available options grouped up
        else:
            for cat in Category.objects.prefetch_related('posts'):
                for p in cat.posts.filter(is_published=True):
                    choices.append((f"cat_{p.id}", f"({cat.title}) → {p.title}"))
                    if p.id not in exclusions:
                        initial_selected.append(f"cat_{p.id}")
            
            for wid in Widget.objects.prefetch_related('widget_posts'):
                for p in wid.widget_posts.filter(is_published=True):
                    choices.append((f"wid_{p.id}", f"({wid.title}) → {p.title}"))
                    if p.id not in exclusions:
                        initial_selected.append(f"wid_{p.id}")

        self.fields['visible_posts'].choices = choices
        self.fields['visible_posts'].initial = initial_selected

    def clean(self):
        cleaned_data = super().clean()
        
        category = cleaned_data.get('category')
        widget = cleaned_data.get('widget')
        body_content = cleaned_data.get('body_content')
        image = cleaned_data.get('image')
        video_url = cleaned_data.get('video_url')

        if category and widget:
            raise ValidationError(
                {"category": "A section cannot contain both a category and a widget."}
            )

        # Relaxed configuration checking rule matching your updated model scope
        if not any([category, widget, body_content, image, video_url]):
            raise ValidationError(
                "Section must contain at least one content engine source or static layout asset (Category, Widget, Text Content, Image, Video)."
            )

        # Space-separated custom_classes string split parsing logic
        custom_classes_str = cleaned_data.get('custom_classes', '')
        if custom_classes_str:
            cleaned_data['classes'] = [cls.strip() for cls in custom_classes_str.split() if cls.strip()]
        else:
            cleaned_data['classes'] = []

        # Build precise target exclusion tracking lists depending on parent selection
        selected_choices = cleaned_data.get('visible_posts', [])
        excluded_ids = []

        if category:
            all_posts = CategoryPost.objects.filter(category=category, is_published=True)
            for p in all_posts:
                if f"cat_{p.id}" not in selected_choices:
                    excluded_ids.append(p.id)
        elif widget:
            all_posts = WidgetPost.objects.filter(widget=widget, is_published=True)
            for p in all_posts:
                if f"wid_{p.id}" not in selected_choices:
                    excluded_ids.append(p.id)

        cleaned_data['excluded_posts'] = excluded_ids
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.classes = self.cleaned_data.get('classes', [])
        instance.excluded_posts = self.cleaned_data.get('excluded_posts', [])
        if commit:
            instance.save()
        return instance


######################################################################################
# --- Marketing & System Forms ---
######################################################################################

class BroadcastForm(forms.ModelForm):
    # Additional virtual control fields that do not require explicit DB model migrations
    target_individual_email = forms.EmailField(
        required=False,
        label="Target Individual Recipient Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control form-control-sm select-recipient-input d-none',
            'placeholder': 'employee@company.com'
        })
    )
    
    target_department_select = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        label="Target Core Department",
        widget=forms.Select(attrs={
            'class': 'form-select form-select-sm select-dept-input d-none'
        })
    )

    class Meta:
        model = NewsPost
        fields = ['title', 'subject', 'sender_email', 'content', 'target_audience', 'scheduled_time']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'subject': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'target_audience': forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'audienceSelect'}),
            'sender_email': forms.EmailInput(attrs={'class': 'form-control form-control-sm'}),
            'content': SummernoteWidget(),
            'scheduled_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control form-control-sm'}),
        }


class SubcribersForm(forms.ModelForm):
    class Meta:
        model = ExternalSubscriber
        fields = ['email']
        widgets = {'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter email'})}
        

class SiteSettingsKeyForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.settings = AppVariable.objects.all().order_by('var_name')

        for setting in self.settings:
            var_name = setting.var_name

            WidgetType = forms.Textarea if var_name in ['site_description', 'footer_text'] else forms.TextInput

            self.fields[var_name] = forms.CharField(
                label=var_name.replace('_', ' ').title(),
                widget=WidgetType(attrs={'class': 'form-control'}),
                required=False,
                initial=setting.var_value
            )

            self.fields[f'desc_{var_name}'] = forms.CharField(
                label=f"{var_name} Description",
                widget=forms.TextInput(attrs={'class': 'form-control'}),
                required=False,
                initial=setting.description
            )

    def save(self):
        for name, value in self.cleaned_data.items():
            if name.startswith("desc_"):
                AppVariable.objects.filter(var_name=name.replace("desc_", "")).update(description=value)
            else:
                AppVariable.objects.filter(var_name=name).update(var_value=value)


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactUs
        fields = [ 'fullname', 'email','subject', 'message']

class CSVUploadForm(forms.Form):
    csv_file = forms.FileField(label="Select CSV File")
