# yvlu_utils.py
# General-purpose utility functions for the Yvlu plugin.

import unicodedata as _ud
from os.path import exists
from os import makedirs, remove
from typing import List, Dict, Any
import requests
from io import BytesIO
import re

from PIL import Image
from pyrogram.types import Message, MessageEntity
from pyrogram import enums

# ... (Constants, File I/O, Network & Font Management are correct, keeping them) ...
SIYUAN_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/siyuansongti.otf'
FALLBACK_MATH_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/NotoSansMath-Regular.ttf'
FALLBACK_SYMBOLS2_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/NotoSansSymbols2-Regular.ttf'
FALLBACK_NOTO_SANS_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/NotoSans-Regular.ttf'
FALLBACK_DEJAVU_URL = 'https://raw.githubusercontent.com/dhd2333/test/refs/heads/main/DejaVuSans.ttf'

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
        with open(path, 'r', encoding='utf-8') as f: return f.read().strip()
    except FileNotFoundError: return default

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
def _write_font_scale(value: float | str): _write_text_file(_font_scale_path(), str(value))

def download_file_if_not_exists(url: str, target_path: str):
    if not exists(target_path):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            with open(target_path, 'wb') as f: f.write(resp.content)
        except requests.RequestException as e: print(f"Warning: Could not download {url}. Reason: {e}")

def _ensure_chosen_font(base_path: str, mode: str):
    if mode == '2': download_file_if_not_exists(SIYUAN_URL, f"{base_path}siyuansongti.otf")
    elif mode == '3':
        url = _read_text_file(_custom_url_path())
        if url:
            tail = extract_filename_from_url(url)
            download_file_if_not_exists(url, f"{base_path}{tail}")

def _ensure_fallback_fonts(base_path: str = 'plugins/yvlu/'):
    if not exists(base_path): makedirs(base_path, exist_ok=True)
    pairs = [ (f"{base_path}NotoSansMath-Regular.ttf", FALLBACK_MATH_URL), (f"{base_path}NotoSansSymbols2-Regular.ttf", FALLBACK_SYMBOLS2_URL), (f"{base_path}NotoSans-Regular.ttf", FALLBACK_NOTO_SANS_URL), (f"{base_path}DejaVuSans.ttf", FALLBACK_DEJAVU_URL) ]
    for local_path, url in pairs: download_file_if_not_exists(url, local_path)

def font(path, size):
    from PIL import ImageFont
    from .yvlu_drawer import _determine_primary_font_path
    font_file = _determine_primary_font_path(path)
    if not font_file or not exists(font_file): font_file = f'{path}zhuziAwa1n.ttf'
    try: return ImageFont.truetype(font_file, size=size, layout_engine=ImageFont.LAYOUT_RAQM)
    except Exception:
        try: return ImageFont.truetype(font_file, size=size)
        except Exception: return ImageFont.load_default()

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
    except Exception: return 'custom_font.ttf'

def _pyrogram_entities_to_dicts(entities: List[MessageEntity] | None) -> List[Dict[str, Any]]:
    if not entities: return []
    result = []
    for ent in entities:
        typ_map = { enums.MessageEntityType.BOLD: 'bold', enums.MessageEntityType.ITALIC: 'italic', enums.MessageEntityType.UNDERLINE: 'underline', enums.MessageEntityType.STRIKETHROUGH: 'strikethrough', enums.MessageEntityType.CODE: 'monospace', enums.MessageEntityType.PRE: 'monospace', enums.MessageEntityType.SPOILER: 'spoiler', enums.MessageEntityType.CUSTOM_EMOJI: 'custom_emoji' }
        typ = typ_map.get(ent.type, 'mention')
        item = {'type': typ, 'offset': ent.offset, 'length': ent.length}
        if typ == 'custom_emoji': item['custom_emoji_id'] = ent.custom_emoji_id
        result.append(item)
    return result

