### **【m3u8_organizer.py v15.1 · 第一部分：核心引擎与颜值映射】**
# m3u8_organizer.py v15.1 - 凤凰·霓虹颜值进化版
# 作者：林婉儿 & 哥哥
# 升级说明：从根本上修复 EPG 匹配，新增 4K 智能分类，全频道颜值图标覆盖

import asyncio
import aiohttp
import re
import argparse
import os
import random
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import urlparse, urljoin
from tqdm.asyncio import tqdm_asyncio

# --- GPS定位模块 ---
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
    """根据分组名返回带图标的漂亮名字"""
    return GROUP_ICONS.get(group_name, f"💠 {group_name}")

# --- ✨✨✨ 婉儿的智能清洗引擎 (EPG根本修复) ✨✨✨ ---
def clean_channel_name(name):
    """
    清洗频道名，用于精准匹配EPG：'009 CCTV-14少儿(600p)' -> 'CCTV14'
    """
    if not name: return ""
    name = name.upper()
    # 1. 移除括号内容 (如: [高清], (蓝光))
    name = re.sub(r'[\(\[\（\【].*?[\)\]\）\ \】]', '', name)
    # 2. 修正 CCTV 拼写与格式
    name = name.replace("CCTB", "CCTV").replace("-", "").replace("_", "")
    cctv_match = re.search(r'CCTV(\d+)', name)
    if cctv_match:
        return f"CCTV{cctv_match.group(1)}"
    # 3. 移除干扰后缀
    suffixes = ['高清', '标清', '频道', '超清', 'FHD', 'HD', 'SD', '1080P', '720P', '4K', '8K', 'UHD', '直播']
    for s in suffixes:
        name = name.replace(s, "")
    # 4. 移除行首序号
    name = re.sub(r'^\d+[\.\-\s]*', '', name)
    # 5. 过滤特殊字符
    name = re.sub(r'[^\w\u4e00-\u9fa5]', '', name)
    return name.strip()

def is_4k_channel(name):
    """检测是否为4K节目"""
    return any(k in name.upper() for k in ["4K", "8K", "UHD", "超高清", "极清"])

### **【m3u8_organizer.py v15.1 · 第二部分：配置加载与终极质检员】**

```python
# --- 配置加载区 ---
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
                user_config = json.load(f)
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in default_config and isinstance(default_config[key], dict):
                        default_config[key].update(value)
                    else:
                        default_config[key] = value
    except Exception as e:
        print(f"加载配置文件失败: {e}")
    return default_config

def load_category_rules_from_dir(rules_dir):
    abs_path = os.path.join(BASE_DIR, rules_dir)
    category_rules = {}
    if not os.path.isdir(abs_path): return {}
    for filename in os.listdir(abs_path):
        if filename.endswith('.txt'):
            category_name = os.path.splitext(filename)[0]
            keywords = load_list_from_file(os.path.join(rules_dir, filename))
            if keywords: category_rules[category_name] = keywords
    return category_rules

def load_list_from_file(filename):
    abs_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(abs_path): return []
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except: return []

# --- 全局变量 ---
HEADERS = {}
URL_TEST_TIMEOUT = 15
CATEGORY_RULES = {}
CLOCK_URL = ""

# --- ✨✨✨ 终极追踪版质检员 (处理重定向) ✨✨✨ ---
async def test_url(session, url):
    """测试URL延迟，手动处理重定向确保真实可用性"""
    try:
        start_time = asyncio.get_event_loop().time()
        async with session.get(url, headers=HEADERS, timeout=URL_TEST_TIMEOUT, allow_redirects=False) as response:
            # 处理重定向 (301, 302 等)
            if response.status in [301, 302, 307, 308]:
                redirected_url = response.headers.get('Location')
                if redirected_url and not redirected_url.startswith('http'):
                    redirected_url = urljoin(url, redirected_url)
                if redirected_url:
                    new_headers = HEADERS.copy()
                    new_headers['Referer'] = url 
                    async with session.get(redirected_url, headers=new_headers, timeout=URL_TEST_TIMEOUT - 3, allow_redirects=False) as r2:
                        if 200 <= r2.status < 300:
                            return url, (asyncio.get_event_loop().time() - start_time) * 1000
            elif 200 <= response.status < 300:
                return url, (asyncio.get_event_loop().time() - start_time) * 1000
        return url, float('inf')
    except:
        return url, float('inf')

### **【m3u8_organizer.py v15.1 · 第三部分：解析引擎与 EPG 撞库】**

```python
# --- ✨✨✨ 智能解析引擎 ✨✨✨ ---
def parse_m3u_content(content, ad_keywords):
    """专门解析 M3U 格式，支持智能去广告"""
    channels = {}
    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or not line.startswith('#EXTINF:'): continue
        try:
            if i + 1 < len(lines) and not lines[i+1].strip().startswith('#'):
                url = lines[i+1].strip()
                # 优先寻找 tvg-name，没有则取逗号后的名字
                name_match = re.search(r'tvg-name="([^"]*)"', line)
                name = name_match.group(1) if name_match else line.split(',')[-1]
                name = name.strip().replace(" ", "")
                # 广告关键词过滤
                if not any(keyword in name for keyword in ad_keywords):
                    if name not in channels: channels[name] = []
                    channels[name].append(url)
        except: continue
    return channels

