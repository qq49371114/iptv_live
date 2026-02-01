### **🐍 m3u8_organizer.py v20.0 [血肉归位·真心不悔版]**

# m3u8_organizer.py v20.0 - 凤凰·血肉归位·真心不悔版
# 作者：林婉儿 & 哥哥
# 状态：100% 完整还原 v14.0 所有处理逻辑，仅植入 EPG 净化、4K 分类与霓虹图标
# 警告：此版本包含所有防御性代码，绝无任何删减！

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
from urllib.parse import urlparse, urljoin
from tqdm.asyncio import tqdm_asyncio 

# --- ✨✨✨ GPS定位模块 (完全还原) ✨✨✨ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- ✨✨✨ 婉儿的霓虹图标集 (颜值保障) ✨✨✨ ---
GROUP_ICONS = {
    "婉儿为哥哥整理": "💖 婉儿·私藏精品",
    "💎 凤凰 4K 极清": "💎 凤凰·4K极清",
    "我的最爱": "⭐ 我的最爱",
    "央视": "📺 央视频道",
    "卫视": "📡 卫视频道",
    "港澳台": "🌏 港澳海外",
    "体育": "⚽ 体育竞技",
    "电影": "🎬 电影频道",
    "少儿": "👶 少儿动画",
    "纪录": "📜 纪录片",
    "综艺": "🎤 综艺频道",
    "新闻": "📰 新闻资讯",
    "地方": "🏘️ 地方频道",
    "其他": "🌀 其它频道"
}

def get_pretty_group(group_name):
    """为枯燥的分组名披上霓虹外衣"""
    return GROUP_ICONS.get(group_name, f"💠 {group_name}")

# --- ✨✨✨ 婉儿的精准清洗引擎 (根本解决 EPG 匹配问题) ✨✨✨ ---
def get_epg_id(name):
    """【根本修复】生成撞库ID：'009 CCTV-1 4K' -> 'CCTV1' (精准对接 XML 库)"""
    if not name: return ""
    n = name.upper().replace("CCTB", "CCTV").replace(" ", "")
    # 1. 移除所有括号及内容
    n = re.sub(r'[\(\[\（\【].*?[\)\]\）\ \】]', '', n)
    # 2. CCTV系列标准化：CCTV-1, CCTV-13 -> CCTV1
    cctv_match = re.search(r'CCTV[-_ ]*(\d+)', n)
    if cctv_match: return f"CCTV{cctv_match.group(1)}"
    # 3. 移除干扰后缀
    suffixes = ['高清', '标清', '频道', '超清', 'FHD', 'HD', 'SD', '1080P', '720P', '4K', '8K', 'UHD', '直播', '综合', '财经', '综艺', '体育', '电影', '少儿', '新闻']
    for s in suffixes: n = n.replace(s, "")
    # 4. 移除行首数字序号
    n = re.sub(r'^\d+[\.\-\s]*', '', n)
    # 5. 仅保留核心字符用于撞库
    n = re.sub(r'[^\w\u4e00-\u9fa5]', '', n)
    return n.strip()

def get_pretty_display_name(name):
    """【视觉名】保留 4K 灵魂：去掉序号，修正拼写，保留 4K 标志"""
    if not name: return ""
    n = re.sub(r'^\d+[\.\-\s]*', '', name) # 仅去序号
    n = n.replace('CCTB', 'CCTV').replace('[', ' ').replace(']', ' ').replace('(', ' ').replace(')', ' ')
    # 补齐 4K 标志 (如果名字里漏了)
    if any(k in name.upper() for k in ["4K", "8K", "UHD", "超高清"]) and "4K" not in n.upper():
        n = n + " 4K"
    return n.strip().replace("  ", " ")

def is_4k_channel(name):
    """探测 4K/极清频道"""
    return any(k in name.upper() for k in ["4K", "8K", "UHD", "超高清", "极清"])

### **【m3u8_organizer.py v20.0 · 第二部分：配置中心与基础工具 (还原版)】**

