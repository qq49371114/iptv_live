# m3u8_organizer.py v7.2 - 规则文件化版
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
import shutil
import json

# --- 配置加载区 ---

def load_global_config(config_path):
    """从JSON文件加载全局配置（超时、请求头等）"""
    default_config = {
        "headers": {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
        },
        "url_test_timeout": 8
    }
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                print(f"正在从 {config_path} 加载外部配置...")
                user_config = json.load(f)
                default_config.update(user_config)
                print("外部配置加载成功！")
        else:
            print(f"配置文件 {config_path} 未找到，将使用默认配置。")
    except Exception as e:
        print(f"加载全局配置文件 {config_path} 失败: {e}，将使用默认配置。")
    return default_config

def load_category_rules_from_dir(rules_dir):
    """从目录加载分类规则，一个文件一个分类"""
    category_rules = {}
    if not os.path.isdir(rules_dir):
        print(f"【警告】规则目录 '{rules_dir}' 不存在，将无法进行分类！")
        return {}
    
    print(f"正在从【规则库】'{rules_dir}' 加载分类规则...")
    for filename in os.listdir(rules_dir):
        if filename.endswith('.txt'):
            category_name = os.path.splitext(filename)[0]
            filepath = os.path.join(rules_dir, filename)
            keywords = load_list_from_file(filepath)
            if keywords:
                category_rules[category_name] = keywords
                print(f"  - 已加载分类 '{category_name}'，包含 {len(keywords)} 个关键字。")
    return category_rules

# --- 全局变量 (将在 main 函数前被赋值) ---
HEADERS = {}
URL_TEST_TIMEOUT = 8
CATEGORY_RULES = {}

# --- 工具函数区 ---
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
        async with session.get(url, headers=HEADERS, timeout=URL_TEST_TIMEOUT) as response:
            if 200 <= response.status < 300:
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000
            return url, float('inf')
    except Exception:
        return url, float('inf')

def parse_content(content, ad_keywords):
    channels = {}
    processed_urls = set()
    def add_channel(name, url):
        name = name.strip()
        if not name or not url or url in processed_urls: return
        if any(keyword in name for keyword in ad_keywords): return
        if name not in channels: channels[name] = []
        channels[name].append(url)
        processed_urls.add(url)
    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith('#EXTM3U'): continue
        try:
            if '#genre#' in line: continue
            if line.startswith('#EXTINF:'):
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    if next_line and not next_line.startswith('#'):
                        url = next_line
                        name_match = re.search(r'tvg-name="([^"]*)"', line)
                        name = name_match.group(1) if name_match else line.split(',')[-1]
                        add_channel(name, url)
            elif ',' in line and 'http' in line:
                last_comma_index = line.rfind(',')
                if last_comma_index != -1:
                    name = line[:last_comma_index]
                    url = line[last_comma_index+1:]
                    if url.startswith('http'): add_channel(name, url)
        except Exception as e:
            print(f"  - 解析行失败: '{line}', 错误: {e}")
    return channels

async def load_epg_data(epg_url):
    if not epg_url: return {}
    print(f"\n加载EPG数据: {epg_url}...")
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

def classify_channel(channel_name):
    """根据全局规则为频道名分类"""
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in channel_name for keyword in keywords):
            return category
    return "其他"

