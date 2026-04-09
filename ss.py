## 插件来自分享，感谢原作者以及后继者们，祝他们好人一生平安！！！
# v2.1 by AI: 将视频来源说明改为可点击的 "我才不喜欢呢" 链接，直接跳转到源视频。
# v2.0 by AI: 增加了频道抓取失败后自动重试其他频道的功能，提高稳定性。

import pickle
import random
import asyncio
from os.path import exists
from pyrogram import Client, enums, errors
from pagermaid.listener import listener
from pagermaid.enums import Message

# --- 配置 ---
config_file = "ss_config.pkl"
DEFAULT_CHANNELS = [
    "kladult",  # 街拍
    "TGcosplay",  # 健身小姐姐
    "botmzt",  # meizi
    "mn539",
    "laosiji100",  # JK yyds 制服诱惑
    "youshipin",  # 轻度二次元
    "xzzp008",
    "meinv_SP",
    "jeansfan",
    "sexy16969"
    "Tg66778"
    "simisebaisi"
    "meizitu3"
    "xiuren_xiezhen"
]

# --- 主功能 ---
@listener(command="ss", description="我才不喜欢 末尾添加 `s` 将启用防剧透功能",
          parameters="[自定义频道] [s]")
async def lsp(client: Client, message: Message):
    bot_message = None
    try:
        p = message.parameter
        spoiler = 's' in p
        
        # 解析参数
        raw_channels = [i for i in p if i != 's']
        user_specified_channel = bool(raw_channels)

        # 确定要尝试的频道列表
        if user_specified_channel:
            channels_to_try = raw_channels
        else:
            if exists(config_file):
                with open(config_file, 'rb') as f:
                    channels = pickle.load(f)
            else:
                channels = DEFAULT_CHANNELS
            
            channels_to_try = channels.copy()
            random.shuffle(channels_to_try)

        bot_message = await message.edit('[我才不喜欢...]', disable_web_page_preview=True)
        video_sent = False

        # 循环尝试频道列表
        for channel in channels_to_try:
            try:
                # 确保频道名是有效的
                if not isinstance(channel, str) or not channel:
                    continue

                await bot_message.edit(f'[正在尝试从 @{channel} 抓取...]', disable_web_page_preview=True)
                
                count = await client.search_messages_count(chat_id=channel, filter=enums.MessagesFilter.VIDEO)
                if count < 1:
                    await bot_message.edit(f'[@{channel} 中没有视频, 跳过...]', disable_web_page_preview=True)
                    await asyncio.sleep(1)
                    continue

                random_offset = random.randint(0, count - 1)
                
                video_message = None
                async for m in client.search_messages(chat_id=channel, offset=random_offset, limit=1, filter=enums.MessagesFilter.VIDEO):
                    video_message = m
                    break
                
                if video_message and video_message.video:
                    await bot_message.edit(f'[已从 @{channel} 找到视频, 正在发送...]', disable_web_page_preview=True)
                    
                    video_file_id = video_message.video.file_id
                    
                    # 获取原始消息的链接
                    # 注意: 这只对公开频道有效
                    message_link = f"https://t.me/{channel}/{video_message.id}"
                    # 使用 Markdown 格式创建带链接的标题
                    caption = f"[我才不喜欢呢]({message_link})"
                    
                    if message.reply_to_message:
                        await message.reply_to_message.reply_video(video_file_id, caption=caption, has_spoiler=spoiler)
                    else:
                        await message.reply_video(
                            video_file_id, 
                            caption=caption, 
                            has_spoiler=spoiler, 
                            quote=False, 
                            reply_to_message_id=message.reply_to_top_message_id
                        )
                    video_sent = True
                    break

            except errors.ChannelPrivate:
                error_msg = f'[@{channel} 是私有频道或不存在]'
            except errors.RPCError as e:
                error_msg = f'[@{channel} 抓取失败: {e.__class__.__name__}]'
            except Exception as e:
                error_msg = f'[@{channel} 出现未知错误]'
            
            if not user_specified_channel:
                await bot_message.edit(f'{error_msg}, 正在尝试下一个...', disable_web_page_preview=True)
                await asyncio.sleep(2)
                continue
            else:
                raise Exception(error_msg)

        if video_sent:
            await bot_message.safe_delete()
            await message.safe_delete()
        else:
            final_msg = "[尝试了所有频道, 都抓取失败了 T_T]"
            await bot_message.edit(final_msg, disable_web_page_preview=True)
            await asyncio.sleep(5)
            await message.safe_delete()
            await bot_message.safe_delete()

    except Exception as e:
        error_text = f"失败了: {e}"
        if bot_message:
            m = await bot_message.edit(error_text)
        else:
            m = await message.edit(error_text)
        await asyncio.sleep(5)
        await message.safe_delete()
        await m.safe_delete()

# --- 配置功能 ---
@listener(command="ss_config", description="设置频道源，多个源用空格分隔",
          parameters="[自定义频道源]")
async def ss_config_func(client: Client, message: Message):
    try:
        if not message.parameter:
            if exists(config_file):
                with open(config_file, 'rb') as f:
                    channels = pickle.load(f)
                msg = f"当前频道源: \n`{' '.join(channels)}`"
            else:
                msg = f"尚未使用自定义配置，当前为默认源: \n`{' '.join(DEFAULT_CHANNELS)}`"
        else:
            with open(config_file, 'wb') as f:
                pickle.dump(message.parameter, f)
            msg = f"频道源已设置为: \n`{' '.join(message.parameter)}`"
        
        m = await message.edit(msg, disable_web_page_preview=True)

    except Exception as e:
        m = await message.edit(f"配置失败: {e}")
    
    await asyncio.sleep(5)
    await message.safe_delete()
    await m.safe_delete()