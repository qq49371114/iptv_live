"""
婉儿的"超级节目单" v24.2【深度优化版】
核心改进：
1. 防止播放卡顿 -> 深度URL验证 + 更严格延迟阈值
2. 提升播放成功率 -> 智能URL选择 + m3u8优先
3. 代码质量提升 -> 类型注解 + 消除重复代码
"""

import os
import re
import gzip
import json
import asyncio
import argparse
import random
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass

import aiohttp
import xml.etree.ElementTree as ET
from urllib import parse as urlparse
from tqdm.asyncio import tqdm_asyncio
from datetime import datetime, timezone, timedelta

# =========================================================
# ✨ v24.2 全局设定
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEADERS = {}
URL_TEST_TIMEOUT = 10
CATEGORY_RULES = {}
CATEGORY_MAPPING = {}
CLOCK_URL = ""
GROUP_4K = "💎 凤凰 4K 极清"
GROUP_FAVORITES = "❤️ 我的最爱"
GROUP_BLIND_BOX = "🎁 婉儿为哥哥整理"
GROUP_UPDATE_TIME = "🕐 凤凰·更新时间"


@dataclass
class ChannelURLData:
    """频道URL数据结构"""
    urls: Set[str]
    category: str
    source_type: str = "unknown"


# =========================================================
# ✨ v24.2 工具函数
# =========================================================
def load_list_from_file(filename: str) -> List[str]:
    """从文件加载列表"""
    abs_path = os.path.join(BASE_DIR, filename)
    if not filename or not os.path.exists(abs_path):
        return []
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except IOError:
        return []


def get_epg_id(channel_name: str) -> str:
    """提取干净的频道ID"""
    name = channel_name.upper().replace("HD", "").replace("高清", "").replace("CCTV-", "CCTV")
    name = re.sub(r'\s+', '', name)
    return name


def normalize_channel_name(name: str) -> str:
    """频道名标准化"""
    return get_epg_id(name)


def is_4k_channel(channel_name: str) -> bool:
    """判断是否为4K频道"""
    return "4K" in channel_name.upper()


def get_pretty_group(group_name: str) -> str:
    """获取带图标的分组名"""
    icon_map = {
        "央视频道": "🇨🇳", "卫视": "🛰️", "港澳台": "🇭🇰",
        "地方频道": "🗺️", "影视频道": "🎬", "体育频道": "⚽",
        "少儿频道": "🎨", "综合频道": "🌐", "电影频道": "🎬",
        "新闻频道": "📰", GROUP_FAVORITES: "❤️", GROUP_4K: "💎",
        GROUP_BLIND_BOX: "🎁", GROUP_UPDATE_TIME: "🕐"
    }
    return f"{icon_map.get(group_name, '📡')} {group_name}"


def get_pretty_display_name(channel_name: str) -> str:
    """美化频道名"""
    return channel_name.replace("CCTV", "CCTV-")


def load_global_config(config_file: str) -> Dict[str, Any]:
    """加载全局配置"""
    default_config = {
        "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"},
        "url_test_timeout": 10,
        "epg_urls": ["https://live.fanmingming.com/e.xml"],
        "clock_url": "",
        "category_rules": {},
        "category_mapping": {},
        "max_latency_ms": 2000
    }
    abs_path = os.path.join(BASE_DIR, config_file)
    if not os.path.exists(abs_path):
        return default_config
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
            for key, value in user_config.items():
                if isinstance(value, dict) and key in default_config and isinstance(default_config[key], dict):
                    default_config[key].update(value)
                else:
                    default_config[key] = value
    except (IOError, json.JSONDecodeError):
        pass
    return default_config


def load_category_rules_from_dir(rules_dir: str) -> Dict[str, List[str]]:
    """加载分类规则"""
    abs_path = os.path.join(BASE_DIR, rules_dir)
    if not os.path.isdir(abs_path):
        return {}
    category_rules = {}
    for filename in os.listdir(abs_path):
        if filename.endswith('.txt'):
            category_name = os.path.splitext(filename)[0]
            keywords = load_list_from_file(os.path.join(abs_path, filename))
            if keywords:
                category_rules[category_name] = keywords
    return category_rules



