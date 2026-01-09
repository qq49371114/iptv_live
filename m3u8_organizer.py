# m3u8_organizer.py v4.1 - 自动化分组版
# 作者：婉儿 & 哥哥

import asyncio
import aiohttp
import re
import argparse
import json
from urllib.parse import urlparse
import os

# --- 配置区 ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
}
TIMEOUT = 5

# ✨ 我们不再需要GROUP_RULES了，因为分组是自动的！

# --- 核心功能区 ---

def load_list_from_file(filename):
    """从txt文件加载列表，一行一个"""
    if not filename:
        return []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"  - 配置文件 {filename} 未找到，将跳过。")
        return []
    except Exception as e:
        print(f"  - 读取配置文件 {filename} 失败: {e}")
        return []

async def test_url(session, url):
    """异步测试单个URL的连通性和响应时间"""
    try:
        start_time = asyncio.get_event_loop().time()
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as response:
            if 200 <= response.status < 300:
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000
            else:
                return url, float('inf')
    except Exception:
        return url, float('inf')

def parse_m3u(content, ad_keywords):
    """解析M3U和TXT格式的内容"""
    channels = {}
    processed_urls = set()

    def add_channel(name, url):
        if not name or not url or url in processed_urls:
            return
        if any(keyword in name for keyword in ad_keywords):
            print(f"  - 过滤广告频道: {name}")
            return
        if name not in channels:
            channels[name] = []
        channels[name].append(url)
        processed_urls.add(url)

    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            if line.startswith('#EXTINF:'):
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    if next_line and not next_line.startswith('#'):
                        url = next_line
                        name_match = re.search(r'tvg-name="([^"]+)"', line)
                        name = name_match.group(1) if name_match else line.split(',')[-1]
                        add_channel(name, url)
            elif ',' in line and 'http' in line:
                parts = line.split(',')
                if len(parts) >= 2:
                    name = parts[0]
                    url = ','.join(parts[1:])
                    add_channel(name, url)
        except Exception as e:
            print(f"  - 解析行失败: '{line}', 错误: {e}")
            
    return channels

async def main(args):
    """主函数"""
    print("报告哥哥，婉儿的“超级节目单” v4.1 开始工作啦！")
    
    print("零步：正在加载外部配置文件...")
    ad_keywords = load_list_from_file(args.blacklist)
    favorite_channels = load_list_from_file(args.favorites)
    
    all_channels = {}
    url_to_group = {} 
    unique_urls = set()

    print("\n第一步：正在读取、解析并过滤所有直播源...")
    for source_pair in args.sources_with_group:
        parts = source_pair.split(':', 1)
        source_path = parts[0]
        group_name = parts[1] if len(parts) > 1 else "其他频道" 
        
        content = ""
        try:
            if source_path.startswith('http'):
                async with aiohttp.ClientSession() as session:
                    async with session.get(source_path, headers=HEADERS, timeout=10) as response:
                        content = await response.text()
            else:
                with open(source_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            channels = parse_m3u(content, ad_keywords)
            for name, urls in channels.items():
                if name not in all_channels:
                    all_channels[name] = []
                all_channels[name].extend(urls)
                for url in urls:
                    unique_urls.add(url)
                    if url not in url_to_group:
                        url_to_group[url] = group_name
        except Exception as e:
            print(f"  - 读取源 {source_path} 失败: {e}")
    print(f"  - 解析完成！...")

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
        valid_urls = []
        for url in set(urls):
            if url_speeds.get(url, float('inf')) != float('inf'):
                valid_urls.append(url)
        if valid_urls:
            valid_urls.sort(key=lambda u: url_speeds[u])
            sorted_channels[name] = valid_urls
    print(f"  - 排序完成！剩余 {len(sorted_channels)} 个拥有可用源的频道。")

    epg_data = {}
    if args.epg:
        print(f"\n第四步：正在加载EPG对应表: {args.epg}...")
        try:
            with open(args.epg, 'r', encoding='utf-8') as f:
                epg_data = json.load(f)
            print("  - EPG对应表加载成功。")
        except Exception as e:
            print(f"  - EPG对应表加载失败: {e}")
    else:
        print("\n第四步：未提供EPG对应表，将不添加额外信息。")

    print("\n第五步：正在生成最终的节目单文件...")
    m3u_filename = f"{args.output}.m3u"
    with open(m3u_filename, 'w', encoding='utf-8') as f:
        f.write(f'#EXTM3U x-tvg-url="{args.epg_url}"\n') if args.epg_url else f.write("#EXTM3U\n")
        
        grouped_channels = {}
        for name, urls in sorted_channels.items():
            fastest_url = urls[0]
            group_name = "我的最爱" if name in favorite_channels else url_to_group.get(fastest_url, "其他频道")
            if group_name not in grouped_channels:
                grouped_channels[group_name] = []
            grouped_channels[group_name].append((name, urls))

        custom_group_order = ["我的最爱"] + [g for g in grouped_channels if g != "我的最爱" and g != "其他频道"] + ["其他频道"]
        
        for group in custom_group_order:
            channels_in_group = grouped_channels.get(group, [])
            channels_in_group.sort(key=lambda x: x[0]) 
            for name, urls in channels_in_group:
                fastest_url = urls[0]
                epg_info = epg_data.get(name, {})
                tvg_id = epg_info.get("tvg-id", name)
                tvg_logo = epg_info.get("tvg-logo", "")
                f.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" tvg-logo="{tvg_logo}" group-title="{group}",{name}\n')
                f.write(f'{fastest_url}\n')

    print(f"  - 已生成优化版M3U文件: {m3u_filename}")

    txt_filename = f"{args.output}.txt"
    with open(txt_filename, 'w', encoding='utf-8') as f:
        for name, urls in sorted_channels.items():
            for url in urls:
                f.write(f'{name},{url}\n')
    print(f"  - 已生成TXT备份文件: {txt_filename}")
    
    print("\n报告哥哥，所有任务已完成！我们的后勤部长更强大啦！")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="婉儿的M3U8直播源整理工具 v4.1")
    parser.add_argument('-i', '--sources-with-group', nargs='+', required=True, help="输入的'源文件路径:分组名'列表")
    parser.add_argument('-e', '--epg', default=None, help="EPG对应表JSON文件 (可选)")
    parser.add_argument('--epg-url', default="", help="外部EPG URL地址 (可选)")
    parser.add_argument('-b', '--blacklist', default="config/blacklist.txt", help="广告关键词黑名单文件")
    parser.add_argument('-f', '--favorites', default="config/favorites.txt", help="最爱频道列表文件")
    parser.add_argument('-o', '--output', default="live", help="输出文件的前缀名")
    args = parser.parse_args()
    
    asyncio.run(main(args))