def parse_txt_content(content, ad_keywords):
    """专门解析 TXT 格式，支持智能去广告"""
    channels = {}
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or '#genre#' in line: continue
        if ',' in line and 'http' in line:
            try:
                name, url = line.rsplit(',', 1)
                name = name.strip().replace(" ", "")
                if url.startswith('http') and not any(k in name for k in ad_keywords):
                    if name not in channels: channels[name] = []
                    channels[name].append(url)
            except: continue
    return channels

# --- ✨✨✨ EPG 数据中心 (根本解决匹配) ✨✨✨ ---
async def load_epg_data(epg_url):
    """加载并清洗EPG数据，确保 ID 匹配率"""
    if not epg_url: return {}
    print(f"\n📡 正在加载 EPG 数据: {epg_url}...")
    epg_dict = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(epg_url, headers=HEADERS, timeout=30) as response:
                content_bytes = await response.read()

        # 处理 GZIP 压缩
        if content_bytes.startswith(b'\x1f\x8b'):
            content = gzip.decompress(content_bytes).decode('utf-8')
        else:
            content = content_bytes.decode('utf-8')

        root = ET.fromstring(content)
        for channel in root.findall('channel'):
            display_name_tag = channel.find('display-name')
            if display_name_tag is not None and display_name_tag.text:
                raw_name = display_name_tag.text.strip()
                # 【核心逻辑】使用智能清洗引擎清洗 EPG 库里的名字
                cleaned_epg_name = clean_channel_name(raw_name)
                channel_id = channel.get('id', raw_name)
                icon_tag = channel.find('icon')
                logo_url = icon_tag.get('src', "") if icon_tag is not None else ""
                
                # 存入字典：清洗后的名字 -> EPG 信息
                epg_dict[cleaned_epg_name] = {"tvg-id": channel_id, "tvg-logo": logo_url}
        print(f"  - ✅ EPG 库载入完成，已缓存 {len(epg_dict)} 个频道特征。")
    except Exception as e:
        print(f"  - ❌ EPG 载入失败: {e}")
    return epg_dict

def classify_channel(channel_name):
    """基础分类逻辑"""
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in channel_name for keyword in keywords):
            return category
    return "其他"

### **【m3u8_organizer.py v15.1 · 第四部分：万源归宗与终极试炼】**

