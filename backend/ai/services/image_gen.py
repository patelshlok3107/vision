"""
Vision Image Generation Service — High-Quality Production Pipeline

Supports multiple providers with quality-first configuration:
- OpenAI gpt-image-1 / dall-e-3 (if OPENAI_API_KEY set)  → highest quality hd
- Pollinations gen.pollinations.ai flux (free, no key)    → flux, high quality
- HuggingFace FLUX.1 / SD3.5 (if HF_API_KEY set)

Never exposes API keys to frontend.
All quality is produced by the generation model itself — never faked via CSS.
"""
import re
import logging
import os
import time
import urllib.parse
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style-aware quality boosters — each style gets a distinct suffix
# ---------------------------------------------------------------------------
_STYLE_BOOSTERS = {
    "realistic": (
        "photorealistic photograph, DSLR, 85mm lens, f/1.8, natural lighting, "
        "realistic skin and texture, accurate anatomy and proportions, sharp focus, "
        "realistic shadows and reflections, natural depth of field, accurate perspective, "
        "high detail, 8k, ultra-realistic, professional photographic composition"
    ),
    "photorealistic": (
        "photorealistic photograph, DSLR, 85mm lens, f/1.8, natural lighting, "
        "realistic skin and texture, accurate anatomy and proportions, sharp focus, "
        "realistic shadows and reflections, natural depth of field, accurate perspective, "
        "high detail, 8k, ultra-realistic, professional photographic composition"
    ),
    "cinematic": (
        "cinematic photograph, dramatic lighting, volumetric light, anamorphic lens, "
        "shallow depth of field, film grain subtle, highly detailed, realistic textures, "
        "professional color grading, 8k, sharp focus"
    ),
    "anime": "anime artwork, vibrant colors, detailed anime illustration, clean lines, studio quality",
    "cartoon": "cartoon artwork, playful illustration, bold colors, clean lines, highly detailed",
    "3d": "high-quality 3D render, octane render, physically based rendering, ultra detailed, sharp",
    "product": "professional commercial product photography, studio lighting, white background subtle, sharp focus, highly detailed, accurate materials",
    "illustration": "detailed illustration, artistic, rich colors, highly detailed, sharp",
    "watercolor": "watercolor painting, soft brush strokes, artistic, highly detailed",
    "oil painting": "oil painting, rich textures, artistic, highly detailed",
    "fantasy": "fantasy artwork, highly detailed illustration, dramatic lighting, sharp, intricate",
    "minimalist": "minimalist style, clean, simple composition, highly detailed, sharp",
}

# Short aliases for detection
_STYLE_KEYWORDS = {
    "realistic": "realistic",
    "photorealistic": "realistic",
    "real photo": "realistic",
    "real-life": "realistic",
    "photograph": "realistic",
    "professional photography": "realistic",
    "cinematic": "cinematic",
    "anime": "anime",
    "cartoon": "cartoon",
    " 3d": "3d",
    "3d render": "3d",
    "product": "product",
    "commercial": "product",
    "illustration": "illustration",
    "watercolor": "watercolor",
    "oil painting": "oil painting",
    "fantasy": "fantasy",
    "minimalist": "minimalist",
    "dragon": "fantasy",
}

_IMAGE_GEN_PHRASES = [
    "generate image", "generate an image", "generate a image", "create image",
    "create an image", "create a image", "make image", "make an image",
    "draw", "render image", "generate photo", "create photo", "generate picture",
    "create picture", "generate portrait", "realistic image", "cinematic image",
    "generate a realistic", "create a realistic", "photorealistic",
    "generate a landscape", "create a landscape", "image of", "picture of", "photo of",
    "generate an illustration", "create an illustration", "generate artwork",
]

_IMAGE_GEN_SINGLE = re.compile(
    r"\b(generate|create|make|draw|render|produce)\b.*\b(image|photo|picture|portrait|illustration|artwork|landscape|scene|wallpaper)\b",
    re.IGNORECASE,
)

