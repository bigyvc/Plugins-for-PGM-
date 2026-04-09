import re
import time
import requests
import yaml
import base64
import calendar
import textwrap
from typing import Dict, Optional, Tuple, List
from urllib.parse import unquote, urlparse
from datetime import datetime, timedelta
from pagermaid.enums import Message
from pagermaid.listener import listener
from pagermaid.utils import alias_command
from pagermaid.dependence import client as http_client

UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
NODE_PATTERNS = [
    'vmess://', 'trojan://', 'ss://', 'ssr://',
    'vless://', 'hy2://', 'hysteria://', 'hy://',
    'tuic://', 'wireguard://', 'socks5://', 'http://',
    'https://', 'shadowtls://', 'naive://'
]
REGION_RULES = [
    # 亚洲常用地区
    ('香港', ['香港', 'hong kong', 'hongkong', 'hk', '🇭🇰', 'hkg']),
    ('台湾', ['台湾', 'taiwan', 'tw', '🇹🇼', 'taipei', 'tpe']),
    ('日本', ['日本', 'japan', 'jp', '🇯🇵', 'tokyo', 'osaka', 'jap']),
    ('新加坡', ['新加坡', 'singapore', 'sg', '🇸🇬', 'sgp']),
    ('韩国', ['韩国', 'korea', 'kr', '🇰🇷', 'seoul', 'kor']),
    # 北美地区
    ('美国', ['美国', 'united states', 'us', 'usa', '🇺🇸', 'los angeles', 'san jose', 'silicon valley']),
    ('加拿大', ['加拿大', 'canada', 'ca', '🇨🇦', 'toronto', 'vancouver']),
    # 欧洲主要地区
    ('英国', ['英国', 'united kingdom', 'uk', '🇬🇧', 'london', 'manchester', 'gbr']),
    ('德国', ['德国', 'germany', 'de', '🇩🇪', 'frankfurt', 'berlin', 'deu']),
    ('法国', ['法国', 'france', 'fr', '🇫🇷', 'paris', 'fra']),
    ('荷兰', ['荷兰', 'netherlands', 'nl', '🇳🇱', 'amsterdam', 'nld']),
    ('瑞士', ['瑞士', 'switzerland', 'ch', '🇨🇭', 'zurich', 'che']),
    # 其他亚洲地区
    ('印度', ['印度', 'india', 'in', '🇮🇳', 'mumbai', 'delhi', 'ind']),
    ('马来西亚', ['马来西亚', 'malaysia', 'my', '🇲🇾', 'kuala lumpur', 'mys']),
    ('泰国', ['泰国', 'thailand', 'th', '🇹🇭', 'bangkok', 'tha']),
    ('越南', ['越南', 'vietnam', 'vn', '🇻🇳', 'hanoi', 'vnm']),
    ('印尼', ['印尼', '印度尼西亚', 'indonesia', 'id', '🇮🇩', 'jakarta', 'idn']),
    ('菲律宾', ['菲律宾', 'philippines', 'ph', '🇵🇭', 'manila', 'phl']),
    ('土耳其', ['土耳其', 'turkey', 'tr', '🇹🇷', 'istanbul', 'ankara', 'tur']),
    # 其他欧洲地区
    ('意大利', ['意大利', 'italy', 'it', '🇮🇹', 'milan', 'rome', 'ita']),
    ('西班牙', ['西班牙', 'spain', 'es', '🇪🇸', 'madrid', 'barcelona', 'esp']),
    ('瑞典', ['瑞典', 'sweden', 'se', '🇸🇪', 'stockholm', 'swe']),
    ('挪威', ['挪威', 'norway', 'no', '🇳🇴', 'oslo', 'nor']),
    ('芬兰', ['芬兰', 'finland', 'fi', '🇫🇮', 'helsinki', 'fin']),
    ('丹麦', ['丹麦', 'denmark', 'dk', '🇩🇰', 'copenhagen', 'dnk']),
    ('波兰', ['波兰', 'poland', 'pl', '🇵🇱', 'warsaw', 'pol']),
    ('奥地利', ['奥地利', 'austria', 'at', '🇦🇹', 'vienna', 'aut']),
    ('比利时', ['比利时', 'belgium', 'be', '🇧🇪', 'brussels', 'bel']),
    ('爱尔兰', ['爱尔兰', 'ireland', 'ie', '🇮🇪', 'dublin', 'irl']),
    ('葡萄牙', ['葡萄牙', 'portugal', 'pt', '🇵🇹', 'lisbon', 'prt']),
    ('希腊', ['希腊', 'greece', 'gr', '🇬🇷', 'athens', 'grc']),
    ('卢森堡', ['卢森堡', 'luxembourg', 'lu', '🇱🇺', 'lux']),
    ('乌克兰', ['乌克兰', 'ukraine', 'ua', '🇺🇦', 'kiev', 'ukr']),
    # 大洋洲
    ('澳大利亚', ['澳大利亚', 'australia', 'au', '🇦🇺', 'sydney', 'melbourne', 'aus']),
    ('新西兰', ['新西兰', 'new zealand', 'nz', '🇳🇿', 'auckland', 'nzl']),
    # 南美地区
    ('巴西', ['巴西', 'brazil', 'br', '🇧🇷', 'sao paulo', 'rio', 'bra']),
    ('阿根廷', ['阿根廷', 'argentina', 'ar', '🇦🇷', 'buenos aires', 'arg']),
    ('智利', ['智利', 'chile', 'cl', '🇨🇱', 'santiago', 'chl']),
    ('哥伦比亚', ['哥伦比亚', 'colombia', 'co', '🇨🇴', 'bogota', 'col']),
    ('墨西哥', ['墨西哥', 'mexico', 'mx', '🇲🇽', 'mexico city', 'mex']),
    # 中东地区
    ('阿联酋', ['阿联酋', 'uae', 'united arab emirates', 'ae', '🇦🇪', 'dubai', 'abu dhabi', 'are']),
    ('以色列', ['以色列', 'israel', 'il', '🇮🇱', 'tel aviv', 'jerusalem', 'isr']),
    ('沙特', ['沙特', '沙特阿拉伯', 'saudi arabia', 'sa', '🇸🇦', 'riyadh', 'sau']),
    # 非洲地区
    ('南非', ['南非', 'south africa', 'za', '🇿🇦', 'johannesburg', 'cape town', 'zaf']),
    ('埃及', ['埃及', 'egypt', 'eg', '🇪🇬', 'cairo', 'egy']),
    # 俄罗斯单独分类
    ('俄罗斯', ['俄罗斯', 'russia', 'ru', '🇷🇺', 'moscow', 'st.petersburg', 'rus'])
]