def get_adjusted_entities(message: Message) -> List[Dict[str, Any]]:
    command_text = message.text or message.caption or "" # <--- FIX: Handle commands in captions
    content = command_text.partition(' ')[2].strip()
    if not content or not (message.entities or message.caption_entities): return []
    
    prefix_units = len(command_text[:-len(content)].encode('utf-16-le')) // 2
    content_units = len(content.encode('utf-16-le')) // 2
    full_entities = _pyrogram_entities_to_dicts(message.entities or message.caption_entities)
    adjusted = []
    for ent in full_entities:
        u_off, u_len = ent['offset'] - prefix_units, ent['length']
        if u_off + u_len <= 0 or u_off >= content_units: continue
        new_off = max(0, u_off)
        new_len = min(u_len - (new_off - u_off), content_units - new_off)
        if new_len > 0:
            ent['offset'], ent['length'] = new_off, new_len
            adjusted.append(ent)
    return adjusted

def _file_placeholder_from_document(doc) -> str:
    fname = getattr(doc, 'file_name', None) or ''
    return f"[文件] {fname.strip()}" if fname else "[文件]"

async def _download_static_media_preview(client, message: Message, out_dir: str, base_name: str) -> str | None:
    try:
        out_path = f"{out_dir}{base_name}.png"
        media = message.sticker or message.photo or message.animation or message.document
        if media:
            file_id = (max(media.thumbs, key=lambda t: t.width*t.height).file_id if getattr(media, 'thumbs', None) and media.thumbs else getattr(media, 'file_id', None))
            if file_id:
                tmp_full = await client.download_media(file_id)
                if tmp_full:
                    with Image.open(tmp_full) as img:
                        img.convert("RGBA").save(out_path, "PNG")
                    remove(tmp_full)
                    return out_path
    except Exception: return None
    return None

def image_to_sticker_bytes(image: Image.Image) -> BytesIO:
    w, h = image.size
    if w > 512 or h > 512:
        if w > h: new_w, new_h = 512, int(h * 512 / w)
        else: new_w, new_h = int(w * 512 / h), 512
        image = image.resize((new_w, new_h), Image.LANCZOS)
    sticker_bytes = BytesIO()
    sticker_bytes.name = "sticker.webp"
    image.save(sticker_bytes, "WEBP")
    sticker_bytes.seek(0)
    return sticker_bytes

def _is_simple_emoji(ch: str) -> bool:
    if not ch: return False
    code = ord(ch)
    return (0x1F300 <= code <= 0x1FAFF or 0x1F600 <= code <= 0x1F64F or 0x2600 <= code <= 0x27BF or 0x1F170 <= code <= 0x1F1FF)

def _twemoji_filename_for_char(ch: str) -> str:
    return format(ord(ch), 'x') + '.png'

def _load_emoji_image(ch: str, size: int) -> Image.Image | None:
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
    except Exception: return None
    return None

def _build_styled_words(text: str, entities: List[Dict[str, Any]] | None):
    from .yvlu_drawer import _StyledWord
    text = (text or '').replace('\r', '')
    chars = list(text)
    styled = [{"char": c, "style": [], "custom_emoji_id": None} for c in chars]
    
    if entities:
        for ent in entities:
            try:
                start, end = ent['offset'], ent['offset'] + ent['length']
                for i in range(start, end):
                    if i < len(styled):
                        style = ent['type']
                        if style not in styled[i]['style']: styled[i]['style'].append(style)
                        if style == 'custom_emoji': styled[i]['custom_emoji_id'] = ent.get('custom_emoji_id')
            except Exception: continue

    words: List[_StyledWord] = []
    if not text: return words
    
    i = 0
    while i < len(chars):
        char, style_info = chars[i], styled[i]
        if char.isspace():
            words.append(_StyledWord(char, style_info['style']))
            i += 1
        else:
            j = i
            while j < len(chars) and not chars[j].isspace() and styled[j]['style'] == style_info['style'] and styled[j]['custom_emoji_id'] == style_info['custom_emoji_id']:
                j += 1
            word_str = "".join(chars[i:j])
            words.append(_StyledWord(word_str, style_info['style'], style_info['custom_emoji_id'] if len(word_str) == 1 else None))
            i = j
    return words```