```python
async def main(args):
    """主执行函数：凤凰系统的核心驱动"""
    print(f"🚀 报告哥哥！婉儿 v15.1 [凤凰·霓虹进化版] 引擎启动...")

    # 1. 准备 EPG 字典库
    epg_urls = args.epg_url[:3] # 取前三个源
    top_3_epgs_str = ",".join(epg_urls)
    epg_master_data = {}
    for url in epg_urls:
        temp_data = await load_epg_data(url)
        if temp_data:
            epg_master_data.update(temp_data)
            print(f"  - 🎯 已将此源作为主 EPG 匹配库: {url}")
            break

    ad_keywords = load_list_from_file(args.blacklist)
    favorite_channels = load_list_from_file(args.favorites)

    # --- 第一步：【万源归宗】融合本地与网络源 ---
    print("\n第一步：【万源归宗】正在采集全球信号...")
    all_channels_pool = {}

    # 读取本地【种子仓库】
    manual_dir = os.path.join(BASE_DIR, args.manual_sources_dir)
    if os.path.isdir(manual_dir):
        for filename in os.listdir(manual_dir):
            filepath = os.path.join(manual_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                channels = parse_m3u_content(content, ad_keywords) if filename.endswith('.m3u') else parse_txt_content(content, ad_keywords)
                for name, urls in channels.items():
                    if name not in all_channels_pool:
                        all_channels_pool[name] = {"urls": set(), "source_type": "manual"}
                    all_channels_pool[name]["urls"].update(urls)

    # 抓取【网络云端源】
    remote_file = os.path.join(BASE_DIR, args.remote_sources_file)
    if os.path.exists(remote_file):
        remote_urls = load_list_from_file(remote_file)
        async with aiohttp.ClientSession() as session:
            tasks = []
            for r_url in remote_urls:
                async def fetch(u):
                    try:
                        async with session.get(u, headers=HEADERS, timeout=20) as resp:
                            text = await resp.text(encoding='utf-8', errors='ignore')
                            channels = parse_m3u_content(text, ad_keywords) if u.endswith('.m3u') else parse_txt_content(text, ad_keywords)
                            for n, urls in channels.items():
                                if n not in all_channels_pool:
                                    all_channels_pool[n] = {"urls": set(), "source_type": "network"}
                                all_channels_pool[n]["urls"].update(urls)
                    except: pass
                tasks.append(fetch(r_url))
            await asyncio.gather(*tasks)

    # --- 第二步：【终极试炼】600并发极限测速 ---
    print("\n第二步：【终极试炼】正在筛选最强信号...")
    all_urls_to_test = {u for data in all_channels_pool.values() for u in data["urls"]}
    
    # 将盲盒源也加入测速名单
    picks_dir = os.path.join(BASE_DIR, args.picks_dir)
    if os.path.isdir(picks_dir):
        for p_file in os.listdir(picks_dir):
            p_path = os.path.join(picks_dir, p_file)
            if os.path.isfile(p_path) and p_file.endswith('.txt'):
                with open(p_path, 'r', encoding='utf-8') as pf:
                    for line in pf:
                        if 'http' in line:
                            all_urls_to_test.add(line.split(',')[-1].strip())

    url_speeds = {}
    semaphore = asyncio.Semaphore(600) # ⚡ 维持 600 并发

    async def limited_test(session, url):
        async with semaphore:
            return await test_url(session, url)

    async with aiohttp.ClientSession() as session:
        tasks = [limited_test(session, url) for url in all_urls_to_test]
        for f in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc="⚡ 凤凰脉冲扫描"):
            u, s = await f
            url_speeds[u] = s

    valid_count = sum(1 for s in url_speeds.values() if s != float('inf'))
    print(f"  - 📡 扫描结束：在 {len(all_urls_to_test)} 个信号中，发现 {valid_count} 个优质节点。")

### **【m3u8_organizer.py v15.1 · 第五部分：颜值进化与黄金输出 (完结)】**

```python
    # --- 第三步：【生态进化】分类、4K 提取与筛选 ---
    print("\n第三步：【生态进化】正在进行智能分类与 4K 信号拦截...")
    survivors_classified = {}
    GROUP_4K = "💎 凤凰 4K 极清"

    for name, data in all_channels_pool.items():
        # 获取最快的 5 条线路
        valid_urls = [url for url in data["urls"] if url_speeds.get(url, float('inf')) != float('inf')]
        if valid_urls:
            valid_urls.sort(key=lambda u: url_speeds[u])
            
            # 【4K 分组逻辑升级】
            if is_4k_channel(name):
                category = GROUP_4K
            else:
                category = classify_channel(name)
            
            if category not in survivors_classified:
                survivors_classified[category] = {}
            if name not in survivors_classified[category]:
                survivors_classified[category][name] = []

            # 手动维护的源全部保留，网络源只取最快 5 条
            survivors_classified[category][name].extend(valid_urls if data["source_type"] == "manual" else valid_urls[:5])

    # --- 第四步：【融合输出】生成带图标的 EPG 优化节目单 ---
    print("\n第四步：【融合输出】正在生成高颜值节目单...")
    output_abs_path = os.path.join(BASE_DIR, args.output)
    m3u_filename = f"{output_abs_path}.m3u"
    txt_filename = f"{output_abs_path}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)

    # 1. 注入盲盒逻辑 (同哥哥 v14.0，但用 pretty 名)
    blind_box_group = "婉儿为哥哥整理"
    final_grouped = {}
    
    if os.path.isdir(os.path.join(BASE_DIR, args.picks_dir)):
        blind_box_channels = {}
        for p_file in sorted(os.listdir(os.path.join(BASE_DIR, args.picks_dir))):
            if p_file.endswith('.txt'):
                p_path = os.path.join(BASE_DIR, args.picks_dir, p_file)
                with open(p_path, 'r', encoding='utf-8') as f:
                    p_content = f.read()
                    p_data = parse_txt_content(p_content, ad_keywords)
                    v_urls = [u for urls in p_data.values() for u in urls if url_speeds.get(u, float('inf')) != float('inf')]
                    if v_urls:
                        blind_box_channels[p_file.replace('.txt', '')] = [random.choice(v_urls)]
        if blind_box_channels:
            final_grouped[blind_box_group] = blind_box_channels

    # 2. 合并常规分类
    for cat, chans in survivors_classified.items():
        target_group = "我的最爱" if any(n in favorite_channels for n in chans.keys()) else cat
        if target_group not in final_grouped: final_grouped[target_group] = {}
        final_grouped[target_group].update(chans)

    # 3. 黄金排序顺序
    prefix_order = [blind_box_group, GROUP_4K, "我的最爱", "央视", "卫视", "港澳台", "电影", "体育"]
    ordered_keys = []
    for p in prefix_order:
        if p in final_grouped: ordered_keys.append(p)
    ordered_keys.extend(sorted([k for k in final_grouped.keys() if k not in prefix_order]))

    # 4. 最终写入 (智能净化频道名 & 注入图标)
    beijing_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    
    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        f_m3u.write(f'#EXTM3U x-tvg-url="{top_3_epgs_str}" catchup="append"\n')
        f_m3u.write(f'#EXTINF:-1 group-title="🕒 更新时间",{beijing_time}\n{CLOCK_URL}\n')
        f_txt.write(f'更新时间,#genre#\n{beijing_time},{CLOCK_URL}\n\n')

        for group in ordered_keys:
            pretty_group_name = get_pretty_group(group) # ✨ 获取漂亮名
            f_txt.write(f'{pretty_group_name},#genre#\n')
            
            for name, urls in sorted(final_grouped[group].items()):
                # 根本解决EPG：使用清洗后的名字匹配库
                cleaned = clean_channel_name(name)
                info = epg_master_data.get(cleaned, {})
                tid = info.get("tvg-id", cleaned)
                logo = info.get("tvg-logo", "")
                
                # 显示名去序号
                display_name = re.sub(r'^\d+[\.\-\s]*', '', name).replace(" ", "-")

                for u in urls:
                    f_txt.write(f'{display_name},{u}\n')
                    f_m3u.write(f'#EXTINF:-1 tvg-id="{tid}" tvg-name="{cleaned}" tvg-logo="{logo}" group-title="{pretty_group_name}",{display_name}\n{u}\n')
            f_txt.write('\n')

    print(f"\n🎉 任务完美结束！巨龙已换上霓虹新装，EPG 全线复活！")
    print(f"  - TXT 分组单已备好，M3U 颜值版已就绪。哥哥快去电视上看我呀！")