def format_size(size: int) -> str:
    if size < 0: size = 0
    level = 0
    while size >= 1024 and level < len(UNITS) - 1:
        size /= 1024
        level += 1
    return f"{size:.2f} {UNITS[level]}"

def format_time_remaining(seconds: int) -> str:
    seconds = int(seconds)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    return f"{str(days).zfill(2)}天{str(hours).zfill(2)}小时"

def calculate_remaining_daily_allowance(remaining_traffic: int, days_to_next_event: int) -> str:
    if days_to_next_event <= 0: return "无法计算"
    daily_allowance = remaining_traffic / days_to_next_event
    return format_size(int(daily_allowance))

def get_speed_emoji(usage_percent: float) -> str:
    if usage_percent < 30: return "🟢 良好"
    if usage_percent < 70: return "🟡 正常"
    if usage_percent < 90: return "🟠 偏高"
    return "🔴 警告"

def estimate_depletion_date(remaining_traffic: int, daily_usage: int) -> str:
    if daily_usage <= 0: return "无法估计"
    days_remaining = remaining_traffic / daily_usage
    depletion_date = datetime.fromtimestamp(time.time() + days_remaining * 86400)
    return depletion_date.strftime("%Y-%m-%d")

def estimate_last_reset_time(reset_day: int, time_now: int) -> int:
    now = datetime.fromtimestamp(time_now)
    if now.day < reset_day:
        prev_month_end = now.replace(day=1) - timedelta(days=1)
        last_day_of_prev_month = calendar.monthrange(prev_month_end.year, prev_month_end.month)[1]
        actual_reset_day = min(reset_day, last_day_of_prev_month)
        last_reset_dt = prev_month_end.replace(day=actual_reset_day)
    else:
        last_reset_dt = now.replace(day=reset_day)
    return int(last_reset_dt.timestamp())

def parse_reset_info(expire_timestamp: int, time_now: int) -> Tuple[str, int, bool, int]:
    now_dt = datetime.fromtimestamp(time_now)
    expire_dt = datetime.fromtimestamp(expire_timestamp)
    is_long_term = (expire_dt - now_dt).days > 3 * 365
    days_to_expire = max(0, (expire_dt - now_dt).days)
    
    if days_to_expire < 45 and not is_long_term:
        return "单次订阅，无重置", days_to_expire, False, 0
    
    reset_day = expire_dt.day
    try:
        if now_dt.day < reset_day:
            next_reset_dt = now_dt.replace(day=reset_day)
        else:
            next_month_dt = (now_dt.replace(day=1) + timedelta(days=32)).replace(day=1)
            last_day_of_next_month = calendar.monthrange(next_month_dt.year, next_month_dt.month)[1]
            actual_reset_day = min(reset_day, last_day_of_next_month)
            next_reset_dt = next_month_dt.replace(day=actual_reset_day)
    except ValueError:
        last_day = calendar.monthrange(now_dt.year, now_dt.month)[1]
        next_reset_dt = now_dt.replace(day=last_day)

    days_to_reset = max(0, (next_reset_dt - now_dt).days)
    
    if abs(days_to_reset - days_to_expire) < 3 and not is_long_term:
        return "单次订阅，无重置", days_to_expire, False, 0
        
    return f"每月{reset_day}日", days_to_reset, True, reset_day

