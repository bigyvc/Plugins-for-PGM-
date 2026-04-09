# ██╗   ██╗██╗   ██╗██╗     ██╗   ██╗
# ╚██╗ ██╔╝██║   ██║██║     ██║   ██║
#  ╚████╔╝ ██║   ██║██║     ██║   ██║
#   ╚██╔╝  ██║   ██║██║     ██║   ██║
#    ██║   ╚██████╔╝███████╗╚██████╔╝
#    ╚═╝    ╚═════╝ ╚══════╝ ╚═════╝
# Yvlu (Quote) Plugin - Combined and Simplified (Syntax FIXED)
#
# 本插件能将 Telegram 消息渲染成精美的语录图片或贴纸。
# 它支持处理文字、Emoji、自定义 Emoji、回复、媒体预览以及多条消息合并。
#
# --- 模块用法说明 ---
#
# 1. 核心命令 (Core Commands):
#
#   -q
#     - 功能: 制作语录并以贴纸 (WebP) 格式发送。这是最常用的命令。
#     - 用法:
#       - 回复一条消息: `-q`
#       - 回复一条消息并引用多条 (正向): `-q 5` (从回复处开始，共5条)
#       - 回复一条消息并引用多条 (反向): `-q -5` (从回复处往上，共5条)
#       - 制作自己的文字语录: `-q 这是我的语录内容`
#       - 回复一条消息并替换其文本: `-q 新的语录文本`
#
#   -qimg
#     - 功能: 制作语录并以高清图片 (PNG) 格式发送。图片无 512px 尺寸限制，更清晰。
#     - 用法: 与 `-q` 完全相同。
#
# 2. 设置命令 (Settings Commands):
#
#   -qset [1|2|3]
#     - 功能: 设置渲染语录时使用的字体。
#     - 参数:
#       - `1`: (默认) 使用插件内置的“逐字安慰体”。
#       - `2`: 使用“思源宋体”(首次使用会自动下载)。
#       - `3`: 使用自定义 URL 字体 (需先用 -qurl 设置)。
#     - 示例: `-qset 2`
#
#   -qurl <字体直链>
#     - 功能: 设置一个自定义字体的直接下载链接 (URL)，并自动切换到字体模式 3。
#     - 示例: `-qurl https://example.com/fonts/MyFont.ttf`
#
#   -qsize <倍率|百分比|reset>
#     - 功能: 调整语录卡片的整体大小，包括字体和布局。
#     - 参数:
#       - 倍率: 如 `1.2` (放大20%), `0.8` (缩小20%)。
#       - 百分比: 如 `120%`, `80%`。
#       - `reset`: 恢复默认大小 (1.0)。
#     - 示例: `-qsize 110%`
#
# ==============================================================================

import logging
import math
import re
import glob as _glob
import unicodedata as _ud
from io import BytesIO
from os import makedirs, remove
from os.path import exists
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import requests
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, enums
from pyrogram.types import Chat, Message, MessageEntity, User

from pagermaid.listener import listener
from pagermaid.utils import alias_command

try:
    from fontTools.ttLib import TTFont, TTCollection
    _FT_AVAILABLE = True
except ImportError:
    TTFont, TTCollection = None, None
    _FT_AVAILABLE = False

# ==============================================================================
# SECTION 1: UTILITY FUNCTIONS (from yvlu_utils.py)
# ==============================================================================

# --- Constants ---
SIYUAN_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/siyuansongti.otf'
FALLBACK_MATH_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/NotoSansMath-Regular.ttf'
FALLBACK_SYMBOLS2_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/NotoSansSymbols2-Regular.ttf'
FALLBACK_NOTO_SANS_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/NotoSans-Regular.ttf'
FALLBACK_DEJAVU_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/DejaVuSans.ttf'

# --- File I/O and Settings Management ---
def _font_mode_path(): return 'plugins/yvlu/font_mode.txt'
def _custom_url_path(): return 'plugins/yvlu/custom_url.txt'
def _custom_font_name_path(): return 'plugins/yvlu/custom_font_name.txt'
def _font_scale_path(): return 'plugins/yvlu/font_scale.txt'

def _emoji_cache_dir():
    base = 'plugins/yvlu/emoji_cache/'
    if not exists(base): makedirs(base, exist_ok=True)
    return base

def _custom_emoji_cache_dir():
    base = 'plugins/yvlu/emoji_custom/'
    if not exists(base): makedirs(base, exist_ok=True)
    return base

def _read_text_file(path: str, default: str = '') -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read().strip()
    except FileNotFoundError:
        return default

def _write_text_file(path: str, content: str):
    with open(path, 'w', encoding='utf-8') as f: f.write(content or '')

def _read_font_mode(): return _read_text_file(_font_mode_path(), '1')
def _write_font_mode(mode: str): _write_text_file(_font_mode_path(), mode)

def _read_font_scale():
    try:
        scale_str = _read_text_file(_font_scale_path(), '1.0').replace('%', '')
        scale = float(scale_str)
        if scale > 10: scale /= 100.0
        return max(0.6, min(3.0, scale))
    except (ValueError, TypeError): return 1.0

def _write_font_scale(value: Union[float, str]): _write_text_file(_font_scale_path(), str(value))

# --- Network and Font Downloading ---
def download_file_if_not_exists(url: str, target_path: str):
    if not exists(target_path):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            with open(target_path, 'wb') as f: f.write(resp.content)
        except requests.RequestException as e:
            logging.warning(f"Could not download {url}. Reason: {e}")