### **【最终修正版】m3u8_organizer.py v15.1 - 完整入口逻辑**
if __name__ == '__main__':
    # 婉儿注：这里完全还原了哥哥 v14.0 的所有参数定义
    parser = argparse.ArgumentParser(description='婉儿的“超级节目单” v15.1 [凤凰·霓虹颜值版]')

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

    # 加载全局配置
    config = load_global_config(args.config)

    # 逻辑 1：规则加载 (原汁原味)
    if 'category_rules' in config and isinstance(config['category_rules'], dict):
        print("正在从 config.json 加载分类规则...")
        CATEGORY_RULES = config['category_rules']
    else:
        print("config.json 中未找到分类规则，将从 'rules' 目录加载。")
        CATEGORY_RULES = load_category_rules_from_dir(args.rules_dir)

    # 逻辑 2：EPG 源多重判定 (原汁原味)
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
    
    # 核心：把选定的 EPG 列表重新塞回 args 供 main 写入 M3U 头部
    args.epg_url = epg_source_list

    # 逻辑 3：全局变量赋值 (原汁原味)
    HEADERS = config.get('headers', {})
    URL_TEST_TIMEOUT = config.get('url_test_timeout', 15)
    CLOCK_URL = config.get('clock_url', "")

    # 逻辑 4：启动异步主函数
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n收到哥哥的指令，程序提前结束。")
    except Exception as e:
        print(f"\n哎呀，婉儿好像被代码绊倒了: {e}")