_CODE_WEBSITE_BLOCKLIST = re.compile(
    r"\b(website|web site|e-?commerce|landing page|dashboard|component|api|react|vue|angular|html|css|javascript|typescript|function|class |npm|build app|deploy)\b",
    re.IGNORECASE,
)
_EDIT_KEYWORDS = re.compile(r"\b(remove background|edit|variation|make it|change to|convert to|transform)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------
def is_image_generation_request(message: str, has_image: bool = False) -> bool:
    if not message or not message.strip():
        return False
    low = message.lower().strip()
    if has_image:
        if any(kw in low for kw in ["what's in", "what is in", "analyze this", "describe this", "what do you see"]):
            return False
        if any(kw in low for kw in ["create", "generate", "make", "variation", "similar", "edit", "change", "transform", "remove background", "black background"]):
            if _CODE_WEBSITE_BLOCKLIST.search(low) and "image" not in low:
                return False
            if any(v in low for v in ["create", "generate", "make", "similar", "variation", "edit", "remove", "change"]):
                return True
    if any(kw in low for kw in ["create a website", "create website", "build a website", "generate a website", "ecommerce website", "e-commerce", "landing page"]):
        if "create a website with" in low and "image" in low:
            return False
        if "website" in low or "ecommerce" in low:
            if not any(p in low for p in ["hero image", "generate image for"]):
                return False
    for phrase in _IMAGE_GEN_PHRASES:
        if phrase in low:
            if _CODE_WEBSITE_BLOCKLIST.search(low) and "image" not in low:
                continue
            return True
    if _IMAGE_GEN_SINGLE.search(low):
        if _CODE_WEBSITE_BLOCKLIST.search(low) and "image" not in low:
            return False
        return True
    short_create = re.match(r"^(create|generate|make|draw)\s+(a\s+)?[a-z0-9 ]{2,40}\.?$", low)
    if short_create and not _CODE_WEBSITE_BLOCKLIST.search(low) and len(low) < 60:
        if any(w in low for w in ["function", "component", "api", "page", "app", "file", "class"]):
            return False
        return True
    return False

def is_image_edit_request(message: str, has_image: bool) -> bool:
    if not has_image or not message:
        return False
    low = message.lower()
    return bool(_EDIT_KEYWORDS.search(low) and any(w in low for w in ["image", "picture", "photo", "background", "it", "this"]))

def detect_style(prompt: str) -> str:
    low = prompt.lower()
    # Priority order: explicit style words first
    for key in ["anime", "cartoon", "3d render", "3d", "product", "illustration", "watercolor", "oil painting", "fantasy", "cinematic", "photorealistic", "realistic", "photograph", "minimalist"]:
        if key in low:
            mapped = _STYLE_KEYWORDS.get(key, key)
            # normalize photorealistic -> realistic
            if mapped == "realistic":
                return "realistic"
            return mapped if mapped in _STYLE_BOOSTERS else key
    # Heuristic: if prompt says fantasy creature but no style, treat as fantasy
    if any(w in low for w in ["dragon", "wizard", "elf", "magic", "fantasy"]):
        return "fantasy"
    if any(w in low for w in ["realistic", "photorealistic", "photo", "photograph"]):
        return "realistic"
    # Default: realistic for high-quality expectation, unless explicitly artistic
    return ""

# ---------------------------------------------------------------------------
# Prompt handling — preserves user intent, enhances short prompts, never genericizes
# ---------------------------------------------------------------------------
def enhance_prompt(prompt: str, style_hint: str = "") -> str:
    original = prompt.strip()
    if not original:
        return "a beautiful landscape, highly detailed, 8k"
    word_count = len(original.split())
    # Detect if already detailed (long + contains visual descriptors)
    has_detail = any(k in original.lower() for k in ["lighting", "camera", "composition", "cinematic", "photorealistic", "detailed", "realistic", "neon", "reflection", "depth", "perspective", "4k", "8k", "photograph", "stadium", "sunset", "rain", "tokyo"])
    is_detailed = word_count >= 14 or (word_count >= 9 and has_detail)

    style = detect_style(original) or (style_hint.lower().strip() if style_hint else "") or ""
    # Normalize style_hint
    if style_hint:
        style = style_hint.lower().strip() if style_hint.lower().strip() in _STYLE_BOOSTERS else style
    # Choose booster based on detected style; default to realistic only if user wants realism
    # For fantasy/dragon without realism, don't force photorealism
    if not style:
        # Default to realistic for photographic prompts; keep fantasy as fantasy
        low = original.lower()
        if any(w in low for w in ["dragon", "fantasy", "anime", "cartoon", "illustration", "3d"]):
            style = "fantasy" if "dragon" in low or "fantasy" in low else ""
        else:
            style = "realistic"

    if is_detailed:
        # Preserve creative direction — only add non-redundant quality booster
        low = original.lower()
        # If style word already present, don't duplicate (avoid cinematic + cinematic booster)
        if style and style.lower() in low:
            return original
        booster = _STYLE_BOOSTERS.get(style, "")
        if booster:
            # Avoid duplicate if already contains similar terms
            if "photorealistic" in low or "realistic" in low or "8k" in low:
                return original
            # Append booster without rewriting
            return f"{original}, {booster}"
        return original

    # Short prompt: expand intelligently, preserve core subject
    cleaned = re.sub(r"^(create|generate|make|draw)\s+(an?\s+)?(image|photo|picture|portrait)?\s*(of\s+)?", "", original, flags=re.IGNORECASE).strip()
    if not cleaned or len(cleaned.split()) < 2:
        cleaned = original
    cleaned = re.sub(r"^(create|generate|make|draw)\s+(a\s+)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.strip(" .")
    if not cleaned:
        cleaned = original.strip(" .")

    booster = _STYLE_BOOSTERS.get(style, _STYLE_BOOSTERS["realistic"])
    # For very short like "a cow", add natural context
    if len(cleaned.split()) <= 3:
        # Add natural environment for animals/objects if not specified
        low_c = cleaned.lower()
        if "cow" in low_c and "field" not in low_c:
            cleaned = f"{cleaned} standing naturally in a green rural field, golden hour lighting"
        elif "car" in low_c and "tokyo" not in low_c and "city" not in low_c:
            pass  # keep as is, booster will add
        elif "ronaldo" in low_c or "football" in low_c or "player" in low_c:
            if "stadium" not in low_c:
                cleaned = f"{cleaned} in a packed stadium"
    return f"{cleaned}, {booster}"

# ---------------------------------------------------------------------------
# Provider config — env-driven, quality-first
# ---------------------------------------------------------------------------
def get_image_config() -> dict:
    size_raw = getattr(settings, "IMAGE_SIZE", "") or os.environ.get("IMAGE_SIZE", "") or "1024x1024"
    quality = getattr(settings, "IMAGE_QUALITY", "") or os.environ.get("IMAGE_QUALITY", "") or "high"
    model = getattr(settings, "IMAGE_MODEL", "") or os.environ.get("IMAGE_MODEL", "") or ""
    provider = getattr(settings, "IMAGE_PROVIDER", "") or os.environ.get("IMAGE_PROVIDER", "") or ""
    # Parse size
    w, h = 1024, 1024
    try:
        if "x" in size_raw.lower():
            a, b = size_raw.lower().split("x")
            w, h = int(a.strip()), int(b.strip())
            w = max(256, min(w, 2048))
            h = max(256, min(h, 2048))
    except:
        pass
    # Provider auto-detect if not set
    if not provider:
        if getattr(settings, "OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""):
            provider = "openai"
        elif os.environ.get("HUGGINGFACE_API_KEY", "") or os.environ.get("HF_API_KEY", ""):
            provider = "huggingface"
        else:
            provider = "pollinations"
    else:
        provider = provider.lower().strip()

    # Default model per provider if not set
    if not model:
        if provider == "openai":
            model = getattr(settings, "OPENAI_IMAGE_MODEL", "gpt-image-1")
        elif provider == "pollinations":
            model = "flux"  # flux is high-quality realistic, not turbo/zimage
        elif provider == "huggingface":
            model = "black-forest-labs/FLUX.1-dev"

    quality = quality.lower().strip() if quality else "high"
    return {"provider": provider, "model": model, "quality": quality, "width": w, "height": h, "size_raw": size_raw}

def get_provider() -> str:
    return get_image_config()["provider"]

# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def _openai_generate(prompt: str, width: int = 1024, height: int = 1024, model: str = "", quality: str = "high") -> str:
    key = getattr(settings, "OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY not configured")
    model = model or getattr(settings, "OPENAI_IMAGE_MODEL", "gpt-image-1")
    # Map sizes: gpt-image-1 supports 1024x1024, 1024x1536, 1536x1024, auto; dall-e-3 limited
    size = f"{width}x{height}"
    if model == "dall-e-3" and size not in ("1024x1024", "1792x1024", "1024x1792"):
        size = "1024x1024"
    # gpt-image-1 supports hd quality
    q = "hd" if quality in ("high", "hd", "ultra", "4k") else "high" if quality in ("high",) else "standard" if model == "dall-e-3" else quality
    if model == "dall-e-3" and q not in ("standard", "hd"):
        q = "hd"
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": model, "prompt": prompt[:32000], "n": 1, "size": size}
    # quality/style mapping
    if model in ("dall-e-3", "gpt-image-1", "gpt-image-1-mini", "gpt-image-1.5"):
        payload["quality"] = q
        if model == "dall-e-3":
            payload["style"] = "natural"  # photorealistic prefers natural over vivid
    resp = requests.post(url, json=payload, headers=headers, timeout=90)
    if not resp.ok:
        raise RuntimeError(f"OpenAI image generation failed {resp.status_code}: {resp.text[:800]}")
    data = resp.json()
    item = data["data"][0]
    img_url = item.get("url") or item.get("b64_json")
    if not img_url:
        raise RuntimeError("OpenAI did not return image URL")
    if not img_url.startswith("http"):
        img_url = f"data:image/png;base64,{img_url}"
    return img_url

def _huggingface_generate(prompt: str, width: int = 1024, height: int = 1024, model: str = "") -> str:
    key = os.environ.get("HUGGINGFACE_API_KEY", "") or os.environ.get("HF_API_KEY", "") or getattr(settings, "HUGGINGFACE_API_KEY", "")
    if not key:
        raise ValueError("HUGGINGFACE_API_KEY not configured")
    model = model or "black-forest-labs/FLUX.1-dev"
    # Prefer Flux inference endpoint
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # FLUX and SD expect width/height via parameters
    payload = {"inputs": prompt[:2000], "parameters": {"width": width, "height": height, "num_inference_steps": 28}}
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    if not resp.ok:
        raise RuntimeError(f"HuggingFace failed {resp.status_code}: {resp.text[:800]}")
    # HF returns raw image bytes for this endpoint; if json with error then handled above
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        # Some models return json with base64
        try:
            j = resp.json()
            if "error" in j:
                raise RuntimeError(j["error"][:500])
        except:
            pass
    import base64
    b64 = base64.b64encode(resp.content).decode()
    # Detect mime
    mime = "image/png"
    if resp.content[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"

def _pollinations_generate(prompt: str, width: int = 1024, height: int = 1024, model: str = "flux", enhance: bool = False, quality: str = "high", seed: int = None) -> str:
    """
    Uses Pollinations high-quality endpoint.
    - If POLLINATIONS_API_KEY present: https://gen.pollinations.ai/image/{prompt}?model=flux (hd quality)
    - Else: legacy https://image.pollinations.ai/prompt/{prompt} which still serves flux free without key
      (keeps high quality without requiring paid key)
    enhance=True lets pollinations rewrite prompt for better quality, but only for short prompts.
    """
    encoded = urllib.parse.quote(prompt[:1500], safe="")
    if seed is None:
        seed = int(time.time() * 1000) % 2147483647
        try:
            import random as _rnd
            seed = (seed + _rnd.randint(0, 999999)) % 2147483647
        except:
            pass
    effective_model = model or "flux"
    if effective_model.lower() in ("flux-pro", "flux-pro-1"):
        effective_model = "flux"
    # Detect key
    poll_key = os.environ.get("POLLINATIONS_API_KEY", "") or (getattr(settings, "POLLINATIONS_API_KEY", "") if hasattr(settings, "POLLINATIONS_API_KEY") else "") or ""
    if not poll_key:
        poll_key = os.environ.get("POLLINATIONS_KEY", "") or ""
    # Choose endpoint: gen.pollinations.ai requires key for most models now, legacy image.pollinations.ai is free
    if poll_key:
        # Authenticated high-quality path: gen.pollinations.ai with flux
        qs_parts = [
            f"model={urllib.parse.quote(effective_model, safe='')}",
            f"width={width}",
            f"height={height}",
            f"seed={seed}",
            f"nologo=true",
            f"nofeed=true",
            f"enhance={str(enhance).lower()}",
            f"safe=false",
            f"key={urllib.parse.quote(poll_key, safe='')}",
        ]
        qs = "&".join(qs_parts)
        url = f"https://gen.pollinations.ai/image/{encoded}?{qs}"
    else:
        # Free high-quality path: legacy image.pollinations.ai still serves flux without key
        # Params supported: model, width, height, seed, enhance, nologo, nofeed, safe
        qs_parts = [
            f"model={urllib.parse.quote(effective_model, safe='')}",
            f"width={width}",
            f"height={height}",
            f"seed={seed}",
            f"nologo=true",
            f"enhance={str(enhance).lower()}",
        ]
        qs = "&".join(qs_parts)
        url = f"https://image.pollinations.ai/prompt/{encoded}?{qs}"
    return url

def generate_image(prompt: str, width: int = 1024, height: int = 1024, style: str = "", enhance: bool = None) -> dict:
    """
    Generate high-quality image via configured provider.
    - Never upscales a bad image; model itself must produce quality.
    - No silent low-quality placeholder fallback — retry then error.
    - Preserves user prompt intent; enhances only short/generic prompts.
    - Style-differentiated: realistic/cinematic/anime etc produce actually different outputs.
    Returns dict: {url: str, prompt_used: str, provider: str, model: str, width, height, quality}
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt required for image generation")
    prompt = prompt.strip()[:32000]
    cfg = get_image_config()
    provider = cfg["provider"]
    model = cfg["model"]
    quality = cfg["quality"]
    # Allow caller to override size if explicitly passed, else use config size
    # But if caller passes default 1024 and config has higher, prefer config for high quality
    if width == 1024 and height == 1024 and (cfg["width"] != 1024 or cfg["height"] != 1024):
        width, height = cfg["width"], cfg["height"]
    # Clamp to provider limits (pollinations allows up to 2048, openai 1792 etc)
    width = max(256, min(width, 2048))
    height = max(256, min(height, 2048))

    # Determine style
    detected_style = detect_style(prompt) or (style.lower().strip() if style else "")
    if style and style.lower().strip() in _STYLE_BOOSTERS:
        detected_style = style.lower().strip()
    # Enhance logic: short prompts enhance, detailed preserve
    # enhance param drives pollinations rewrite; for others we pre-enhance via enhance_prompt
    word_count = len(prompt.split())
    has_detail = any(k in prompt.lower() for k in ["lighting", "camera", "composition", "cinematic", "photorealistic", "detailed", "realistic", "neon", "reflection", "depth", "perspective", "stadium", "sunset", "tokyo", "rain"])
    is_detailed = word_count >= 14 or (word_count >= 9 and has_detail)

    if enhance is None:
        # Auto decide: enhance only for short/generic, not for detailed creative direction
        enhance = not is_detailed

    # Build final prompt_used via style-aware enhancement
    if len(prompt.split()) < 12 or not is_detailed:
        prompt_used = enhance_prompt(prompt, style_hint=detected_style)
    else:
        # Detailed: preserve but ensure quality booster if not already present and style needs it
        prompt_used = enhance_prompt(prompt, style_hint=detected_style) if detected_style else prompt
        if prompt_used == prompt and detected_style and detected_style in _STYLE_BOOSTERS:
            # If already detailed and no booster added (because already had realism words), keep original to avoid genericizing
            pass

    # For pollinations, if enhance is True, we let server enhance; if False we send our enhanced prompt_used
    # For other providers, we always send prompt_used (pre-enhanced)
    logger.info("[ImageGen] provider=%s model=%s quality=%s style=%s enhance=%s width=%s height=%s prompt_used=%.140s", provider, model, quality, detected_style, enhance, width, height, prompt_used)

    start = time.time()
    last_err = None
    # Retry once on failure (don't fallback to worse model)
    for attempt in range(2):
        try:
            if provider == "openai":
                url = _openai_generate(prompt_used, width, height, model=model, quality=quality)
            elif provider == "huggingface":
                url = _huggingface_generate(prompt_used, width, height, model=model)
            else:  # pollinations
                # pollinations flux high quality
                url = _pollinations_generate(prompt_used, width, height, model=model, enhance=enhance, quality=quality)
            elapsed = int((time.time() - start) * 1000)
            logger.info("[ImageGen] success provider=%s model=%s elapsed=%dms url=%.90s", provider, model, elapsed, url)
            return {"url": url, "prompt_used": prompt_used, "provider": provider, "model": model, "width": width, "height": height, "quality": quality}
        except Exception as e:
            last_err = e
            logger.warning("[ImageGen] attempt %s failed provider=%s model=%s error=%s", attempt+1, provider, model, str(e)[:400])
            if attempt == 0:
                # Retry with fresh seed (pollinations seed randomization already) and small delay
                time.sleep(0.6)
                continue
            break
    # No silent low-quality fallback — surface error
    logger.error("[ImageGen] failed after retry provider=%s model=%s error=%s", provider, model, last_err)
    raise RuntimeError(f"Image generation failed: {str(last_err)[:600]}")

def generate_image_variation(base_prompt: str, edit_instruction: str, width: int = 1024, height: int = 1024) -> dict:
    """
    Combine base prompt with edit instruction for variation requests like "make it winter".
    Preserves original intent, appends variation.
    """
    combined = f"{base_prompt}, {edit_instruction.strip().lstrip('.')}"
    combined = re.sub(r",\s*,", ",", combined)
    # Detect style of variation to keep consistency
    style = detect_style(base_prompt) or detect_style(edit_instruction)
    return generate_image(combined, width, height, style=style)
