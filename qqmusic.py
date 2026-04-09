

""" 音源来自互联网，不保证一直可用。如有侵权请联系我删除 """

from pagermaid.listener import listener
from pagermaid.enums import Message
from pagermaid.dependence import client
from io import BytesIO
from urllib.parse import urlparse
from os.path import basename, splitext
from re import sub, search
from pagermaid.utils import alias_command
import asyncio

# 用于缓存搜索结果的字典：{chat_id: [MusicItem1, MusicItem2, ...]}
_cached_search_results: dict[int, list['MusicItem']] = {}
# 用于管理缓存过期任务的字典：{chat_id: asyncio.Task}
_cached_expiry_timers: dict[int, asyncio.Task] = {}
# 缓存过期时间（秒）
CACHE_EXPIRY_SECONDS = 300 # 5分钟

class MusicItem:
    """
    音乐信息的容器类。
    """
    def __init__(self, title: str, singer: str, url: str, cover_url: str):
        self.title = title
        self.singer = singer
        self.url = url
        self.cover_url = cover_url
        self.caption = f"{self.title} - {self.singer}"


qqmusic_help_msg = f"""
QQ音乐点歌。
i.e.
`,{alias_command('qqmusic')} 晴天 周杰伦`  # 搜索并列出前5首歌曲，等待用户选择
`,{alias_command('qqmusic')} 3`  # 在列出歌曲后，选择下载第3首
`,{alias_command('qqmusic')} 晴天 周杰伦 -n 2`  # 直接指定下载第二首歌曲
"""

async def _get_single_qq_music_info(song_name: str, index: int) -> MusicItem | None:
    """
    从外部 QQ 音乐 API 获取单首音乐信息。这是一个内部辅助函数。

    Args:
        song_name: 要搜索的歌曲名称。
        index: 从搜索结果中选择的第几首歌曲（基于1的索引）。

    Returns:
        一个 MusicItem 对象，包含歌曲详细信息；如果未找到或出错，则返回 None。
    """
    api_url = "https://hhlqilongzhu.cn/api/dg_QQmusicflac.php"
    params = {"msg": song_name, "n": index, "type": "json"}

    try:
        res = await client.get(api_url, params=params, timeout=5.0) # 缩短单个请求的超时时间
        res.raise_for_status() # 检查 HTTP 状态码，如果不是 2xx，则抛出异常
        data = res.json()

        # 检查API响应码和数据是否存在
        if data.get("code") == 200 and data.get("data") and data["data"].get("music_url"):
            song_data = data["data"]
            return MusicItem(
                title=song_data.get("song_name", "未知歌曲"),
                singer=song_data.get("song_singer", "未知歌手"),
                url=song_data["music_url"],
                cover_url=song_data.get("cover"),
            )
        # 如果是未找到歌曲的错误码，则返回 None，不抛出异常
        elif data.get("code") == 404 or "未找到相关歌曲" in data.get("msg", ""):
            return None
        else:
            # 对于其他API错误，可以考虑打印日志但仍返回 None，以便外层继续尝试其他索引
            # print(f"API返回错误码: {data.get('code')}, 消息: {data.get('msg')}")
            return None
    except Exception:
        # 捕获网络错误等，返回 None
        # print(f"获取单首音乐信息出错: {e}")
        return None

async def search_qq_music(song_name: str, max_results: int = 5) -> list[MusicItem]:
    """
    搜索 QQ 音乐，并尝试获取前 N 首歌曲。

    Args:
        song_name: 要搜索的歌曲名称。
        max_results: 最多尝试获取的歌曲数量。

    Returns:
        一个包含 MusicItem 对象的列表。
    """
    results = []
    for i in range(1, max_results + 1):
        song = await _get_single_qq_music_info(song_name, i)
        if song:
            results.append(song)
        else:
            # 如果某个索引返回 None (表示未找到或错误)，则通常意味着后续索引也没有了
            # 停止继续尝试，避免不必要的请求
            break
    return results


async def download_audio(url: str, title: str, singer: str) -> BytesIO:
    """
    从给定 URL 下载音频文件到 BytesIO 缓冲区。

    Args:
        url: 音频文件的 URL。
        title: 歌曲标题（用于文件名）。
        singer: 歌手名称（用于文件名）。

    Returns:
        一个 BytesIO 对象，包含音频数据，其 name 属性已设置。

    Raises:
        Exception: 如果下载失败。
    """
    try:
        async with client.stream("GET", url, timeout=30.0) as response:
            response.raise_for_status()  # 检查 HTTP 状态码，如果不是 2xx，则抛出异常

            buffer = BytesIO()
            async for chunk in response.aiter_bytes():
                buffer.write(chunk)

            # 从 URL 中确定文件扩展名
            path = urlparse(url).path
            ext = splitext(basename(path))[1] or ".mp3" # 如果没有扩展名，默认使用 .mp3

            # 清理文件名中的非法字符，使其兼容不同操作系统
            file_name = f"{title} - {singer}{ext}"
            file_name = sub(r'[\\/:*?"<>|]', "_", file_name)

            buffer.name = file_name # 为 BytesIO 设置 name 属性，这对于 Telegram 很有用
            buffer.seek(0) # 将缓冲区指针移到开始位置
            return buffer

    except Exception as e:
        raise Exception(f"下载音频出错: {e}")


async def download_cover(url: str) -> BytesIO:
    """
    从给定 URL 下载封面图片到 BytesIO 缓冲区。

    Args:
        url: 封面图片的 URL。

    Returns:
        一个 BytesIO 对象，包含图片数据，其 name 属性已设置。

    Raises:
        Exception: 如果下载失败。
    """
    try:
        res = await client.get(url, timeout=10.0)
        res.raise_for_status()  # 检查 HTTP 状态码，如果不是 2xx，则抛出异常

        img = BytesIO(res.content)
        img.name = "cover.jpg" # Telegram 缩略图通常需要文件名
        img.seek(0) # 将缓冲区指针移到开始位置
        return img

    except Exception as e:
        raise Exception(f"下载封面图出错: {e}")


