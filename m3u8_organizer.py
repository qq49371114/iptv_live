# m3u8_organizer.py v8.1 - EPG优选版
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
    """从JSON文件加载全局配置"""
    default_config = {
        "headers": {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
        },
        "url_test_timeout": 8,
        "clock_url": "http://epg.pw/zdy/clock.m3u8"
    }
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                print(f"正在从 {config_path} 加载外部配置...")
                user_config = json.load(f)
                # 使用深度更新，确保嵌套的字典（如headers）也能正确合并
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in default_config and isinstance(default_config[key], dict):
                        default_config[key].update(value)
                    else:
                        default_config[key] = value
                print("外部配置加载成功！")
        else:
            print(f"配置文件 {config_path} 未找到，将使用默认配置。")
    except Exception as e:
        print(f"加载全局配置文件 {config_path} 失败: {e}，将使用默认配置。")
    return default_config

def load_category_rules_from_dir(rules_dir):
    """从目录加载分类规则"""
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

# --- 全局变量 ---
HEADERS = {}
URL_TEST_TIMEOUT = 8
CATEGORY_RULES = {}
CLOCK_URL = ""

# --- 工具函数区 ---
def load_list_from_file(filename):
    """从文件加载列表，去除空行和注释"""
    if not filename or not os.path.exists(filename):
        if filename: print(f"  - 配置文件 {filename} 未找到，将跳过。")
        return []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"  - 读取配置文件 {filename} 失败: {e}")
        return []

async def test_url(session, url):
    """测试单个URL的延迟，返回 (url, 延迟毫秒)"""
    try:
        start_time = asyncio.get_event_loop().time()
        async with session.get(url, headers=HEADERS, timeout=URL_TEST_TIMEOUT) as response:
            if 200 <= response.status < 400: # 扩大成功状态码范围
                end_time = asyncio.get_event_loop().time()
                return url, (end_time - start_time) * 1000
            return url, float('inf')
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return url, float('inf')
    except Exception:
        return url, float('inf')

def parse_content(content, ad_keywords):
    """从文本内容中解析出频道名称和URL"""
    channels = {}
    processed_urls = set()

    def add_channel(name, url):
        name = name.strip()
        url = url.strip()
        if not name or not url or url in processed_urls: return
        # 过滤广告频道
        if any(keyword in name for keyword in ad_keywords): return
        
        if name not in channels: channels[name] = []
        channels[name].append(url)
        processed_urls.add(url)

    lines = content.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith('#EXTM3U'): continue
        try:
            # 兼容 #genre# 格式
            if '#genre#' in line: continue
            
            # 优先处理 M3U 格式
            if line.startswith('#EXTINF:'):
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    if next_line and not next_line.startswith('#'):
                        url = next_line
                        # 尝试从 tvg-name 获取频道名，失败则从行尾获取
                        name_match = re.search(r'tvg-name="([^"]*)"', line)
                        name = name_match.group(1) if name_match else line.split(',')[-1]
                        add_channel(name, url)
            # 兼容 频道名,URL 格式
            elif ',' in line and 'http' in line:
                last_comma_index = line.rfind(',')
                if last_comma_index != -1:
                    name = line[:last_comma_index]
                    url = line[last_comma_index+1:]
                    if url.startswith('http'): add_channel(name, url)
        except Exception as e:
            # 在解析失败时打印更详细的日志，方便排查
            # print(f"  - 解析行时遇到问题: '{line}', 错误: {e}")
            pass # 正式运行时可以注释掉，避免过多输出
    return channels