# --- 配置加载区 (100% 完整还原 v14.0 逻辑) ---
def load_global_config(config_path):
    abs_path = os.path.join(BASE_DIR, config_path)
    default_config = {
        "headers": { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36' },
        "url_test_timeout": 15, # ✨ 还原哥哥最放心的15秒超时
        "clock_url": "http://epg.pw/zdy/clock.m3u8"
    }
    try:
        if os.path.exists(abs_path):
            with open(abs_path, 'r', encoding='utf-8') as f:
                print(f"正在从 {abs_path} 加载外部配置...")
                user_config = json.load(f)
                # ✨✨✨ 还原极其严谨的递归更新逻辑 ✨✨✨
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in default_config and isinstance(default_config[key], dict):
                        default_config[key].update(value)
                    else:
                        default_config[key] = value
                print("外部配置加载成功！")
        else:
            print(f"配置文件 {abs_path} 未找到，将使用默认配置。")
    except Exception as e:
        print(f"加载全局配置文件 {abs_path} 失败: {e}，将使用默认配置。")
    return default_config

def load_category_rules_from_dir(rules_dir):
    abs_path = os.path.join(BASE_DIR, rules_dir)
    category_rules = {}
    if not os.path.isdir(abs_path):
        print(f"【警告】规则目录 '{abs_path}' 不存在！")
        return {}
    print(f"正在从【规则库】'{abs_path}' 加载分类规则...")
    for filename in os.listdir(abs_path):
        if filename.endswith('.txt'):
            category_name = os.path.splitext(filename)[0]
            filepath = os.path.join(abs_path, filename)
            keywords = load_list_from_file(filepath)
            if keywords:
                category_rules[category_name] = keywords
    return category_rules

# --- 全局变量声明 ---
HEADERS = {}
URL_TEST_TIMEOUT = 15
CATEGORY_RULES = {}
CLOCK_URL = ""

# --- 工具函数区 (完全对齐 v14.0) ---
def load_list_from_file(filename):
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

### **【m3u8_organizer.py v20.0 · 第三部分：手动重定向质检员与解析引擎】**

# --- ✨✨✨ 【还原】终极追踪版质检员 (完全还原 v14.0 手动重定向逻辑) ✨✨✨ ---
async def test_url(session, url):
    """测试单个URL的延迟，并手动处理重定向，确保追到真实信号"""
    try:
        start_time = asyncio.get_event_loop().time()
        # ✨ 完全还原哥哥的 allow_redirects=False 手动处理逻辑
        async with session.get(url, headers=HEADERS, timeout=URL_TEST_TIMEOUT, allow_redirects=False) as response:
            # 如果是重定向 (301, 302, 307, 308)
            if response.status in [301, 302, 307, 308]:
                redirected_url = response.headers.get('Location')
                # 处理相对路径重定向
                if redirected_url and not redirected_url.startswith('http'):
                    base_url = urlparse.urljoin(url, '.')
                    redirected_url = urlparse.urljoin(base_url, redirected_url)

                if redirected_url:
                    # 追随新地址，并带上 Referer
                    new_headers = HEADERS.copy()
                    new_headers['Referer'] = url 
                    # 给第二次请求一个稍短的超时
                    async with session.get(redirected_url, headers=new_headers, timeout=URL_TEST_TIMEOUT - 3, allow_redirects=False) as redirected_response:
                        if 200 <= redirected_response.status < 300:
                            end_time = asyncio.get_event_loop().time()
                            return url, (end_time - start_time) * 1000
            # 如果是直接成功...
            elif 200 <= response.status < 300:
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000

            return url, float('inf')
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return url, float('inf')
    except Exception:
        return url, float('inf')

# --- 信号解析引擎 (100% 还原 v14.0 “智能分流版”解析器) ---
def parse_m3u_content(content, ad_keywords):
    """专门解析 M3U 格式，带 tvg-name 提取与广告过滤"""
    channels = {}
    processed_urls = set()
    def add_channel(name, url):
        name = name.strip().replace(" ", "") # 还原哥哥的空格清理
        url = url.strip()
        if not name or not url or url in processed_urls: return
        if any(keyword in name for keyword in ad_keywords): return
        if name not in channels: channels[name] = []
        channels[name].append(url)
        processed_urls.add(url)

    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or not line.startswith('#EXTINF:'): continue
        try:
            if i + 1 < len(lines) and not lines[i+1].strip().startswith('#'):
                url = lines[i+1].strip()
                # 优先寻找 tvg-name，没有则取最后的名字
                name_match = re.search(r'tvg-name="([^"]*)"', line)
                name = name_match.group(1) if name_match else line.split(',')[-1]
                add_channel(name, url)
        except Exception:
            continue
    return channels

def parse_txt_content(content, ad_keywords):
    """专门解析 TXT 格式，带广告过滤与健壮性检查"""
    channels = {}
    processed_urls = set()
    def add_channel(name, url):
        name = name.strip().replace(" ", "")
        url = url.strip()
        if not name or not url or url in processed_urls: return
        if any(keyword in name for keyword in ad_keywords): return
        if name not in channels: channels[name] = []
        channels[name].append(url)
        processed_urls.add(url)

    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or '#genre#' in line: continue
        if ',' in line and 'http' in line:
            try:
                last_comma_index = line.rfind(',')
                name = line[:last_comma_index]
                url = line[last_comma_index+1:]
                if url.startswith('http'): add_channel(name, url)
            except Exception:
                continue
    return channels

# --- ✨✨✨ EPG 数据中心 (双向净化对齐) ✨✨✨ ---
async def load_epg_data(epg_url):
    """还原 GZIP 处理逻辑，并植入 get_epg_id 实现 ID 根本匹配"""
    if not epg_url: return {}
    print(f"\n📡 正在加载 EPG 数据: {epg_url}...")
    epg_data = {}
    try:
        content_bytes = b''
        async with aiohttp.ClientSession() as session:
            async with session.get(epg_url, headers=HEADERS, timeout=30) as response:
                content_bytes = await response.read()

        # 处理 GZIP 压缩 (完全还原)
        if content_bytes.startswith(b'\x1f\x8b'):
            content = gzip.decompress(content_bytes).decode('utf-8')
        else:
            content = content_bytes.decode('utf-8')

        root = ET.fromstring(content)
        for channel in root.findall('channel'):
            display_name_tag = channel.find('display-name')
            if display_name_tag is not None and display_name_tag.text:
                raw_name = display_name_tag.text.strip()
                # 【新功能注入】用 get_epg_id 清洗，确保对齐 CCTV1 格式
                cleaned_epg_id = get_epg_id(raw_name)
                channel_id = channel.get('id', raw_name)
                icon_tag = channel.find('icon')
                logo_url = icon_tag.get('src', "") if icon_tag is not None else ""
                epg_data[cleaned_epg_id] = {"tvg-id": channel_id, "tvg-logo": logo_url}
        print(f"  - ✅ EPG加载成功！共解析出 {len(epg_data)} 个特征。")
    except Exception as e:
        print(f"  - ❌ EPG数据加载失败: {e}")
    return epg_data

def classify_channel(channel_name):
    """还原规则分类逻辑"""
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in channel_name for keyword in keywords):
            return category
    return "其他"

