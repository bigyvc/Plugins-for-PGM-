# yvlu.py for PagerMaid-Pyro (Main Plugin File)
# Handles Telegram API interaction, command parsing, and orchestrates the process.

import logging
from io import BytesIO
from os.path import exists
from os import makedirs, remove
import glob as _glob

from pyrogram.client import Client
from pyrogram import enums
from pyrogram.types import Message, User, Chat
from PIL import Image

from pagermaid.listener import listener
from pagermaid.utils import alias_command

from . import yvlu_drawer, yvlu_utils

yvlu_cmd = alias_command('yvlu')
yvlu_set_cmd = alias_command('yvlu_set')
yvlu_url_cmd = alias_command('yvlu_url')
yvlu_size_cmd = alias_command('yvlu_size')
yvlu_img_cmd = alias_command('yvlu_img')

# --- Settings Commands (No changes needed) ---
@listener(command=yvlu_set_cmd,
          description=f"设置 yvlu 字体：`-{yvlu_set_cmd} 1` 使用原字体；`-{yvlu_set_cmd} 2` 使用思源宋体（自动下载）；`-{yvlu_set_cmd} 3` 使用自定义URL字体。",
          parameters="[1|2|3]")
async def yvlu_set(client: Client, message: Message):
    try:
        command_text = message.text or message.caption or ""
        arg = command_text.partition(' ')[2].strip()
        if arg not in ('1', '2', '3'):
            await message.edit(f'用法：-{yvlu_set_cmd} 1 | 2 | 3（默认1；3为自定义URL字体）')
            return
        yvlu_utils._write_font_mode(arg)
        if arg == '2':
            await message.edit('设置字体为思源宋体（下载中…')
            yvlu_utils._ensure_chosen_font('plugins/yvlu/', '2')
        elif arg == '3':
            await message.edit('设置字体为自定义URL字体（下载中…')
            yvlu_utils._ensure_chosen_font('plugins/yvlu/', '3')
        await message.edit(f'字体模式已设置为 {arg}。')
    except Exception as e:
        logging.error(f"Yvlu-set failed: {e}", exc_info=True)
        await message.edit('设置失败。')

@listener(command=yvlu_url_cmd,
          description=f"设置自定义字体URL。",
          parameters="<url>")
async def yvlu_url(client: Client, message: Message):
    try:
        command_text = message.text or message.caption or ""
        arg = command_text.partition(' ')[2].strip()
        if not arg:
            await message.edit(f'用法：-{yvlu_url_cmd} <字体直链>')
            return
        if not exists('plugins/yvlu/'): makedirs('plugins/yvlu/', exist_ok=True)
        yvlu_utils._write_text_file(yvlu_utils._custom_url_path(), arg)
        tail = yvlu_utils.extract_filename_from_url(arg)
        yvlu_utils._write_text_file(yvlu_utils._custom_font_name_path(), tail)
        await message.edit('下载自定义字体中…')
        yvlu_utils.download_file_if_not_exists(arg, f"plugins/yvlu/{tail}")
        yvlu_utils._write_font_mode('3')
        yvlu_utils._ensure_chosen_font('plugins/yvlu/', '3')
        await message.edit(f'已设置自定义URL为模式3，并保存文件名 `{tail}`。')
    except Exception as e:
        logging.error(f"Yvlu-url failed: {e}", exc_info=True)
        await message.edit('设置失败，请检查链接。')

@listener(command=yvlu_size_cmd,
          description=f"设置整体字体与布局倍率。",
          parameters="<scale|percent|reset>")
async def yvlu_size(client: Client, message: Message):
    try:
        command_text = message.text or message.caption or ""
        arg = command_text.partition(' ')[2].strip()
        if not arg:
            await message.edit(f'用法：-{yvlu_size_cmd} <倍率|百分比|reset>')
            return
        if arg.lower() in ('reset', 'default'):
            yvlu_utils._write_font_scale('1.0')
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
        yvlu_utils._write_font_scale(scale)
        await message.edit(f'已设置字体与布局倍率为 {scale:.2f}。')
    except Exception as e:
        logging.error(f"Yvlu-size failed: {e}", exc_info=True)
        await message.edit('设置失败。')

# --- ROBUST HELPER FUNCTIONS ---
async def _get_sender_info(message: Message) -> dict:
    sender = message.from_user or message.sender_chat
    if isinstance(sender, User):
        first, last = sender.first_name or '', sender.last_name or ''
        name = yvlu_utils._normalize_name(first).strip()
        if last: name = (name + ' ' + yvlu_utils._normalize_name(last)).strip()
        photo_id = sender.photo.big_file_id if sender.photo else None
        return {"name": name, "id": sender.id, "photo_id": photo_id, "entity": sender}
    if isinstance(sender, Chat):
        name = sender.title or "未知频道"
        photo_id = sender.photo.big_file_id if sender.photo else None
        return {"name": name, "id": sender.id, "photo_id": photo_id, "entity": sender}
    return {"name": "匿名", "id": 0, "photo_id": None, "entity": None}

