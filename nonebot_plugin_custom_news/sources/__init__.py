"""内置数据源注册表。每个源对应日报中的一张卡片。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDef:
    id: str
    name: str
    route: str
    category: str
    emoji: str
    default_enabled: bool = False
    default_limit: int = 10
    #: 抓取器：dailyhot（默认，走 DailyHotApi）/ netease_music / qq_music
    fetcher: str = "dailyhot"


#: 分类 → 中文名（WebUI 分组用）
CATEGORY_LABELS: dict[str, str] = {
    "video": "视频热榜",
    "social": "社交热议",
    "news": "新闻热点",
    "tech": "科技圈",
    "global": "全球资讯",
    "dev": "开发者",
    "fun": "趣味速览",
    "music": "音乐新歌",
}

BUILTIN_SOURCES: list[SourceDef] = [
    # 视频热榜
    SourceDef("bilibili", "B站热点", "/bilibili", "video", "📺", True, 10),
    # 社交热议 / 近期重大事件
    SourceDef("weibo", "微博热搜", "/weibo", "social", "🔥", True, 10),
    SourceDef("douyin", "抖音热点", "/douyin", "social", "🎵", False, 10),
    SourceDef("baidu", "百度热搜", "/baidu", "social", "🔍", False, 8),
    # 新闻热点
    SourceDef("thepaper", "澎湃新闻", "/thepaper", "news", "📰", True, 8),
    SourceDef("toutiao", "今日头条", "/toutiao", "news", "📄", True, 8),
    SourceDef("qq-news", "腾讯新闻", "/qq-news", "news", "🐧", False, 8),
    # 科技圈
    SourceDef("ithome", "IT之家", "/ithome", "tech", "💻", True, 8),
    SourceDef("36kr", "36氪", "/36kr", "tech", "🚀", True, 8),
    SourceDef("huxiu", "虎嗅", "/huxiu", "tech", "🐯", False, 8),
    SourceDef("sspai", "少数派", "/sspai", "tech", "⚡", False, 8),
    # 全球资讯
    SourceDef("sina-news", "新浪新闻", "/sina-news", "global", "🌐", True, 8),
    SourceDef("netease-news", "网易新闻", "/netease-news", "global", "🎣", False, 8),
    SourceDef("zhihu", "知乎热榜", "/zhihu", "social", "🧠", False, 8),
    # 开发者（默认关闭）
    SourceDef("hellogithub", "HelloGitHub", "/hellogithub", "dev", "🐙", False, 6),
    SourceDef("v2ex", "V2EX", "/v2ex", "dev", "💬", False, 6),
    SourceDef("juejin", "稀土掘金", "/juejin", "dev", "⛏️", False, 6),
    # 趣味速览（默认关闭）
    SourceDef("hupu", "虎扑步行街", "/hupu", "fun", "🏀", False, 6),
    SourceDef("earthquake", "地震速报", "/earthquake", "fun", "🫨", False, 6),
    SourceDef("history-today", "历史上的今天", "/history", "fun", "🕰️", False, 6),
    # 音乐新歌（直连官方接口，不走 DailyHotApi）
    SourceDef(
        "netease-new", "网易云新歌榜", "", "music", "🎵", True, 10, "netease_music"
    ),
    SourceDef("qq-new", "QQ音乐新歌榜", "", "music", "🎧", True, 10, "qq_music"),
]

BUILTIN_SOURCE_MAP: dict[str, SourceDef] = {s.id: s for s in BUILTIN_SOURCES}