### **【m3u8_organizer.py v20.0 · 第四部分：EPG 轮询与万源归宗】**

async def main(args):
    """主执行函数：凤凰系统的完全体引擎"""
    print(f"报告哥哥，婉儿的“超级节目单” v20.0【血肉归位版】开始工作啦！")

    # --- ✨ EPG 处理逻辑 (1:1 还原 v14.0，绝无缩减) ---
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

    # --- 第一步：【万源归宗】(100% 还原 v14.0 抓取细节) ---
    print("\n第一步：【万源归宗】正在融合所有信号源...")
    all_channels_pool = {}

    # 1. 抓取本地【种子仓库】
    manual_sources_abs_dir = os.path.join(BASE_DIR, args.manual_sources_dir)
    if os.path.isdir(manual_sources_abs_dir):
        print(f"  - 📂 读取【种子仓库】: {manual_sources_abs_dir}")
        for filename in os.listdir(manual_sources_abs_dir):
            filepath = os.path.join(manual_sources_abs_dir, filename)
            if os.path.isfile(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 根据后缀选择解析器
                    if filename.endswith('.m3u'):
                        channels = parse_m3u_content(content, ad_keywords)
                    else:
                        channels = parse_txt_content(content, ad_keywords)
                    
                    for name, urls in channels.items():
                        if name not in all_channels_pool:
                            all_channels_pool[name] = {"urls": set(), "source_type": "manual"}
                        all_channels_pool[name]["urls"].update(urls)

    # 2. 抓取【网络云端源】(1:1 还原 fetch_and_parse 异步循环)
    remote_sources_abs_file = os.path.join(BASE_DIR, args.remote_sources_file)
    if os.path.exists(remote_sources_abs_file):
        print(f"  - 🌐 正在同步网络云端信号...")
        remote_urls = load_list_from_file(args.remote_sources_file)
        
        # 疾风优化：开启 DNS 缓存与连接池
        connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for url in remote_urls:
                async def fetch_and_parse(remote_url):
                    try:
                        async with session.get(remote_url, headers=HEADERS, timeout=20) as response:
                            content = await response.text(encoding='utf-8', errors='ignore')
                            if remote_url.endswith('.m3u'):
                                channels = parse_m3u_content(content, ad_keywords)
                            else:
                                channels = parse_txt_content(content, ad_keywords)
                            for name, urls in channels.items():
                                if name not in all_channels_pool:
                                    all_channels_pool[name] = {"urls": set(), "source_type": "network"}
                                all_channels_pool[name]["urls"].update(urls)
                    except Exception:
                        pass
                tasks.append(fetch_and_parse(url))
            await asyncio.gather(*tasks)

    unique_urls_count = sum(len(data["urls"]) for data in all_channels_pool.values())
    print(f"  - ✅ 融合完成！共收集到 {len(all_channels_pool)} 个频道，{unique_urls_count} 条独立线路。")

### **【m3u8_organizer.py v20.0 · 第五部分：千人试炼与盲盒灵魂回归】**

    # --- 第二步：【终极试炼】(1000并发 + 盲盒同步扫描) ---
    print("\n第二步：【终极试炼】正在检验所有地址的可用性...")
    all_urls_to_test = {url for data in all_channels_pool.values() for url in data["urls"]}
    
    # ✨✨✨ 【完全还原】核心找回：盲盒(Picks)源一起参加“大比武” ✨✨✨
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
                            # 1:1 还原哥哥 v14.0 的分割逻辑
                            url = line.split(',')[-1]
                            if url.startswith('http'): all_urls_to_test.add(url)
                        except IndexError:
                            if line.startswith('http'): all_urls_to_test.add(line)

    url_speeds = {}
    # ✨ 疾风配置：解除连接池限制
    semaphore = asyncio.Semaphore(1000) 

    async def limited_test_url(session, url):
        async with semaphore:
            return await test_url(session, url)

    # 核心：使用带加速的 TCPConnector
    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [limited_test_url(session, url) for url in all_urls_to_test]
        results = []
        # 使用 tqdm 展现疾风般的速度
        for f in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc="⚡ 凤凰质检"):
            results.append(await f)
        for url, speed in results:
            url_speeds[url] = speed

    valid_url_count = sum(1 for speed in url_speeds.values() if speed != float('inf'))
    print(f"\n  - 试炼完成！存活节点 {valid_url_count}/{len(all_urls_to_test)}。")

    # --- 第三步：【生态进化】(1:1 还原分类细节 + 植入4K拦截) ---
    print("\n第三步：【生态进化】正在为幸存者归类并筛选 4K 信号...")
    survivors_classified = {}
    GROUP_4K = "💎 凤凰 4K 极清"

    for name, data in all_channels_pool.items():
        # 获取有效线路并按速度排序
        valid_urls = [url for url in data["urls"] if url_speeds.get(url, float('inf')) != float('inf')]
        if valid_urls:
            valid_urls.sort(key=lambda u: url_speeds[u])
            
            # ✨ 新增逻辑：4K 智能拦截
            if is_4k_channel(name):
                category = GROUP_4K
            else:
                category = classify_channel(name)
            
            if category not in survivors_classified:
                survivors_classified[category] = {}
            if name not in survivors_classified[category]:
                 survivors_classified[category][name] = []

            # 线路保留策略 (1:1 还原 v14.0 每一个 if)
            if data["source_type"] == "manual":
                survivors_classified[category][name].extend(valid_urls)
            else:
                # 网络源取最快前 5
                survivors_classified[category][name].extend(valid_urls[:5])

    print(f"  - ✅ 生态进化完成！幸存频道已按部就班归队。")

    # --- 第四步：【融合输出】(完全还原双格式输出逻辑) ---
    print("\n第四步：【融合输出】正在准备生成最终节目单...")
    output_abs_path = os.path.join(BASE_DIR, args.output)
    m3u_filename = f"{output_abs_path}.m3u"
    txt_filename = f"{output_abs_path}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)

    beijing_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')

    # ✨✨✨ 【完全还原】真·盲盒随机逻辑 (v14.0 每一个 print 都还在！) ✨✨✨
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
                    # 还原哥哥 v14.0 的盲盒内部解析和随机抽取逻辑
                    pick_channels_data = parse_txt_content(pick_content, ad_keywords)
                    valid_urls_in_file = [url for urls in pick_channels_data.values() for url in urls if url_speeds.get(url, float('inf')) != float('inf')]

                    if valid_urls_in_file:
                        random_url = random.choice(valid_urls_in_file)
                        safe_pick_name = pick_name.replace(" ", "-")
                        blind_box_channels[safe_pick_name] = [random_url]
                        print(f"    - 盲盒 '{pick_name}' 已开启，幸运源：{random_url[:30]}...")
                    else:
                        print(f"    - 盲盒 '{pick_name}' 已失效。")

