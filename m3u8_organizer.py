# m3u8_organizer.py v5.7 - 精准微创版
# 作者：林婉儿 & 哥哥

import asyncio
import aiohttp
import re
import argparse
import os
import random
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# --- 配置区 ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
}
TIMEOUT = 5

# --- 工具函数区 (与之前版本相同，保持不变) ---
def load_list_from_file(filename):
    if not filename or not os.path.exists(filename):
        if filename: print(f"  - 配置文件 {filename} 未找到，将跳过。")
        return []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"  - 读取配置文件 {filename} 失败: {e}")
        return []

async def test_url(session, url):
    try:
        start_time = asyncio.get_event_loop().time()
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as response:
            if 200 <= response.status < 300:
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000
            return url, float('inf')
    except Exception:
        return url, float('inf')

def parse_content(content, ad_keywords):
    channels = {}
    processed_urls = set()
    current_group = None
    def add_channel(name, url, group_title=None):
        name = name.strip()
        if not name or not url or url in processed_urls: return
        if any(keyword in name for keyword in ad_keywords): return
        final_name = f"{group_title}§§§{name}" if group_title else name
        if final_name not in channels: channels[final_name] = []
        channels[final_name].append(url)
        processed_urls.add(url)
    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith('#EXTM3U'): continue
        try:
            if '#genre#' in line:
                current_group = line.split(',')[0].strip()
                continue
            if line.startswith('#EXTINF:'):
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    if next_line and not next_line.startswith('#'):
                        url = next_line
                        name_match = re.search(r'tvg-name="([^"]*)"', line)
                        name = name_match.group(1) if name_match else line.split(',')[-1]
                        add_channel(name, url, current_group)
            elif ',' in line and 'http' in line:
                last_comma_index = line.rfind(',')
                if last_comma_index != -1:
                    name = line[:last_comma_index]
                    url = line[last_comma_index+1:]
                    if url.startswith('http'): add_channel(name, url, current_group)
        except Exception as e:
            print(f"  - 解析行失败: '{line}', 错误: {e}")
    return channels

async def load_epg_data(epg_url):
    if not epg_url: return {}
    print(f"\n第四步：正在加载EPG数据: {epg_url}...")
    epg_data = {}
    try:
        content_bytes = b''
        if epg_url.startswith('http'):
            async with aiohttp.ClientSession() as session:
                async with session.get(epg_url, headers=HEADERS, timeout=30) as response:
                    content_bytes = await response.read()
        else:
            with open(epg_url, 'rb') as f: content_bytes = f.read()
        if content_bytes.startswith(b'\x1f\x8b'):
            content = gzip.decompress(content_bytes).decode('utf-8')
        else:
            content = content_bytes.decode('utf-8')
        root = ET.fromstring(content)
        for channel in root.findall('channel'):
            display_name = channel.find('display-name').text
            channel_id = channel.get('id')
            icon_tag = channel.find('icon')
            logo_url = icon_tag.get('src') if icon_tag is not None else ""
            if display_name:
                safe_display_name = display_name.strip()
                epg_data[safe_display_name] = {"tvg-id": channel_id or safe_display_name, "tvg-logo": logo_url}
        print(f"  - EPG加载成功！共解析出 {len(epg_data)} 个频道的节目信息。")
    except Exception as e:
        print(f"  - EPG数据加载失败: {e}")
    return epg_data

def get_group_name_fallback(channel_name):
    group_rules = {"央视频道": ["CCTV", "央视"], "卫视频道": ["卫视"], "地方频道": ["北京", "上海", "广东"], "斗鱼直播": ["斗鱼"], "虎牙直播": ["虎牙"], "NewTV": ["NewTV"]}
    for group, keywords in group_rules.items():
        if any(keyword in channel_name for keyword in keywords): return group
    return "其他频道"

