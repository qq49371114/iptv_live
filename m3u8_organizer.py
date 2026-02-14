import os
import re
import gzip
import json
import asyncio
import argparse
import random
import aiohttp
import xml.etree.ElementTree as ET
from urllib import parse as urlparse
from tqdm.asyncio import tqdm_asyncio
import datetime # <--- 我们就用这种最简单的、只导入“大工具箱”的方式！

# =========================================================
# ✨ V22.0 全局设定：我们的“创世法则”
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEADERS = {}
URL_TEST_TIMEOUT = 15
CATEGORY_RULES = {}
CLOCK_URL = ""
GROUP_4K = "💎 凤凰 4K 极清"

# =========================================================
# ✨ V22.0 工具函数：我们的“创世工具箱”
# =========================================================
def load_list_from_file(filename):
    """从文件加载列表，并去除注释和空行"""
    abs_path = os.path.join(BASE_DIR, filename)
    if not filename or not os.path.exists(abs_path):
        if filename: print(f"  - 配置文件 {abs_path} 未找到，将跳过。")
        return []
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"  - 读取配置文件 {abs_path} 失败: {e}")
        return []

def get_epg_id(channel_name):
    """【双向净化】的核心，从各种频道名中，提取出最干净、最标准的ID，用于匹配"""
    # 这里可以根据你的需要，添加更多的净化规则
    # 比如去掉 "HD", "高清", "CCTV-", "CCTV" 等
    name = channel_name.upper().replace("HD", "").replace("高清", "").replace("CCTV-", "CCTV")
    name = re.sub(r'\s+', '', name) # 去掉所有空白符
    return name

def is_4k_channel(channel_name):
    """判断一个频道是否为 4K 频道"""
    return "4K" in channel_name.upper()

def get_pretty_group(group_name):
    """为分类名称添加漂亮的图标"""
    icon_map = {
        "央视": "CCTV",
        "卫视": "🛰️",
        "港澳台": "🇭🇰",
        "我的最爱": "❤️",
        GROUP_4K: "💎"
    }
    return f"{icon_map.get(group_name, '📺')} {group_name}"

def get_pretty_display_name(channel_name):
    """美化最终在播放列表里显示的频道名"""
    # 比如，可以把 "CCTV1" 变成 "CCTV-1"，或者加上清晰度标识
    return channel_name.replace("CCTV", "CCTV-")

# =========================================================
# ✨ V22.1 配置中心：我们的“后勤总管”
# =========================================================
def load_global_config(config_file):
    """加载全局配置文件，并与默认值合并"""
    default_config = {
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        },
        "url_test_timeout": 15,
        "epg_urls": ["https://live.fanmingming.com/e.xml"],
        "clock_url": "http://quan.suning.com/getSysTime.do",
        "category_rules": {}
    }
    abs_path = os.path.join(BASE_DIR, config_file)
    if not os.path.exists(abs_path):
        print(f"全局配置文件 {abs_path} 未找到，将使用默认配置。")
        return default_config
    
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
            # ✨✨✨ 100% 还原哥哥你那极其严谨的递归更新逻辑 ✨✨✨
            for key, value in user_config.items():
                if isinstance(value, dict) and key in default_config and isinstance(default_config[key], dict):
                    default_config[key].update(value)
                else:
                    default_config[key] = value
            print("外部配置加载成功！")
    except Exception as e:
        print(f"加载全局配置文件 {abs_path} 失败: {e}，将使用默认配置。")
    return default_config

def load_category_rules_from_dir(rules_dir):
    """从外部规则目录加载分类规则，作为备用方案"""
    abs_path = os.path.join(BASE_DIR, rules_dir)
    category_rules = {}
    if not os.path.isdir(abs_path):
        print(f"【警告】备用规则目录 '{abs_path}' 不存在！")
        return {}
    print(f"正在从【备用规则库】'{abs_path}' 加载分类规则...")
    for filename in os.listdir(abs_path):
        if filename.endswith('.txt'):
            category_name = os.path.splitext(filename)[0]
            filepath = os.path.join(abs_path, filename)
            keywords = load_list_from_file(filepath)
            if keywords:
                category_rules[category_name] = keywords
    return category_rules