async def _fetch_and_cache_custom_emojis(client: Client, emoji_ids: list[int]) -> dict[int, Image.Image]:
    if not emoji_ids: return {}
    images, cache_dir = {}, yvlu_utils._custom_emoji_cache_dir()
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
                if exists(cache_path): images[doc_id] = Image.open(cache_path).convert('RGBA')
            except Exception as e: logging.warning(f"Failed to process custom emoji {doc_id}: {e}")
    except Exception as e: logging.error(f"Could not fetch custom emoji stickers: {e}", exc_info=True)
    return images

# --- MAIN PLUGIN LOGIC ---
async def _yvlu_logic_handler(client: Client, message: Message, as_photo: bool = False):
    try:
        if not exists('plugins/yvlu/'): makedirs('plugins/yvlu/', exist_ok=True)
        yvlu_utils._ensure_chosen_font('plugins/yvlu/', yvlu_utils._read_font_mode())
        yvlu_utils._ensure_fallback_fonts('plugins/yvlu/')
        if not exists('plugins/yvlu/zhuziAwa1n.ttf'):
            await message.edit('首次运行，下载预置字体中。。。')
            yvlu_utils.download_file_if_not_exists('https://raw.githubusercontent.com/dhd2333/test/main/zhuziAwa1n.ttf', 'plugins/yvlu/zhuziAwa1n.ttf')
        
        quality_multiplier = 5.0

        reply_message = message.reply_to_message
        command_text = message.text or message.caption or ""
        content = command_text.partition(' ')[2].strip()
        final_image, avatar_paths_to_clean = None, set()

        if not reply_message and content:
            sender_info = await _get_sender_info(message)
            if sender_info['photo_id']:
                p = await client.download_media(sender_info['photo_id'], file_name=f"plugins/yvlu/{sender_info['id']}.jpg")
                if p: avatar_paths_to_clean.add(p)
            final_image = await _render_single_message_image(client, message, sender_info, quality_multiplier=quality_multiplier, as_photo=as_photo)
        elif reply_message:
            if content.lstrip('-').isdigit() and content != "0":
                n = int(content)
                num_messages = abs(n)
                if num_messages == 1:
                    sender_info = await _get_sender_info(reply_message)
                    if sender_info['photo_id']:
                        p = await client.download_media(sender_info['photo_id'], file_name=f"plugins/yvlu/{sender_info['id']}.jpg")
                        if p: avatar_paths_to_clean.add(p)
                    final_image = await _render_single_message_image(client, reply_message, sender_info, quality_multiplier=quality_multiplier, as_photo=as_photo)
                else:
                    start_id = reply_message.id
                    message_ids = range(start_id, start_id + num_messages) if n > 0 else range(start_id - num_messages + 1, start_id + 1)
                    msgs = [m for m in await client.get_messages(message.chat.id, message_ids) if m]
                    all_emoji_ids = [e.custom_emoji_id for m in msgs if m.entities for e in m.entities if e.type == enums.MessageEntityType.CUSTOM_EMOJI]
                    all_custom_emoji_images = await _fetch_and_cache_custom_emojis(client, all_emoji_ids)
                    rendered_images, prev_uid = [], None
                    for m in msgs:
                        sender_info = await _get_sender_info(m)
                        if sender_info['photo_id']:
                            p = await client.download_media(sender_info['photo_id'], file_name=f"plugins/yvlu/{sender_info['id']}.jpg")
                            if p: avatar_paths_to_clean.add(p)
                        img = await _render_single_message_image(client, m, sender_info, all_custom_emoji_images, prev_uid, quality_multiplier=quality_multiplier, as_photo=as_photo)
                        if img: rendered_images.append(img)
                        prev_uid = sender_info['id']
                    if rendered_images: final_image = yvlu_drawer.combine_images(rendered_images)
            else:
                sender_info = await _get_sender_info(reply_message)
                if sender_info['photo_id']:
                    p = await client.download_media(sender_info['photo_id'], file_name=f"plugins/yvlu/{sender_info['id']}.jpg")
                    if p: avatar_paths_to_clean.add(p)
                final_image = await _render_single_message_image(client, reply_message, sender_info, override_text=content, quality_multiplier=quality_multiplier, as_photo=as_photo)
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
                sticker_bytes = yvlu_utils.image_to_sticker_bytes(final_image)
                await client.send_sticker(message.chat.id, sticker=sticker_bytes, reply_to_message_id=reply_to_id)
            await message.delete()
        else:
            await message.edit("生成语录失败。")
    except Exception as e:
        logging.error(f"Yvlu plugin failed: {e}", exc_info=True)
        await message.edit(f"处理失败，发生错误: {e}")
    finally:
        for path in avatar_paths_to_clean:
            if exists(path): remove(path)
        try:
            for p in _glob.glob('plugins/yvlu/emoji_custom/*.png'): remove(p)
            for p in _glob.glob('plugins/yvlu/emoji_cache/*.png'): remove(p)
        except Exception as e:
            logging.warning(f"Could not clean emoji cache: {e}")

@listener(command=yvlu_cmd,
          description="制作一条消息的语录，并作为贴纸发送",
          parameters="[text/reply or n/-n]")