async def load_epg_data(epg_url):
    """加载并解析EPG数据，支持gzip压缩"""
    if not epg_url: return {}
    print(f"\n加载EPG数据: {epg_url}...")
    epg_data = {}
    try:
        content_bytes = b''
        async with aiohttp.ClientSession() as session:
            async with session.get(epg_url, headers=HEADERS, timeout=30) as response:
                content_bytes = await response.read()
        
        # 自动检测并解压gzip
        if content_bytes.startswith(b'\x1f\x8b'):
            content = gzip.decompress(content_bytes).decode('utf-8')
        else:
            content = content_bytes.decode('utf-8')
            
        root = ET.fromstring(content)
        for channel in root.findall('channel'):
            display_name_tag = channel.find('display-name')
            if display_name_tag is not None and display_name_tag.text:
                display_name = display_name_tag.text.strip()
                channel_id = channel.get('id', display_name)
                icon_tag = channel.find('icon')
                logo_url = icon_tag.get('src', "") if icon_tag is not None else ""
                epg_data[display_name] = {"tvg-id": channel_id, "tvg-logo": logo_url}
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
    print("报告哥哥，婉儿的“超级节目单” v8.1【EPG优选】版开始工作啦！")
    
    # --- ✨✨✨ 新增：EPG源优选 ✨✨✨ ---
    print("\nEPG源优选：正在测试所有EPG地址...")
    async with aiohttp.ClientSession() as session:
        epg_tasks = [test_url(session, url) for url in args.epg_url]
        epg_results = await asyncio.gather(epg_tasks)
    
    valid_epgs = [(url, speed) for url, speed in epg_results if speed != float('inf')]
    if not valid_epgs:
        print("  - 警告：所有EPG源均不可用！将无法加载节目信息。")
        best_epg_url = ""
        top_3_epgs_str = ""
    else:
        # 按速度排序
        valid_epgs.sort(key=lambda x: x[1])
        # 选出最快的前3个
        top_3_epgs = [url for url, speed in valid_epgs[:3]]
        top_3_epgs_str = ",".join(top_3_epgs)
        # 本次运行使用最快的那个
        best_epg_url = valid_epgs[0][0]
        print(f"  - EPG优选完成！本次将使用: {best_epg_url}")
        print(f"  - 最终将写入这几个源: {top_3_epgs_str}")

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
    if os.path.isdir(args.picks_dir):
        for pick_file in os.listdir(args.picks_dir):
            pick_path = os.path.join(args.picks_dir, pick_file)
            if os.path.isfile(pick_path) and pick_file.endswith('.txt'):
                with open(pick_path, 'r', encoding='utf-8') as pf:
                    pick_content = pf.read()
                    pick_channels = parse_content(pick_content, ad_keywords)
                    for urls in pick_channels.values():
                        all_urls_to_test.update(urls)

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
    # ✨ 使用我们优选出的最佳EPG源来加载数据
    epg_data = await load_epg_data(best_epg_url)
    m3u_filename = f"{args.output}.m3u"
    txt_filename = f"{args.output}.txt"
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)
    beijing_time = datetime.now(timezone(timedelta(hours=8)))
    update_time_str = beijing_time.strftime('%Y-%m-%d %H:%M:%S')

    # 1. 准备盲盒分组
    blind_box_group_name = "婉儿为哥哥整理"
    blind_box_channels = {}
    if os.path.isdir(args.picks_dir):
        print("  - 发现【每日精选】盲盒，正在准备...")
        pick_files = sorted(os.listdir(args.picks_dir))
        for pick_file in pick_files:
            pick_path = os.path.join(args.picks_dir, pick_file)
            if os.path.isfile(pick_path) and pick_file.endswith('.txt'):
                pick_name = os.path.splitext(pick_file)[0]
                with open(pick_path, 'r', encoding='utf-8') as pf:
                    pick_content = pf.read()
                pick_channels = parse_content(pick_content, ad_keywords)
                pick_valid_urls = [url for urls in pick_channels.values() for url in urls if url_speeds.get(url, float('inf')) != float('inf')]
                if pick_valid_urls:
                    random_url = random.choice(pick_valid_urls)
                    safe_pick_name = pick_name.replace(" ", "-")
                    blind_box_channels[safe_pick_name] = [random_url]
                    print(f"    - 盲盒 '{pick_name}' 已开启，幸运源已备好！")
                else:
                    print(f"    - 盲盒 '{pick_name}' 中的所有源均已失效。")
    else:
        print("  - 未找到【每日精选】盲盒目录 (picks)，将跳过此功能。")

    # 2. 准备常规分组
    final_grouped_channels = {}
    if blind_box_channels:
        final_grouped_channels[blind_box_group_name] = blind_box_channels

    for category, channels in survivors_classified.items():
        # 这里的channels是 {"频道名": ["url1", "url2"]}
        for name, urls in channels.items():
            # 判断这个频道应该属于哪个最终分组
            group_name = "我的最爱" if name in favorite_channels else category
            
            if group_name not in final_grouped_channels:
                final_grouped_channels[group_name] = {}
            if name not in final_grouped_channels[group_name]:
                 final_grouped_channels[group_name][name] = []
            final_grouped_channels[group_name][name].extend(urls)

    # 3. 确定最终的黄金排序
    prefix_order = ["婉儿为哥哥整理", "我的最爱", "央视", "卫视", "地方", "港澳台"]
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

    # 4. 按照黄金顺序，统一写入文件
    with open(m3u_filename, 'w', encoding='utf-8') as f_m3u, open(txt_filename, 'w', encoding='utf-8') as f_txt:
        # --- ✨✨✨ 核心修改：写入优选出的多个EPG源 ✨✨✨
        # 昨晚改好的不会崩的开头，我只把 x-tvg-url 的值换掉，其他结构完全不变！
        f_m3u.write(f'#EXTM3U x-tvg-url="{top_3_epgs_str}" catchup="append" catchup-source="?playseek=${{(b)yyyyMMddHHmmss}}-${{(e)yyyyMMddHHmmss}}"\n') if top_3_epgs_str else f_m3u.write("#EXTM3U\n")
        f_m3u.write(f'#EXTINF:-1 group-title="更新时间",{update_time_str}\n')
        f_m3u.write(f'{CLOCK_URL}\n')
        
        f_txt.write(f'更新时间,#genre#\n')
        f_txt.write(f'{update_time_str},{CLOCK_URL}\n\n')
        
        for group in ordered_groups:
            channels_in_group = final_grouped_channels.get(group)
            if not channels_in_group: continue
            
            f_txt.write(f'{group},#genre#\n')
            
            for name, urls in sorted(channels_in_group.items()):
                safe_name = name.replace(" ", "-")
                
                epg_info = epg_data.get(name, epg_data.get(safe_name, {}))
                tvg_id = epg_info.get("tvg-id", safe_name)
                tvg_logo = epg_info.get("tvg-logo", "")
                
                if group == blind_box_group_name:
                    if urls:
                        url = urls[0]
                        f_txt.write(f'{safe_name},{url}\n')
                        f_m3u.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{safe_name}" tvg-logo="{tvg_logo}" group-title="{group}",{safe_name}\n')
                        f_m3u.write(f'#EXTVLCOPT:network-caching=1000\n')
                        f_m3u.write(f'{url}\n')
                else:
                    for url in urls:
                        f_txt.write(f'{safe_name},{url}\n')
                        
                        catchup_tag = ""
                        if "PLTV" in url or "TVOD" in url or "/OtpUser/" in url:
                            catchup_tag = ' catchup="append" catchup-source="?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"'
                        elif ".php" in url and "id=" in url:
                             catchup_tag = ' catchup="append" catchup-source="&playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"'

                        f_m3u.write(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{safe_name}" tvg-logo="{tvg_logo}" group-title="{group}"{catchup_tag},{safe_name}\n')
                        f_m3u.write(f'{url}\n')

            f_txt.write('\n')

    print(f"\n第五步：任务完成！我们的生态系统已按黄金顺序完成最终进化！")

    if __name__ == '__main__':
       parser = argparse.ArgumentParser(description='婉儿的“超级节目单” v8.2【配置中心】版')
    
    # 核心路径配置
       parser.add_argument('--config', type=str, default='config.json', help='全局JSON配置文件的路径')
       parser.add_argument('--rules-dir', type=str, default='rules', help='【备用】分类规则目录')
       parser.add_argument('--manual-sources-dir', type=str, default='sources_manual', help='【种子仓库】手动维护的源目录')
       parser.add_argument('--remote-sources-file', type=str, default='sources.txt', help='包含远程直播源URL列表的文件')
       parser.add_argument('--picks-dir', type=str, default='picks', help='【每日精选】盲盒源目录')
    
    # EPG参数，现在它的默认值是None，方便我们判断用户是否从命令行输入了
       parser.add_argument('--epg-url', nargs='+', default=None, help='【覆盖】EPG数据源URL，会覆盖配置文件中的设置')

    # 其他功能性配置
       parser.add_argument('-b', '--blacklist', type=str, default='config/blacklist.txt', help='频道黑名单文件')
       parser.add_argument('-f', '--favorites', type=str, default='config/favorites.txt', help='收藏频道列表文件')
       parser.add_argument('-o', '--output', type=str, default='dist/live', help='输出文件的前缀（不含扩展名）')
    
       args = parser.parse_args()

    # --- ✨✨✨ 核心升级：从配置中心加载 ✨✨✨ ---
    
    # 1. 加载主配置文件
       config = load_global_config(args.config)
    
    # 2. 加载分类规则 (优先从config.json读取)
    if 'category_rules' in config and isinstance(config['category_rules'], dict):
        print("正在从 config.json 加载分类规则...")
        CATEGORY_RULES = config['category_rules']
    else:
        print("config.json 中未找到分类规则，将从 'rules' 目录加载。")
        CATEGORY_RULES = load_category_rules_from_dir(args.rules_dir)

    # 3. 加载EPG源列表 (命令行 > 配置文件 > 硬编码默认值)
    epg_source_list = []
    if args.epg_url:
         epg_source_list = args.epg_url
         print("检测到命令行EPG参数，优先使用！")
    elif 'epg_urls' in config and isinstance(config['epg_urls'], list):
         epg_source_list = config['epg_urls']
         print("正在从 config.json 加载EPG源列表...")
    else:
         epg_source_list = ['https://live.fanmingming.com/e.xml'] # 保留一个最后的备胎
         print("未找到任何EPG配置，使用内置备用地址。")
    # 将最终的EPG列表赋值回args，这样main函数就不用改了
         args.epg_url = epg_source_list

    # 4. 初始化其他全局变量
         HEADERS = config.get('headers', {})
         URL_TEST_TIMEOUT = config.get('url_test_timeout', 8)
         CLOCK_URL = config.get('clock_url', "")
    
    # 启动异步主程序
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\n收到哥哥的指令，程序提前结束。")