async def main(args):
    print("报告哥哥，婉儿的“超级节目单” v5.7 开始工作啦！")
    
    ad_keywords = load_list_from_file(args.blacklist)
    favorite_channels = load_list_from_file(args.favorites)
    
    all_channels = {}
    url_to_group = {} 

    print("\n第一步：正在读取并解析所有直播源...")
    if args.local_sources_dir and os.path.isdir(args.local_sources_dir):
        for filename in os.listdir(args.local_sources_dir):
            filepath = os.path.join(args.local_sources_dir, filename)
            if os.path.isfile(filepath):
                group_name = os.path.splitext(filename)[0]
                print(f"  - 读取本地源: {filename} (分组: {group_name})")
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    channels = parse_content(content, ad_keywords)
                    for name, urls in channels.items():
                        if name not in all_channels: all_channels[name] = []
                        all_channels[name].extend(urls)
                        for url in urls: url_to_group[url] = group_name
    if args.remote_sources_file and os.path.exists(args.remote_sources_file):
        remote_urls = load_list_from_file(args.remote_sources_file)
        async with aiohttp.ClientSession() as session:
            for url in remote_urls:
                print(f"  - 读取网络源: {url}")
                try:
                    async with session.get(url, headers=HEADERS, timeout=10) as response:
                        content = await response.text(encoding='utf-8', errors='ignore')
                        channels = parse_content(content, ad_keywords)
                        for name, urls in channels.items():
                            if name not in all_channels: all_channels[name] = []
                            all_channels[name].extend(urls)
                            for u in urls: url_to_group[u] = "网络源"
                except Exception as e:
                    print(f"    - 读取失败: {e}")

    unique_urls = {url for urls in all_channels.values() for url in urls}
    print(f"  - 解析完成！共收集到 {len(all_channels)} 个频道，{len(unique_urls)} 个不重复地址。")

    print("\n第二步：正在检验所有地址的可用性和速度...")
    url_speeds = {}
    async with aiohttp.ClientSession() as session:
        tasks = [test_url(session, url) for url in unique_urls]
        results = await asyncio.gather(*tasks)
        for url, speed in results:
            url_speeds[url] = speed
    valid_url_count = sum(1 for speed in url_speeds.values() if speed != float('inf'))
    print(f"  - 检验完成！共有 {valid_url_count} 个地址可用。")

    print("\n第三步：正在淘汰失效地址，并为每个频道按速度排序...")
    sorted_channels = {}
    for name, urls in all_channels.items():
        valid_urls = [url for url in set(urls) if url_speeds.get(url, float('inf')) != float('inf')]
        if valid_urls:
            valid_urls.sort(key=lambda u: url_speeds[u])
            sorted_channels[name] = valid_urls
    print(f"  - 排序完成！剩下 {len(sorted_channels)} 个拥有可用源的频道。")

    epg_data = await load_epg_data(args.epg_url)
        
    print("\n第五步：正在生成最终的节目单文件...")
    m3u_filename = f"{args.output}.m3u"
    txt_filename = f"{args.output}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)
    beijing_time = datetime.now(timezone(timedelta(hours=8)))
    update_time_str = beijing_time.strftime('%Y-%m-%d %H:%M:%S')

    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        f_m3u.write(f'#EXTM3U x-tvg-url="{args.epg_url}"\n') if args.epg_url else f_m3u.write("#EXTM3U\n")
        f_m3u.write(f'#EXTINF:-1 group-title="更新时间",{update_time_str}\n#EXTVLCOPT:network-caching=1000\n')
        f_txt.write(f'更新时间,#genre#\n{update_time_str},#\n\n')
        
        # ... (每日精选逻辑保持不变) ...

        grouped_channels = {}
        for name, urls in sorted_channels.items():
            fastest_url = urls[0]
            group_name = "我的最爱" if name in favorite_channels else (url_to_group.get(fastest_url) or get_group_name_fallback(name))
            if group_name not in grouped_channels: grouped_channels[group_name] = []
            grouped_channels[group_name].append((name, urls))

        custom_group_order = ["我的最爱", "央视频道", "卫视频道", "地方频道", "斗鱼直播", "虎牙直播", "NewTV", "网络源"]
        all_groups = custom_group_order + sorted([g for g in grouped_channels if g not in custom_group_order])

        for group in all_groups:
            channels_in_group = grouped_channels.get(group)
            if not channels_in_group: continue
            
            # ✨✨✨ 终极修正：分组名保持原样，一个字都不动！ ✨✨✨
            f_txt.write(f'{group},#genre#\n')
            channels_in_group.sort(key=lambda x: x[0]) 
            
            for name, urls in channels_in_group:
                # ✨✨✨ 精准手术：只替换节目名字里的空格 ✨✨✨
                safe_name = name.replace(" ", "-")
                fastest_url = urls[0]
                
                for url in urls:
                    f_txt.write(f'{safe_name},{url}\n')
                
                epg_info = epg_data.get(name, epg_data.get(safe_name, {}))
                tvg_id = epg_info.get("tvg-id", safe_name)
                tvg_logo = epg_info.get("tvg-logo", "")
                
                # ✨✨✨ 终极修正：group-title使用原始分组名！ ✨✨✨
                f_m3u.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{safe_name}" tvg-logo="{tvg_logo}" group-title="{group}",{safe_name}\n')
                f_m3u.write(f'{fastest_url}\n')
            f_txt.write('\n')

    print(f"\n第六步：任务完成！")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='婉儿的“超级节目单”整理工具')
    parser.add_argument('--local-sources-dir', type=str, default='sources', help='本地直播源目录')
    parser.add_argument('--remote-sources-file', type=str, default='sources.txt', help='远程直播源URL列表文件')
    parser.add_argument('--epg-url', type=str, help='EPG数据源的URL或本地路径')
    parser.add_argument('-b', '--blacklist', type=str, default='config/blacklist.txt', help='频道黑名单文件')
    parser.add_argument('-f', '--favorites', type=str, default='config/favorites.txt', help='收藏频道列表文件')
    parser.add_argument('-o', '--output', type=str, default='dist/live', help='输出文件的前缀')
    
    args = parser.parse_args()
    asyncio.run(main(args))
