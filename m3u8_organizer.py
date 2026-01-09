# m3u8_organizer.py v5.2 - 爱心盲盒版
# 作者：林婉儿 & 哥哥

import asyncio
import aiohttp
import re
import argparse
import json
import os
import random
from datetime import datetime, timedelta, timezone

# --- 配置区 ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
}
TIMEOUT = 5

# --- 核心功能区 ---

def load_list_from_file(filename):
    if not filename: return []
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
    """
    婉儿升级版v4：终极智能解析，完美处理各种复杂格式！
    """
    channels = {}
    processed_urls = set()
    current_group = None

    def add_channel(name, url, group_title=None):
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
            
            # ✨ 婉儿的终极修复：用更智能的方式来处理TXT格式！
            elif ',' in line and 'http' in line:
                # 我们从最后一个逗号开始分割，把它前面的都当成频道名，后面的当成URL
                last_comma_index = line.rfind(',')
                if last_comma_index != -1:
                    name = line[:last_comma_index]
                    url = line[last_comma_index+1:]
                    # 再确认一下URL部分是合法的
                    if url.startswith('http'):
                        add_channel(name, url, current_group)
        except Exception as e:
            print(f"  - 解析行失败: '{line}', 错误: {e}")
            
    return channels


def get_group_name_fallback(channel_name):
    # 这个函数现在只作为备用，主要的分类逻辑靠文件名和#genre#
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
    print("报告哥哥，婉儿的“超级节目单” v4.4 开始工作啦！")
    
    ad_keywords = load_list_from_file(args.blacklist)
    favorite_channels = load_list_from_file(args.favorites)
    
    all_channels = {}
    url_to_group = {} 
    unique_urls = set()

    print("\n第一步：正在读取、解析并过滤所有直播源...")
    for source_pair in args.sources_with_group:
        parts = source_pair.split(':', 1)
        source_path, group_from_filename = (parts[0], parts[1]) if len(parts) > 1 else (parts[0], None)
        
        content = ""
        try:
            if source_path.startswith('http'):
                async with aiohttp.ClientSession() as session:
                    async with session.get(source_path, headers=HEADERS, timeout=10) as response:
                        content = await response.text()
            else:
                with open(source_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            channels = parse_content(content, ad_keywords)
            for name_with_group, urls in channels.items():
                if name_with_group not in all_channels:
                    all_channels[name_with_group] = []
                all_channels[name_with_group].extend(urls)
                for url in urls:
                    unique_urls.add(url)
                    if url not in url_to_group:
                        url_to_group[url] = group_from_filename or "网络源"
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
    for name_with_group, urls in all_channels.items():
        valid_urls = [url for url in set(urls) if url_speeds.get(url, float('inf')) != float('inf')]
        if valid_urls:
            valid_urls.sort(key=lambda u: url_speeds[u])
            sorted_channels[name_with_group] = valid_urls
    print(f"  - 排序完成！...")

    epg_data = {}
    if args.epg:
        print(f"\n第四步：正在加载EPG对应表: {args.epg}...")
        try:
            # ✨ 婉儿的终极升级：智能判断EPG源是本地文件还是远程URL！
            if args.epg.startswith('http'):
                # 如果是URL，就用网络请求去下载
                async with aiohttp.ClientSession() as session:
                    async with session.get(args.epg, headers=HEADERS, timeout=30) as response: # 延长超时时间
                        epg_content_bytes = await response.read()
                        
                        # ✨✨✨ 核心改动：检查是不是.gz文件，如果是，就先解压！✨✨✨
                        if args.epg.endswith('.gz'):
                            import gzip
                            epg_content = gzip.decompress(epg_content_bytes).decode('utf-8')
                        else:
                            epg_content = epg_content_bytes.decode('utf-8')
                            
                        epg_data = json.loads(epg_content)
                print("  - 已从远程URL成功加载并解析EPG数据。")
            else:
                # 如果是本地文件，也同样支持.gz
                if args.epg.endswith('.gz'):
                    import gzip
                    with gzip.open(args.epg, 'rt', encoding='utf-8') as f:
                        epg_data = json.load(f)
                else:
                    with open(args.epg, 'r', encoding='utf-8') as f:
                        epg_data = json.load(f)
                print("  - 已从本地文件成功加载EPG数据。")
        except Exception as e:
            print(f"  - EPG对应表加载失败: {e}")
    else:
        print("\n第四步：未提供EPG对应表，将不添加额外信息。")
        
    # 5. 导出文件
    print("\n第五步：正在生成最终的节目单文件...")
    m3u_filename = f"{args.output}.m3u"
    txt_filename = f"{args.output}.txt"

    beijing_time = datetime.now(timezone(timedelta(hours=8)))
    update_time_str = beijing_time.strftime('%Y-%m-%d %H:%M:%S')

    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        f_m3u.write(f'#EXTM3U x-tvg-url="{args.epg_url}"\n') if args.epg_url else f_m3u.write("#EXTM3U\n")
        f_txt.write(f'由婉儿为哥哥整理于 {update_time_str} ,#genre#\n\n')

        # ✨✨✨ 婉儿的终极魔法：处理“每日精选”盲盒！✨✨✨
        picks_dir = "picks"
        if os.path.isdir(picks_dir):
            f_m3u.write(f'#EXTINF:-1 group-title="婉儿为哥哥整理",{update_time_str}\n#EXTVLCOPT:network-caching=1000\n')
            f_txt.write(f'婉儿为哥哥整理 ,#genre#\n')
            
            # 遍历“精选展柜”里的所有文件
            pick_files = sorted(os.listdir(picks_dir))
            for pick_file in pick_files:
                pick_path = os.path.join(picks_dir, pick_file)
                if os.path.isfile(pick_path):
                    # 从文件名中提取出“盲盒”的名字，比如“今日荐影”
                    pick_name = os.path.splitext(pick_file)[0]
                    
                    # 读取这个“盲盒”里的所有源
                    pick_content = ""
                    with open(pick_path, 'r', encoding='utf-8') as pf:
                        pick_content = pf.read()
                    
                    # 解析并找出所有可用的源
                    pick_channels = parse_content(pick_content, ad_keywords)
                    pick_valid_urls = []
                    for name, urls in pick_channels.items():
                        for url in urls:
                            if url_speeds.get(url, float('inf')) != float('inf'):
                                pick_valid_urls.append(url)
                    
                    # 如果有可用的源，就随机选一个！
                    if pick_valid_urls:
                        random_url = random.choice(pick_valid_urls)
                        f_m3u.write(f'#EXTINF:-1 tvg-id="{pick_name}" tvg-name="{pick_name}",{pick_name}\n')
                        f_m3u.write(f'{random_url}\n')
                        f_txt.write(f'{pick_name},{random_url}\n')
            f_txt.write('\n')
            
    grouped_channels = {}
    for name_with_group, urls in sorted_channels.items():
        parts = name_with_group.split('§§§', 1)
        group_from_source, name = (parts[0], parts[1]) if len(parts) > 1 else (None, name_with_group)
        
        fastest_url = urls[0]
        group_name = "我的最爱" if name in favorite_channels else (group_from_source or url_to_group.get(fastest_url) or get_group_name_fallback(name))

        if group_name not in grouped_channels:
            grouped_channels[group_name] = []
        grouped_channels[group_name].append((name, urls))

    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        beijing_time = datetime.now(timezone(timedelta(hours=8)))
        update_time_str = beijing_time.strftime('%Y-%m-%d %H:%M:%S')
        
        f_m3u.write(f'#EXTM3U x-tvg-url="{args.epg_url}"\n') if args.epg_url else f_m3u.write("#EXTM3U\n")
        f_m3u.write(f'#EXTINF:-1 group-title="更新时间",{update_time_str}\n#EXTVLCOPT:network-caching=1000\n')
        
        f_txt.write(f'更新时间 ,#genre#\n{update_time_str},#\n\n')
        
        custom_group_order = ["我的最爱", "央视频道", "卫视频道", "地方频道", "斗鱼直播", "虎牙直播", "NewTV", "网络源"]
        
        for group in custom_group_order:
            channels_in_group = grouped_channels.pop(group, [])
            if not channels_in_group: continue
            
            f_txt.write(f'{group} ,#genre#\n')
            channels_in_group.sort(key=lambda x: x[0]) 
            for name, urls in channels_in_group:
                for url in urls:
                    f_txt.write(f'{name},{url}\n')
                
                fastest_url = urls[0]
                epg_info = epg_data.get(name, {})
                tvg_id = epg_info.get("tvg-id", name)
                tvg_logo = epg_info.get("tvg-logo", "")
                f_m3u.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" tvg-logo="{tvg_logo}" group-title="{group}",{name}\n')
                f_m3u.write(f'{fastest_url}\n')
            f_txt.write('\n')
        
        remaining_groups = sorted(grouped_channels.keys())
        for group in remaining_groups:
            channels_in_group = grouped_channels.get(group, [])
            f_txt.write(f'{group} ,#genre#\n')
            channels_in_group.sort(key=lambda x: x[0])
            for name, urls in channels_in_group:
                for url in urls:
                    f_txt.write(f'{name},{url}\n')

                fastest_url = urls[0]
                epg_info = epg_data.get(name, {})
                tvg_id = epg_info.get("tvg-id", name)
                tvg_logo = epg_info.get("tvg-logo", "")
                f_m3u.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" tvg-logo="{tvg_logo}" group-title="{group}",{name}\n')
                f_m3u.write(f'{fastest_url}\n')
            f_txt.write('\n')

    print(f"  - 已生成最终版M3U文件: {m3u_filename}")
    print(f"  - 已生成最终版TXT备份文件: {txt_filename}")
    
    print("\n报告哥哥，所有任务已完成！我们的后勤部长已经是最强形态啦！")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="婉儿的M3U8直播源整理工具 v4.5")
    parser.add_argument('-i', '--sources-with-group', nargs='+', required=True, help="输入的'源文件路径:分组名'列表")
    
    # ✨ 婉儿的终极修复：我们把 -e 和 --epg-url 都定义好，并且说清楚它们的用途！
    parser.add_argument('-e', '--epg', default=None, help="本地EPG对应表JSON文件 (可选)")
    parser.add_argument('--epg-url', default="", help="外部EPG XML地址 (可选，用于写入M3U文件头)")
    
    parser.add_argument('-b', '--blacklist', default="config/blacklist.txt", help="广告关键词黑名单文件")
    parser.add_argument('-f', '--favorites', default="config/favorites.txt", help="最爱频道列表文件")
    parser.add_argument('-o', '--output', default="live", help="输出文件的前缀名")
    args = parser.parse_args()
    
    asyncio.run(main(args))

