import io
import math
import uuid
import logging
from PIL import Image
from django.conf import settings
import google.genai as genai

from .models import ComplaintResolution

logger = logging.getLogger(__name__)




def generate_order_number():
    """Generates a unique order number for the checkout process."""
    return f"ORD-{uuid.uuid4().hex[:8].upper()}"


# ==============================================================================
# 1. SEMANTIC SEARCH & VECTOR RAG UTILITIES
# ==============================================================================

def calculate_cosine_similarity(vec_a, vec_b):
    """
    Computes mathematical similarity rating between two vector coordinates.
    Returns value between -1.0 (opposite) and 1.0 (identical).
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
        
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    return dot_product / (norm_a * norm_b)


def get_semantically_matching_resolutions(user_raw_text, limit=3, min_threshold=0.38, standard_fallback=None):
    """
    Generates text embeddings using text-embedding-004 and returns top matches.
    If text is empty but image attachments exist, handles request gracefully via fallback text.
    """
    cleaned_text = user_raw_text.strip() if user_raw_text else ""
    
    # Handle image-only updates (Fix A) by injecting structural context if explicit text is absent
    if not cleaned_text:
        if standard_fallback:
            cleaned_text = standard_fallback
        else:
            return []

    try:
        from core.models import AppVariable
        api_key = AppVariable.get_setting('API_3')
    except Exception:
        api_key = getattr(settings, "GEMINI_API_KEY", "")

    if not api_key:
        logger.error("Semantic search aborted: Missing valid GEMINI_API_KEY.")
        return []

    try:
        client = genai.Client(api_key=api_key)
        # Upgraded to text-embedding-004 for improved accuracy and faster response windows
        response = client.models.embed_content(
            model="text-embedding-004",
            contents=cleaned_text,
        )
        query_vector = response.embeddings[0].values
    except Exception as e:
        logger.error(f"Failed to generate search embedding vector: {str(e)}")
        return []

    # Pull candidate dataset cleanly into memory buffer profiles
    candidates = ComplaintResolution.objects.filter(embedding__isnull=False).only(
        'id', 'embedding', 'complaint_summary', 'resolution_script', 'successful_resolution', 'effectiveness_score'
    )
    
    scored_resolutions = []
    for resolution in candidates:
        similarity = calculate_cosine_similarity(query_vector, resolution.embedding)
        if similarity >= min_threshold:
            scored_resolutions.append((similarity, resolution))

    # Sort down by vector similarity match rank, then resolve via historical effectiveness metrics
    scored_resolutions.sort(key=lambda x: (x[0], x[1].effectiveness_score), reverse=True)

    return [item[1] for item in scored_resolutions[:limit]]


def optimize_chat_image_bytes(file_wrapper, max_dimension=1024, quality=80):
    """
    Downsamples uploaded file objects to compressed WebP buffers safely.
    Handles variable canvas transparency vectors cleanly to optimize token allocations.
    """
    try:
        file_wrapper.seek(0)
        img = Image.open(file_wrapper)
        
        # Fixed: Explicitly convert palette files containing transparent alphas to RGBA before separation
        if img.mode == "P" and "transparency" in img.info:
            img = img.convert("RGBA")

        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1]) # Safely target alpha plane channel matrix
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
            
        # Scale bounding calculations symmetrically 
        width, height = img.size
        if width > max_dimension or height > max_dimension:
            scale = max_dimension / max(width, height)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="WEBP", quality=quality, method=4)
        compressed_bytes = output_buffer.getvalue()
        
        # Handle structural sizing metadata logging fields accurately
        original_size = getattr(file_wrapper, 'size', len(compressed_bytes))
        logger.info(f"Optimized image asset: {original_size / 1024:.1f}KB down to {len(compressed_bytes) / 1024:.1f}KB")
        
        return compressed_bytes
        
    except Exception as e:
        logger.error(f"Image compression pipeline broke down: {str(e)}", exc_info=True)
        try:
            file_wrapper.seek(0)
            return file_wrapper.read()
        except Exception:
            return b""

            \

# def get_semantically_matching_resolutions(user_raw_text, limit=3, min_threshold=0.38):
#     """
#     Converts incoming customer text into an on-the-fly search embedding,
#     compares it to saved records, and returns the top matching resolutions.
#     """
#     cleaned_text = user_raw_text.strip() if user_raw_text else ""
#     if not cleaned_text:
#         return []

#     # Credential routing match
#     try:
#         from core.models import AppVariable
#         api_key = AppVariable.get_setting('API_3')
#     except Exception:
#         api_key = getattr(settings, "GEMINI_API_KEY", "")

#     if not api_key:
#         logger.error("Semantic search aborted: Missing valid GEMINI_API_KEY.")
#         return []

#     try:
#         client = genai.Client(api_key=api_key)
#         response = client.models.embed_content(
#             model="gemini-embedding-001",
#             contents=cleaned_text,
#         )
#         query_vector = response.embeddings[0].values
#     except Exception as e:
#         logger.error(f"Failed to generate search embedding vector: {str(e)}")
#         return []

#     # Get resolutions that have embeddings ready
#     candidates = ComplaintResolution.objects.filter(embedding__isnull=False)
    
#     scored_resolutions = []
#     for resolution in candidates:
#         similarity = calculate_cosine_similarity(query_vector, resolution.embedding)
        
#         if similarity >= min_threshold:
#             scored_resolutions.append((similarity, resolution))

#     # Sort descending by vector similarity score, fallback to historical effectiveness
#     scored_resolutions.sort(key=lambda x: (x[0], x[1].effectiveness_score), reverse=True)

#     return [item[1] for item in scored_resolutions[:limit]]


# # ==============================================================================
# # 2. IMAGE COMPRESSION & OPTIMIZATION PIPELINE
# # ==============================================================================

# def optimize_chat_image_bytes(file_wrapper, max_dimension=1024, quality=80):
#     """
#     Reads an uploaded file memory stream, downsizes it safely maintaining aspects,
#     and returns compressed WebP bytes to drastically lower latency and token usage.
#     """
#     try:
#         file_wrapper.seek(0)
#         img = Image.open(file_wrapper)
        
#         # Convert color profiles like RGBA/P to standard RGB for WebP conversion compliance
#         if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
#             # Create a clean white background canvas fallback
#             background = Image.new("RGB", img.size, (255, 255, 255))
#             background.paste(img, mask=img.convert("RGBA").split()[3])
#             img = background
#         elif img.mode != "RGB":
#             img = img.convert("RGB")
            
#         # Scale dimensions gracefully down if it exceeds maximum production layout constraints
#         width, height = img.size
#         if width > max_dimension or height > max_dimension:
#             if width > height:
#                 new_width = max_dimension
#                 new_height = int(height * (max_dimension / width))
#             else:
#                 new_height = max_dimension
#                 new_width = int(width * (max_dimension / height))
            
#             img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
#         # Save output bytes direct into memory array buffer streams
#         output_buffer = io.BytesIO()
#         img.save(output_buffer, format="WEBP", quality=quality, method=4)
        
#         compressed_bytes = output_buffer.getvalue()
#         logger.info(f"Optimized layout attachment from {file_wrapper.size / 1024:.1f}KB down to {len(compressed_bytes) / 1024:.1f}KB")
        
#         return compressed_bytes
        
#     except Exception as e:
#         logger.error(f"Image compression pipeline broke down: {str(e)}")
#         # Failure safety barrier: Fallback to reading raw file bytes uncompressed
#         try:
#             file_wrapper.seek(0)
#             return file_wrapper.read()
#         except Exception:
#             return b""

            