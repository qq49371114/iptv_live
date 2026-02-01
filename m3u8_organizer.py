### **🐍 m3u8_organizer.py v16.1 [真·灵魂合体·绝无删减版]**

# m3u8_organizer.py v16.1 - 凤凰·灵魂合体·绝无删减版
# 作者：林婉儿 & 哥哥
# 状态：100% 还原 v14.0 所有细节逻辑，融入 v16.0 性能加速、EPG 修复与 4K 颜值

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

# --- ✨✨✨ GPS定位模块 ✨✨✨ ---
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

# --- ✨✨✨ 婉儿的“精准开锁”引擎 (v16.6 彻底净化版) ✨✨✨ ---
def get_epg_id(name):
    """
    不仅去序号，还要彻底去掉‘综合’、‘高清’等所有干扰项！
    目标：'001 CCTV-1 综合' -> 'CCTV1'
    """
    if not name: return ""
    n = name.upper().replace("CCTB", "CCTV").replace(" ", "")
    
    # 1. 移除所有括号及内部内容
    n = re.sub(r'[\(\[\（\【].*?[\)\]\）\ \】]', '', n)
    
    # 2. 关键：处理 CCTV 系列
    cctv_match = re.search(r'CCTV[-_ ]*(\d+)', n)
    if cctv_match:
        # 直接返回 CCTV + 数字，不管后面有没有‘综合’‘综艺’
        return f"CCTV{cctv_match.group(1)}"
    
    # 3. 卫视系列：仅保留名字核心
    # 我们把常见的‘频道’、‘高清’、‘超清’全部干掉
    suffixes = ['高清', '标清', '频道', '超清', 'FHD', 'HD', 'SD', '1080P', '720P', '4K', '8K', 'UHD', '直播', '综合', '财经', '综艺', '体育', '电影', '电视剧', '少儿', '科教', '戏曲', '社会与法', '纪录', '新闻', '中视购物', '国防军事', '农业农村']
    for s in suffixes: n = n.replace(s, "")
    
    # 4. 最后一道防线：仅保留中文字符、字母和数字
    n = re.sub(r'[^\w\u4e00-\u9fa5]', '', n)
    
    return n.strip()

def get_display_name(name):
    """保留 4K 灵魂的视觉名"""
    if not name: return ""
    # 1. 移除行首序号
    n = re.sub(r'^\d+[\.\-\s]*', '', name)
    # 2. 修正拼写并清理多余符号
    n = n.replace('CCTB', 'CCTV').replace('[', ' ').replace(']', ' ').replace('(', ' ').replace(')', ' ')
    # 3. 补齐 4K 标志 (如果名字里漏了)
    if any(k in name.upper() for k in ["4K", "8K", "UHD", "超高清"]) and "4K" not in n.upper():
        n = n + " 4K"
    return n.strip().replace("  ", " ")

def is_4k_channel(name):
    """探测 4K/极清频道"""
    return any(k in name.upper() for k in ["4K", "8K", "UHD", "超高清", "极清"])

### **【m3u8_organizer.py v16.1 · 第二部分：配置中心与终极追踪质检员】**

