import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  CardBody,
  Chip,
  Input,
  Modal,
  SegTabs,
  Select,
  Slider,
  Switch,
  Tip,
} from "../ui";
import { api } from "../api";
import type {
  BackgroundItem,
  ConfigResponse,
  DigestCardData,
  PaletteColors,
  Theme,
} from "../types";
import ColorField from "../components/ColorField";
import DigestMock from "../components/DigestMock";

function defaultTheme(id: string): Theme {
  return {
    id,
    name: "新主题",
    background: { type: "preset", value: "sakura", overlay: 0.35, overlay_mode: "light", blur: 0 },
    palette: {
      mode: "auto",
      colors: {
        primary: "#e8739a", accent: "#6db7e8", text: "#33333f", subtext: "#6f6f82",
        card_bg: "rgba(255,255,255,0.55)", card_border: "rgba(255,255,255,0.7)",
        rank1: "#ff5d5d", rank2: "#ff9f43", rank3: "#ffc94d",
        rank_n: "#9aa0b0", hot: "#8d92a6",
      },
    },
    cards: { columns: 2, items_per_card: 10, border_radius: 24, glass_blur: 18, glass_saturation: 1.4, shadow: 2, show_hot: true },
    typography: { scale: 1.0, title_weight: 700 },
    header: { title: "今日热点速递", subtitle: "全网热点 · 一图速览", show_date: true },
    footer: { custom_text: "", show_credit: true },
    per_card: {},
  };
}

const TABS = [
  { key: "bg", label: "🖼️ 背景与配色" },
  { key: "cards", label: "🃏 卡片样式" },
  { key: "typo", label: "✒️ 文字页眉脚" },
  { key: "percard", label: "🏷️ 分卡配色" },
];

