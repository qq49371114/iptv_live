# m3u8_organizer.py v5.4 - 最终兼容版
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
TIMEOUT = 5 # 单个URL的测试超时时间

# --- 工具函数区 ---

def load_list_from_file(filename):
    """从文件中加载列表，如黑名单、收藏夹。"""
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
    """异步测试单个URL的可用性和响应速度。"""
    try:
        start_time = asyncio.get_event_loop().time()
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as response:
            if 200 <= response.status < 300:
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000  # 返回毫秒
            return url, float('inf')
    except Exception:
        return url, float('inf')

def parse_content(content, ad_keywords):
    """从M3U或TXT格式的文本内容中解析出频道名和URL。"""
    channels = {}
    processed_urls = set()
    current_group = None

    def add_channel(name, url, group_title=None):
        name = name.strip()
        if not name or not url or url in processed_urls: return
        if any(keyword in name for keyword in ad_keywords): return
        
        final_name = f"{group_title}§§§{name}" if group_title else name
        if final_name not in channels:
            channels[final_name] = []
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
                    if url.startswith('http'):
                        add_channel(name, url, current_group)
        except Exception as e:
            print(f"  - 解析行失败: '{line}', 错误: {e}")
            
    return channels

async def load_epg_data(epg_url):
    """
    ✨ 婉儿的智能EPG加载器 v1.0 ✨
    - 自动判断是URL还是本地文件
    - 自动检测并解压Gzip
    - 使用正确的XML解析器
    """
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
            with open(epg_url, 'rb') as f:
                content_bytes = f.read()

        # 智能检测Gzip并解压
        if content_bytes.startswith(b'\x1f\x8b'):
            print("  - 检测到Gzip压缩，正在解压...")
            content = gzip.decompress(content_bytes).decode('utf-8')
        else:
            content = content_bytes.decode('utf-8')

        # 使用XML解析器
        print("  - 正在使用XML解析器解析EPG...")
        root = ET.fromstring(content)
        for channel in root.findall('channel'):
            display_name = channel.find('display-name').text
            channel_id = channel.get('id')
            icon_tag = channel.find('icon')
            logo_url = icon_tag.get('src') if icon_tag is not None else ""
            if display_name:
                # ✨ 净化EPG中的频道名空格，用于后续匹配
                safe_display_name = display_name.strip()
                epg_data[safe_display_name] = {"tvg-id": channel_id or safe_display_name, "tvg-logo": logo_url}
        print(f"  - EPG加载成功！共解析出 {len(epg_data)} 个频道的节目信息。")

    except ET.ParseError as e:
        print(f"  - EPG文件XML解析失败: {e}。请检查文件格式是否正确。")
    except Exception as e:
        print(f"  - EPG数据加载失败: {e}")
        
    return epg_data

def get_group_name_fallback(channel_name):
    """备用分组逻辑，根据频道名关键字猜测分组。"""
    group_rules = {
        "央视频道": ["CCTV", "央视"], "卫视频道": ["卫视"], "地方频道": ["北京", "上海", "广东"],
        "斗鱼直播": ["斗鱼"], "虎牙直播": ["虎牙"], "NewTV": ["NewTV"],
    }
    for group, keywords in group_rules.items():
        for keyword in keywords:
            if keyword in channel_name:
                return group
    return "其他频道"