def extract_airport_name_from_headers(headers: dict, url: str) -> str:
   # """提取机场名称，优先使用 Content-Disposition，否则 fallback 到域名"""
    if 'Content-Disposition' in headers:
        content_disp = headers['Content-Disposition']
        match = re.search(r"filename\*=UTF-8''(.+?)(?:;|$)", content_disp, re.IGNORECASE) or \
                re.search(r'filename="(.+?)"', content_disp, re.IGNORECASE)
        if match:
              try:
                   filename = unquote(match.group(1), encoding='utf-8') # 提取文件名
                   # 如果以 .yaml 结尾，则去掉它
                   if filename.lower().endswith('.yaml'):
                      filename = filename[:-5]
                   return filename
              except:
                   # 为备用方案增加处理逻辑
                   filename = match.group(1)
                   if filename.lower().endswith('.yaml'):
                      filename = filename[:-5]
                   return filename
    return urlparse(url).hostname or "未知机场"

def get_node_info(text_content: str) -> Optional[Dict]:
    try:
        config = yaml.safe_load(text_content)
        if config and 'proxies' in config and isinstance(config['proxies'], list):
            type_count, regions, identified_region_count = {}, {}, 0
            total_nodes = len(config['proxies'])
            
            for proxy in config['proxies']:
                proxy_type = proxy.get('type', '').lower()
                if proxy_type: type_count[proxy_type] = type_count.get(proxy_type, 0) + 1
                name = proxy.get('name', '').lower()
                region_found = False
                for region_name, keywords in REGION_RULES:
                    if any(keyword in name for keyword in keywords):
                        regions[region_name] = regions.get(region_name, 0) + 1
                        identified_region_count += 1
                        region_found = True
                        break
            
            other_regions_count = total_nodes - identified_region_count
            if other_regions_count > 0: regions['其他'] = other_regions_count
            return {'node_count': total_nodes, 'type_count': type_count, 'regions': regions}
    except (yaml.YAMLError, AttributeError):
        pass

    try:
        decoded_content = base64.b64decode(text_content).decode('utf-8')
        node_lines = [line for line in decoded_content.splitlines() if line.strip()]
        type_count, regions, identified_region_count = {}, {}, 0
        
        for line in node_lines:
            line_lower = line.lower()
            for pattern in NODE_PATTERNS:
                if line.startswith(pattern):
                    type_count[pattern.replace('://', '')] = type_count.get(pattern.replace('://', ''), 0) + 1
                    break
            
            region_found = False
            for region_name, keywords in REGION_RULES:
                if any(keyword in line_lower for keyword in keywords):
                    regions[region_name] = regions.get(region_name, 0) + 1
                    identified_region_count += 1
                    region_found = True
                    break

        other_regions_count = len(node_lines) - identified_region_count
        if other_regions_count > 0: regions['其他'] = other_regions_count
        return {'node_count': len(node_lines), 'type_count': type_count, 'regions': regions}
    except:
        return None

def format_date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

@listener(is_plugin=True, outgoing=True, command=alias_command("sub"),
          description='识别订阅链接并获取信息\n使用方法：使用该命令发送或回复一段带有一条或多条订阅链接的文本',
          parameters='<url>')
