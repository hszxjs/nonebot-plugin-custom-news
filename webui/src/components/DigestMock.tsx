import type { DigestCardData, Theme } from "../types";

interface Props {
  theme: Theme;
  cards: DigestCardData[];
  /** 预览背景图 URL（preset/upload 用接口地址；wallpaper 用随机图占位） */
  bgUrl: string | null;
}

/** 日报 React 实时模拟预览：与后端模板使用同一套 CSS 变量体系 */

function fmtHot(hot: number | null): string {
  if (hot == null || hot <= 0) return "";
  if (hot >= 1e8) return `${(hot / 1e8).toFixed(1).replace(/\.0$/, "")}亿`;
  if (hot >= 1e4) return `${(hot / 1e4).toFixed(1).replace(/\.0$/, "")}万`;
  return String(hot);
}

const MOCK_ITEMS = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    rank: i + 1,
    title: [
      "示例新闻标题：科技巨头发布全新一代旗舰产品",
      "示例：全国天气迎来转折，冷空气即将南下",
      "示例：年度票房冠军诞生，观众口碑持续发酵",
      "示例：新型电池技术取得突破，续航翻倍",
      "示例：这座城市再次上榜宜居榜单",
    ][i % 5],
    hot: [1234.5, 987.6, 567.8, 234.5, 88.8][i % 5],
  }));