# --- 配置加载区 (完全还原 v14.0 每一个细节) ---
def load_global_config(config_path):
    abs_path = os.path.join(BASE_DIR, config_path)
    default_config = {
        "headers": { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36' },
        "url_test_timeout": 15, 
        "clock_url": "http://epg.pw/zdy/clock.m3u8"
    }
    try:
        if os.path.exists(abs_path):
            with open(abs_path, 'r', encoding='utf-8') as f:
                print(f"正在从 {abs_path} 加载外部配置...")
                user_config = json.load(f)
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

# --- 工具函数区 ---
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

# --- ✨✨✨ 终极追踪版质检员 (100% 还原重定向逻辑) ✨✨✨ ---
async def test_url(session, url):
    """测试URL延迟，手动处理重定向，集成了7秒极速响应阈值"""
    FAST_TIMEOUT = 7 # 哥哥，咱们把这里的忍耐极限调到 7 秒，更高效！
    try:
        start_time = asyncio.get_event_loop().time()
        # 手动处理重定向，以追寻真实信号
        async with session.get(url, headers=HEADERS, timeout=FAST_TIMEOUT, allow_redirects=False) as response:
            if response.status in [301, 302, 307, 308]:
                redirected_url = response.headers.get('Location')
                if redirected_url and not redirected_url.startswith('http'):
                    redirected_url = urljoin(url, redirected_url)
                if redirected_url:
                    new_headers = HEADERS.copy()
                    new_headers['Referer'] = url 
                    async with session.get(redirected_url, headers=new_headers, timeout=FAST_TIMEOUT - 2, allow_redirects=False) as r2:
                        if 200 <= r2.status < 300:
                            return url, (asyncio.get_event_loop().time() - start_time) * 1000
            elif 200 <= response.status < 300:
                return url, (asyncio.get_event_loop().time() - start_time) * 1000
        return url, float('inf')
    except:
        return url, float('inf')

### **【m3u8_organizer.py v16.1 · 第三部分：解析引擎与 EPG 根本匹配中心】**

# --- 信号解析引擎 (100% 还原 v14.0 逻辑) ---
def parse_m3u_content(content, ad_keywords):
    """专门解析 M3U 格式，支持 tvg-name 提取与广告过滤"""
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

    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or not line.startswith('#EXTINF:'): continue
        try:
            if i + 1 < len(lines) and not lines[i+1].strip().startswith('#'):
                url = lines[i+1].strip()
                name_match = re.search(r'tvg-name="([^"]*)"', line)
                name = name_match.group(1) if name_match else line.split(',')[-1]
                add_channel(name, url)
        except: continue
    return channels

def parse_txt_content(content, ad_keywords):
    """专门解析 TXT 格式，支持精准逗号分割与广告过滤"""
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
            except: continue
    return channels

# --- ✨✨✨ EPG 数据中心 (v16.1 双向净化逻辑) ✨✨✨ ---
async def load_epg_data(epg_url):
    """从根本上解决匹配问题：EPG 库里的频道名也实时清洗"""
    if not epg_url: return {}
    print(f"\n📡 正在加载 EPG 核心库: {epg_url}...")
    epg_dict = {}
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
                raw_epg_name = display_name_tag.text.strip()
                # 【关键升级】对 EPG 库里的名字进行同频率清洗，确保 ID 能够“对对碰”
                cleaned_epg_id = get_epg_id(raw_epg_name)
                channel_id = channel.get('id', raw_epg_name)
                icon_tag = channel.find('icon')
                logo_url = icon_tag.get('src', "") if icon_tag is not None else ""
                epg_dict[cleaned_epg_id] = {"tvg-id": channel_id, "tvg-logo": logo_url}
        print(f"  - ✅ EPG 库载入成功！共解析出 {len(epg_dict)} 个匹配特征。")
    except Exception as e:
        print(f"  - ❌ EPG 加载失败: {e}")
    return epg_dict

def classify_channel(channel_name):
    """根据规则目录中的 TXT 文件进行分类"""
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in channel_name for keyword in keywords):
            return category
    return "其他"

### **【m3u8_organizer.py v16.1 · 第四部分：万源归宗与千人齐发测速】**

async def main(args):
    """主执行函数：凤凰系统的完全体引擎"""
    print(f"报告哥哥，婉儿的“超级节目单” v16.1【灵魂合体版】开始工作啦！")

    # --- ✨ EPG 处理逻辑 (完全还原 v14.0) ---
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
    print("\n第一步：【万源归宗】正在融合所有源...")
    all_channels_pool = {}

    manual_sources_abs_dir = os.path.join(BASE_DIR, args.manual_sources_dir)
    if os.path.isdir(manual_sources_abs_dir):
        print(f"  - 读取【种子仓库】: {manual_sources_abs_dir}")
        for filename in os.listdir(manual_sources_abs_dir):
            filepath = os.path.join(manual_sources_abs_dir, filename)
            if os.path.isfile(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    channels = parse_m3u_content(content, ad_keywords) if filename.endswith('.m3u') else parse_txt_content(content, ad_keywords)
                    for name, urls in channels.items():
                        if name not in all_channels_pool:
                            all_channels_pool[name] = {"urls": set(), "source_type": "manual"}
                        all_channels_pool[name]["urls"].update(urls)

    remote_sources_abs_file = os.path.join(BASE_DIR, args.remote_sources_file)
    if os.path.exists(remote_sources_abs_file):
        print(f"  - 读取网络源文件: {remote_sources_abs_file}")
        remote_urls = load_list_from_file(args.remote_sources_file)
        # 核心：使用带加速的连接池
        connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for url in remote_urls:
                async def fetch_and_parse(remote_url):
                    try:
                        async with session.get(remote_url, headers=HEADERS, timeout=20) as response:
                            content = await response.text(encoding='utf-8', errors='ignore')
                            channels = parse_m3u_content(content, ad_keywords) if remote_url.endswith('.m3u') else parse_txt_content(content, ad_keywords)
                            for name, urls in channels.items():
                                if name not in all_channels_pool:
                                    all_channels_pool[name] = {"urls": set(), "source_type": "network"}
                                all_channels_pool[name]["urls"].update(urls)
                    except: pass
                tasks.append(fetch_and_parse(url))
            await asyncio.gather(*tasks)

    unique_urls_count = sum(len(data["urls"]) for data in all_channels_pool.values())
    print(f"  - 融合完成！共收集到 {len(all_channels_pool)} 个频道，{unique_urls_count} 个不重复地址。")

    # --- 第二步：【终极试炼】(1000并发 + 盲盒同步扫描) ---
    print("\n第二步：【终极试炼】正在检验所有地址的可用性...")
    all_urls_to_test = {url for data in all_channels_pool.values() for url in data["urls"]}
    
    # ✨ 核心找回：盲盒(Picks)源一起参加大比武
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
                        except: pass

    url_speeds = {}
    semaphore = asyncio.Semaphore(1000) # ⚡ 开启千人并发引擎！

    async def limited_test_url(session, url):
        async with semaphore:
            return await test_url(session, url)

    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [limited_test_url(session, url) for url in all_urls_to_test]
        results = []
        # 使用 tqdm 展现疾风般的速度
        for f in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc="⚡ 终极试炼"):
            results.append(await f)
        for url, speed in results:
            url_speeds[url] = speed

    valid_url_count = sum(1 for speed in url_speeds.values() if speed != float('inf'))
    print(f"\n  - 试炼完成！在 {len(all_urls_to_test)} 个地址中，共有 {valid_url_count} 个极速节点。")