# =========================================================
# ✨ V22.1 质检员：我们的“终极追踪神探”
# =========================================================
async def test_url(session, url):
    """【100% 还原】测试单个URL的延迟，并手动处理重定向"""
    try:
        start_time = asyncio.get_event_loop().time()
        async with session.get(url, headers=HEADERS, timeout=URL_TEST_TIMEOUT, allow_redirects=False) as response:
            if response.status in [301, 302, 307, 308]:
                redirected_url = response.headers.get('Location')
                if redirected_url and not redirected_url.startswith('http'):
                    base_url = urlparse.urljoin(url, '.')
                    redirected_url = urlparse.urljoin(base_url, redirected_url)

                if redirected_url:
                    new_headers = HEADERS.copy()
                    new_headers['Referer'] = url 
                    async with session.get(redirected_url, headers=new_headers, timeout=URL_TEST_TIMEOUT - 3, allow_redirects=False) as redirected_response:
                        if 200 <= redirected_response.status < 300:
                            end_time = asyncio.get_event_loop().time()
                            return url, (end_time - start_time) * 1000
            elif 200 <= response.status < 300:
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000
            return url, float('inf')
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return url, float('inf')
    except Exception:
        return url, float('inf')

# =========================================================
# ✨ V22.1 解析引擎：我们的“双语同声传译”
# =========================================================
def classify_channel(channel_name):
    """【100% 还原】外部规则分类逻辑，作为备用"""
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in channel_name for keyword in keywords):
            return category
    return None # 返回 None，而不是“其他”，方便我们判断

def parse_m3u_content(content, ad_keywords):
    """【语言统一】专门解析 M3U 格式，优先使用 #genre#"""
    channels = {}
    processed_urls = set()
    current_category_from_genre = None

    def add_channel(name, url, group_title_from_tag):
        name = name.strip().replace(" ", "")
        url = url.strip()
        if not name or not url or url in processed_urls: return
        if any(keyword in name for keyword in ad_keywords): return
        
        # 优先级：文件内 #genre# > EXTINF里的 group-title > 外部 rules 文件夹 > "其他"
        final_category = current_category_from_genre or group_title_from_tag or classify_channel(name) or "其他"

        if final_category not in channels: channels[final_category] = {}
        if name not in channels[final_category]: channels[final_category][name] = []
        channels[final_category][name].append(url)
        processed_urls.add(url)

    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line: continue
        
        if '#genre#' in line:
            try:
                current_category_from_genre = line.split(',')[0].strip()
            except: pass
            continue

        if not line.startswith('#EXTINF:'): continue
        
        try:
            if i + 1 < len(lines) and not lines[i+1].strip().startswith('#'):
                url = lines[i+1].strip()
                group_match = re.search(r'group-title="([^"]*)"', line)
                group_title = group_match.group(1).strip() if group_match else None
                name_match = re.search(r'tvg-name="([^"]*)"', line)
                name = name_match.group(1) if name_match else line.split(',')[-1]
                add_channel(name, url, group_title)
        except Exception:
            continue
    return channels

def parse_txt_content(content, ad_keywords):
    """【语言统一】专门解析 TXT 格式，支持 #genre#"""
    channels = {}
    processed_urls = set()
    current_category = "其他"

    def add_channel(name, url):
        name = name.strip().replace(" ", "")
        url = url.strip()
        if not name or not url or url in processed_urls: return
        if any(keyword in name for keyword in ad_keywords): return
        
        category_to_use = current_category
        classified_category = classify_channel(name)
        if classified_category: category_to_use = classified_category

        if category_to_use not in channels: channels[category_to_use] = {}
        if name not in channels[category_to_use]: channels[category_to_use][name] = []
        channels[category_to_use][name].append(url)
        processed_urls.add(url)

    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'): continue
        
        if '#genre#' in line:
            try:
                current_category = line.split(',')[0].strip()
            except: pass
            continue

        if ',' in line and 'http' in line:
            try:
                last_comma_index = line.rfind(',')
                name = line[:last_comma_index]
                url = line[last_comma_index+1:]
                if url.startswith('http'): add_channel(name, url)
            except Exception:
                continue
    return channels