async def yv_lu(client: Client, message: Message):
    await message.edit('处理中 (贴纸模式)...')
    await _yvlu_logic_handler(client, message, as_photo=False)

@listener(command=yvlu_img_cmd,
          description="制作一条消息的语录，并作为图片发送（无512px尺寸限制）",
          parameters="[text/reply or n/-n]")
async def yv_lu_img(client: Client, message: Message):
    await message.edit('处理中 (高清图片模式)...')
    await _yvlu_logic_handler(client, message, as_photo=True)

async def _render_single_message_image(client: Client, msg: Message, sender_info: dict, custom_emojis_cache: dict = None, prev_uid: int = None, override_text: str = None, quality_multiplier: float = 2.0, as_photo: bool = False) -> Image.Image | None:
    if override_text:
        text = override_text
        entities = []
    else:
        msg_text = msg.text or msg.caption or ""
        is_self_quote = not msg.reply_to_message and msg_text.partition(' ')[2].strip()
        text = msg_text.partition(' ')[2].strip() if is_self_quote else msg_text
        entities = yvlu_utils.get_adjusted_entities(msg) if is_self_quote else yvlu_utils._pyrogram_entities_to_dicts(msg.entities or msg.caption_entities)
    
    media_path = await yvlu_utils._download_static_media_preview(client, msg, 'plugins/yvlu/', f"__m_{msg.id}")
    
    if custom_emojis_cache is None:
        emoji_ids = [e['custom_emoji_id'] for e in entities if e.get('custom_emoji_id')]
        custom_emoji_images = await _fetch_and_cache_custom_emojis(client, emoji_ids)
    else:
        custom_emoji_images = custom_emojis_cache

    reply_data = await _get_reply_data(client, msg)
    name_tail_img = await yvlu_drawer._load_user_premium_badge_emoji_img(client, sender_info['entity'])
    avatar_rel = f"{sender_info['id']}.jpg" if sender_info['id'] and exists(f"plugins/yvlu/{sender_info['id']}.jpg") else None
    
    if not override_text and not media_path and msg.document:
        text += ('\n' if text else '') + yvlu_utils._file_placeholder_from_document(msg.document)

    suppress_sender = bool(prev_uid is not None and sender_info['id'] == prev_uid)

    # <-- START: FINAL CORRECTED CALL LOGIC -->
    # We now build a single, unified dictionary of all arguments for the drawing function.
    # This is the most robust way to pass parameters and avoids all previous errors.
    draw_kwargs = {
        'name': sender_info['name'],
        'text': text,
        'avatar_path': avatar_rel,
        'path': 'plugins/yvlu/',
        'media_path': media_path,
        'media_type': 'sticker' if msg.sticker else None,
        'entities': entities,
        'user_id_for_color': sender_info['id'],
        'custom_emoji_images': custom_emoji_images,
        'name_tail_emoji_img': name_tail_img,
        'suppress_sender': suppress_sender,
        'quality_multiplier': quality_multiplier,
        'is_sticker_mode': not as_photo
    }
    draw_kwargs.update(reply_data)
    
    image = yvlu_drawer.yvlu_generate(**draw_kwargs)
    # <-- END: FINAL CORRECTED CALL LOGIC -->

    if media_path and exists(media_path): remove(media_path)
    return image

async def _get_reply_data(client: Client, message: Message) -> dict:
    if not message.reply_to_message:
        return {}
    
    l1_reply_msg = message.reply_to_message
    
    if l1_reply_msg.sticker:
        return {}
    
    l1_sender_info = await _get_sender_info(l1_reply_msg)
    l1_text = l1_reply_msg.text or l1_reply_msg.caption or ''
    if l1_reply_msg.document:
        l1_text += (' ' if l1_text else '') + yvlu_utils._file_placeholder_from_document(l1_reply_msg.document)
    
    reply_data = {
        "reply_name": l1_sender_info['name'],
        "reply_text": l1_text,
        "reply_entities": yvlu_utils._pyrogram_entities_to_dicts(l1_reply_msg.entities or l1_reply_msg.caption_entities),
        "reply_chat_id": l1_sender_info['id'],
        "reply_name_tail_emoji_img": await yvlu_drawer._load_user_premium_badge_emoji_img(client, l1_sender_info['entity'])
    }

    l2_reply_id = l1_reply_msg.reply_to_message_id
    if l2_reply_id:
        try:
            l2_reply_msg = await client.get_messages(l1_reply_msg.chat.id, l2_reply_id)
            
            if l2_reply_msg and not l2_reply_msg.sticker and (l2_reply_msg.from_user or l2_reply_msg.sender_chat):
                l2_sender_info = await _get_sender_info(l2_reply_msg)
                l2_text = l2_reply_msg.text or l2_reply_msg.caption or ''
                if l2_reply_msg.document:
                    l2_text += (' ' if l2_text else '') + yvlu_utils._file_placeholder_from_document(l2_reply_msg.document)
                
                reply_data["nested_reply_name"] = l2_sender_info['name']
                reply_data["nested_reply_text"] = l2_text
                reply_data["nested_reply_chat_id"] = l2_sender_info['id']
        except Exception:
            pass
            
    return reply_data