def _ensure_chosen_font(base_path: str, mode: str):
    if mode == '2': download_file_if_not_exists(SIYUAN_URL, f"{base_path}siyuansongti.otf")
    elif mode == '3':
        url = _read_text_file(_custom_url_path())
        if url:
            tail = extract_filename_from_url(url)
            download_file_if_not_exists(url, f"{base_path}{tail}")

def _ensure_fallback_fonts(base_path: str = 'plugins/yvlu/'):
    if not exists(base_path): makedirs(base_path, exist_ok=True)
    pairs = [
        (f"{base_path}NotoSansMath-Regular.ttf", FALLBACK_MATH_URL),
        (f"{base_path}NotoSansSymbols2-Regular.ttf", FALLBACK_SYMBOLS2_URL),
        (f"{base_path}NotoSans-Regular.ttf", FALLBACK_NOTO_SANS_URL),
        (f"{base_path}DejaVuSans.ttf", FALLBACK_DEJAVU_URL)
    ]
    for local_path, url in pairs:
        download_file_if_not_exists(url, local_path)

def font(path, size):
    font_file = _determine_primary_font_path(path)
    if not font_file or not exists(font_file):
        font_file = f'{path}zhuziAwa1n.ttf'
    try:
        return ImageFont.truetype(font_file, size=size, layout_engine=ImageFont.LAYOUT_RAQM)
    except Exception:
        try:
            return ImageFont.truetype(font_file, size=size)
        except Exception:
            return ImageFont.load_default()

