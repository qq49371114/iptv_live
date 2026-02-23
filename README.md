# 📺 直播源整理工具 - 婉儿的"超级节目单"

> v24.3 子流验证版 - 解决播放卡顿，提升播放体验

![version](https://img.shields.io/badge/version-24.3-blue)
![python](https://img.shields.io/badge/python-3.8+-green)
![license](https://img.shields.io/badge/license-MIT-orange)

---

## ✨ 特性

### 🎯 v24.2 核心改进

| 功能 | v24.0 | v24.2 | 说明 |
|------|-------|-------|------|
| **URL验证** | HTTP延迟测试 | ✅ 深度流验证 | 读取m3u8流1KB数据确保真实可用 |
| **延迟阈值** | 3000ms | ✅ 2000ms | 更严格淘汰慢源 |
| **URL选择** | 随机/延迟排序 | ✅ 智能排序 | 手动源+m3u8+低延迟三重优先 |
| **每频道线路** | 最多5条 | ✅ 最多3条 | 精简提速 |
| **并发控制** | 1000 | ✅ 800 | 更稳定 |

### 🌟 主要功能

- 🔍 **深度URL验证** - 确保流媒体真实可用
- ⚡ **智能URL选择** - 自动选择最佳线路
- 📊 **多源融合** - 支持本地和网络源混合
- 🎨 **自动分类** - 智能分类央视频道、卫视、体育等
- 📺 **EPG支持** - 支持节目单信息
- 🧩 **盲盒精选** - 每日精选随机推荐
- ❤️ **收藏功能** - 收藏频道优先展示
- 💎 **4K频道独立** - 4K源单独分组

---

## 📦 安装

### 环境要求

- Python 3.8+
- pip

### 安装依赖

```bash
pip install aiohttp tqdm
```

或使用 requirements.txt:

```bash
pip install -r requirements.txt
```

---

## 🚀 快速开始

### 基本使用

```bash
# 直接运行（使用默认配置）
python m3u8_organizer.py

# 运行后会在 dist/ 目录生成：
# - live.m3u (M3U格式)
# - live.txt (纯文本格式)
```

### 自定义参数

```bash
python m3u8_organizer.py   --config config.json   --manual-sources-dir sources_manual   --remote-sources-file sources.txt
```

---

## ⚙️ 配置说明

### config.json 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `max_latency_ms` | 2000 | URL延迟阈值（毫秒） |
| `url_test_timeout` | 10 | URL测试超时（秒） |
| `epg_urls` | [...] | EPG数据源列表 |
| `category_rules` | {...} | 频道分类规则 |
| `category_mapping` | {...} | 频道名称映射 |

### 配置示例

```json
{
  "headers": {
    "User-Agent": "Mozilla/5.0 ..."
  },
  "url_test_timeout": 10,
  "max_latency_ms": 2000,
  "epg_urls": [
    "https://live.fanmingming.com/e.xml"
  ],
  "category_rules": {
    "央视频道": ["CCTV", "央视"],
    "卫视频道": ["卫视", "湖南", "浙江"]
  }
}
```

---

## 📁 目录结构

```
iptv_live/
├── m3u8_organizer.py     # 主程序
├── config.json           # 配置文件
├── sources.txt           # 网络源列表
├── sources_manual/       # 手动维护的源
│   ├── cctv.m3u
│   └── satellite.txt
├── picks/                # 盲盒精选
│   ├── daily1.txt
│   └── daily2.txt
├── config/
│   ├── blacklist.txt     # 黑名单
│   └── favorites.txt     # 收藏频道
├── rules/                # 分类规则
└── dist/                 # 输出目录
    ├── live.m3u
    └── live.txt
```

---

## 🎯 高级功能

### 添加手动源

将你的稳定源放入 `sources_manual/` 目录：

```bash
# 支持 .m3u 和 .txt 格式
sources_manual/
├── my_cctv.m3u
├── satellite.txt
└── sports.m3u
```

### 收藏频道

在 `config/favorites.txt` 添加要收藏的频道：

```
CCTV1
CCTV5
湖南卫视
浙江卫视
```

收藏的频道会显示在 `❤️ 我的最爱` 分组，并且优先使用手动源。

### 黑名单

在 `config/blacklist.txt` 添加要过滤的关键词：

```
# 过滤广告或不相关频道
广告
测试频道
XXX
```

### 盲盒精选

在 `picks/` 目录放置 .txt 文件：

```
picks/
├── today.txt
└── random.txt
```

内容格式：
```
频道1,http://url1
频道2,http://url2
```

---

## 📊 输出结果

### 分组顺序

```
1. 🕐 凤凰·更新时间
2. 🎁 婉儿为哥哥整理
3. 💎 凤凰 4K 极清
4. ❤️ 我的最爱
5. 央视频道
6. 卫视频道
7. 港澳台
8. 地方频道
9. 体育频道
10. 其他...
```

### 文件格式

**M3U格式** - 适合 PotPlayer、IPTVV 等播放器

**TXT格式** - 适合简单播放器

---

## 🔧 故障排除

### 播放卡顿

如果还是卡顿，可以调整 `config.json`:

```json
{
  "max_latency_ms": 1500,  // 更严格，1.5秒
  "url_test_timeout": 8     // 更快淘汰慢源
}
```

### 源太少

如果筛选后源太少：

1. 放宽延迟阈值：`max_latency_ms: 3000`
2. 增加网络源：在 `sources.txt` 添加更多源
3. 添加手动源：在 `sources_manual/` 添加稳定源

### 运行超时

如果运行超时：

```bash
# 增加超时时间（默认10分钟）
timeout 1800 python m3u8_organizer.py
```

---

## 📝 更新日志

### v24.3 (2024-02-23)
### v24.3 (2024-02-23)

- 🔥 新增m3u8子流验证（解析播放列表）
- 🔥 新增真实流地址测试（.ts/.m3u8片段）
- 🎯 修复：解决列表中源播放不了的问题
- 🎯 优化：更准确地验证直播源可用性

### v24.2 (2024-02-23)

- ✨ 新增深度URL验证（读取流数据）
- ✨ 新增智能URL选择（手动源+m3u8+延迟）
- 🎯 优化延迟阈值为2000ms
- 🎯 优化每频道保留3条最佳线路
- 🎨 添加类型注解，提升代码质量
- 📦 使用@dataclass优化数据结构

### v24.0

- 初始版本

---

## 📄 许可证

MIT License

---

## 🙏 致谢

- 首发源：[fanmingming/live](https://github.com/fanmingming/live)
- EPG源：[live.fanmingming.com](https://live.fanmingming.com)

---

## 💚 反馈与支持

如果觉得好用，请给个 ⭐️ Star！

有问题请提 [Issue](https://github.com/qq49371114/iptv_live/issues)

---

**Made with ❤️ by 婉儿**