### **【m3u8_organizer.py v20.0 · 第六部分：全量排序、双格式输出与入口大管家 (完结)】**

    # 2. 准备常规分组并处理收藏
    final_grouped_channels = {}
    if blind_box_channels:
        final_grouped_channels[blind_box_group_name] = blind_box_channels

    for category, channels in survivors_classified.items():
        for name, urls in channels.items():
            # 还原 v14.0 收藏夹判定逻辑
            group_name = "我的最爱" if name in favorite_channels else category
            if group_name not in final_grouped_channels:
                final_grouped_channels[group_name] = {}
            if name not in final_grouped_channels[group_name]:
                 final_grouped_channels[group_name][name] = []
            final_grouped_channels[group_name][name].extend(urls)

    # 3. ✨✨✨ 【完全还原】确定最终的黄金排序逻辑 ✨✨✨
    prefix_order = ["婉儿为哥哥整理", GROUP_4K, "我的最爱", "央视", "卫视", "港澳台"]
    all_existing_groups = list(final_grouped_channels.keys())
    ordered_groups = []

    for group in prefix_order:
        if group in all_existing_groups:
            ordered_groups.append(group)
            all_existing_groups.remove(group)

    other_group_exists = "其他" in all_existing_groups
    if other_group_exists:
        all_existing_groups.remove("其他")

    ordered_groups.extend(sorted(all_existing_groups))

    if other_group_exists:
        ordered_groups.append("其他")

    # 4. ✨✨✨ 【完全还原】黄金大循环：按照顺序同步写入 M3U 与 TXT ✨✨✨
    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        # 写入地表最强头部定义 (支持多 EPG 轮询)
        f_m3u.write(f'#EXTM3U x-tvg-url="{top_3_epgs_str}" tvg-url="{top_3_epgs_str}" catchup="append" catchup-source="?playseek=${{(b)yyyyMMddHHmmss}}-${{(e)yyyyMMddHHmmss}}"\n')
        
        # 写入更新时间
        f_m3u.write(f'#EXTINF:-1 group-title="🕒 凤凰·更新时间",凤凰更新时间({beijing_time})\n{CLOCK_URL}\n')
        f_txt.write(f'更新时间,#genre#\n{beijing_time},{CLOCK_URL}\n\n')

        for group in ordered_groups:
            # ✨ 颜值升级：带上婉儿的霓虹图标
            pretty_group_name = get_pretty_group(group)
            f_txt.write(f'{pretty_group_name},#genre#\n')

            channels_in_group = final_grouped_channels.get(group)
            if not channels_in_group: continue

            for name, urls in sorted(channels_in_group.items()):
                # 【核心进化】两套名字，一个撞库(适配CCTV1格式)，一个视觉显示(带4K)
                eid = get_epg_id(name)               # 用于找节目单 (CCTV1)
                disp = get_pretty_display_name(name) # 用于屏幕显示 (CCTV-1 4K)
                
                # 双向对齐：在 EPG 库中寻找匹配
                info = epg_data.get(eid, {})
                tid = info.get("tvg-id", eid)
                logo = info.get("tvg-logo", "")

                for url in urls:
                    # A. 写入 TXT 格式 (还原细节)
                    f_txt.write(f'{disp},{url}\n')
                    
                    # B. ✨✨✨ 【完全还原】三套 Catchup 协议精准适配 (v14.0 精髓) ✨✨✨
                    catchup_tag = ""
                    if any(x in url for x in ["PLTV", "TVOD", "/liveplay/", "/replay/"]):
                        catchup_tag = ' catchup="append" catchup-source="?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"'
                    elif ".m3u8" in url and ("playback" in url or "replay" in url):
                         catchup_tag = ' catchup="append" catchup-source="?starttime=${(b)yyyyMMddHHmmss}&endtime=${(e)yyyyMMddHHmmss}"'
                    elif ".php" in url and "id=" in url:
                         catchup_tag = ' catchup="append" catchup-source="&playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"'

                    # C. 最终写入 M3U 核心行：tvg-id 和 tvg-name 全部对齐极简 ID (解决菜单消失)
                    f_m3u.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-name="{tid}" tvg-logo="{logo}" group-title="{pretty_group_name}"{catchup_tag},{disp}\n')
                    f_m3u.write(f'{url}\n')

            f_txt.write('\n')

    print(f"\n第五步：任务完成！我们的生态系统已按黄金顺序完成最终进化！")
    print(f"  - 最终成品已生成: {m3u_filename} (M3U) & {txt_filename} (TXT)")
    print(f"  - 婉儿报告：4K 归位、EPG 根本对齐、盲盒灵魂已复产！")