async def main(args):
    print("报告哥哥，婉儿的“超级节目单” v5.4 开始工作啦！")
    
    ad_keywords = load_list_from_file(args.blacklist)
    favorite_channels = load_list_from_file(args.favorites)
    
    all_channels = {}
    url_to_group = {} 

    print("\n第一步：正在读取并解析所有直播源...")
    
    # 1. 处理本地源目录
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

    # 2. 处理远程源文件
    if args.remote_sources_file and os.path.exists(args.remote_sources_file):
        remote_urls = load_list_from_file(args.remote_sources_file)
        async with aiohttp.ClientSession() as session:
            for url in remote_urls:
                print(f"  - 读取网络源: {url}")
                try:
                    async with session.get(url, headers=HEADERS, timeout=10) as response:
                        content = await response.text()
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

    # 第四步：加载EPG数据
    epg_data = await load_epg_data(args.epg_url)
        
    print("\n第五步：正在生成最终的节目单文件...")
    m3u_filename = f"{args.output}.m3u"
    txt_filename = f"{args.output}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)

    beijing_time = datetime.now(timezone(timedelta(hours=8)))
    update_time_str = beijing_time.strftime('%Y-%m-%d %H:%M:%S')

    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, \
         open(txt_filename, 'w', encoding='utf-8') as f_txt:
        
        # 写入文件头
        f_m3u.write(f'#EXTM3U x-tvg-url="{args.epg_url}"\n') if args.epg_url else f_m3u.write("#EXTM3U\n")
        f_m3u.write(f'#EXTINF:-1 group-title="更新时间",{update_time_str}\n#EXTVLCOPT:network-caching=1000\n')
        f_txt.write(f'更新时间,#genre#\n{update_time_str},#\n\n')

        # 处理“每日精选”盲盒
        picks_dir = "picks"
        if os.path.isdir(picks_dir):
            f_m3u.write(f'#EXTINF:-1 group-title="婉儿为哥哥整理",{update_time_str}\n#EXTVLCOPT:network-caching=1000\n')
            f_txt.write(f'婉儿为哥哥整理,#genre#\n')
            
            pick_files = sorted(os.listdir(picks_dir))
            for pick_file in pick_files:
                pick_path = os.path.join(picks_dir, pick_file)
                if os.path.isfile(pick_path):
                    pick_name = os.path.splitext(pick_file)[0]
                    with open(pick_path, 'r', encoding='utf-8') as pf:
                        pick_content = pf.read()
                    
                    pick_channels = parse_content(pick_content, ad_keywords)
                    pick_valid_urls = [url for urls in pick_channels.values() for url in urls if url_speeds.get(url, float('inf')) != float('inf')]
                    
                    if pick_valid_urls:
                        random_url = random.choice(pick_valid_urls)
                        safe_pick_name = pick_name.replace(" ", "-") # 净化盲盒名
                        f_m3u.write(f'#EXTINF:-1 tvg-id="{safe_pick_name}" tvg-name="{safe_pick_name}",{safe_pick_name}\n{random_url}\n')
                        f_txt.write(f'{safe_pick_name},{random_url}\n')
            f_txt.write('\n')
            
        # 准备常规频道数据
        grouped_channels = {}
        for name, urls in sorted_channels.items():
            fastest_url = urls[0]
            group_name = "我的最爱" if name in favorite_channels else (url_to_group.get(fastest_url) or get_group_name_fallback(name))

            if group_name not in grouped_channels:
                grouped_channels[group_name] = []
            grouped_channels[group_name].append((name, urls))

        # 写入常规频道
        custom_group_order = ["我的最爱", "央视频道", "卫视频道", "地方频道", "斗鱼直播", "虎牙直播", "NewTV", "网络源"]
        all_groups = custom_group_order + sorted([g for g in grouped_channels if g not in custom_group_order])

        for group in all_groups:
            channels_in_group = grouped_channels.get(group)
            if not channels_in_group: continue
            
            # ✨✨✨ 关键净化：替换分组名中的空格 ✨✨✨
            safe_group = group.replace(" ", "-")
            f_txt.write(f'{safe_group},#genre#\n')
            channels_in_group.sort(key=lambda x: x[0]) 
            
            for name, urls in channels_in_group:
                # ✨✨✨ 关键净化：替换频道名中的空格 ✨✨✨
                safe_name = name.replace(" ", "-")
                fastest_url = urls[0]
                
                # 写入TXT文件 (所有源)
                for url in urls:
                    f_txt.write(f'{safe_name},{url}\n')
                
                # 写入M3U文件 (最快的源)
                epg_info = epg_data.get(name, epg_data.get(safe_name, {})) # 优先用原名匹配EPG，再尝试用净化名
                tvg_id = epg_info.get("tvg-id", safe_name)
                tvg_logo = epg_info.get("tvg-logo", "")
                f_m3u.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{safe_name}" tvg-logo="{tvg_logo}" group-title="{safe_group}",{safe_name}\n')
                f_m3u.write(f'{fastest_url}\n')
            f_txt.write('\n')

    print(f"\n第六步：任务完成！节目单已生成到 {m3u_filename} 和 {txt_filename}")
    print("哥哥辛苦啦，现在我们的节目单完美啦！ (づ｡◕‿‿◕｡)づ")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='婉儿的“超级节目单”整理工具')
    parser.add_argument('--local-sources-dir', type=str, default='sources', help='本地直播源目录 (例如: sources/)')
    parser.add_argument('--remote-sources-file', type=str, default='sources.txt', help='包含远程直播源URL列表的文件 (例如: sources.txt)')
    parser.add_argument('--epg-url', type=str, help='EPG数据源的URL或本地路径')
    parser.add_argument('-b', '--blacklist', type=str, default='config/blacklist.txt', help='频道黑名单文件')
    parser.add_argument('-f', '--favorites', type=str, default='config/favorites.txt', help='收藏频道列表文件')
    parser.add_argument('-o', '--output', type=str, default='dist/live', help='输出文件的前缀 (不含扩展名)')
    
    args = parser.parse_args()
    
    asyncio.run(main(args))