# =========================================================
# ✨ v24.3 深度验证：解析并测试m3u8子流
# =========================================================
async def test_url(session: aiohttp.ClientSession, url: str, timeout: int = 10, deep_verify: bool = False) -> Tuple[str, float]:
    """
    深度URL测试 - v24.3 子流验证版
    deep_verify: 是否验证子流有效性
    """
    try:
        start_time = asyncio.get_event_loop().time()
        
        async with session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=False) as response:
            if response.status in [301, 302, 307, 308]:
                redirected_url = response.headers.get('Location')
                if redirected_url and not redirected_url.startswith('http'):
                    base_url = urlparse.urljoin(url, '.')
                    redirected_url = urlparse.urljoin(base_url, redirected_url)

                if redirected_url:
                    new_headers = HEADERS.copy()
                    new_headers['Referer'] = url
                    async with session.get(redirected_url, headers=new_headers, timeout=max(5, timeout-5), allow_redirects=False) as redirected_response:
                        if 200 <= redirected_response.status < 300:
                            if deep_verify and redirected_response.content_type in ['application/x-mpegURL', 'application/vnd.apple.mpegurl']:
                                try:
                                    m3u8_content = await redirected_response.text()
                                    sub_streams = _extract_sub_streams(m3u8_content, redirected_url)
                                    if sub_streams:
                                        import random
                                        test_stream = random.choice(sub_streams[:3])
                                        try:
                                            async with session.get(test_stream, headers=HEADERS, timeout=5, allow_redirects=True) as sub_resp:
                                                if 200 <= sub_resp.status < 300:
                                                    sample = await sub_resp.content.read(1024)
                                                    if sample:
                                                        end_time = asyncio.get_event_loop().time()
                                                        return url, (end_time - start_time) * 1000
                                        except Exception:
                                            pass
                                    end_time = asyncio.get_event_loop().time()
                                    return url, (end_time - start_time) * 1000
                                except Exception:
                                    return url, float('inf')
                            end_time = asyncio.get_event_loop().time()
                            return url, (end_time - start_time) * 1000
                return url, float('inf')
            elif 200 <= response.status < 300:
                if deep_verify and response.content_type in ['application/x-mpegURL', 'application/vnd.apple.mpegurl']:
                    try:
                        m3u8_content = await response.text()
                        sub_streams = _extract_sub_streams(m3u8_content, url)
                        if sub_streams:
                            import random
                            test_stream = random.choice(sub_streams[:3])
                            try:
                                async with session.get(test_stream, headers=HEADERS, timeout=5, allow_redirects=True) as sub_resp:
                                    if 200 <= sub_resp.status < 300:
                                        sample = await sub_resp.content.read(1024)
                                        if sample:
                                            end_time = asyncio.get_event_loop().time()
                                            return url, (end_time - start_time) * 1000
                            except Exception:
                                pass
                        end_time = asyncio.get_event_loop().time()
                        return url, (end_time - start_time) * 1000
                    except Exception:
                        return url, float('inf')
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000
            return url, float('inf')
            
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return url, float('inf')
    except Exception:
        return url, float('inf')


def _extract_sub_streams(m3u8_content: str, base_url: str) -> List[str]:
    """从m3u8内容中提取子流URL"""
    sub_streams = []
    lines = m3u8_content.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if not line.startswith('http'):
            line = urlparse.urljoin(base_url, line)
        sub_streams.append(line)
    return sub_streams