def parse_arguments(raw_args: str) -> tuple[str, int | None]:
    """
    解析原始命令参数，提取歌曲名称和可选的直接下载索引。

    Args:
        raw_args: 消息中的原始参数字符串。

    Returns:
        一个包含歌曲名称 (str) 和可选的直接下载索引 (int | None) 的元组。
        如果指定了 -n X，则返回 X；否则返回 None。
    """
    direct_index = None
    match = search(r"-n\s*(\d+)", raw_args)
    if match:
        direct_index = int(match.group(1))
        raw_args = sub(r"-n\s*\d+", "", raw_args) # 从字符串中移除索引部分

    song_query = raw_args.strip()
    return song_query, max(1, direct_index) if direct_index else None # 确保索引至少为 1


async def _clear_cache_after_delay(chat_id: int, delay: int):
    """
    在指定延迟后清除特定聊天 ID 的缓存。
    """
    await asyncio.sleep(delay)
    if chat_id in _cached_search_results:
        del _cached_search_results[chat_id]
        if chat_id in _cached_expiry_timers:
            del _cached_expiry_timers[chat_id]
        # 可以选择在这里发送一条消息告知用户缓存已过期，但可能过于打扰

async def _download_and_reply(message: Message, status_message: Message, song: MusicItem):
    """
    辅助函数：下载并发送歌曲。
    """
    try:
        audio_buffer = await download_audio(song.url, song.title, song.singer)

        thumb_buffer = None
        if song.cover_url:
            try:
                thumb_buffer = await download_cover(song.cover_url)
            except Exception: # 捕获任何异常；封面图是可选的
                pass # 如果封面下载失败，则静默处理

        await message.reply_audio(
            audio_buffer,
            caption=song.caption,
            title=song.title,
            performer=song.singer,
            thumb=thumb_buffer,
            quote=False, # 不引用原消息
            reply_to_message_id=message.reply_to_top_message_id, # 回复到主题串的顶层消息
        )

        await status_message.safe_delete() # 清理状态消息

    except Exception as e:
        await status_message.edit(f"下载或发送歌曲出错: {str(e)}")


@listener(command="qqmusic", description="QQ Music", parameters="[query | index]")
async def qqmusic(message: Message):
    """
    QQ 音乐点歌功能。支持搜索列表选择或直接指定索引下载。
    """
    chat_id = message.chat.id

    if not message.arguments:
        return await message.edit(qqmusic_help_msg)

    # 尝试解析参数，判断是搜索查询还是选择序号
    arg_parts = message.arguments.split()
    potential_select_index = None
    if len(arg_parts) == 1 and arg_parts[0].isdigit():
        potential_select_index = int(arg_parts[0])

    # 如果用户输入的是纯数字，并且当前聊天有缓存的搜索结果
    if potential_select_index is not None and chat_id in _cached_search_results:
        selected_index = potential_select_index - 1 # 转换为0-based索引
        cached_songs = _cached_search_results[chat_id]

        if 0 <= selected_index < len(cached_songs):
            song_to_download = cached_songs[selected_index]
            status = await message.edit(f"📥 正在下载《{song_to_download.caption}》...")
            await _download_and_reply(message, status, song_to_download)

            # 选定后，清除该聊天的缓存和计时器
            if chat_id in _cached_expiry_timers:
                _cached_expiry_timers[chat_id].cancel()
                del _cached_expiry_timers[chat_id]
            del _cached_search_results[chat_id]
            return
        else:
            return await message.edit("选择的序号无效。请选择列表中的一个数字。")
    else:
        # 执行新的搜索查询或直接指定索引下载
        song_query, direct_download_index = parse_arguments(message.arguments)

        if not song_query:
            return await message.edit(qqmusic_help_msg)

        try:
            if direct_download_index: # 用户直接指定了 -n X
                status = await message.edit(
                    f"🔍 正在搜索《{song_query}》，你选择了第{direct_download_index}首..."
                )
                song = await _get_single_qq_music_info(song_query, direct_download_index)
                if not song:
                    await status.edit(f"🚫 未找到《{song_query}》的第{direct_download_index}首歌曲。")
                    return
                await status.edit("正在下载音频及封面图...")
                await _download_and_reply(message, status, song)
            else: # 执行搜索并列出结果
                status = await message.edit(f"🔍 正在搜索《{song_query}》...")
                search_results = await search_qq_music(song_query, max_results=5) # 默认列出前5首

                if not search_results:
                    await status.edit(f"🚫 未找到《{song_query}》的任何歌曲。")
                    return

                # 缓存搜索结果
                _cached_search_results[chat_id] = search_results

                # 取消之前的缓存过期计时器（如果有）并设置新的
                if chat_id in _cached_expiry_timers:
                    _cached_expiry_timers[chat_id].cancel()
                _cached_expiry_timers[chat_id] = asyncio.create_task(
                    _clear_cache_after_delay(chat_id, CACHE_EXPIRY_SECONDS)
                )

                result_list = "\n".join(
                    f"{i+1}. {s.title} - {s.singer}"
                    for i, s in enumerate(search_results)
                )
                await status.edit(
                    f"找到以下歌曲：\n\n{result_list}\n\n请回复 `,qqmusic [序号]` 选择下载。"
                    f"\n（列表将在 {CACHE_EXPIRY_SECONDS // 60} 分钟后失效）"
                )

        except Exception as e:
            await message.edit(f"出错: {str(e)}")