async def main(args):
    print("报告哥哥，婉儿的“超级节目单” v7.2【规则文件化】版开始工作啦！")
    
    ad_keywords = load_list_from_file(args.blacklist)
    favorite_channels = load_list_from_file(args.favorites)
    
    print("\n第一步：【万源归宗】正在融合所有源...")
    all_channels_pool = {}
    if os.path.isdir(args.manual_sources_dir):
        print(f"  - 读取【种子仓库】: {args.manual_sources_dir}")
        for filename in os.listdir(args.manual_sources_dir):
            filepath = os.path.join(args.manual_sources_dir, filename)
            if os.path.isfile(filepath) and filename.endswith('.txt'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    channels = parse_content(content, ad_keywords)
                    for name, urls in channels.items():
                        if name not in all_channels_pool:
                            all_channels_pool[name] = {"urls": set(), "source_type": "manual"}
                        all_channels_pool[name]["urls"].update(urls)
    if args.remote_sources_file and os.path.exists(args.remote_sources_file):
        print(f"  - 读取网络源文件: {args.remote_sources_file}")
        remote_urls = load_list_from_file(args.remote_sources_file)
        async with aiohttp.ClientSession() as session:
            for url in remote_urls:
                try:
                    async with session.get(url, headers=HEADERS, timeout=10) as response:
                        content = await response.text(encoding='utf-8', errors='ignore')
                        channels = parse_content(content, ad_keywords)
                        for name, urls in channels.items():
                            if name not in all_channels_pool:
                                all_channels_pool[name] = {"urls": set(), "source_type": "network"}
                            all_channels_pool[name]["urls"].update(urls)
                except Exception as e:
                    print(f"    - 读取网络源 {url} 失败: {e}")
    unique_urls_count = sum(len(data["urls"]) for data in all_channels_pool.values())
    print(f"  - 融合完成！共收集到 {len(all_channels_pool)} 个频道，{unique_urls_count} 个不重复地址。")

    print("\n第二步：【终极试炼】正在检验所有地址的可用性...")
    all_urls_to_test = {url for data in all_channels_pool.values() for url in data["urls"]}
    url_speeds = {}
    async with aiohttp.ClientSession() as session:
        tasks = [test_url(session, url) for url in all_urls_to_test]
        results = await asyncio.gather(*tasks)
        for url, speed in results:
            url_speeds[url] = speed
    valid_url_count = sum(1 for speed in url_speeds.values() if speed != float('inf'))
    print(f"  - 试炼完成！共有 {valid_url_count} 个地址可用。")

    print("\n第三步：【生态进化】正在分类幸存者并更新【成品仓库】...")
    survivors_classified = {}
    for name, data in all_channels_pool.items():
        valid_urls = [url for url in data["urls"] if url_speeds.get(url, float('inf')) != float('inf')]
        if valid_urls:
            valid_urls.sort(key=lambda u: url_speeds[u])
            category = classify_channel(name)
            if category not in survivors_classified:
                survivors_classified[category] = {}
            if name not in survivors_classified[category]:
                survivors_classified[category][name] = []
            if data["source_type"] == "manual":
                survivors_classified[category][name].extend(valid_urls)
            else:
                survivors_classified[category][name].extend(valid_urls[:5])
    if os.path.exists(args.generated_sources_dir):
        shutil.rmtree(args.generated_sources_dir)
    os.makedirs(args.generated_sources_dir, exist_ok=True)
    print(f"  - 已清空并重建【成品仓库】: {args.generated_sources_dir}")
    for category, channels in survivors_classified.items():
        network_survivors = {name: urls for name, urls in channels.items() if all_channels_pool.get(name, {}).get("source_type") == "network"}
        if network_survivors:
            filepath = os.path.join(args.generated_sources_dir, f"{category}.txt")
            with open(filepath, 'w', encoding='utf-8') as f:
                for name, urls in sorted(network_survivors.items()):
                    for url in urls:
                        f.write(f"{name},{url}\n")
            print(f"    - 已生成成品: {filepath}")

    print("\n第四步：【融合输出】正在生成最终节目单...")
    epg_data = await load_epg_data(args.epg_url)
    m3u_filename = f"{args.output}.m3u"
    txt_filename = f"{args.output}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)
    beijing_time = datetime.now(timezone(timedelta(hours=8)))
    update_time_str = beijing_time.strftime('%Y-%m-%d %H:%M:%S')
    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        f_m3u.write(f'#EXTM3U x-tvg-url="{args.epg_url}"\n') if args.epg_url else f_m3u.write("#EXTM3U\n")
        f_m3u.write(f'#EXTINF:-1 group-title="更新时间",{update_time_str}\n#EXTVLCOPT:network-caching=1000\n')
        f_txt.write(f'更新时间,#genre#\n{update_time_str},#\n\n')
        final_grouped_channels = {}
        for category, channels in survivors_classified.items():
            group_name = category
            is_favorite_group = any(name in favorite_channels for name in channels.keys())
            if is_favorite_group:
                group_name = "我的最爱"
            if group_name not in final_grouped_channels:
                final_grouped_channels[group_name] = {}
            final_grouped_channels[group_name].update(channels)
        
        # 确保分组顺序
        custom_group_order = ["我的最爱"] + list(CATEGORY_RULES.keys()) + ["其他"]
        # 去重并保持顺序
        ordered_groups = []
        for group in custom_group_order:
            if group not in ordered_groups:
                ordered_groups.append(group)

        for group in ordered_groups:
            channels_in_group = final_grouped_channels.get(group)
            if not channels_in_group: continue
            f_txt.write(f'{group},#genre#\n')
            for name, urls in sorted(channels_in_group.items()):
                safe_name = name.replace(" ", "-")
                fastest_url = urls[0]
                for url in urls:
                    f_txt.write(f'{safe_name},{url}\n')
                epg_info = epg_data.get(name, epg_data.get(safe_name, {}))
                tvg_id = epg_info.get("tvg-id", safe_name)
                tvg_logo = epg_info.get("tvg-logo", "")
                f_m3u.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{safe_name}" tvg-logo="{tvg_logo}" group-title="{group}",{safe_name}\n')
                f_m3u.write(f'{fastest_url}\n')
            f_txt.write('\n')
    print(f"\n第五步：任务完成！我们的生态系统完成了一次进化！")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='婉儿的“超级节目单” v7.2【规则文件化】版')
    parser.add_argument('--config', type=str, default='config.json', help='全局JSON配置文件的路径')
    parser.add_argument('--rules-dir', type=str, default='rules', help='【规则库】分类规则目录')
    parser.add_argument('--manual-sources-dir', type=str, default='sources_manual', help='【种子仓库】手动维护的源目录')
    parser.add_argument('--generated-sources-dir', type=str, default='sources_generated', help='【成品仓库】脚本自动生成的源目录')
    parser.add_argument('--remote-sources-file', type=str, default='sources.txt', help='包含远程直播源URL列表的文件')
    parser.add_argument('--epg-url', type=str, help='EPG数据源的URL或本地路径')
    parser.add_argument('-b', '--blacklist', type=str, default='config/blacklist.txt', help='频道黑名单文件')
    parser.add_argument('-f', '--favorites', type=str, default='config/favorites.txt', help='收藏频道列表文件')
    parser.add_argument('-o', '--output', type=str, default='dist/live', help='输出文件的前缀')
    
    args = parser.parse_args()

    # --- 真正的配置加载在这里执行 ---
    config = load_global_config(args.config)
    HEADERS = config['headers']
    URL_TEST_TIMEOUT = config['url_test_timeout']
    CATEGORY_RULES = load_category_rules_from_dir(args.rules_dir)
    
    asyncio.run(main(args))