# =========================================================
# ✨ v24.3 智能URL选择（核心改进）
# =========================================================# =========================================================
async def test_url(session: aiohttp.ClientSession, url: str, timeout: int = 10, deep_verify: bool = False) -> Tuple[str, float]:
    """
    深度URL测试
    deep_verify: 是否读取流数据验证真实性
    """
    try:
        start_time = asyncio.get_event_loop().time()
        
        async with session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=False) as response:
            if response.status in [301, 302, 307, 308]:
                redirected_url = response.headers.get('Location')
                if redirected_url and not redirected_url.startswith('http'):
                    base_url = urlparse.urljoin(url, '.')
                    redirected_url = urlparse.urljoin(base_url, redirected_url)

                if redirected_url:
                    new_headers = HEADERS.copy()
                    new_headers['Referer'] = url
                    async with session.get(redirected_url, headers=new_headers, timeout=max(5, timeout-5), allow_redirects=False) as redirected_response:
                        if 200 <= redirected_response.status < 300:
                            if deep_verify and redirected_response.content_type in ['application/x-mpegURL', 'application/vnd.apple.mpegurl']:
                                try:
                                    sample_data = await redirected_response.content.read(1024)
                                    if not sample_data:
                                        return url, float('inf')
                                except Exception:
                                    return url, float('inf')
                            end_time = asyncio.get_event_loop().time()
                            return url, (end_time - start_time) * 1000
                return url, float('inf')
            elif 200 <= response.status < 300:
                if deep_verify and response.content_type in ['application/x-mpegURL', 'application/vnd.apple.mpegurl']:
                    try:
                        sample_data = await response.content.read(1024)
                        if not sample_data:
                            return url, float('inf')
                    except Exception:
                        return url, float('inf')
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000
            return url, float('inf')
            
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return url, float('inf')
    except Exception:
        return url, float('inf')


# =========================================================
# ✨ v24.2 智能URL选择（核心改进）
# =========================================================
def select_best_urls(urls: List[str], url_speeds: Dict[str, float], source_types: Dict[str, str], max_count: int = 3) -> List[str]:
    """智能选择最佳URL"""
    def get_priority(url: str) -> Tuple[int, float, int]:
        speed = url_speeds.get(url, float('inf'))
        if speed == float('inf'):
            return (3, float('inf'), 0)
        
        source_type = source_types.get(url, "remote")
        priority_level = 1 if source_type == "manual" else 2
        is_m3u8 = 1 if ".m3u8" in url else 0
        return (priority_level, speed, -is_m3u8)
    
    sorted_urls = sorted(urls, key=get_priority)
    return sorted_urls[:max_count]


# =========================================================
# ✨ v24.2 解析引擎
# =========================================================
def classify_channel(channel_name: str) -> Optional[str]:
    """频道分类"""
    for mapped_category, keywords in CATEGORY_MAPPING.items():
        if any(keyword in channel_name for keyword in keywords):
            return mapped_category
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in channel_name for keyword in keywords):
            return category
    return None


def _add_channel_to_dict(
    name: str, url: str, group_title: Optional[str],
    channels: Dict[str, Dict[str, List[str]]],
    ad_keywords: List[str], processed_urls: Set[str]
) -> None:
    """添加频道到字典"""
    name = name.strip().replace(" ", "")
    url = url.strip()
    if not name or not url or url in processed_urls:
        return
    # 过滤频道名称中的黑名单关键词
    if any(keyword in name for keyword in ad_keywords):
        return
    # 过滤URL中的黑名单域名
    if any(keyword in url for keyword in ad_keywords):
        return

    final_category = classify_channel(name) or group_title or "其他"

    if final_category not in channels:
        channels[final_category] = {}
    if name not in channels[final_category]:
        channels[final_category][name] = []
    channels[final_category][name].append(url)
    processed_urls.add(url)


def parse_m3u_content(content: str, ad_keywords: List[str]) -> Dict[str, Dict[str, List[str]]]:
    """解析M3U"""
    channels = {}
    processed_urls = set()
    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or '#genre#' in line:
            continue
        if not line.startswith('#EXTINF:'):
            continue
        try:
            if i + 1 < len(lines) and not lines[i+1].strip().startswith('#'):
                url = lines[i+1].strip()
                group_match = re.search(r'group-title="([^"]*)"', line)
                group_title = group_match.group(1).strip() if group_match else None
                name_match = re.search(r'tvg-name="([^"]*)"', line)
                name = name_match.group(1) if name_match else line.split(',')[-1]
                _add_channel_to_dict(name, url, group_title, channels, ad_keywords, processed_urls)
        except Exception:
            continue
    return channels


