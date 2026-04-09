# yvlu_drawer.py
# The "Graphics Engine" for the Yvlu plugin. (Gradient Background Version)

import math
from os.path import exists
from typing import Tuple, List, Dict, Any, Optional, Callable, Set

from PIL import Image, ImageFont, ImageDraw

try:
    from fontTools.ttLib import TTFont, TTCollection
    _FT_AVAILABLE = True
except ImportError:
    TTFont, TTCollection = None, None
    _FT_AVAILABLE = False

from . import yvlu_utils

_FONT_CMAP_CACHE: Dict[str, Set[int]] = {}
_FONT_OBJECT_CACHE: Dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

class _StyledWord:
    def __init__(self, word: str, style: List[str] | None = None, custom_emoji_id: int | None = None):
        self.word, self.style, self.custom_emoji_id = word, style or [], custom_emoji_id

def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    color = color.strip().lstrip('#')
    if len(color) == 3: color = ''.join([c * 2 for c in color])
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)

def _draw_linear_gradient(size: Tuple[int, int], color1: str, color2: str) -> Image.Image:
    w, h = size
    img = Image.new('RGBA', (w, h))
    r1, g1, b1 = _hex_to_rgb(color1)
    r2, g2, b2 = _hex_to_rgb(color2)
    for y in range(h):
        t = y / max(h - 1, 1)
        r, g, b = int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t)
        for x in range(w): img.putpixel((x, y), (r, g, b, 255))
    return img

def _rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    mask_scale = 4
    w, h = size
    large_size = (w * mask_scale, h * mask_scale)
    large_radius = radius * mask_scale
    mask = Image.new('L', large_size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, large_size[0], large_size[1]), 
        radius=large_radius, 
        fill=255
    )
    return mask.resize(size, Image.LANCZOS)

