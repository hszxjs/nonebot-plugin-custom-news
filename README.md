# nonebot-plugin-custom-news 全网热点日报

> 每日网罗全网热点 —— B站、微博、新闻、科技、全球资讯一图速览。
> 高自定义主题卡片（背景图 + 自动取色 + 毛玻璃），定时推送到群/私聊，附带 HeroUI 打造的 WebUI 可视化后台。

![NoneBot2](https://img.shields.io/badge/NoneBot2-2.3+-ea5252) ![Python](https://img.shields.io/badge/Python-3.10+-3776ab) ![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 功能

- **全网热点聚合**：基于 [DailyHotApi](https://github.com/imsyy/DailyHotApi)，内置 B站/微博/澎湃/头条/IT之家/36氪/新浪等 20 个源，可自定义任意路由源；另有**网易云/QQ音乐新歌榜**（直连官方公开接口，无需登录）
- **主题化日报图**：背景图（预设 6 张 / 上传 / 必应每日壁纸）+ 毛玻璃卡片 + 榜单样式，全部可视化定制
- **自动取色**：从背景图提取主色生成整套配色（遮罩带主色调渲染，背景-卡片-标题浑然一体），WCAG 对比度自动校验
- **定时推送**：多时段 cron（每时段可绑不同主题，如早报浅色/晚报深色），命令订阅 + WebUI 双通道管理
- **音乐账号登录（WebUI）**：网易云支持扫码 + 手机验证码登录（纯协议实现，无需外部服务），QQ音乐支持扫码登录（ptlogin 协议）；双平台均支持手动导入浏览器 Cookie 兜底。登录后音乐卡片可获得真实播放直链
- **WebUI 后台**：HeroUI v3 + HarmonyOS Sans 字体，主题工坊实时预览 + 真实渲染、数据源管理、推送管理、音乐账号、系统设置
- **新闻深读（AI 解析）**：日报后自动跟随/命令触发，抓取新闻**原文**（trafilatura 提取正文）交给 LLM 解析，输出聊天记录风格的深度解读图（事件/背景/要点/影响/锐评）
- **全适配器兼容**：基于 uniseg UniMessage，支持 OneBot v11/v12、QQ官方、Telegram、Discord 等

## 📦 安装

```bash
nb plugin install nonebot-plugin-custom-news
# 或
pip install nonebot-plugin-custom-news
```

在 `.env` 中可选配置：

```ini
custom_news_dailyhot_api_url=https://api-hot.imsyy.top   # 建议自部署
custom_news_webui_password=你的WebUI密码                  # 不填则首次启动随机生成并打印日志
custom_news_render_width=1280   # pad 宽幅长图
custom_news_cache_ttl=1800
custom_news_timezone=Asia/Shanghai
```

新闻深读（LLM）在 WebUI「设置」页配置：OpenAI 兼容 Base URL / API Key / 模型（DeepSeek、智谱、Ollama 等均可），支持日报后自动跟随；API Key 填 `mock` 可预览样式。

渲染依赖 Playwright 浏览器，首次使用请执行：

```bash
playwright install chromium-headless-shell
```

## 🚀 使用

### 机器人命令

| 命令 | 说明 |
|---|---|
| `今日热点` | 立即生成今日全网热点日报图 |
| `订阅热点` / `退订热点` | 将本会话加入/移出定时推送列表 |
| `热点帮助` | 查看帮助 |
| `热点解析` | AI 深读：抓取新闻原文，生成聊天记录风格的深度解读图（需配置 LLM） |
| `新歌榜` | 网易云/QQ音乐各发一条 QQ 合并转发聊天记录：Top10 文字榜单 + 每首歌可播放音乐卡片 + 热评 Top3 |

### WebUI

浏览器打开 `http://bot-host:port/custom-news/webui/`（需 FastAPI driver，默认账号 `admin`，初始密码见启动日志）：

- **总览**：状态统计 / 最近渲染图 / 立即渲染 / 立即推送
- **主题工坊**：左侧主题列表（色板预览），中间分区编辑（背景/配色/卡片/文字/分卡覆写），右侧 React 实时预览 + Playwright 真实渲染
- **数据源**：22 个内置源滑块开关 + 条数调整 + 自定义源（含音乐新歌分类）
- **推送管理**：推送目标 + 多时段定时任务（每时段独立主题）
- **设置**：渲染参数 / 缓存 / 每日壁纸 / 修改密码

## 🔧 自部署 DailyHotApi（推荐）

公共实例在海外且有限流风险，生产环境建议一行 Docker 自部署：

```bash
docker run --restart always -d -p 6688:6688 imsyy/dailyhot-api:latest
```

然后在 WebUI「数据源」页把地址改为 `http://127.0.0.1:6688`。

## 🎨 主题系统

每套主题为一个 JSON：

- **背景**：预设 / 上传 / 必应每日壁纸，遮罩浓度与色调（浅/深）、背景模糊
- **配色**：`auto`（背景图提取主色 → 主色/强调色/文字/榜单色 + 对比度校验）或 `manual`（11 项逐个指定）
- **卡片**：每行卡片数（默认 2，pad 宽幅下标题基本一行放下）、每卡条数、圆角、毛玻璃强度/饱和度、阴影、热度显示；榜单标题超长自动两行换行（CJK 两端对齐 + 斑马纹行底）
- **文字**：标题/副标题/页脚文案、字号缩放、标题字重
- **分卡覆写**：按数据源单独指定卡片主色（如微博红、B站蓝）

内置 6 套预设主题：樱粉 / 星夜 / 海空 / 暮金 / 薄荷 / 墨白。

## 📁 项目结构

```
nonebot_plugin_custom_news/   # Python 后端
├── sources/      # DailyHotApi 客户端、每日壁纸
├── fetcher.py    # 并发抓取 + TTL缓存 + 失败降级
├── palette.py    # 背景图取色 → 自动配色
├── renderer.py   # Jinja2 模板 → Playwright 截图
├── scheduler.py  # 多时段定时推送
├── matcher.py    # 命令处理
├── templates/    # 日报 HTML 模板
├── fonts/        # HarmonyOS Sans SC（woff2）
├── assets/       # 预设背景图
└── webui/        # REST API + 前端构建产物
webui/            # 前端源码（React 19 + Vite + Tailwind v4 + HeroUI v3）
```

前端二次开发：`cd webui && npm i && npm run build`，产物自动复制到 `nonebot_plugin_custom_news/webui/dist`。

## 📄 字体版权

内置 HarmonyOS Sans SC 字体遵循 [HarmonyOS Sans Fonts License](https://developer.huawei.com/consumer/cn/design/resource-V1/)（免费使用与随软件分发），不可单独出售字体文件。

## License

MIT