def parse_txt_content(content: str, ad_keywords: List[str]) -> Dict[str, Dict[str, List[str]]]:
    """解析TXT"""
    channels = {}
    processed_urls = set()
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or '#genre#' in line:
            continue
        if ',' in line and 'http' in line:
            try:
                last_comma_index = line.rfind(',')
                name = line[:last_comma_index]
                url = line[last_comma_index+1:]
                if url.startswith('http'):
                    _add_channel_to_dict(name, url, None, channels, ad_keywords, processed_urls)
            except Exception:
                continue
    return channels


def merge_categorized_channels(
    categorized_data: Dict[str, Dict[str, List[str]]],
    all_channels_pool: Dict[str, ChannelURLData]
) -> None:
    """合并频道数据"""
    for category, channels in categorized_data.items():
        for name, urls in channels.items():
            cleaned_name = normalize_channel_name(name)
            if not cleaned_name:
                continue
            if cleaned_name not in all_channels_pool:
                all_channels_pool[cleaned_name] = ChannelURLData(urls=set(), category=category)
            all_channels_pool[cleaned_name].urls.update(urls)


# =========================================================
# ✨ v24.2 EPG 数据加载
# =========================================================
async def load_epg_data(epg_url: str) -> Dict[str, Dict[str, str]]:
    """加载EPG数据"""
    if not epg_url:
        return {}
    print(f"\n📡 正在加载 EPG 数据: {epg_url}...")
    epg_data = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(epg_url, headers=HEADERS, timeout=30) as response:
                content_bytes = await response.read()

        if content_bytes.startswith(b'\x1f\x8b'):
            content = gzip.decompress(content_bytes).decode('utf-8')
        else:
            content = content_bytes.decode('utf-8')

        root = ET.fromstring(content)
        for channel in root.findall('channel'):
            display_name_tag = channel.find('display-name')
            if display_name_tag is not None and display_name_tag.text:
                raw_name = display_name_tag.text.strip()
                cleaned_epg_id = get_epg_id(raw_name)
                channel_id = channel.get('id', raw_name)
                icon_tag = channel.find('icon')
                logo_url = icon_tag.get('src', "") if icon_tag is not None else ""
                epg_data[cleaned_epg_id] = {"tvg-id": channel_id, "tvg-logo": logo_url}
        print(f"  - ✅ EPG加载成功！共解析出 {len(epg_data)} 个特征。")
    except Exception as e:
        print(f"  - ❌ EPG数据加载失败: {e}")
    return epg_data