# --- Text and Entity Processing ---
def _get_command_content(command_text: str) -> str:
    """Robustly gets content after a command, handling various whitespaces."""
    parts = (command_text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""

def _normalize_name(text: str) -> str:
    s = _ud.normalize('NFD', text or '')
    return ''.join(ch for ch in s if _ud.combining(ch) == 0)

def _normalize_text_for_render(text: str) -> str:
    if not text: return ''
    return ''.join(_ud.normalize('NFKC', ch) if len(_ud.normalize('NFKC', ch)) == 1 else ch for ch in text)

def extract_filename_from_url(url: str) -> str:
    try:
        tail = url.split('/')[-1].split('?', 1)[0]
        return tail if tail else 'custom_font.ttf'
    except Exception:
        return 'custom_font.ttf'

def _pyrogram_entities_to_dicts(entities: Optional[List[MessageEntity]]) -> List[Dict[str, Any]]:
    if not entities: return []
    result = []
    for ent in entities:
        typ_map = {
            enums.MessageEntityType.BOLD: 'bold',
            enums.MessageEntityType.ITALIC: 'italic',
            enums.MessageEntityType.UNDERLINE: 'underline',
            enums.MessageEntityType.STRIKETHROUGH: 'strikethrough',
            enums.MessageEntityType.CODE: 'monospace',
            enums.MessageEntityType.PRE: 'monospace',
            enums.MessageEntityType.SPOILER: 'spoiler',
            enums.MessageEntityType.CUSTOM_EMOJI: 'custom_emoji'
        }
        typ = typ_map.get(ent.type, 'mention')
        item = {'type': typ, 'offset': ent.offset, 'length': ent.length}
        if typ == 'custom_emoji':
            item['custom_emoji_id'] = ent.custom_emoji_id
        result.append(item)
    return result

def get_adjusted_entities(message: Message) -> List[Dict[str, Any]]:
    command_text = message.text or message.caption or ""
    content = _get_command_content(command_text)
    if not content or not (message.entities or message.caption_entities):
        return []

    prefix_units = len(command_text[:-len(content)].encode('utf-16-le')) // 2
    content_units = len(content.encode('utf-16-le')) // 2
    full_entities = _pyrogram_entities_to_dicts(message.entities or message.caption_entities)
    adjusted = []
    for ent in full_entities:
        u_off, u_len = ent['offset'] - prefix_units, ent['length']
        if u_off + u_len <= 0 or u_off >= content_units:
            continue
        new_off = max(0, u_off)
        new_len = min(u_len - (new_off - u_off), content_units - new_off)
        if new_len > 0:
            ent['offset'], ent['length'] = new_off, new_len
            adjusted.append(ent)
    return adjusted

def _file_placeholder_from_document(doc) -> str:
    fname = getattr(doc, 'file_name', None) or ''
    return f"[文件] {fname.strip()}" if fname else "[文件]"

# --- Media and Image Handling ---
async def _download_static_media_preview(client, message: Message, out_dir: str, base_name: str) -> Optional[str]:
    try:
        out_path = f"{out_dir}{base_name}.png"
        media = message.sticker or message.photo or message.animation or message.document
        if media:
            file_id = (max(media.thumbs, key=lambda t: t.width * t.height).file_id
                       if getattr(media, 'thumbs', None) and media.thumbs
                       else getattr(media, 'file_id', None))
            if file_id:
                tmp_full = await client.download_media(file_id)
                if tmp_full:
                    with Image.open(tmp_full) as img:
                        img.convert("RGBA").save(out_path, "PNG")
                    remove(tmp_full)
                    return out_path
    except Exception:
        return None
    return None

def image_to_sticker_bytes(image: Image.Image) -> BytesIO:
    w, h = image.size
    if w > 512 or h > 512:
        if w > h:
            new_w, new_h = 512, int(h * 512 / w)
        else:
            new_w, new_h = int(w * 512 / h), 512
        image = image.resize((new_w, new_h), Image.LANCZOS)
    sticker_bytes = BytesIO()
    sticker_bytes.name = "sticker.webp"
    image.save(sticker_bytes, "WEBP")
    sticker_bytes.seek(0)
    return sticker_bytes

# --- Emoji Handling ---
def _is_simple_emoji(ch: str) -> bool:
    if not ch: return False
    code = ord(ch)
    return (0x1F300 <= code <= 0x1FAFF or 0x1F600 <= code <= 0x1F64F or
            0x2600 <= code <= 0x27BF or 0x1F170 <= code <= 0x1F1FF)

def _twemoji_filename_for_char(ch: str) -> str:
    return format(ord(ch), 'x') + '.png'

def _load_emoji_image(ch: str, size: int) -> Optional[Image.Image]:
    if not _is_simple_emoji(ch): return None
    cache_dir = _emoji_cache_dir()
    fname = _twemoji_filename_for_char(ch)
    fpath = cache_dir + fname
    try:
        if not exists(fpath):
            url = f'https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/{fname}'
            download_file_if_not_exists(url, fpath)
        if exists(fpath):
            img = Image.open(fpath).convert('RGBA')
            return img.resize((size, size), Image.LANCZOS) if size > 0 else img
    except Exception:
        return None
    return None
    
# --- Styled Word Builder ---
class _StyledWord:
    def __init__(self, word: str, style: Optional[List[str]] = None, custom_emoji_id: Optional[int] = None):
        self.word, self.style, self.custom_emoji_id = word, style or [], custom_emoji_id

def _is_cjk(char: str) -> bool:
    """Checks if a character is a CJK Unified Ideograph."""
    code = ord(char)
    # Common CJK Unified Ideographs range
    return 0x4e00 <= code <= 0x9fff

def _build_styled_words(text: str, entities: Optional[List[Dict[str, Any]]]):
    text = (text or '').replace('\r', '')
    if not text:
        return []

    chars = list(text)
    styled = [{"char": c, "style": [], "custom_emoji_id": None} for c in chars]

    if entities:
        for ent in entities:
            try:
                start, end = ent['offset'], ent['offset'] + ent['length']
                for i in range(start, end):
                    if i < len(styled):
                        style = ent['type']
                        if style not in styled[i]['style']:
                            styled[i]['style'].append(style)
                        if style == 'custom_emoji':
                            styled[i]['custom_emoji_id'] = ent.get('custom_emoji_id')
            except Exception:
                continue

    words: List[_StyledWord] = []
    i = 0
    while i < len(chars):
        style_info = styled[i]
        char = chars[i]

        if char.isspace():
            words.append(_StyledWord(char, style_info['style']))
            i += 1
            continue

        # Start of a new word
        j = i
        # Determine the script type of the first character (CJK or not)
        is_first_char_cjk = _is_cjk(char)

        while j < len(chars):
            current_char = chars[j]
            current_style_info = styled[j]

            # Break conditions for the current word:
            # 1. Is a space character
            # 2. Style or custom emoji ID changes
            # 3. Script type changes (from CJK to non-CJK or vice-versa)
            if (current_char.isspace() or
                    current_style_info['style'] != style_info['style'] or
                    current_style_info['custom_emoji_id'] != style_info['custom_emoji_id'] or
                    _is_cjk(current_char) != is_first_char_cjk):
                break
            j += 1
        
        word_str = "".join(chars[i:j])
        is_single_char = len(word_str) == 1
        
        words.append(_StyledWord(
            word_str,
            style_info['style'],
            style_info['custom_emoji_id'] if is_single_char else None
        ))
        i = j
        
    return words

# ==============================================================================
# SECTION 2: DRAWING ENGINE (from yvlu_drawer.py)
# ==============================================================================

_FONT_CMAP_CACHE: Dict[str, Set[int]] = {}
_FONT_OBJECT_CACHE: Dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

# --- Basic Drawing Helpers ---
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

# --- Font and Text Measurement ---
def measure_text_size(text_value, font_obj):
    try:
        bbox = font_obj.getbbox(text_value)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        try:
            return font_obj.getsize(text_value)
        except Exception:
            return 0, 0

def _truncate_text(text: str, font_obj, max_width: int) -> str:
    if not text: return ""
    text = text.replace('\n', ' ').strip()
    if measure_text_size(text, font_obj)[0] <= max_width:
        return text

    truncated = ""
    for char in text:
        if measure_text_size(truncated + char + "…", font_obj)[0] > max_width:
            break
        truncated += char
    return truncated + "…"

def _determine_primary_font_path(base_path: str = 'plugins/yvlu/') -> Optional[str]:
    mode = _read_font_mode()
    if mode == '2' and exists(f'{base_path}siyuansongti.otf'):
        return f'{base_path}siyuansongti.otf'
    if mode == '3':
        custom_name = _read_text_file(_custom_font_name_path())
        if custom_name and exists(f'{base_path}{custom_name}'):
            return f'{base_path}{custom_name}'
    if exists(f'{base_path}zhuziAwa1n.ttf'):
        return f'{base_path}zhuziAwa1n.ttf'
    if exists(f'{base_path}ZhuZiAWan-2.ttc'):
        return f'{base_path}ZhuZiAWan-2.ttc'
    return None

def _load_font_cmap(font_path: str) -> Set[int]:
    if font_path in _FONT_CMAP_CACHE: return _FONT_CMAP_CACHE[font_path]
    codepoints: Set[int] = set()
    if not (_FT_AVAILABLE and font_path and exists(font_path)):
        _FONT_CMAP_CACHE[font_path] = codepoints
        return codepoints
    try:
        tt = TTFont(font_path, lazy=True)
        for table in tt['cmap'].tables:
            codepoints.update(table.cmap.keys())
        tt.close()
    except Exception:
        try:
            if TTCollection:
                ttc = TTCollection(font_path)
                for f in ttc.fonts:
                    for table in f['cmap'].tables:
                        codepoints.update(table.cmap.keys())
                ttc.close()
        except Exception:
            pass
    _FONT_CMAP_CACHE[font_path] = codepoints
    return codepoints

def _open_font(font_path: str, size: int) -> Optional[ImageFont.FreeTypeFont]:
    key = (font_path, int(size))
    if key in _FONT_OBJECT_CACHE: return _FONT_OBJECT_CACHE[key]
    if not font_path: return None
    try:
        f = ImageFont.truetype(font_path, size=size, layout_engine=ImageFont.LAYOUT_RAQM)
    except Exception:
        f = ImageFont.truetype(font_path, size=size)
    _FONT_OBJECT_CACHE[key] = f
    return f

def _font_has_char(font_path: Optional[str], ch: str) -> bool:
    if not font_path: return False
    return ord(ch) in _load_font_cmap(font_path)

def _make_fallback_resolver(primary_font_path: Optional[str], font_size: int, base_path: str = 'plugins/yvlu/'):
    _ensure_fallback_fonts(base_path)
    paths = {
        "math": f"{base_path}NotoSansMath-Regular.ttf",
        "sym2": f"{base_path}NotoSansSymbols2-Regular.ttf",
        "noto": f"{base_path}NotoSans-Regular.ttf",
        "deja": f"{base_path}DejaVuSans.ttf"
    }
    def resolver(ch: str) -> Optional[ImageFont.FreeTypeFont]:
        if primary_font_path and _font_has_char(primary_font_path, ch):
            return _open_font(primary_font_path, font_size)
        for key in ["math", "sym2", "noto", "deja"]:
            if _font_has_char(paths[key], ch):
                return _open_font(paths[key], font_size)
        return None
    return resolver

def _measure_text_size_with_fallback(text_value: str, font_base: ImageFont.FreeTypeFont, char_font_resolver: Optional[Callable[[str], Optional[ImageFont.FreeTypeFont]]]) -> Tuple[int, int]:
    if not char_font_resolver: return measure_text_size(text_value, font_base)
    width, height = 0, measure_text_size('A', font_base)[1]
    for ch in text_value:
        if ch == '\n': continue
        f = char_font_resolver(ch) or font_base
        w, h = measure_text_size(ch, f)
        width += w
        height = max(height, h)
    return width, height

# --- Rich Text and Element Rendering ---
def _render_rich_text(text: str, entities: Optional[List[Dict[str, Any]]], font_base: ImageFont.FreeTypeFont, font_color: Tuple[int, int, int], max_width: int, font_size: int, **kwargs) -> Image.Image:
    custom_emoji_images = kwargs.get('custom_emoji_images', {})
    try:
        ascent, descent = font_base.getmetrics()
        line_height = int((ascent + descent) * 1.15)
    except Exception:
        line_height = int(font_size * 1.55)
    char_font_resolver = _make_fallback_resolver(_determine_primary_font_path(), font_size) if _FT_AVAILABLE else None
    words = _build_styled_words(_normalize_text_for_render(text), entities)
    
    # REWRITTEN: Intelligent line-wrapping logic
    lines: List[List[_StyledWord]] = [[]]
    if not words: # Handle empty text case
        return Image.new('RGBA', (1, line_height), (0, 0, 0, 0))

    current_line_width = 0
    space_width = _measure_text_size_with_fallback(" ", font_base, char_font_resolver)[0]

    def token_width(word: _StyledWord) -> int:
        emo_size = font_size + max(2, font_size // 6)
        if word.custom_emoji_id or (len(word.word) == 1 and _is_simple_emoji(word.word)):
            return emo_size
        return _measure_text_size_with_fallback(word.word, font_base, char_font_resolver)[0]

    for word in words:
        if word.word == '\n':
            lines.append([])
            current_line_width = 0
            continue
        
        # Skip standalone spaces from original text, we'll add them logically
        if word.word.isspace():
            continue

        word_width = token_width(word)

        # Handle single words that are too long
        if word_width > max_width and len(word.word) > 1:
            if current_line_width > 0: # Start a new line for the long word
                lines.append([])
                current_line_width = 0
            
            temp_word_str = ""
            for char in word.word:
                char_w = _measure_text_size_with_fallback(char, font_base, char_font_resolver)[0]
                if current_line_width + char_w > max_width:
                    if temp_word_str:
                        lines[-1].append(_StyledWord(temp_word_str, word.style))
                    lines.append([])
                    temp_word_str = char
                    current_line_width = char_w
                else:
                    temp_word_str += char
                    current_line_width += char_w
            if temp_word_str:
                lines[-1].append(_StyledWord(temp_word_str, word.style))
            continue

        # If the line is not empty, check if adding a space and the new word fits
        if lines[-1]:
            if current_line_width + space_width + word_width > max_width:
                # Doesn't fit, start a new line
                lines.append([word])
                current_line_width = word_width
            else:
                # Fits, add a space and then the word
                lines[-1].append(_StyledWord(" ", [])) # Add a logical space
                lines[-1].append(word)
                current_line_width += space_width + word_width
        else:
            # First word on a new line
            lines[-1].append(word)
            current_line_width = word_width

    # Calculate final canvas size
    canvas_w = 0
    for line in lines:
        line_w = sum(token_width(w) for w in line)
        canvas_w = max(canvas_w, line_w)
    canvas_w = min(canvas_w, max_width)
    canvas_h = len(lines) * line_height
    
    img = Image.new('RGBA', (int(canvas_w), int(canvas_h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 0
    for line in lines:
        x = 0
        for word in line:
            fill = font_color
            if 'monospace' in word.style: fill = (88, 135, 167)
            if 'mention' in word.style: fill = (106, 183, 236)
            w, h = token_width(word), line_height
            is_emoji = (word.custom_emoji_id and custom_emoji_images.get(word.custom_emoji_id)) or \
                       (len(word.word) == 1 and _is_simple_emoji(word.word))
            if is_emoji:
                emo_size = font_size + max(2, font_size // 6)
                emo_img = custom_emoji_images.get(word.custom_emoji_id) or _load_emoji_image(word.word, emo_size)
                if emo_img:
                    img.paste(emo_img.resize((emo_size, emo_size), Image.LANCZOS),
                              (int(x), int(y + (line_height - emo_size) // 2)), emo_img)
            else:
                cursor_x = x
                effective_font_resolver = char_font_resolver or (lambda c: font_base)
                for ch in word.word:
                    f = effective_font_resolver(ch) or font_base
                    ch_w = measure_text_size(ch, f)[0]
                    if x + ch_w <= canvas_w + 1: # Add tolerance for rounding
                        d.text((cursor_x, y), ch, fill=fill, font=f)
                        cursor_x += ch_w
            if 'strikethrough' in word.style:
                d.line((x, y + h // 2, x + w, y + h // 2), fill=fill, width=max(1, font_size // 12))
            if 'underline' in word.style:
                d.line((x, y + h - 2, x + w, y + h - 2), fill=fill, width=max(1, font_size // 12))
            x += w
        y += line_height
    return img

async def _load_user_premium_badge_emoji_img(client, user_entity) -> Optional[Image.Image]:
    if not user_entity or not getattr(user_entity, 'is_premium', False):
        return None
    doc_id = getattr(getattr(user_entity, 'emoji_status', None), 'custom_emoji_id', None)
    if doc_id:
        try:
            cache_dir = _custom_emoji_cache_dir()
            cache_path = f"{cache_dir}{doc_id}.png"
            if exists(cache_path):
                return Image.open(cache_path).convert('RGBA')
        except Exception:
            pass
    size = 128
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy, r1, r2 = size // 2, size // 2, size * 0.42, size * 0.18
    points = [(int(cx + (r1 if i % 2 == 0 else r2) * math.cos(math.radians(i * 36))),
               int(cy + (r1 if i % 2 == 0 else r2) * math.sin(math.radians(i * 36)))) for i in range(10)]
    draw.polygon(points, fill=(255, 215, 0, 255))
    return img

# --- Main Image Generation Function ---
def yvlu_generate(**kwargs) -> Image.Image:
    name = kwargs.get('name', '')
    text = kwargs.get('text', '')
    avatar_path = kwargs.get('avatar_path')
    path = kwargs.get('path', 'plugins/yvlu/')
    quality_multiplier = kwargs.get('quality_multiplier', 2.0)
    is_sticker_mode = kwargs.get('is_sticker_mode', False)

    user_scale = _read_font_scale()
    scale = quality_multiplier * user_scale
    
    avatar_size, indent, rect_round_radius = int(50 * scale), int(14 * scale), int(25 * scale)
    
    text_font_size = int(24 * scale)
    name_font = font(path, int(22 * scale))
    text_font = font(path, text_font_size)
    reply_font = font(path, int(20 * scale))

    name_palette = ['#FF8E86', '#FFA357', '#B18FFF', '#4DD6BF', '#45E8D1', '#7AC9FF', '#FF7FD5']
    user_id = kwargs.get('user_id_for_color')
    name_color = _hex_to_rgb(name_palette[abs(hash(name) if user_id is None else int(user_id)) % len(name_palette)])
    text_color = (255, 255, 255)
    reply_text_color = (230, 230, 230)

    reply_name = kwargs.get('reply_name')
    reply_text = kwargs.get('reply_text')
    reply_chat_id = kwargs.get('reply_chat_id')
    nested_reply_name = kwargs.get('nested_reply_name')
    nested_reply_text = kwargs.get('nested_reply_text')
    nested_reply_chat_id = kwargs.get('nested_reply_chat_id')

    name_img = _render_rich_text(name, [{'type': 'bold', 'offset': 0, 'length': len(name)}], name_font, name_color, 4096, int(22*scale)) if name and not kwargs.get('suppress_sender') else None
    
    BASE_STICKER_LAYOUT_WIDTH = 420
    BASE_IMAGE_LAYOUT_WIDTH = 800

    if is_sticker_mode:
        text_max_width = int(BASE_STICKER_LAYOUT_WIDTH * scale)
    else:
        text_max_width = int(BASE_IMAGE_LAYOUT_WIDTH * scale)
        
    text_img = _render_rich_text(text, kwargs.get('entities'), text_font, text_color, text_max_width, text_font_size, custom_emoji_images=kwargs.get('custom_emoji_images')) if text else None
    
    media_img = None
    if kwargs.get('media_path') and exists(kwargs['media_path']):
        with Image.open(kwargs['media_path']) as m:
            max_media_size = text_max_width
            m.thumbnail((max_media_size, max_media_size), Image.LANCZOS)
            media_img = m.convert("RGBA")

    content_w = max(
        (name_img.width if name_img else 0), 
        (text_img.width if text_img else 0), 
        (media_img.width if media_img else 0), 
        int(100 * scale) if text else 1 
    )

    reply_box_img = None
    reply_box_height = 0
    if reply_name and reply_chat_id is not None:
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

    avatar_space = avatar_size + int(10 * scale)
    y_cursor = indent
    if reply_box_img: y_cursor += reply_box_height + int(8 * scale)
    if name_img: y_cursor += name_img.height + int(5 * scale)
    if media_img: y_cursor += media_img.height + int(5 * scale)
    if text_img: y_cursor += text_img.height
    y_cursor += indent
    
    canvas_w = avatar_space + content_w + indent * 2
    canvas_h = max(y_cursor, avatar_size + indent * 2)
    
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


# ==============================================================================
# SECTION 3: MAIN PLUGIN LOGIC & LISTENERS (from yvlu.py)
# ==============================================================================

q_cmd = alias_command('q')
q_set_cmd = alias_command('qset')
q_url_cmd = alias_command('qurl')
q_size_cmd = alias_command('qsize')
q_img_cmd = alias_command('qimg')

# --- Settings Commands ---
@listener(command=q_set_cmd,
          description=f"设置语录字体：`-{q_set_cmd} 1` 原字体；`-{q_set_cmd} 2` 思源宋体；`-{q_set_cmd} 3` 自定义URL字体。",
          parameters="[1|2|3]")
async def quote_set(client: Client, message: Message):
    try:
        command_text = message.text or message.caption or ""
        arg = _get_command_content(command_text)
        if arg not in ('1', '2', '3'):
            await message.edit(f'用法：-{q_set_cmd} 1 | 2 | 3（默认1；3为自定义URL字体）')
            return
        _write_font_mode(arg)
        if arg == '2':
            await message.edit('设置字体为思源宋体（下载中…')
            _ensure_chosen_font('plugins/yvlu/', '2')
        elif arg == '3':
            await message.edit('设置字体为自定义URL字体（下载中…')
            _ensure_chosen_font('plugins/yvlu/', '3')
        await message.edit(f'字体模式已设置为 {arg}。')
    except Exception as e:
        logging.error(f"Quote-set failed: {e}", exc_info=True)
        await message.edit('设置失败。')

@listener(command=q_url_cmd,
          description="设置自定义字体URL。",
          parameters="<url>")
async def quote_url(client: Client, message: Message):
    try:
        command_text = message.text or message.caption or ""
        arg = _get_command_content(command_text)
        if not arg:
            await message.edit(f'用法：-{q_url_cmd} <字体直链>')
            return
        if not exists('plugins/yvlu/'): makedirs('plugins/yvlu/', exist_ok=True)
        _write_text_file(_custom_url_path(), arg)
        tail = extract_filename_from_url(arg)
        _write_text_file(_custom_font_name_path(), tail)
        await message.edit('下载自定义字体中…')
        download_file_if_not_exists(arg, f"plugins/yvlu/{tail}")
        _write_font_mode('3')
        _ensure_chosen_font('plugins/yvlu/', '3')
        await message.edit(f'已设置自定义URL为模式3，并保存文件名 `{tail}`。')
    except Exception as e:
        logging.error(f"Quote-url failed: {e}", exc_info=True)
        await message.edit('设置失败，请检查链接。')

@listener(command=q_size_cmd,
          description="设置整体字体与布局倍率。",
          parameters="<scale|percent|reset>")
async def quote_size(client: Client, message: Message):
    try:
        command_text = message.text or message.caption or ""
        arg = _get_command_content(command_text)
        if not arg:
            await message.edit(f'用法：-{q_size_cmd} <倍率|百分比|reset>')
            return
        if arg.lower() in ('reset', 'default'):
            _write_font_scale('1.0')
            await message.edit('已重置字体与布局倍率为 1.0。')
            return
        val = arg.replace('%', '')
        try:
            scale = float(val)
            if scale > 10: scale /= 100.0
        except ValueError:
            await message.edit('解析倍率失败，请输入如 1.2 或 120%')
            return
        scale = max(0.6, min(3.0, scale))
        _write_font_scale(scale)
        await message.edit(f'已设置字体与布局倍率为 {scale:.2f}。')
    except Exception as e:
        logging.error(f"Quote-size failed: {e}", exc_info=True)
        await message.edit('设置失败。')

# --- Main Logic Helper Functions ---
async def _get_sender_info(message: Message) -> dict:
    sender = message.from_user or message.sender_chat
    if isinstance(sender, User):
        first, last = sender.first_name or '', sender.last_name or ''
        name = _normalize_name(first).strip()
        if last: name = (name + ' ' + _normalize_name(last)).strip()
        photo_id = sender.photo.big_file_id if sender.photo else None
        return {"name": name, "id": sender.id, "photo_id": photo_id, "entity": sender}
    if isinstance(sender, Chat):
        name = sender.title or "未知频道"
        photo_id = sender.photo.big_file_id if sender.photo else None
        return {"name": name, "id": sender.id, "photo_id": photo_id, "entity": sender}
    return {"name": "匿名", "id": 0, "photo_id": None, "entity": None}

async def _fetch_and_cache_custom_emojis(client: Client, emoji_ids: list[int]) -> dict[int, Image.Image]:
    if not emoji_ids: return {}
    images, cache_dir = {}, _custom_emoji_cache_dir()
    try:
        stickers = await client.get_custom_emoji_stickers(list(set(emoji_ids)))
        for sticker in stickers:
            doc_id = sticker.custom_emoji_id
            cache_path = f"{cache_dir}{doc_id}.png"
            try:
                if not exists(cache_path):
                    dl_path = await client.download_media(sticker.file_id)
                    if dl_path:
                        with Image.open(dl_path) as img:
                            img.convert('RGBA').save(cache_path, 'PNG')
                        remove(dl_path)
                if exists(cache_path):
                    images[doc_id] = Image.open(cache_path).convert('RGBA')
            except Exception as e:
                logging.warning(f"Failed to process custom emoji {doc_id}: {e}")
    except Exception as e:
        logging.error(f"Could not fetch custom emoji stickers: {e}", exc_info=True)
    return images

async def _get_reply_data(client: Client, message: Message) -> dict:
    if not message.reply_to_message:
        return {}
    
    l1_reply_msg = message.reply_to_message
    if l1_reply_msg.sticker:
        return {}
    
    l1_sender_info = await _get_sender_info(l1_reply_msg)
    l1_text = l1_reply_msg.text or l1_reply_msg.caption or ''
    if l1_reply_msg.document:
        l1_text += (' ' if l1_text else '') + _file_placeholder_from_document(l1_reply_msg.document)
    
    reply_data = {
        "reply_name": l1_sender_info['name'],
        "reply_text": l1_text,
        "reply_entities": _pyrogram_entities_to_dicts(l1_reply_msg.entities or l1_reply_msg.caption_entities),
        "reply_chat_id": l1_sender_info['id'],
        "reply_name_tail_emoji_img": await _load_user_premium_badge_emoji_img(client, l1_sender_info['entity'])
    }

    l2_reply_id = l1_reply_msg.reply_to_message_id
    if l2_reply_id:
        try:
            l2_reply_msg = await client.get_messages(l1_reply_msg.chat.id, l2_reply_id)
            if l2_reply_msg and not l2_reply_msg.sticker and (l2_reply_msg.from_user or l2_reply_msg.sender_chat):
                l2_sender_info = await _get_sender_info(l2_reply_msg)
                l2_text = l2_reply_msg.text or l2_reply_msg.caption or ''
                if l2_reply_msg.document:
                    l2_text += (' ' if l2_text else '') + _file_placeholder_from_document(l2_reply_msg.document)
                
                reply_data["nested_reply_name"] = l2_sender_info['name']
                reply_data["nested_reply_text"] = l2_text
                reply_data["nested_reply_chat_id"] = l2_sender_info['id']
        except Exception:
            pass
            
    return reply_data

# REFACTORED: This function is now a "dumb" renderer.
async def _render_single_message_image(
    client: Client, 
    msg_for_metadata: Message, 
    sender_info: dict, 
    text_to_render: str,
    entities_to_render: list,
    custom_emojis_cache: Optional[dict] = None, 
    prev_uid: Optional[int] = None, 
    quality_multiplier: float = 2.0, 
    as_photo: bool = False
) -> Optional[Image.Image]:
    
    media_path = await _download_static_media_preview(client, msg_for_metadata, 'plugins/yvlu/', f"__m_{msg_for_metadata.id}")
    
    if custom_emojis_cache is None:
        emoji_ids = [e['custom_emoji_id'] for e in entities_to_render if e.get('custom_emoji_id')]
        custom_emoji_images = await _fetch_and_cache_custom_emojis(client, emoji_ids)
    else:
        custom_emoji_images = custom_emojis_cache

    reply_data = await _get_reply_data(client, msg_for_metadata)
    name_tail_img = await _load_user_premium_badge_emoji_img(client, sender_info['entity'])
    avatar_rel = f"{sender_info['id']}.jpg" if sender_info['id'] and exists(f"plugins/yvlu/{sender_info['id']}.jpg") else None
    
    if not media_path and msg_for_metadata.document:
        text_to_render += ('\n' if text_to_render else '') + _file_placeholder_from_document(msg_for_metadata.document)

    suppress_sender = bool(prev_uid is not None and sender_info['id'] == prev_uid)

    draw_kwargs = {
        'name': sender_info['name'],
        'text': text_to_render,
        'avatar_path': avatar_rel,
        'path': 'plugins/yvlu/',
        'media_path': media_path,
        'entities': entities_to_render,
        'user_id_for_color': sender_info['id'],
        'custom_emoji_images': custom_emoji_images,
        'name_tail_emoji_img': name_tail_img,
        'suppress_sender': suppress_sender,
        'quality_multiplier': quality_multiplier,
        'is_sticker_mode': not as_photo
    }
    draw_kwargs.update(reply_data)
    
    image = yvlu_generate(**draw_kwargs)

    if media_path and exists(media_path): remove(media_path)
    return image

# --- Core Logic Handler ---
async def _quote_logic_handler(client: Client, message: Message, as_photo: bool = False):
    try:
        if not exists('plugins/yvlu/'): makedirs('plugins/yvlu/', exist_ok=True)
        _ensure_chosen_font('plugins/yvlu/', _read_font_mode())
        _ensure_fallback_fonts('plugins/yvlu/')
        if not exists('plugins/yvlu/zhuziAwa1n.ttf'):
            await message.edit('首次运行，下载预置字体中。。。')
            download_file_if_not_exists('https://raw.githubusercontent.com/dhd2333/test/main/zhuziAwa1n.ttf', 'plugins/yvlu/zhuziAwa1n.ttf')
        
        quality_multiplier = 5.0

        reply_message = message.reply_to_message
        command_text = message.text or message.caption or ""
        content = _get_command_content(command_text)
        final_image, avatar_paths_to_clean = None, set()

        # Case 1: Self-quote (e.g., -q Hello World)
        if not reply_message and content:
            sender_info = await _get_sender_info(message)
            if sender_info['photo_id']:
                p = await client.download_media(sender_info['photo_id'], file_name=f"plugins/yvlu/{sender_info['id']}.jpg")
                if p: avatar_paths_to_clean.add(p)
            
            text_to_render = content
            entities_to_render = get_adjusted_entities(message)
            
            final_image = await _render_single_message_image(
                client, message, sender_info, text_to_render, entities_to_render,
                quality_multiplier=quality_multiplier, as_photo=as_photo
            )
        
        # Case 2: Replying to a message
        elif reply_message:
            # Subcase 2a: Multi-message quote (e.g., -q 5)
            if content.lstrip('-').isdigit() and content != "0":
                n = int(content)
                num_messages = abs(n)
                start_id = reply_message.id
                message_ids = range(start_id, start_id + num_messages) if n > 0 else range(start_id - num_messages + 1, start_id + 1)
                msgs = [m for m in await client.get_messages(message.chat.id, message_ids) if m]
                
                all_emoji_ids = []
                for m in msgs:
                    if m.entities:
                        all_emoji_ids.extend([e.custom_emoji_id for e in m.entities if e.type == enums.MessageEntityType.CUSTOM_EMOJI])

                all_custom_emoji_images = await _fetch_and_cache_custom_emojis(client, all_emoji_ids)
                rendered_images, prev_uid = [], None
                
                for m in msgs:
                    sender_info = await _get_sender_info(m)
                    if sender_info['photo_id']:
                        p = await client.download_media(sender_info['photo_id'], file_name=f"plugins/yvlu/{sender_info['id']}.jpg")
                        if p: avatar_paths_to_clean.add(p)
                    
                    text_to_render = m.text or m.caption or ""
                    entities_to_render = _pyrogram_entities_to_dicts(m.entities or m.caption_entities)

                    img = await _render_single_message_image(
                        client, m, sender_info, text_to_render, entities_to_render,
                        all_custom_emoji_images, prev_uid, quality_multiplier, as_photo
                    )
                    if img: rendered_images.append(img)
                    prev_uid = sender_info['id']
                if rendered_images: final_image = combine_images(rendered_images)
            
            # Subcase 2b: Single message quote (with or without text override)
            else:
                sender_info = await _get_sender_info(reply_message)
                if sender_info['photo_id']:
                    p = await client.download_media(sender_info['photo_id'], file_name=f"plugins/yvlu/{sender_info['id']}.jpg")
                    if p: avatar_paths_to_clean.add(p)
                
                if content: # User provided new text to override
                    text_to_render = content
                    entities_to_render = []
                else: # User did not provide new text, use original
                    text_to_render = reply_message.text or reply_message.caption or ""
                    entities_to_render = _pyrogram_entities_to_dicts(reply_message.entities or reply_message.caption_entities)

                final_image = await _render_single_message_image(
                    client, reply_message, sender_info, text_to_render, entities_to_render,
                    quality_multiplier=quality_multiplier, as_photo=as_photo
                )
        
        # Case 3: Invalid command usage
        else:
            await message.edit('你需要回复一条消息，或在命令后提供文本。')
            return

        if final_image:
            reply_to_id = message.reply_to_message_id or (reply_message.id if reply_message else None)
            if as_photo:
                photo_bytes = BytesIO()
                photo_bytes.name = "yvlu.png"
                final_image.save(photo_bytes, "PNG")
                photo_bytes.seek(0)
                await client.send_photo(message.chat.id, photo=photo_bytes, reply_to_message_id=reply_to_id)
            else:
                sticker_bytes = image_to_sticker_bytes(final_image)
                await client.send_sticker(message.chat.id, sticker=sticker_bytes, reply_to_message_id=reply_to_id)
            await message.delete()
        else:
            await message.edit("生成语录失败。")

    except Exception as e:
        logging.error(f"Quote plugin failed: {e}", exc_info=True)
        await message.edit(f"处理失败，发生错误: {e}")
    finally:
        for path in avatar_paths_to_clean:
            if exists(path): remove(path)
        try:
            for p in _glob.glob('plugins/yvlu/emoji_custom/*.png'): remove(p)
            for p in _glob.glob('plugins/yvlu/emoji_cache/*.png'): remove(p)
        except Exception as e:
            logging.warning(f"Could not clean emoji cache: {e}")

# --- Command Listeners ---
@listener(command=q_cmd,
          description="制作一条消息的语录，并作为贴纸发送",
          parameters="[text/reply or n/-n]")
async def quote_sticker(client: Client, message: Message):
    await message.edit('处理中 (贴纸模式)...')
    await _quote_logic_handler(client, message, as_photo=False)

@listener(command=q_img_cmd,
          description="制作一条消息的语录，并作为图片发送（无512px尺寸限制）",
          parameters="[text/reply or n/-n]")
async def quote_image(client: Client, message: Message):
    await message.edit('处理中 (高清图片模式)...')
    await _quote_logic_handler(client, message, as_photo=True)