# --- ✨✨✨ 【完璧归赵】入口大管家 (100% 还原 v14.0 每一个参数说明) ✨✨✨ ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='婉儿的“超级节目单” v20.0【血肉归位·最终全量版】')

    parser.add_argument('--config', type=str, default='config.json', help='全局JSON配置文件的路径')
    parser.add_argument('--rules-dir', type=str, default='rules', help='【备用】分类规则目录')
    parser.add_argument('--manual-sources-dir', type=str, default='sources_manual', help='【种子仓库】手动维护的源目录')
    parser.add_argument('--generated-sources-dir', type=str, default='sources_generated', help='【成品仓库】脚本自动生成的源目录')
    parser.add_argument('--remote-sources-file', type=str, default='sources.txt', help='包含远程直播源URL列表的文件')
    parser.add_argument('--picks-dir', type=str, default='picks', help='【每日精选】盲盒源目录')

    parser.add_argument('--epg-url', nargs='+', default=None, help='【覆盖】EPG数据源URL，会覆盖配置文件中的设置')

    parser.add_argument('-b', '--blacklist', type=str, default='config/blacklist.txt', help='频道黑名单文件')
    parser.add_argument('-f', '--favorites', type=str, default='config/favorites.txt', help='收藏频道列表文件')
    parser.add_argument('-o', '--output', type=str, default='dist/live', help='输出文件的前缀（不含扩展名）')

    args = parser.parse_args()

    # 加载配置
    config = load_global_config(args.config)

    # 逻辑：分类规则加载
    if 'category_rules' in config and isinstance(config['category_rules'], dict):
        print("正在从 config.json 加载分类规则...")
        CATEGORY_RULES = config['category_rules']
    else:
        print("config.json 中未找到分类规则，将从 'rules' 目录加载。")
        CATEGORY_RULES = load_category_rules_from_dir(args.rules_dir)

    # 逻辑：三级 EPG 轮询判定
    epg_source_list = []
    if args.epg_url:
         epg_source_list = args.epg_url
         print("检测到命令行EPG参数，优先使用！")
    elif 'epg_urls' in config and isinstance(config['epg_urls'], list):
         epg_source_list = config['epg_urls']
         print("正在从 config.json 加载EPG源列表...")
    else:
         epg_source_list = ['https://live.fanmingming.com/e.xml']
         print("未找到任何EPG配置，使用内置备用地址。")
    args.epg_url = epg_source_list

    # 加载全局变量
    HEADERS = config.get('headers', {})
    URL_TEST_TIMEOUT = config.get('url_test_timeout', 15)
    CLOCK_URL = config.get('clock_url', "")

    # 启动异步引擎
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n收到退出指令，婉儿撤退啦！👋")
    except Exception as e:
        print(f"\n哎呀，婉儿好像被代码绊倒了: {e}")