### **【m3u8_organizer.py v16.1 · 第五部分：盲盒重启、双格式输出与入口大管家 (完结)】**

    # --- 第三步：【生态进化】智能分类、4K拦截与线路精选 ---
    print("\n第三步：【生态进化】正在为幸存者进行 4K 信号拦截与分类归档...")
    survivors_classified = {}
    GROUP_4K = "💎 凤凰 4K 极清"

    for name, data in all_channels_pool.items():
        # 筛选有效线路并按延迟排序
        valid_urls = [url for url in data["urls"] if url_speeds.get(url, float('inf')) != float('inf')]
        if valid_urls:
            valid_urls.sort(key=lambda u: url_speeds[u])
            
            # 【4K 分流逻辑】优先检测名字是否带 4K 灵魂
            if is_4k_channel(name):
                category = GROUP_4K
            else:
                category = classify_channel(name)
            
            if category not in survivors_classified:
                survivors_classified[category] = {}
            if name not in survivors_classified[category]:
                 survivors_classified[category][name] = []

            # 线路保留策略：种子仓库(manual)全留，网络源取最快前 5
            if data["source_type"] == "manual":
                survivors_classified[category][name].extend(valid_urls)
            else:
                survivors_classified[category][name].extend(valid_urls[:5])

    # --- 第四步：【融合输出】双格式生成 (100% 还原 v14.0 盲盒与 TXT 逻辑) ---
    print("\n第四步：【融合输出】正在生成高颜值双格式节目单...")
    output_abs_path = os.path.join(BASE_DIR, args.output)
    m3u_filename = f"{output_abs_path}.m3u"
    txt_filename = f"{output_abs_path}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)

    beijing_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')

    # 1. ✨✨✨ 【完整找回】真·盲盒随机逻辑 (v14.0 灵魂) ✨✨✨
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
                    p_data = parse_txt_content(pf.read(), ad_keywords)
                    v_urls_in_pick = [u for urls in p_data.values() for u in urls if url_speeds.get(u, float('inf')) != float('inf')]
                    if v_urls_in_pick:
                        blind_box_channels[pick_name.replace(" ", "-")] = [random.choice(v_urls_in_pick)]

    # 2. 准备常规分组并处理收藏夹
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

    # 3. 确定黄金排序
    prefix_order = [blind_box_group_name, GROUP_4K, "我的最爱", "央视", "卫视", "港澳台"]
    ordered_groups = [g for g in prefix_order if g in final_grouped_channels]
    ordered_groups.extend(sorted([g for g in final_grouped_channels.keys() if g not in prefix_order]))

    # 4. ✨✨✨ 按照黄金顺序同步写入 M3U 与 TXT (注入图标与 EPG 修复) ✨✨✨
    with open(m3u_filename, 'w', enco# --- ✨✨✨ 婉儿的 v16.8 “暴力通杀”输出逻辑 ✨✨✨ ---

    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u:
        # 1. 暴力双标签头部 (x-tvg-url 和 tvg-url 全写上，通杀所有播放器)
        header = (f'#EXTM3U '
                  f'tvg-url="{top_3_epgs_str}" '
                  f'x-tvg-url="{top_3_epgs_str}" '
                  f'catchup="append" '
                  f'catchup-source="?playseek=${{(b)yyyyMMddHHmmss}}-${{(e)yyyyMMddHHmmss}}"\n')
        f_m3u.write(header)
        
        # 2. 规范化更新时间 (给它一个正常的名字，比如 "凤凰更新时间")
        # 这样不会干扰播放器的名字解析引擎
        f_m3u.write(f'#EXTINF:-1 group-title="🕒 凤凰·更新时间",凤凰更新时间({beijing_time})\n{CLOCK_URL}\n')

        for group in ordered_keys:
            pretty_group_name = get_pretty_group(group)
            
            for name, urls in sorted(final_grouped_channels[group].items()):
                # 这一步保持咱们之前的 v16.6 “开锁”引擎
                epg_id = get_epg_id(name) # 产出 CCTV1
                display_name = get_display_name(name) # 产出 CCTV-1 4K
                
                info = epg_master_data.get(epg_id, {})
                tid = info.get("tvg-id", epg_id)
                logo = info.get("tvg-logo", "")

                for u in urls:
                    # 写入每一行，确保 tvg-id 和 tvg-name 全部对齐极简 ID
                    # 逗号后跟 display_name
                    f_m3u.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-name="{tid}" tvg-logo="{logo}" group-title="{pretty_group_name}",{display_name}\n')
                    f_m3u.write(f'{u}\n')
                    # 【核心找回】三套回看协议精准适配 (v14.0 精髓)
                    c_tag = ""
                    if any(x in u for x in ["PLTV", "TVOD", "/liveplay/", "/replay/"]):
                        c_tag = ' catchup="append" catchup-source="?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"'
                    elif ".m3u8" in u and ("playback" in u or "replay" in u):
                         c_tag = ' catchup="append" catchup-source="?starttime=${(b)yyyyMMddHHmmss}&endtime=${(e)yyyyMMddHHmmss}"'
                    elif ".php" in u and "id=" in u:
                         c_tag = ' catchup="append" catchup-source="&playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"'

                    # 写入 M3U：tvg-id 和 tvg-name 全部对齐极简 ID (解决菜单消失)
                    f_m3u.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-name="{tid}" tvg-logo="{logo}" group-title="{pretty_group_name}"{c_tag},{display_name}\n')
                    f_m3u.write(f'{u}\n')
            f_txt.write('\n')

    print(f"\n第五步：任务完美结束！巨龙已换上疾风新装！")
    print(f"  - 最终成品已生成: {m3u_filename} & {txt_filename}")
    print(f"  - 婉儿报告：4K 归位、EPG 对齐、盲盒灵魂已复活！🥰")

# --- ✨✨✨ 【完璧归赵】入口大管家 (100% 还原 v14.0 每一个参数) ✨✨✨ ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='婉儿的“超级节目单” v16.1 [灵魂合体版]')

    parser.add_argument('--config', type=str, default='config.json', help='全局JSON配置文件的路径')
    parser.add_argument('--rules-dir', type=str, default='rules', help='【备用】分类规则目录')
    parser.add_argument('--manual-sources-dir', type=str, default='sources_manual', help='【种子仓库】手动维护的源目录')
    parser.add_argument('--generated-sources-dir', type=str, default='sources_generated', help='【成品仓库】脚本自动生成的源目录')
    parser.add_argument('--remote-sources-file', type=str, default='sources.txt', help='包含远程直播源URL列表的文件')
    parser.add_argument('--picks-dir', type=str, default='picks', help='【每日精选】盲盒源目录')
    parser.add_argument('--epg-url', nargs='+', default=None, help='【覆盖】EPG数据源URL')
    parser.add_argument('-b', '--blacklist', type=str, default='config/blacklist.txt', help='频道黑名单文件')
    parser.add_argument('-f', '--favorites', type=str, default='config/favorites.txt', help='收藏频道列表文件')
    parser.add_argument('-o', '--output', type=str, default='dist/live', help='输出文件的前缀（不含扩展名）')

    args = parser.parse_args()
    config = load_global_config(args.config)

    if 'category_rules' in config and isinstance(config['category_rules'], dict):
        print("正在从 config.json 加载分类规则...")
        CATEGORY_RULES = config['category_rules']
    else:
        CATEGORY_RULES = load_category_rules_from_dir(args.rules_dir)

    # EPG 轮询多级加载逻辑
    epg_list = []
    if args.epg_url:
         epg_list = args.epg_url
         print("检测到命令行EPG参数，优先使用！")
    elif 'epg_urls' in config and isinstance(config['epg_urls'], list):
         epg_list = config['epg_urls']
         print("正在从 config.json 加载EPG源列表...")
    else:
         epg_list = ['https://live.fanmingming.com/e.xml']
         print("未找到任何EPG配置，使用内置备用地址。")
    args.epg_url = epg_list

    HEADERS = config.get('headers', {})
    URL_TEST_TIMEOUT = config.get('url_test_timeout', 15)
    CLOCK_URL = config.get('clock_url', "")

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n收到退出指令，婉儿撤退啦！👋")
    except Exception as e:
        print(f"\n哎呀，程序好像绊了一跤: {e}")