async def subinfo(_, msg: Message):
    headers = {'User-Agent': 'ClashMeta'}
    message_raw = msg.reply_to_message.text if msg.reply_to_message else msg.text
    url_list = re.findall(r"https?://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|]", message_raw)
    
    if not url_list:
        await msg.edit("未找到有效的订阅链接。")
        return
        
    await msg.edit(f"正在查询 {len(url_list)} 个订阅链接，请稍候...")
    
    reports = []
    for initial_url in url_list:
        try:
            res = await http_client.get(initial_url, headers=headers, timeout=10, follow_redirects=True)
            url = str(res.url)
            airport_name = extract_airport_name_from_headers(res.headers, url)
            url_line = f"订阅链接：`{url}`"
            
            if res.status_code != 200:
                body_block = f"```\n状态：无法访问 (状态码: {res.status_code})\n```"
                reports.append(f"{url_line}\n{body_block}")
                continue

            try:
                info = res.headers['subscription-userinfo']
                info_num = [int(float(x)) for x in re.findall(r'\d+', info)]
                upload, download, total, time_now = info_num[0], info_num[1], info_num[2], int(time.time())
                used, remaining = upload + download, total - (upload + download)
                usage_percent = round(used / total * 100, 2) if total > 0 else 0

                # Determine subscription status directly, replacing the deleted function call
                expire_ts = info_num[3] if len(info_num) >= 4 and info_num[3] > 0 else 0
                sub_status = "有效"
                if expire_ts and time_now > expire_ts:
                    sub_status = "已过期"
                elif remaining <= 0:
                    sub_status = "流量已用尽"

                output_lines = [
                    '📌 **基本信息**', f'机场名称：{airport_name}', f'订阅状态：{sub_status}','',
                    '📊 **流量信息**', f'总计流量：{format_size(total)}',
                    f'已用流量：{format_size(used)} (↑{format_size(upload)} ↓{format_size(download)})',
                    f'剩余流量：{format_size(remaining)} {get_speed_emoji(usage_percent)}',
                    f"使用进度：{'█' * int(20 * usage_percent / 100) + '░' * (20 - int(20 * usage_percent / 100))}"
                ]
                
                if expire_ts:
                    output_lines.extend(['', '⏱️ **时间信息**'])
                    if time_now <= expire_ts:
                        output_lines.append(f'到期时间：{format_date(expire_ts)} (剩 {format_time_remaining(expire_ts - time_now)})')
                    else:
                        output_lines.append(f'到期提醒：此订阅已于 {format_date(expire_ts)} 过期！')

                    reset_info, days_to_reset, has_reset, reset_day = parse_reset_info(expire_ts, time_now)
                    if has_reset:
                        last_reset_time = estimate_last_reset_time(reset_day, time_now)
                        output_lines.extend([
                            f'重置周期：{reset_info}', f'上次重置：{format_date(last_reset_time)}',
                            f'下次重置：还有 {days_to_reset} 天', '', '📈 **使用情况分析**',
                            f'建议日均：{calculate_remaining_daily_allowance(remaining, days_to_reset)}'
                        ])
                        if time_now > last_reset_time and used > 0:
                            daily_bytes = used / max(1, (time_now - last_reset_time) / 86400)
                            up_percent = round(upload / used * 100, 2)
                            output_lines.extend([
                                f'本期日均：{format_size(int(daily_bytes))}',
                                f'预估耗尽：{estimate_depletion_date(remaining, daily_bytes)}',
                                f'上下行比：↑{up_percent:.2f}% / ↓{100-up_percent:.2f}%'
                            ])

                node_info = get_node_info(res.text)
                if node_info:
                    output_lines.extend(['', '🌐 **节点信息**', f"节点总数：{node_info['node_count']}"])
                    if node_info.get('type_count'):
                        types_str = ', '.join(f'{k}:{v}' for k, v in sorted(node_info['type_count'].items(), key=lambda i: i[1], reverse=True))
                        output_lines.append(f'节点类型：{types_str}')
                    if node_info.get('regions'):
                        sorted_regions = sorted(node_info['regions'].items(), key=lambda i: i[1], reverse=True)
                        full_region_string = ", ".join([f"{k}({v})" for k, v in sorted_regions])
                        prefix = "地区分布："
                        wrapper = textwrap.TextWrapper(width=200, initial_indent=prefix, subsequent_indent=' ' * len(prefix))
                        wrapped_regions = wrapper.fill(full_region_string)
                        output_lines.append(wrapped_regions)

                output_lines.extend(['', f'查询时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
                
                body_block = "```\n" + "\n".join(output_lines) + "\n```"
                reports.append(f"{url_line}\n{body_block}")
            
            except (KeyError, IndexError):
                node_info = get_node_info(res.text)
                # This is the corrected logic, replacing the deleted function call.
                status = "有效" if node_info and node_info.get('node_count', 0) > 0 else "无效或格式不支持"
                report_lines = ['📌 **基本信息**', f'机场名称：{airport_name}', f'订阅状态：{status}','', '⚠️ **提示**', '无流量信息']
                if node_info: report_lines.append(f"节点数量：{node_info.get('node_count')}")
                body_block = "```\n" + "\n".join(report_lines) + "\n```"
                reports.append(f"{url_line}\n{body_block}")

        except Exception as e:
            url_line = f"订阅链接：`{initial_url}`"
            body_block = f"```\n⚠️ **查询出错**\n{type(e).__name__}: {str(e)}\n```"
            reports.append(f"{url_line}\n{body_block}")

    separator = "\n\n━━━━━━━━━━━━━━\n\n"
    await msg.edit(separator.join(reports))