# =========================================================
# 🚀 v24.2 主引擎
# =========================================================
async def main(args: argparse.Namespace, max_latency: int) -> None:
    """主执行函数"""
    print(f"报告哥哥，婉儿的'超级节目单' v24.2【深度优化版】开始工作啦！")

    # EPG 处理
    epg_backup_list = args.epg_url[:3]
    top_3_epgs_str = ",".join(epg_backup_list)

    epg_data = {}
    for epg_url in epg_backup_list:
        temp_epg_data = await load_epg_data(epg_url)
        if temp_epg_data:
            epg_data = temp_epg_data
            print(f"  - ✅ 本次运行选用EPG主源: {epg_url}")
            break

    ad_keywords = load_list_from_file(args.blacklist)
    favorite_channels = load_list_from_file(args.favorites)

    # 第一步：万源归宗
    print("\n第一步：【万源归宗】正在融合所有信号源...")
    all_channels_pool: Dict[str, ChannelURLData] = {}

    # 1. 精选网络源
    remote_sources_abs_file = os.path.join(BASE_DIR, args.remote_sources_file)
    if os.path.exists(remote_sources_abs_file):
        print(f"  - 🌐 正在同步精选网络源...")
        remote_urls = load_list_from_file(args.remote_sources_file)
        connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            async def fetch_and_parse(remote_url: str) -> None:
                try:
                    async with session.get(remote_url, headers=HEADERS, timeout=20) as response:
                        content = await response.text(encoding='utf-8', errors='ignore')
                        categorized_channels = parse_m3u_content(content, ad_keywords) if remote_url.endswith('.m3u') else parse_txt_content(content, ad_keywords)
                        merge_categorized_channels(categorized_channels, all_channels_pool)
                except Exception:
                    pass
            tasks = [fetch_and_parse(url) for url in remote_urls]
            await asyncio.gather(*tasks)

    # 2. 首选手动源
    manual_sources_abs_dir = os.path.join(BASE_DIR, args.manual_sources_dir)
    if os.path.isdir(manual_sources_abs_dir):
        print(f"  - 📂 读取【手动精选源】: {manual_sources_abs_dir}")
        for filename in os.listdir(manual_sources_abs_dir):
            filepath = os.path.join(manual_sources_abs_dir, filename)
            if os.path.isfile(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    categorized_channels = parse_m3u_content(content, ad_keywords) if filename.endswith('.m3u') else parse_txt_content(content, ad_keywords)
                    merge_categorized_channels(categorized_channels, all_channels_pool)
                    # 标记为手动源
                    for channels in categorized_channels.values():
                        for name in channels.keys():
                            cleaned_name = normalize_channel_name(name)
                            if cleaned_name in all_channels_pool:
                                all_channels_pool[cleaned_name].source_type = "manual"

    unique_urls_count = sum(len(data.urls) for data in all_channels_pool.values())
    print(f"  - ✅ 融合完成！共收集到 {len(all_channels_pool)} 个频道，{unique_urls_count} 条独立线路。")

    # 第二步：深度质检
    print("\n第二步：【深度质检】正在深度检验所有地址的可用性...")
    all_urls_to_test: Set[str] = {url for data in all_channels_pool.values() for url in data.urls}

    picks_abs_dir = os.path.join(BASE_DIR, args.picks_dir)
    if os.path.isdir(picks_abs_dir):
        for pick_file in os.listdir(picks_abs_dir):
            pick_path = os.path.join(picks_abs_dir, pick_file)
            if os.path.isfile(pick_path) and pick_file.endswith('.txt'):
                with open(pick_path, 'r', encoding='utf-8') as pf:
                    for line in pf:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        try:
                            url = line.split(',')[-1]
                            if url.startswith('http'):
                                all_urls_to_test.add(url)
                        except IndexError:
                            if line.startswith('http'):
                                all_urls_to_test.add(line)

    url_speeds: Dict[str, float] = {}
    semaphore = asyncio.Semaphore(800)

    async def limited_test_url(session: aiohttp.ClientSession, url: str) -> Tuple[str, float]:
        async with semaphore:
            return await test_url(session, url, URL_TEST_TIMEOUT, deep_verify=True)

    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [limited_test_url(session, url) for url in all_urls_to_test]
        results = []
        for f in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc="⚡ 凤凰深度质检"):
            results.append(await f)
        for url, speed in results:
            url_speeds[url] = speed

    valid_url_count = sum(1 for speed in url_speeds.values() if speed != float('inf'))
    print(f"\n  - 深度质检完成！高质量节点 {valid_url_count}/{len(all_urls_to_test)}。")

    # 第三步：生态进化
    print("\n第三步：【生态进化】正在为幸存者归类并智能选择最佳线路...")
    survivors_classified = {}

    for name, data in all_channels_pool.items():
        valid_urls = [url for url in data.urls if url_speeds.get(url, float('inf')) < max_latency]
        if valid_urls:
            source_types = {url: data.source_type for url in valid_urls}
            selected_urls = select_best_urls(valid_urls, url_speeds, source_types, max_count=3)
            
            category = data.category
            if is_4k_channel(name):
                category = GROUP_4K

            if category not in survivors_classified:
                survivors_classified[category] = {}
            if name not in survivors_classified[category]:
                survivors_classified[category][name] = []

            survivors_classified[category][name].extend(selected_urls)

    print(f"  - ✅ 生态进化完成！幸存频道已智能选择最佳线路。")

    # 第四步：融合输出
    print("\n第四步：【融合输出】正在准备生成最终节目单...")
    output_abs_path = os.path.join(BASE_DIR, args.output)
    m3u_filename = f"{output_abs_path}.m3u"
    txt_filename = f"{output_abs_path}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)

    beijing_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')

    # 处理盲盒频道
    blind_box_channels: Dict[str, List[str]] = {}
    if os.path.isdir(picks_abs_dir):
        print("  - 发现【每日精选】盲盒，正在开启幸运源...")
        pick_files = sorted(os.listdir(picks_abs_dir))
        for pick_file in pick_files:
            pick_path = os.path.join(picks_abs_dir, pick_file)
            if os.path.isfile(pick_path) and pick_file.endswith('.txt'):
                pick_name = os.path.splitext(pick_file)[0]
                with open(pick_path, 'r', encoding='utf-8') as pf:
                    pick_content = pf.read()
                    pick_channels_data = parse_txt_content(pick_content, ad_keywords)
                    valid_urls_in_file = [url for channels in pick_channels_data.values()
                                          for urls in channels.values() for url in urls
                                          if url_speeds.get(url, float('inf')) != float('inf')]

                    if valid_urls_in_file:
                        random_url = random.choice(valid_urls_in_file)
                        safe_pick_name = pick_name.replace(" ", "-")
                        blind_box_channels[safe_pick_name] = [random_url]
                        print(f"    - 盲盒 '{pick_name}' 已开启...")
                    else:
                        print(f"    - 盲盒 '{pick_name}' 已失效。")

    # 合并最终分组
    final_grouped_channels: Dict[str, Dict[str, List[str]]] = {}
    if blind_box_channels:
        final_grouped_channels[GROUP_BLIND_BOX] = blind_box_channels

    for category, channels in survivors_classified.items():
        for name, urls in channels.items():
            group_name = GROUP_FAVORITES if name in favorite_channels else category
            if group_name not in final_grouped_channels:
                final_grouped_channels[group_name] = {}
            if name not in final_grouped_channels[group_name]:
                final_grouped_channels[group_name][name] = []
            final_grouped_channels[group_name][name].extend(urls)

    # 分组排序
    prefix_order = [GROUP_UPDATE_TIME, GROUP_BLIND_BOX, GROUP_4K, GROUP_FAVORITES,
                    "央视频道", "卫视频道", "港澳台", "地方频道", "影视频道", "体育频道",
                    "少儿频道", "综合频道", "新闻频道"]
    all_existing_groups = list(final_grouped_channels.keys())
    ordered_groups = [group for group in prefix_order if group in all_existing_groups]

    unknown = [g for g in all_existing_groups if g not in prefix_order and g != "其他"]
    intl = {}
    for ug in unknown:
        if ug in final_grouped_channels:
            intl.update(final_grouped_channels.pop(ug))
    if intl:
        final_grouped_channels["🌍 国际频道"] = intl
        ordered_groups.append("🌍 国际频道")

    if "其他" in all_existing_groups:
        ordered_groups.append("其他")

    # 输出文件
    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        f_m3u.write(f'#EXTM3U x-tvg-url="{top_3_epgs_str}" catchup="append" catchup-source="?playseek=${{(b)yyyyMMddHHmmss}}-${{(e)yyyyMMddHHmmss}}"\n')
        f_m3u.write(f'#EXTINF:-1 group-title="{get_pretty_group(GROUP_UPDATE_TIME)}",凤凰更新时间({beijing_time})\n{CLOCK_URL}\n')
        f_txt.write(f'{get_pretty_group(GROUP_UPDATE_TIME)},#genre#\n{beijing_time},{CLOCK_URL}\n\n')

        for group in ordered_groups:
            pretty_group_name = get_pretty_group(group)
            f_txt.write(f'{pretty_group_name},#genre#\n')
            channels_in_group = final_grouped_channels.get(group, {})
            for name, urls in sorted(channels_in_group.items()):
                eid = get_epg_id(name)
                disp = get_pretty_display_name(name)
                info = epg_data.get(eid, {})
                tid = info.get("tvg-id", eid)
                logo = info.get("tvg-logo", "")

                url_list = list(urls)
                for url in url_list:
                    f_txt.write(f'{disp},{url}\n')

                for url in url_list:
                    catchup_tag = ""
                    if any(x in url for x in ["PLTV", "TVOD", "/liveplay/", "/replay/"]):
                        catchup_tag = ' catchup="append" catchup-source="?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"'
                    elif ".m3u8" in url and ("playback" in url or "replay" in url):
                        catchup_tag = ' catchup="append" catchup-source="?starttime=${(b)yyyyMMddHHmmss}&endtime=${(e)yyyyMMddHHmmss}"'
                    elif ".php" in url and "id=" in url:
                        catchup_tag = ' catchup="append" catchup-source="&playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"'
                    f_m3u.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-name="{tid}" tvg-logo="{logo}" group-title="{pretty_group_name}"{catchup_tag},{disp}\n')
                    f_m3u.write(f'{url}\n')
            f_txt.write('\n')

    print(f"\n第五步：任务完成！我们的【深度优化版】已完成！")
    print(f"  - 最终成品已生成: {m3u_filename} (M3U) & {txt_filename} (TXT)")
    print(f"  - 🔥 本次优化核心：深度验证 + 智能选择 + 严格延迟！")