# =========================================================
# ✨ V22.1 EPG 数据中心：我们的“情报局”
# =========================================================
async def load_epg_data(epg_url):
    """【100% 还原】GZIP 处理逻辑与双向净化"""
    if not epg_url: return {}
    print(f"\n📡 正在加载 EPG 数据: {epg_url}...")
    epg_data = {}
    try:
        content_bytes = b''
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
# 🚀 V22.1 主引擎：我们的“创世核心”
# =========================================================
async def main(args):
    """主执行函数：凤凰系统的完全体引擎"""
    print(f"报告哥哥，婉儿的“超级节目单” v22.1【创世终章版】开始工作啦！")

    # --- EPG 处理逻辑 ---
    epg_backup_list = args.epg_url[:3]
    top_3_epgs_str = ",".join(epg_backup_list)
    print(f"\nEPG处理：最终将写入这几个EPG源到文件: {top_3_epgs_str}")

    epg_data = {}
    for epg_url in epg_backup_list:
        temp_epg_data = await load_epg_data(epg_url)
        if temp_epg_data:
            epg_data = temp_epg_data
            print(f"  - ✅ 本次运行选用EPG主源: {epg_url}")
            break
    if not epg_data:
        print("  - ⚠️ 警告：所有EPG源均不可用！")

    ad_keywords = load_list_from_file(args.blacklist)
    favorite_channels = load_list_from_file(args.favorites)

    # --- 第一步：【万源归宗】 ---
    print("\n第一步：【万源归宗】正在融合所有信号源...")
    # 统一的数据结构：{ "频道名": {"urls": set(), "category": "分类"} }
    all_channels_pool = {} 

    def merge_categorized_channels(categorized_data):
        """一个专门用来融合“已分类数据”的辅助函数"""
        for category, channels in categorized_data.items():
            for name, urls in channels.items():
                cleaned_name = name.strip().replace(" ", "")
                if not cleaned_name: continue
                if cleaned_name not in all_channels_pool:
                    all_channels_pool[cleaned_name] = {"urls": set(), "category": category}
                all_channels_pool[cleaned_name]["urls"].update(urls)

    # 1. 抓取本地【种子仓库】
    manual_sources_abs_dir = os.path.join(BASE_DIR, args.manual_sources_dir)
    if os.path.isdir(manual_sources_abs_dir):
        print(f"  - 📂 读取【种子仓库】: {manual_sources_abs_dir}")
        for filename in os.listdir(manual_sources_abs_dir):
            filepath = os.path.join(manual_sources_abs_dir, filename)
            if os.path.isfile(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if filename.endswith('.m3u'):
                        categorized_channels = parse_m3u_content(content, ad_keywords)
                    else:
                        categorized_channels = parse_txt_content(content, ad_keywords)
                    merge_categorized_channels(categorized_channels)

    # 2. 抓取【网络云端源】
    remote_sources_abs_file = os.path.join(BASE_DIR, args.remote_sources_file)
    if os.path.exists(remote_sources_abs_file):
        print(f"  - 🌐 正在同步网络云端信号...")
        remote_urls = load_list_from_file(args.remote_sources_file)
        
        connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            async def fetch_and_parse(remote_url):
                try:
                    async with session.get(remote_url, headers=HEADERS, timeout=20) as response:
                        content = await response.text(encoding='utf-8', errors='ignore')
                        if remote_url.endswith('.m3u'):
                            categorized_channels = parse_m3u_content(content, ad_keywords)
                        else:
                            categorized_channels = parse_txt_content(content, ad_keywords)
                        merge_categorized_channels(categorized_channels)
                except Exception:
                    pass
            for url in remote_urls:
                tasks.append(fetch_and_parse(url))
            await asyncio.gather(*tasks)

    unique_urls_count = sum(len(data["urls"]) for data in all_channels_pool.values())
    print(f"  - ✅ 融合完成！共收集到 {len(all_channels_pool)} 个频道，{unique_urls_count} 条独立线路。")

    # --- 第二步：【终极试炼】 ---
    print("\n第二步：【终极试炼】正在检验所有地址的可用性...")
    all_urls_to_test = {url for data in all_channels_pool.values() for url in data["urls"]}

    # 【100% 还原】盲盒(Picks)源一起参加“大比武”
    picks_abs_dir = os.path.join(BASE_DIR, args.picks_dir)
    if os.path.isdir(picks_abs_dir):
        for pick_file in os.listdir(picks_abs_dir):
            pick_path = os.path.join(picks_abs_dir, pick_file)
            if os.path.isfile(pick_path) and pick_file.endswith('.txt'):
                with open(pick_path, 'r', encoding='utf-8') as pf:
                    for line in pf:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        try:
                            url = line.split(',')[-1]
                            if url.startswith('http'): all_urls_to_test.add(url)
                        except IndexError:
                            if line.startswith('http'): all_urls_to_test.add(line)

    url_speeds = {}
    semaphore = asyncio.Semaphore(1000) 

    async def limited_test_url(session, url):
        async with semaphore:
            return await test_url(session, url)

    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [limited_test_url(session, url) for url in all_urls_to_test]
        results = []
        for f in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc="⚡ 凤凰质检"):
            results.append(await f)
        for url, speed in results:
            url_speeds[url] = speed

    valid_url_count = sum(1 for speed in url_speeds.values() if speed != float('inf'))
    print(f"\n  - 试炼完成！存活节点 {valid_url_count}/{len(all_urls_to_test)}。")

    # --- 第三步：【生态进化】 ---
    print("\n第三步：【生态进化】正在为幸存者归类并筛选 4K 信号...")
    survivors_classified = {}

    for name, data in all_channels_pool.items():
        valid_urls = [url for url in data["urls"] if url_speeds.get(url, float('inf')) != float('inf')]
        if valid_urls:
            valid_urls.sort(key=lambda u: url_speeds[u])

            # 优先使用“万源归宗”时记录的分类
            category = data.get("category", "其他")
            
            # 4K 智能拦截，提升到专属分类
            if is_4k_channel(name):
                category = GROUP_4K
            
            if category not in survivors_classified:
                survivors_classified[category] = {}
            if name not in survivors_classified[category]:
                 survivors_classified[category][name] = []

            # 【100% 还原】线路保留策略
            if data.get("source_type") == "manual":
                survivors_classified[category][name].extend(valid_urls)
            else:
                survivors_classified[category][name].extend(valid_urls[:5])

    print(f"  - ✅ 生态进化完成！幸存频道已按部就班归队。")

    # --- 第四步：【融合输出】 ---
    print("\n第四步：【融合输出】正在准备生成最终节目单...")
    output_abs_path = os.path.join(BASE_DIR, args.output)
    m3u_filename = f"{output_abs_path}.m3u"
    txt_filename = f"{output_abs_path}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)

    beijing_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')

    # 【100% 还原】真·盲盒随机逻辑
    blind_box_group_name = "婉儿为哥哥整理"
    blind_box_channels = {}
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
                    
                    # 从解析出的数据中提取有效URL
                    valid_urls_in_file = []
                    for channels in pick_channels_data.values():
                        for urls in channels.values():
                            valid_urls_in_file.extend([url for url in urls if url_speeds.get(url, float('inf')) != float('inf')])

                    if valid_urls_in_file:
                        random_url = random.choice(valid_urls_in_file)
                        safe_pick_name = pick_name.replace(" ", "-")
                        blind_box_channels[safe_pick_name] = [random_url]
                        print(f"    - 盲盒 '{pick_name}' 已开启，幸运源：{random_url[:50]}...")
                    else:
                        print(f"    - 盲盒 '{pick_name}' 已失效。")

    # 准备常规分组并处理收藏
    final_grouped_channels = {}
    if blind_box_channels:
        final_grouped_channels[blind_box_group_name] = blind_box_channels

    for category, channels in survivors_classified.items():
        for name, urls in channels.items():
            group_name = "我的最爱" if name in favorite_channels else category
            if group_name not in final_grouped_channels:
                final_grouped_channels[group_name] = {}
            if name not in final_grouped_channels[group_name]:
                 final_grouped_channels[group_name][name] = []
            final_grouped_channels[group_name][name].extend(urls)

    # 【100% 还原】黄金排序逻辑
    prefix_order = ["婉儿为哥哥整理", GROUP_4K, "我的最爱", "央视", "卫视", "港澳台"]
    all_existing_groups = list(final_grouped_channels.keys())
    ordered_groups = []
    for group in prefix_order:
        if group in all_existing_groups:
            ordered_groups.append(group)
            all_existing_groups.remove(group)
    other_group_exists = "其他" in all_existing_groups
    if other_group_exists: all_existing_groups.remove("其他")
    ordered_groups.extend(sorted(all_existing_groups))
    if other_group_exists: ordered_groups.append("其他")

    # 【100% 还原】黄金大循环与双格式输出
    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        f_m3u.write(f'#EXTM3U x-tvg-url="{top_3_epgs_str}" tvg-url="{top_3_epgs_str}" catchup="append" catchup-source="?playseek=${{(b)yyyyMMddHHmmss}}-${{(e)yyyyMMddHHmmss}}"\n')
        f_m3u.write(f'#EXTINF:-1 group-title="🕒 凤凰·更新时间",凤凰更新时间({beijing_time})\n{CLOCK_URL}\n')
        f_txt.write(f'更新时间,#genre#\n{beijing_time},{CLOCK_URL}\n\n')

        for group in ordered_groups:
            pretty_group_name = get_pretty_group(group)
            f_txt.write(f'{pretty_group_name},#genre#\n')
            channels_in_group = final_grouped_channels.get(group)
            if not channels_in_group: continue
            for name, urls in sorted(channels_in_group.items()):
                eid = get_epg_id(name)
                disp = get_pretty_display_name(name)
                info = epg_data.get(eid, {})
                tid = info.get("tvg-id", eid)
                logo = info.get("tvg-logo", "")
                for url in urls:
                    f_txt.write(f'{disp},{url}\n')
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

    print(f"\n第五步：任务完成！我们的生态系统已按黄金顺序完成最终进化！")
    print(f"  - 最终成品已生成: {m3u_filename} (M3U) & {txt_filename} (TXT)")
    print(f"  - 婉儿报告：4K 归位、EPG 根本对齐、盲盒灵魂已复产！")