export default function DigestMock({ theme, cards, bgUrl }: Props) {
  const c = theme.palette.colors;
  const useMock = cards.length === 0;
  const display = useMock
    ? [
        { source_id: "demo1", name: "示例热榜", emoji: "📰", stale: false, items: MOCK_ITEMS(theme.cards.items_per_card) },
        { source_id: "demo2", name: "示例科技", emoji: "💻", stale: false, items: MOCK_ITEMS(theme.cards.items_per_card) },
      ]
    : cards.map((x) => ({ ...x, items: x.items.slice(0, theme.cards.items_per_card) }));

  const overlayRgb =
    theme.background.overlay_mode === "light" ? "255,255,255" : "12,14,24";
  const scale = theme.typography.scale;
  const shadows = [
    "none",
    "4px 6px 16px rgba(0,0,0,.10)",
    "10px 16px 36px rgba(0,0,0,.16)",
    "16px 26px 52px rgba(0,0,0,.28)",
  ];

  return (
    <div
      className="relative w-full overflow-hidden rounded-xl"
      style={{
        aspectRatio: "auto",
        minHeight: 360,
        background: bgUrl
          ? `center / cover no-repeat url(${bgUrl})`
          : `linear-gradient(135deg, ${c.primary}33, ${c.accent}33)`,
      }}
    >
      {theme.background.blur > 0 && (
        <div
          className="absolute inset-0"
          style={{ backdropFilter: `blur(${theme.background.blur}px)` }}
        />
      )}
      <div
        className="absolute inset-0"
        style={{
          background: `linear-gradient(180deg, rgba(${overlayRgb},${theme.background.overlay}) 0%, rgba(${overlayRgb},${(theme.background.overlay * 0.55).toFixed(2)}) 45%, rgba(${overlayRgb},${theme.background.overlay}) 100%)`,
        }}
      />
      <div
        className="relative flex flex-col gap-2 overflow-hidden p-3"
        style={{ color: c.text, fontSize: 13 * scale }}
      >
        <div className="text-center">
          {theme.header.show_date && (
            <span
              className="inline-block rounded-full px-3 py-0.5 text-[10px]"
              style={{ background: c.card_bg, border: `1px solid ${c.card_border}` }}
            >
              <span
                className="mr-1 inline-block h-1 w-1 rounded-full"
                style={{ background: c.primary }}
              />
              2026年08月27日 · 星期四
            </span>
          )}
          <div
            className="mt-1 font-bold"
            style={{
              fontSize: 20 * scale,
              fontWeight: theme.typography.title_weight,
              // 注意：必须用 backgroundImage 长属性；background 简写会重置
              // background-clip，且 React 差量更新不会重设未变化的 clip → 变色块
              backgroundImage: `linear-gradient(120deg, ${c.primary}, ${c.accent})`,
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            {theme.header.title || "今日热点速递"}
          </div>
          <div className="text-[10px] tracking-widest" style={{ color: c.subtext }}>
            {theme.header.subtitle}
          </div>
          <div
            className="mx-auto mt-1.5 h-0.5 w-16 rounded-full"
            style={{
              background: `linear-gradient(90deg, transparent, ${c.primary}, ${c.accent}, transparent)`,
            }}
          />
        </div>

        <div
          className="grid gap-2"
          style={{
            gridTemplateColumns: `repeat(${theme.cards.columns}, minmax(0, 1fr))`,
          }}
        >
          {display.slice(0, theme.cards.columns * 2).map((card) => {
            const cardColor = theme.per_card[card.source_id] ?? c.primary;
            return (
              <div
                key={card.source_id}
                className="relative overflow-hidden p-2.5"
                style={{
                  background: c.card_bg,
                  border: `1px solid ${c.card_border}`,
                  borderRadius: theme.cards.border_radius / 2,
                  backdropFilter: `blur(${theme.cards.glass_blur / 2}px) saturate(${theme.cards.glass_saturation})`,
                  boxShadow: shadows[theme.cards.shadow] ?? shadows[2],
                }}
              >
                <div
                  className="pointer-events-none absolute inset-0"
                  style={{
                    borderRadius: theme.cards.border_radius / 2,
                    background:
                      "linear-gradient(135deg, rgba(255,255,255,.28) 0%, rgba(255,255,255,.06) 30%, transparent 50%)",
                  }}
                />
                <div className="mb-1.5 flex items-center gap-1.5">
                  <span
                    className="flex h-5 w-5 items-center justify-center rounded-md text-[11px]"
                    style={{
                      background: `color-mix(in srgb, ${cardColor} 16%, transparent)`,
                      border: `1px solid color-mix(in srgb, ${cardColor} 30%, transparent)`,
                    }}
                  >
                    {card.emoji}
                  </span>
                  <span className="truncate text-xs font-bold">{card.name}</span>
                </div>
                <div
                  className="mb-1.5 h-0.5 rounded-full"
                  style={{
                    background: `linear-gradient(90deg, ${cardColor}, transparent)`,
                  }}
                />
                <div className="flex flex-col gap-0.5">
                  {card.items.slice(0, 6).map((item) => {
                    const rk = item.rank;
                    const top3 = rk <= 3;
                    return (
                      <div
                        key={rk}
                        className="flex items-start gap-1.5 rounded-md px-1.5 py-1"
                        style={
                          rk % 2 === 0
                            ? { background: `color-mix(in srgb, ${c.text} 4.5%, transparent)` }
                            : undefined
                        }
                      >
                        <span
                          className="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded text-[9px] font-bold"
                          style={
                            top3
                              ? { background: c[`rank${rk}` as "rank1" | "rank2" | "rank3"], color: "#fff" }
                              : {
                                  background: `color-mix(in srgb, ${c.subtext} 18%, transparent)`,
                                  color: c.rank_n,
                                }
                          }
                        >
                          {rk}
                        </span>
                        <span
                          className="min-w-0 flex-1 text-[11px] font-medium leading-snug [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2] [overflow:hidden] [text-align:justify]"
                        >
                          {item.title}
                        </span>
                        {theme.cards.show_hot && (
                          <span className="mt-0.5 shrink-0 text-[9px]" style={{ color: c.hot }}>
                            {fmtHot(item.hot)}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        <div className="pt-1 text-center text-[9px]" style={{ color: c.subtext }}>
          {theme.footer.custom_text && <div>{theme.footer.custom_text}</div>}
          <div>
            2026-08-27 08:00
            {theme.footer.show_credit ? " · Powered by nonebot-plugin-custom-news" : ""}
          </div>
        </div>
      </div>
    </div>
  );
}