def _circle_crop(image: Image.Image, size: int) -> Image.Image:
    w, h = image.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS).convert('RGBA')
    mask_scale = 4
    mask_large_size = size * mask_scale
    mask = Image.new('L', (mask_large_size, mask_large_size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, mask_large_size, mask_large_size), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    result = Image.new('RGBA', (size, size), (0, 0, 0, 0)) 
    result.paste(image, (0, 0), mask)
    return result

def measure_text_size(text_value, font_obj):
    try:
        bbox = font_obj.getbbox(text_value)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        try: return font_obj.getsize(text_value)
        except Exception: return 0, 0

def _truncate_text(text: str, font, max_width: int) -> str:
    if not text: return ""
    text = text.replace('\n', ' ').strip()
    if measure_text_size(text, font)[0] <= max_width:
        return text
    
    truncated = ""
    for char in text:
        if measure_text_size(truncated + char + "…", font)[0] > max_width:
            break
        truncated += char
    return truncated + "…"

def _determine_primary_font_path(base_path: str = 'plugins/yvlu/') -> str | None:
    mode = yvlu_utils._read_font_mode()
    if mode == '2' and exists(f'{base_path}siyuansongti.otf'): return f'{base_path}siyuansongti.otf'
    if mode == '3':
        custom_name = yvlu_utils._read_text_file(yvlu_utils._custom_font_name_path())
        if custom_name and exists(f'{base_path}{custom_name}'): return f'{base_path}{custom_name}'
    if exists(f'{base_path}zhuziAwa1n.ttf'): return f'{base_path}zhuziAwa1n.ttf'
    if exists(f'{base_path}ZhuZiAWan-2.ttc'): return f'{base_path}ZhuZiAWan-2.ttc'
    return None

def _load_font_cmap(font_path: str) -> Set[int]:
    if font_path in _FONT_CMAP_CACHE: return _FONT_CMAP_CACHE[font_path]
    codepoints: Set[int] = set()
    if not (_FT_AVAILABLE and font_path and exists(font_path)):
        _FONT_CMAP_CACHE[font_path] = codepoints
        return codepoints
    try:
        tt = TTFont(font_path, lazy=True)
        for table in tt['cmap'].tables: codepoints.update(table.cmap.keys())
        tt.close()
    except Exception:
        try:
            if TTCollection:
                ttc = TTCollection(font_path)
                for f in ttc.fonts:
                    for table in f['cmap'].tables: codepoints.update(table.cmap.keys())
                ttc.close()
        except Exception: pass
    _FONT_CMAP_CACHE[font_path] = codepoints
    return codepoints

def _open_font(font_path: str, size: int) -> ImageFont.FreeTypeFont | None:
    key = (font_path, int(size))
    if key in _FONT_OBJECT_CACHE: return _FONT_OBJECT_CACHE[key]
    if not font_path: return None
    try: f = ImageFont.truetype(font_path, size=size, layout_engine=ImageFont.LAYOUT_RAQM)
    except Exception: f = ImageFont.truetype(font_path, size=size)
    _FONT_OBJECT_CACHE[key] = f
    return f

def _font_has_char(font_path: str | None, ch: str) -> bool:
    if not font_path: return False
    return ord(ch) in _load_font_cmap(font_path)

def _make_fallback_resolver(primary_font_path: str | None, font_size: int, base_path: str = 'plugins/yvlu/'):
    yvlu_utils._ensure_fallback_fonts(base_path)
    paths = { "math": f"{base_path}NotoSansMath-Regular.ttf", "sym2": f"{base_path}NotoSansSymbols2-Regular.ttf", "noto": f"{base_path}NotoSans-Regular.ttf", "deja": f"{base_path}DejaVuSans.ttf" }
    def resolver(ch: str) -> ImageFont.FreeTypeFont | None:
        if primary_font_path and _font_has_char(primary_font_path, ch): return _open_font(primary_font_path, font_size)
        for key in ["math", "sym2", "noto", "deja"]:
            if _font_has_char(paths[key], ch): return _open_font(paths[key], font_size)
        return None
    return resolver

from .yvlu_utils import _normalize_text_for_render, _build_styled_words, _is_simple_emoji, _load_emoji_image

def _measure_text_size_with_fallback(text_value: str, base_font: ImageFont.FreeTypeFont, char_font_resolver: Optional[Callable[[str], Optional[ImageFont.FreeTypeFont]]]) -> Tuple[int, int]:
    if not char_font_resolver: return measure_text_size(text_value, base_font)
    width, height = 0, measure_text_size('A', base_font)[1]
    for ch in text_value:
        if ch == '\n': continue
        f = char_font_resolver(ch) or base_font
        w, h = measure_text_size(ch, f)
        width += w
        height = max(height, h)
    return width, height

def _estimate_text_block_width(text: str, entities: List[Dict[str, Any]], font_base: ImageFont.FreeTypeFont, font_size: int, **kwargs) -> int:
    if not text: return 1
    try:
        ascent, descent = font_base.getmetrics()
        line_height = int((ascent + descent) * 1.15)
    except Exception:
        line_height = int(font_size * 1.55)
    words = yvlu_utils._build_styled_words(_normalize_text_for_render(text), entities)
    char_font_resolver = _make_fallback_resolver(_determine_primary_font_path(), font_size) if _FT_AVAILABLE else None
    total_width = 0
    for word in words:
        emo_size = font_size + max(2, font_size // 6)
        if word.custom_emoji_id or (len(word.word) == 1 and _is_simple_emoji(word.word)):
            total_width += emo_size
        else:
            total_width += _measure_text_size_with_fallback(word.word, font_base, char_font_resolver)[0]
    total_area = total_width * line_height
    ideal_width = math.sqrt(total_area)
    min_width = font_size * 8
    max_width = font_size * 30
    return int(max(min_width, min(ideal_width, max_width)))

def _render_rich_text(text: str, entities: List[Dict[str, Any]] | None, font_base: ImageFont.FreeTypeFont, font_color: Tuple[int, int, int], max_width: int, font_size: int, **kwargs) -> Image.Image:
    custom_emoji_images = kwargs.get('custom_emoji_images', {})
    try:
        ascent, descent = font_base.getmetrics()
        line_height = int((ascent + descent) * 1.15)
    except Exception: line_height = int(font_size * 1.55)
    char_font_resolver = _make_fallback_resolver(_determine_primary_font_path(), font_size) if _FT_AVAILABLE else None
    words = yvlu_utils._build_styled_words(_normalize_text_for_render(text), entities)
    lines: List[List[_StyledWord]] = [[]]
    x, wrap_margin = 0, max(2, font_size // 6)
    
    def token_width(word: _StyledWord) -> int:
        emo_size = font_size + max(2, font_size // 6)
        if word.custom_emoji_id or (len(word.word) == 1 and _is_simple_emoji(word.word)): return emo_size
        return _measure_text_size_with_fallback(word.word, font_base, char_font_resolver)[0]

    for word in words:
        if word.word == '\n':
            lines.append([])
            x = 0
            continue
        w = token_width(word)
        if x > 0 and x + w > max_width - wrap_margin:
            lines.append([word])
            x = w
        else:
            lines[-1].append(word)
            x += w
            
    canvas_w = max((sum(token_width(w) for w in line) for line in lines), default=1)
    canvas_h = len(lines) * line_height
    img = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 0
    for line in lines:
        x = 0
        for word in line:
            fill = font_color
            if 'monospace' in word.style: fill = (88, 135, 167)
            if 'mention' in word.style: fill = (106, 183, 236)
            w, h = token_width(word), line_height
            is_emoji = (word.custom_emoji_id and custom_emoji_images.get(word.custom_emoji_id)) or (len(word.word) == 1 and _is_simple_emoji(word.word))
            if is_emoji:
                emo_size = font_size + max(2, font_size // 6)
                emo_img = custom_emoji_images.get(word.custom_emoji_id) or _load_emoji_image(word.word, emo_size)
                if emo_img: img.paste(emo_img.resize((emo_size, emo_size), Image.LANCZOS), (x, y + (line_height - emo_size) // 2), emo_img)
            else:
                cursor_x = x
                for ch in word.word:
                    f = char_font_resolver(ch) if char_font_resolver else font_base
                    if not f: f = font_base
                    d.text((cursor_x, y), ch, fill=fill, font=f)
                    cursor_x += measure_text_size(ch, f)[0]
            if 'strikethrough' in word.style: d.line((x, y + h // 2, x + w, y + h // 2), fill=fill, width=max(1, font_size // 12))
            if 'underline' in word.style: d.line((x, y + h - 2, x + w, y + h - 2), fill=fill, width=max(1, font_size // 12))
            x += w
        y += line_height
    return img

async def _load_user_premium_badge_emoji_img(client, user_entity) -> Image.Image | None:
    if not user_entity or not getattr(user_entity, 'is_premium', False): return None
    doc_id = getattr(getattr(user_entity, 'emoji_status', None), 'custom_emoji_id', None)
    if doc_id:
        try:
            cache_dir = yvlu_utils._custom_emoji_cache_dir()
            cache_path = f"{cache_dir}{doc_id}.png"
            if exists(cache_path): return Image.open(cache_path).convert('RGBA')
        except Exception: pass
    size = 128
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy, r1, r2 = size // 2, size // 2, size * 0.42, size * 0.18
    points = [(int(cx + (r1 if i%2==0 else r2) * math.cos(math.radians(i*36))), int(cy + (r1 if i%2==0 else r2) * math.sin(math.radians(i*36)))) for i in range(10)]
    draw.polygon(points, fill=(255, 215, 0, 255))
    return img

def yvlu_generate(**kwargs) -> Image.Image:
    # Extract all parameters from the unified kwargs dictionary
    name = kwargs.get('name', '')
    text = kwargs.get('text', '')
    avatar_path = kwargs.get('avatar_path')
    path = kwargs.get('path', 'plugins/yvlu/')
    quality_multiplier = kwargs.get('quality_multiplier', 2.0)
    is_sticker_mode = kwargs.get('is_sticker_mode', False)

    user_scale = yvlu_utils._read_font_scale()
    scale = quality_multiplier * user_scale
    
    avatar_size, indent, rect_round_radius = int(50 * scale), int(14 * scale), int(25 * scale)
    
    # --- Font Definitions ---
    text_font_size = int(24 * scale)
    name_font = yvlu_utils.font(path, int(22 * scale))
    text_font = yvlu_utils.font(path, text_font_size)
    reply_font = yvlu_utils.font(path, int(20 * scale))

    # --- Color Palette ---
    name_palette = ['#FF8E86', '#FFA357', '#B18FFF', '#4DD6BF', '#45E8D1', '#7AC9FF', '#FF7FD5']
    user_id = kwargs.get('user_id_for_color')
    name_color = _hex_to_rgb(name_palette[abs(hash(name) if user_id is None else int(user_id)) % len(name_palette)])
    text_color = (255, 255, 255)
    reply_text_color = (230, 230, 230)

    # --- Extract Reply Data from kwargs ---
    reply_name = kwargs.get('reply_name')
    reply_text = kwargs.get('reply_text')
    reply_chat_id = kwargs.get('reply_chat_id')
    nested_reply_name = kwargs.get('nested_reply_name')
    nested_reply_text = kwargs.get('nested_reply_text')
    nested_reply_chat_id = kwargs.get('nested_reply_chat_id')

    # --- Render Main Content Elements ---
    name_img = _render_rich_text(name, [{'type': 'bold', 'offset': 0, 'length': len(name)}], name_font, name_color, 4096, int(22*scale)) if name and not kwargs.get('suppress_sender') else None
    
    # <-- START: DYNAMIC LAYOUT CALCULATION -->
    text_max_width = _estimate_text_block_width(text, kwargs.get('entities'), text_font, text_font_size)
    
    # Apply final constraints based on output mode
    if is_sticker_mode:
        # For stickers, the final visual width should not exceed the target frame size
        IDEAL_VISUAL_WIDTH_1X = 420
        sticker_max_width = int(IDEAL_VISUAL_WIDTH_1X * quality_multiplier)
        text_max_width = min(text_max_width, sticker_max_width)
    else:
        # For images, allow a wider layout but prevent Telegram dimension errors
        image_max_width = int(800 * quality_multiplier)
        text_max_width = min(text_max_width, image_max_width)
    # <-- END: DYNAMIC LAYOUT CALCULATION -->

    text_img = _render_rich_text(text, kwargs.get('entities'), text_font, text_color, text_max_width, text_font_size, custom_emoji_images=kwargs.get('custom_emoji_images')) if text else None
    
    media_img = None
    if kwargs.get('media_path') and exists(kwargs['media_path']):
        with Image.open(kwargs['media_path']) as m:
            max_media_size = text_max_width
            m.thumbnail((max_media_size, max_media_size), Image.LANCZOS)
            media_img = m.convert("RGBA")

    # --- Calculate Content Width ---
    content_w = max((name_img.width if name_img else 0), (text_img.width if text_img else 0), (media_img.width if media_img else 0), 1)

    # --- START: Reply Box Calculation & Rendering ---
    reply_box_img = None
    reply_box_height = 0
    if reply_name and reply_chat_id is not None:
        # Define layout constants
        reply_padding_ver, reply_padding_hor = int(8 * scale), int(10 * scale)
        reply_bar_width, nested_padding = int(4 * scale), int(6 * scale)
        
        nested_reply_img, nested_reply_height = None, 0
        if nested_reply_name and nested_reply_chat_id is not None:
            nested_max_w = content_w - (reply_padding_hor * 2) - reply_bar_width
            nested_name_color = _hex_to_rgb(name_palette[abs(int(nested_reply_chat_id)) % len(name_palette)])
            nested_name_trunc = _truncate_text(nested_reply_name, reply_font, nested_max_w)
            nested_text_trunc = _truncate_text(nested_reply_text, reply_font, nested_max_w)
            _, nested_name_h = measure_text_size(nested_name_trunc, reply_font)
            _, nested_text_h = measure_text_size(nested_text_trunc, reply_font)
            
            nested_reply_height = nested_name_h + nested_text_h + (nested_padding * 2)
            nested_reply_img = Image.new('RGBA', (content_w, nested_reply_height), (0,0,0,0))
            nested_draw = ImageDraw.Draw(nested_reply_img)
            
            nested_bg_mask = _rounded_mask((content_w - reply_padding_hor, nested_reply_height), int(10 * scale))
            nested_bg = Image.new('RGBA', (content_w - reply_padding_hor, nested_reply_height), (0,0,0, 40))
            nested_reply_img.paste(nested_bg, (reply_padding_hor, 0), nested_bg_mask)
            nested_draw.line([(reply_padding_hor, 0), (reply_padding_hor, nested_reply_height)], fill=nested_name_color, width=reply_bar_width)
            
            nested_cursor_x = reply_padding_hor + reply_bar_width + nested_padding
            nested_draw.text((nested_cursor_x, nested_padding), nested_name_trunc, font=reply_font, fill=nested_name_color)
            nested_draw.text((nested_cursor_x, nested_padding + nested_name_h), nested_text_trunc, font=reply_font, fill=reply_text_color)

        reply_max_w = content_w - reply_padding_hor - reply_bar_width
        reply_name_color = _hex_to_rgb(name_palette[abs(int(reply_chat_id)) % len(name_palette)])
        reply_name_trunc = _truncate_text(reply_name, reply_font, reply_max_w)
        reply_text_trunc = _truncate_text(reply_text, reply_font, reply_max_w)
        _, reply_name_h = measure_text_size(reply_name_trunc, reply_font)
        _, reply_text_h = measure_text_size(reply_text_trunc, reply_font)
        
        reply_box_height = reply_name_h + reply_text_h + (reply_padding_ver * 2)
        if nested_reply_img: reply_box_height += nested_reply_height + reply_padding_ver

        reply_box_img = Image.new('RGBA', (content_w, reply_box_height), (0,0,0,0))
        reply_draw = ImageDraw.Draw(reply_box_img)
        reply_draw.line([(0, 0), (0, reply_box_height)], fill=reply_name_color, width=reply_bar_width)
        
        reply_cursor_y, reply_cursor_x = reply_padding_ver, reply_bar_width + reply_padding_hor
        if nested_reply_img:
            reply_box_img.paste(nested_reply_img, (reply_bar_width, reply_cursor_y), nested_reply_img)
            reply_cursor_y += nested_reply_img.height + reply_padding_ver
        
        reply_draw.text((reply_cursor_x, reply_cursor_y), reply_name_trunc, font=reply_font, fill=reply_name_color)
        reply_cursor_y += reply_name_h
        reply_draw.text((reply_cursor_x, reply_cursor_y), reply_text_trunc, font=reply_font, fill=reply_text_color)
    # --- END: Reply Box Calculation & Rendering ---

    # --- Calculate Final Canvas Size ---
    avatar_space = avatar_size + int(10 * scale)
    y_cursor = indent
    if reply_box_img: y_cursor += reply_box_height + int(8 * scale)
    if name_img: y_cursor += name_img.height + int(5 * scale)
    if media_img: y_cursor += media_img.height + int(5 * scale)
    if text_img: y_cursor += text_img.height
    y_cursor += indent
    
    canvas_w = avatar_space + content_w + indent * 2
    canvas_h = max(y_cursor, avatar_size + indent * 2)
    
    # --- Draw Final Image ---
    canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    
    rect_w, rect_h = canvas_w - avatar_space, canvas_h
    rect = _draw_linear_gradient((rect_w, rect_h), '#1b1429', '#30264d')
    mask = _rounded_mask((rect_w, rect_h), rect_round_radius)
    canvas.paste(rect, (avatar_space, 0), mask)
    
    if avatar_path and exists(f'{path}{avatar_path}') and not kwargs.get('suppress_sender'):
        with Image.open(f'{path}{avatar_path}') as avatar_img:
            avatar_canvas = _circle_crop(avatar_img, avatar_size)
            canvas.paste(avatar_canvas, (0, int(5*scale)), avatar_canvas)
            
    y_cursor, content_x = indent, avatar_space + indent
    
    if reply_box_img:
        canvas.paste(reply_box_img, (content_x, y_cursor), reply_box_img)
        y_cursor += reply_box_img.height + int(8 * scale)
    if name_img:
        canvas.paste(name_img, (content_x, y_cursor), name_img)
        y_cursor += name_img.height + int(5 * scale)
    if media_img:
        media_mask = _rounded_mask(media_img.size, int(10 * scale))
        canvas.paste(media_img, (content_x, y_cursor), media_mask)
        y_cursor += media_img.height + int(5 * scale)
    if text_img:
        canvas.paste(text_img, (content_x, y_cursor), text_img)
        
    return canvas

def combine_images(images: List[Image.Image], padding: int = 8) -> Image.Image:
    if not images: return Image.new('RGBA', (1, 1), (0,0,0,0))
    max_w = max(im.width for im in images)
    total_h = sum(im.height for im in images) + padding * (len(images) - 1)
    canvas = Image.new('RGBA', (max_w, total_h), (0, 0, 0, 0))
    y_offset = 0
    for im in images:
        canvas.paste(im, (0, y_offset), im)
        y_offset += im.height + padding
    return canvas