# =========================================================
# 🏛️ V22.1 创世入口：我们的“上帝之手”
# =========================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='婉儿的“超级节目单” v22.1【创世终章版】')
    parser.add_argument('--config', type=str, default='config.json', help='全局JSON配置文件的路径')
    parser.add_argument('--rules-dir', type=str, default='rules', help='【备用】分类规则目录')
    parser.add_argument('--manual-sources-dir', type=str, default='sources_manual', help='【种子仓库】手动维护的源目录')
    parser.add_argument('--remote-sources-file', type=str, default='sources.txt', help='包含远程直播源URL列表的文件')
    parser.add_argument('--picks-dir', type=str, default='picks', help='【每日精选】盲盒源目录')
    parser.add_argument('--epg-url', nargs='+', default=None, help='【覆盖】EPG数据源URL')
    parser.add_argument('-b', '--blacklist', type=str, default='config/blacklist.txt', help='频道黑名单文件')
    parser.add_argument('-f', '--favorites', type=str, default='config/favorites.txt', help='收藏频道列表文件')
    parser.add_argument('-o', '--output', type=str, default='dist/live', help='输出文件的前缀')
    args = parser.parse_args()

    config = load_global_config(args.config)
    
    if 'category_rules' in config and isinstance(config['category_rules'], dict):
        CATEGORY_RULES = config['category_rules']
    else:
        CATEGORY_RULES = load_category_rules_from_dir(args.rules_dir)
        
    epg_source_list = args.epg_url or config.get('epg_urls', ['https://live.fanmingming.com/e.xml'])
    args.epg_url = epg_source_list

    HEADERS = config.get('headers', {})
    URL_TEST_TIMEOUT = config.get('url_test_timeout', 15)
    CLOCK_URL = config.get('clock_url', "")

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n好的哥哥，婉儿收到指令，提前结束本次工作啦！")
    except Exception as e:
        print(f"\n啊哦，程序遇到了一个意想不到的错误: {e}")