export default function ThemeEditorPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [theme, setTheme] = useState<Theme | null>(null);
  const [backgrounds, setBackgrounds] = useState<BackgroundItem[]>([]);
  const [cards, setCards] = useState<DigestCardData[]>([]);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [tab, setTab] = useState("bg");
  const [renderModal, setRenderModal] = useState(false);
  const [newModal, setNewModal] = useState(false);

  useEffect(() => {
    (async () => {
      const cfg = await api.getConfig();
      setConfig(cfg);
      const t = cfg.config.themes[cfg.config.active_theme_id];
      if (t) setTheme(structuredClone(t));
      const bg = await api.listBackgrounds();
      setBackgrounds([...bg.preset, ...bg.uploaded]);
      api.getDigestCards().then((r) => setCards(r.cards)).catch(() => setCards([]));
    })();
  }, []);

  const patch = useCallback((fn: (t: Theme) => void) => {
    setTheme((prev) => {
      if (!prev) return prev;
      const next = structuredClone(prev);
      fn(next);
      return next;
    });
  }, []);

  const bgPreviewUrl = useMemo(() => {
    if (!theme) return null;
    if (theme.background.type === "preset") {
      return `/custom-news/api/backgrounds/preset/${theme.background.value}`;
    }
    if (theme.background.type === "upload") {
      return `/custom-news/api/backgrounds/file/${encodeURIComponent(theme.background.value)}`;
    }
    return null;
  }, [theme]);

  const save = async (): Promise<boolean> => {
    if (!theme) return false;
    setBusy("save");
    try {
      await api.saveTheme(theme);
      const cfg = await api.getConfig();
      setConfig(cfg);
      setMsg(`✅ 主题「${theme.name}」已保存`);
      return true;
    } catch (e) {
      setMsg(`❌ ${e instanceof Error ? e.message : "保存失败"}`);
      return false;
    } finally {
      setBusy("");
    }
  };

  const renderReal = async () => {
    if (!theme) return;
    setBusy("render");
    setMsg("");
    try {
      const r = await api.renderPreview({ theme });
      setPreviewImage(r.image);
      setRenderModal(true);
    } catch (e) {
      setMsg(`❌ ${e instanceof Error ? e.message : "渲染失败"}`);
    } finally {
      setBusy("");
    }
  };

  const applyAutoPalette = async () => {
    if (!theme) return;
    setBusy("palette");
    try {
      const r = await api.extractPalette(theme.background);
      patch((t) => {
        t.palette.colors = r.colors;
        t.palette.mode = "manual";
      });
      setMsg("✅ 已从背景图提取配色并应用（切换为手动模式）");
    } catch (e) {
      setMsg(`❌ ${e instanceof Error ? e.message : "提取失败"}`);
    } finally {
      setBusy("");
    }
  };

  if (!config || !theme) {
    return <div className="p-8 text-center text-muted">加载中…</div>;
  }

  const colors = theme.palette.colors;
  const setColor = (key: keyof PaletteColors) => (v: string) =>
    patch((t) => {
      t.palette.colors[key] = v;
      t.palette.mode = "manual";
    });
  const themeList = Object.values(config.config.themes);
  const presetBgs = backgrounds.filter((b) => b.id);
  const uploadBgs = backgrounds.filter((b) => !b.id);

  return (
    <div className="grid gap-4 xl:grid-cols-[210px_minmax(0,1fr)_400px]">
      {/* 主题列表 */}
      <Card className="h-fit glass">
        <CardBody className="gap-1 p-3">
          <div className="mb-1 flex items-center justify-between px-1">
            <span className="text-small font-semibold">我的主题</span>
            <Button size="sm" variant="light" isIconOnly onPress={() => setNewModal(true)} title="新建主题">
              ＋
            </Button>
          </div>
          {themeList.map((t) => (
            <div
              key={t.id}
              className={`flex cursor-pointer items-center gap-1 rounded-xl px-3 py-2 text-small transition-colors ${
                t.id === theme.id ? "bg-accent/15 font-semibold text-accent" : "hover:bg-surface-hover"
              }`}
              onClick={() => setTheme(structuredClone(t))}
            >
              <span className="flex flex-1 flex-col gap-1">
                <span className="truncate">{t.name}</span>
                <span className="flex gap-1">
                  {[t.palette.colors.primary, t.palette.colors.accent, t.palette.colors.rank1, t.palette.colors.rank2, t.palette.colors.rank3].map((c, i) => (
                    <span key={i} className="h-1.5 w-3.5 rounded-full" style={{ background: c }} />
                  ))}
                </span>
              </span>
              {t.id === config.config.active_theme_id && <Chip color="success">使用中</Chip>}
            </div>
          ))}
          <div className="mt-2 flex flex-col gap-1.5">
            <Button size="sm" isLoading={busy === "save"} onPress={() => void save()}>
              💾 保存当前主题
            </Button>
            <Button
              size="sm"
              variant="flat"
              color="success"
              onPress={async () => {
                if (await save()) {
                  await api.activateTheme(theme.id);
                  const cfg = await api.getConfig();
                  setConfig(cfg);
                  setMsg(`✅ 已激活「${theme.name}」，定时推送与「今日热点」命令将使用该主题`);
                }
              }}
            >
              ⭐ 保存并启用
            </Button>
            <Button
              size="sm"
              variant="flat"
              onPress={async () => {
                const r = await api.duplicateTheme(theme.id);
                const cfg = await api.getConfig();
                setConfig(cfg);
                setTheme(structuredClone(cfg.config.themes[r.id]));
              }}
            >
              📋 复制为副本
            </Button>
            {!config.preset_theme_ids.includes(theme.id) && (
              <Button
                size="sm"
                variant="flat"
                color="danger"
                onPress={async () => {
                  try {
                    await api.deleteTheme(theme.id);
                  } catch (e) {
                    setMsg(`❌ ${e instanceof Error ? e.message : "删除失败"}`);
                    return;
                  }
                  const cfg = await api.getConfig();
                  setConfig(cfg);
                  setTheme(structuredClone(cfg.config.themes[cfg.config.active_theme_id]));
                }}
              >
                🗑️ 删除主题
              </Button>
            )}
          </div>
        </CardBody>
      </Card>

      {/* 编辑表单 */}
      <Card className="glass glass-hover">
        <CardBody className="p-4">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <Input
              className="w-48"
              label="主题名称"
              value={theme.name}
              onValueChange={(v) => patch((t) => (t.name = v))}
            />
            {msg && <span className="text-small text-muted">{msg}</span>}
          </div>

          <div className="mb-4 mt-1">
            <SegTabs tabs={TABS} active={tab} onChange={setTab} />
          </div>

          {tab === "bg" && (
            <div className="flex flex-col gap-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <Select
                  label="背景类型"
                  value={theme.background.type}
                  onChange={(v) => patch((t) => (t.background.type = v as never))}
                  options={[
                    { value: "preset", label: "预设背景" },
                    { value: "upload", label: "上传图片" },
                    { value: "wallpaper", label: "每日在线壁纸（必应）" },
                  ]}
                />
                {theme.background.type === "preset" && (
                  <Select
                    label="预设背景"
                    value={theme.background.value}
                    onChange={(v) => patch((t) => (t.background.value = v))}
                    options={presetBgs.map((b) => ({ value: b.id!, label: b.name }))}
                  />
                )}
                {theme.background.type === "upload" && (
                  <div className="flex items-end gap-2">
                    <Select
                      className="flex-1"
                      label="已上传图片"
                      value={theme.background.value}
                      onChange={(v) => patch((t) => (t.background.value = v))}
                      options={uploadBgs.map((b) => ({ value: b.name, label: b.name }))}
                    />
                    <label className="cursor-pointer rounded-xl bg-accent-soft px-3 py-2 text-small text-accent hover:bg-accent-soft-hover">
                      上传
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={async (e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          setBusy("upload");
                          try {
                            const r = await api.uploadBackground(file);
                            const bg = await api.listBackgrounds();
                            setBackgrounds([...bg.preset, ...bg.uploaded]);
                            patch((t) => {
                              t.background.type = "upload";
                              t.background.value = r.filename;
                            });
                          } catch (err) {
                            setMsg(`❌ ${err instanceof Error ? err.message : "上传失败"}`);
                          } finally {
                            setBusy("");
                          }
                        }}
                      />
                    </label>
                  </div>
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <Slider
                  label="遮罩浓度"
                  minValue={0}
                  maxValue={0.9}
                  step={0.05}
                  value={theme.background.overlay}
                  onChange={(v) => patch((t) => (t.background.overlay = v))}
                  formatValue={(v) => `${(v * 100).toFixed(0)}%`}
                />
                <Select
                  label="遮罩颜色"
                  value={theme.background.overlay_mode}
                  onChange={(v) => patch((t) => (t.background.overlay_mode = v as never))}
                  options={[
                    { value: "light", label: "白色（浅色系主题）" },
                    { value: "dark", label: "深色（暗色系主题）" },
                  ]}
                />
                <Slider
                  label="背景模糊"
                  minValue={0}
                  maxValue={24}
                  step={1}
                  value={theme.background.blur}
                  onChange={(v) => patch((t) => (t.background.blur = v))}
                  formatValue={(v) => `${v}px`}
                />
                <div className="flex flex-col gap-1.5">
                  <Switch
                    isSelected={theme.palette.mode === "auto"}
                    onValueChange={(v) => patch((t) => (t.palette.mode = v ? "auto" : "manual"))}
                  >
                    自动配色
                  </Switch>
                  <span className="text-tiny leading-snug text-muted/80">
                    开启后由背景图实时提取整套配色并自动校验对比度
                  </span>
                </div>
              </div>

              {theme.palette.mode === "manual" ? (
                <div className="grid gap-2 rounded-xl bg-surface-secondary/60 p-3 sm:grid-cols-2 lg:grid-cols-3">
                  <ColorField label="主色 Primary" value={colors.primary} onChange={setColor("primary")} />
                  <ColorField label="强调色 Accent" value={colors.accent} onChange={setColor("accent")} />
                  <ColorField label="正文文字" value={colors.text} onChange={setColor("text")} />
                  <ColorField label="次级文字" value={colors.subtext} onChange={setColor("subtext")} />
                  <ColorField label="卡片底色 (支持rgba)" value={colors.card_bg} onChange={setColor("card_bg")} />
                  <ColorField label="卡片描边 (支持rgba)" value={colors.card_border} onChange={setColor("card_border")} />
                  <ColorField label="第1名" value={colors.rank1} onChange={setColor("rank1")} />
                  <ColorField label="第2名" value={colors.rank2} onChange={setColor("rank2")} />
                  <ColorField label="第3名" value={colors.rank3} onChange={setColor("rank3")} />
                  <ColorField label="普通名次" value={colors.rank_n} onChange={setColor("rank_n")} />
                  <ColorField label="热度数值" value={colors.hot} onChange={setColor("hot")} />
                </div>
              ) : (
                <div className="rounded-xl bg-surface-secondary/60 p-3 text-small text-muted">
                  自动配色已开启：渲染时将从背景图实时提取主色、强调色、文字与榜单配色，并自动校验对比度。
                </div>
              )}
            </div>
          )}

          {tab === "cards" && (
            <div className="grid gap-4 py-1 sm:grid-cols-2">
              <Slider label="每行卡片数" minValue={1} maxValue={4} step={1} value={theme.cards.columns} onChange={(v) => patch((t) => (t.cards.columns = v))} />
              <Slider label="每卡条数" minValue={1} maxValue={20} step={1} value={theme.cards.items_per_card} onChange={(v) => patch((t) => (t.cards.items_per_card = v))} />
              <Slider label="圆角" minValue={0} maxValue={48} step={2} value={theme.cards.border_radius} onChange={(v) => patch((t) => (t.cards.border_radius = v))} formatValue={(v) => `${v}px`} />
              <Slider label="毛玻璃强度" minValue={0} maxValue={40} step={1} value={theme.cards.glass_blur} onChange={(v) => patch((t) => (t.cards.glass_blur = v))} formatValue={(v) => `${v}px`} />
              <Slider label="毛玻璃饱和度" minValue={1} maxValue={2.5} step={0.1} value={theme.cards.glass_saturation} onChange={(v) => patch((t) => (t.cards.glass_saturation = v))} formatValue={(v) => `${v.toFixed(1)}x`} />
              <Slider label="阴影强度" minValue={0} maxValue={3} step={1} value={theme.cards.shadow} onChange={(v) => patch((t) => (t.cards.shadow = v))} />
              <Switch isSelected={theme.cards.show_hot} onValueChange={(v) => patch((t) => (t.cards.show_hot = v))}>
                显示热度数值
              </Switch>
            </div>
          )}

          {tab === "typo" && (
            <div className="grid gap-4 py-1 sm:grid-cols-2">
              <Input label="日报大标题" value={theme.header.title} onValueChange={(v) => patch((t) => (t.header.title = v))} />
              <Input label="副标题" value={theme.header.subtitle} onValueChange={(v) => patch((t) => (t.header.subtitle = v))} />
              <Input label="页脚自定义文案" placeholder="如：每天早八，热点速递" value={theme.footer.custom_text} onValueChange={(v) => patch((t) => (t.footer.custom_text = v))} />
              <Slider label="整体字号缩放" minValue={0.7} maxValue={1.5} step={0.05} value={theme.typography.scale} onChange={(v) => patch((t) => (t.typography.scale = v))} formatValue={(v) => `${v.toFixed(2)}x`} />
              <Slider label="标题字重" minValue={400} maxValue={900} step={100} value={theme.typography.title_weight} onChange={(v) => patch((t) => (t.typography.title_weight = v))} />
              <div className="flex items-center gap-6">
                <Switch isSelected={theme.header.show_date} onValueChange={(v) => patch((t) => (t.header.show_date = v))}>
                  显示日期胶囊
                </Switch>
                <Switch isSelected={theme.footer.show_credit} onValueChange={(v) => patch((t) => (t.footer.show_credit = v))}>
                  显示插件署名
                </Switch>
              </div>
            </div>
          )}

          {tab === "percard" && (
            <div className="py-1">
              <p className="mb-3 text-small text-muted">
                为指定数据源的卡片单独指定主色（标题横线与图标底色），恢复主色即跟随主题。
              </p>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {cards.map((c) => (
                  <div key={c.source_id} className="rounded-xl bg-surface-secondary/60 p-2">
                    <ColorField
                      label={`${c.emoji} ${c.name}`}
                      value={theme.per_card[c.source_id] ?? colors.primary}
                      onChange={(v) =>
                        patch((t) => {
                          if (v === t.palette.colors.primary) delete t.per_card[c.source_id];
                          else t.per_card[c.source_id] = v;
                        })
                      }
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      {/* 实时预览 */}
      <div className="flex flex-col gap-3">
        <Card className="glass sticky top-4">
          <CardBody className="gap-3 p-4">
            <div className="flex items-center justify-between">
              <span className="font-semibold">实时预览</span>
              <Tip content="调用后端 Playwright 生成最终日报图">
                <Button size="sm" variant="flat" isLoading={busy === "render" || busy === "palette" || busy === "upload"} onPress={() => void renderReal()}>
                  📸 真实渲染
                </Button>
              </Tip>
            </div>
            <DigestMock theme={theme} cards={cards} bgUrl={bgPreviewUrl} />
            <Button size="sm" variant="flat" onPress={() => void applyAutoPalette()} isLoading={busy === "palette"}>
              🎨 用当前背景提取配色
            </Button>
            <p className="text-tiny text-muted/80">
              预览为 React 模拟效果；「真实渲染」生成最终日报图（记得先保存主题再渲染推送）。
            </p>
          </CardBody>
        </Card>
      </div>

      <Modal
        isOpen={renderModal}
        onClose={() => setRenderModal(false)}
        title="真实渲染结果（当前编辑中的主题）"
        wide
        footer={<Button onPress={() => setRenderModal(false)}>关闭</Button>}
      >
        {previewImage && (
          <img src={`data:image/png;base64,${previewImage}`} alt="渲染结果" className="w-full rounded-xl" />
        )}
      </Modal>

      <NewThemeModal
        isOpen={newModal}
        onClose={() => setNewModal(false)}
        base={theme}
        onOk={(base, name, id) => {
          const t = base ? structuredClone(base) : defaultTheme(id);
          t.id = id;
          t.name = name;
          setTheme(t);
          setNewModal(false);
        }}
      />
    </div>
  );
}

function NewThemeModal({
  isOpen,
  onClose,
  base,
  onOk,
}: {
  isOpen: boolean;
  onClose: () => void;
  base: Theme | null;
  onOk: (base: Theme | null, name: string, id: string) => void;
}) {
  const [name, setName] = useState("");
  const [fromCurrent, setFromCurrent] = useState(true);
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="新建主题"
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            取消
          </Button>
          <Button
            isDisabled={!name.trim()}
            onPress={() => onOk(fromCurrent ? base : null, name.trim(), `custom_${Date.now().toString(36)}`)}
          >
            创建
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label="主题名称" value={name} onValueChange={setName} />
        <Switch isSelected={fromCurrent} onValueChange={setFromCurrent}>
          基于当前主题创建
        </Switch>
        <p className="text-tiny text-muted">注意：新主题需点击「保存」后才会写入配置。</p>
      </div>
    </Modal>
  );
}