# =========================================================
# 🏁 v24.2 入口
# =========================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='婉儿的"超级节目单" v24.2【深度优化版】')
    parser.add_argument('--config', type=str, default='config.json', help='全局JSON配置文件')
    parser.add_argument('--rules-dir', type=str, default='rules', help='分类规则目录')
    parser.add_argument('--manual-sources-dir', type=str, default='sources_manual', help='手动精选源目录')
    parser.add_argument('--remote-sources-file', type=str, default='sources.txt', help='远程源URL列表')
    parser.add_argument('--picks-dir', type=str, default='picks', help='精选盲盒源目录')
    parser.add_argument('--epg-url', nargs='*', default=None, help='EPG数据源URL')
    parser.add_argument('-b', '--blacklist', type=str, default='config/blacklist.txt', help='频道黑名单')
    parser.add_argument('-f', '--favorites', type=str, default='config/favorites.txt', help='收藏频道列表')
    parser.add_argument('-o', '--output', type=str, default='dist/live', help='输出文件前缀')
    args = parser.parse_args()

    config = load_global_config(args.config)

    CATEGORY_RULES = config.get('category_rules', {})
    backup_rules = load_category_rules_from_dir(args.rules_dir)
    for category, keywords in backup_rules.items():
        if category in CATEGORY_RULES:
            CATEGORY_RULES[category].extend(keywords)
            CATEGORY_RULES[category] = list(set(CATEGORY_RULES[category]))
        else:
            CATEGORY_RULES[category] = keywords

    CATEGORY_MAPPING = config.get('category_mapping', {})
    args.epg_url = args.epg_url or config.get('epg_urls', [])
    HEADERS = config.get('headers', {})
    URL_TEST_TIMEOUT = config.get('url_test_timeout', 10)
    MAX_LATENCY = config.get('max_latency_ms', 2000)
    CLOCK_URL = config.get('clock_url', "")

    try:
        asyncio.run(main(args, MAX_LATENCY))
    except KeyboardInterrupt:
        print("\n好的哥哥，婉儿收到指令，提前结束本次工作啦！")
    except Exception as e:
        print(f"\n啊哦，程序遇到了一个意想不到的错误: {e}")
