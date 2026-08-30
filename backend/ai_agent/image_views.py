"""
AI Image Generation API views.
POST /api/ai/generate-image/
GET  /api/ai/generate-image/status/ (health)
"""
import logging
import time
import re
from django.conf import settings
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status as http_status
from ai.services.image_gen import generate_image, enhance_prompt, is_image_generation_request, get_provider

logger = logging.getLogger(__name__)

# Simple in-memory rate limiting
_rate_store = {}  # key -> list[timestamps]

def _rate_limited(key: str, limit: int = 10, window: int = 60) -> bool:
    now = time.time()
    lst = _rate_store.get(key, [])
    lst = [t for t in lst if now - t < window]
    _rate_store[key] = lst
    if len(lst) >= limit:
        return True
    lst.append(now)
    _rate_store[key] = lst
    return False

class ImageGenerateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Auth check: allow guest but rate limit stricter
        user = getattr(request, 'user', None)
        is_guest = not user or not user.is_authenticated
        ip = request.META.get('REMOTE_ADDR', 'unknown')
        rate_key = f"img:{user.id}" if not is_guest else f"img:guest:{ip}"
        limit = 5 if is_guest else 20
        if _rate_limited(rate_key, limit=limit, window=60):
            return Response({"error": "Rate limited. Please wait a moment before generating another image."}, status=429)

        prompt = (request.data.get('prompt') or request.data.get('message') or "").strip()
        # Also accept 'prompt' from JSON
        if not prompt:
            return Response({"error": "Prompt required. Describe what image you want."}, status=400)
        if len(prompt) > 2000:
            return Response({"error": "Prompt too long (max 2000 characters)."}, status=400)
        # Validate not code request masquerading
        if not is_image_generation_request(prompt) and len(prompt.split()) < 3:
            # Still allow if user explicitly passed via image endpoint
            pass

        # Aspect ratio / size — respect IMAGE_SIZE env default but allow override
        # Default from config
        from ai.services.image_gen import get_image_config
        cfg = get_image_config()
        width = cfg["width"]
        height = cfg["height"]
        # Override via aspect param
        aspect = (request.data.get('aspect_ratio') or request.data.get('aspect') or "").strip()
        if aspect in ("16:9", "16x9"):
            width, height = 1280, 720
        elif aspect in ("9:16", "9x16"):
            width, height = 720, 1280
        elif aspect in ("4:3",):
            width, height = 1024, 768
        elif aspect in ("3:2",):
            width, height = 1024, 680
        elif aspect in ("1:1", "square"):
            width, height = 1024, 1024
        # Allow explicit width/height to override
        try:
            w_raw = request.data.get('width', None)
            h_raw = request.data.get('height', None)
            if w_raw is not None or h_raw is not None:
                w = int(w_raw) if w_raw is not None else width
                h = int(h_raw) if h_raw is not None else height
                if 256 <= w <= 2048 and 256 <= h <= 2048:
                    width, height = w, h
        except: pass

        style = (request.data.get('style') or "").strip().lower()
        # enhance: auto if not provided, else bool
        enhance_raw = request.data.get('enhance', None)
        if enhance_raw is None or enhance_raw == "auto":
            enhance = None
        else:
            enhance = str(enhance_raw).lower() not in ("0", "false", "off", "no") if isinstance(enhance_raw, str) else bool(enhance_raw)

        # Conversation context for variation
        conversation_id = request.data.get('conversation_id')
        # If variation request like "make it winter", combine with last prompt if available
        low = prompt.lower().strip()
        is_variation = len(prompt) < 80 and any(kw in low for kw in ["make it", "change to", "convert to", "variation", "edit", "now", "more", "less"])
        if is_variation and conversation_id:
            try:
                from ai_agent.models import Conversation, Message
                conv = Conversation.objects.filter(id=conversation_id).first()
                if conv:
                    # Find last assistant message containing image prompt
                    last_msg = Message.objects.filter(conversation=conv, role="assistant").order_by("-created_at").first()
                    if last_msg and last_msg.metadata and last_msg.metadata.get("image_prompt"):
                        base = last_msg.metadata["image_prompt"]
                        prompt = f"{base}, {prompt}"
                        logger.info("[ImageGen] Variation combined: %s", prompt[:120])
            except Exception as e:
                logger.warning("[ImageGen] variation lookup failed: %s", e)

        try:
            result = generate_image(prompt, width=width, height=height, style=style, enhance=enhance)
        except ValueError as ve:
            return Response({"error": str(ve)}, status=400)
        except Exception as e:
            logger.error("[ImageGen] generation failed: %s", e)
            # Don't expose raw backend error
            return Response({"error": "Couldn't generate the image. Please try again.", "detail": str(e)[:300]}, status=500)

        # Store in conversation if provided
        metadata_extra = {}
        if conversation_id:
            try:
                from ai_agent.models import Conversation, Message, Attachment
                from django.utils import timezone
                user = request.user if not is_guest else None
                if user and conversation_id:
                    conv = Conversation.objects.filter(id=conversation_id, user=user).first()
                    if conv:
                        # Save assistant message with image markdown + metadata
                        md = f"![Generated Image]({result['url']})\n\n*Prompt: {result['prompt_used'][:300]}*"
                        Message.objects.create(
                            conversation=conv,
                            role="assistant",
                            content=md,
                            metadata={"image_url": result["url"], "image_prompt": result["prompt_used"], "image_provider": result["provider"], "is_image_generation": True}
                        )
                        conv.last_message_at = timezone.now()
                        conv.save(update_fields=["last_message_at", "updated_at"])
            except Exception as e:
                logger.warning("[ImageGen] failed to save to conversation: %s", e)

        return Response({
            "url": result["url"],
            "prompt_used": result["prompt_used"],
            "provider": result["provider"],
            "width": result["width"],
            "height": result["height"],
        })

    def get(self, request):
        # Health / capability check
        provider = get_provider()
        has_openai = bool(getattr(settings, "OPENAI_API_KEY", "") or __import__("os").environ.get("OPENAI_API_KEY", ""))
        return Response({"provider": provider, "available": True, "has_openai_key": has_openai})

class ImageEditView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        return Response({"error": "Image editing is not yet supported by the current provider. Generation with reference image will be used instead. Use /api/ai/generate-image/ with a prompt."}, status=501)
