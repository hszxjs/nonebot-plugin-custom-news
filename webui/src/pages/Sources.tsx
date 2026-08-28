import { useCallback, useEffect, useState } from "react";
import { ArrowsClockwise, FloppyDisk, X } from "@phosphor-icons/react";
import { Button, Card, CardBody, Input, PageHeader, Switch } from "../ui";
import { api } from "../api";
import type { CustomSourceDef, SourceSetting } from "../types";

const CATEGORY_ICON: Record<string, string> = {
  video: "📺",
  social: "🔥",
  news: "📰",
  tech: "💻",
  global: "🌐",
  dev: "🐙",
  fun: "🎲",
  music: "🎼",
  custom: "✨",
};

/** builtin id → category（与后端注册表一致） */
const BUILTIN_CATEGORY_OF: Record<string, string> = {
  bilibili: "video",
  weibo: "social", douyin: "social", baidu: "social", zhihu: "social",
  thepaper: "news", toutiao: "news", "qq-news": "news",
  ithome: "tech", "36kr": "tech", huxiu: "tech", sspai: "tech",
  "sina-news": "global", "netease-news": "global",
  hellogithub: "dev", v2ex: "dev", juejin: "dev",
  hupu: "fun", earthquake: "fun", "history-today": "fun",
  "netease-new": "music", "qq-new": "music",
};

interface SourceRow {
  id: string;
  name: string;
  route: string;
  emoji: string;
  enabled: boolean;
  limit: number;
  isCustom: boolean;
}

export default function SourcesPage() {
  const [rows, setRows] = useState<SourceRow[]>([]);
  const [categoryLabels, setCategoryLabels] = useState<Record<string, string>>({});
  const [apiUrl, setApiUrl] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [newCustom, setNewCustom] = useState({ name: "", route: "", emoji: "📌" });

  const load = useCallback(async () => {
    const cfg = await api.getConfig();
    setCategoryLabels(cfg.category_labels);
    setApiUrl(cfg.config.general.dailyhot_api_url);
    const builtinRows: SourceRow[] = cfg.builtin_sources.map((b) => ({
      id: b.id,
      name: b.name,
      route: b.route,
      emoji: b.emoji,
      enabled: cfg.config.sources[b.id]?.enabled ?? false,
      limit: cfg.config.sources[b.id]?.limit ?? 8,
      isCustom: false,
    }));
    const customRows: SourceRow[] = cfg.config.custom_sources.map((c) => ({
      id: c.id,
      name: c.name,
      route: c.route,
      emoji: c.emoji,
      enabled: c.enabled,
      limit: c.limit,
      isCustom: true,
    }));
    setRows([...builtinRows, ...customRows]);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const patchRow = (id: string, patch: Partial<SourceRow>) =>
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const removeRow = (id: string) => setRows((prev) => prev.filter((r) => r.id !== id));

  const save = async () => {
    setBusy("save");
    setMsg("");
    try {
      const sources: Record<string, SourceSetting> = {};
      const custom: CustomSourceDef[] = [];
      for (const r of rows) {
        if (r.isCustom) {
          custom.push({
            id: r.id,
            name: r.name,
            route: r.route,
            category: "custom",
            emoji: r.emoji,
            limit: r.limit,
            enabled: r.enabled,
          });
        } else {
          sources[r.id] = { enabled: r.enabled, limit: r.limit };
        }
      }
      await api.updateConfig({ sources, custom_sources: custom });
      const cfg = await api.getConfig();
      await api.updateConfig({
        general: { ...cfg.config.general, dailyhot_api_url: apiUrl },
      });
      setMsg("✅ 数据源配置已保存");
    } catch (e) {
      setMsg(`❌ ${e instanceof Error ? e.message : "保存失败"}`);
    } finally {
      setBusy("");
    }
  };

  const refreshAll = async () => {
    setBusy("refresh");
    setMsg("抓取中…");
    try {
      const r = await api.refreshSources();
      setMsg(
        r.ok
          ? `✅ ${r.cards.length} 个源成功${r.failed.length ? `，失败：${r.failed.join("、")}` : ""}`
          : "❌ 全部源抓取失败，请检查 DailyHotApi 地址",
      );
    } catch (e) {
      setMsg(`❌ ${e instanceof Error ? e.message : "刷新失败"}`);
    } finally {
      setBusy("");
    }
  };

  const enabledCount = rows.filter((r) => r.enabled).length;
  const customRows = rows.filter((r) => r.isCustom);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="数据源"
        desc={`已启用 ${enabledCount}/${rows.length} 个源 · 切换滑块开关各源，保存后生效`}
        actions={
          <div className="flex gap-2">
            <Button size="sm" variant="flat" isLoading={busy === "refresh"} onPress={refreshAll}>
              <ArrowsClockwise className="h-4 w-4" /> 抓取测试
            </Button>
            <Button size="sm" isLoading={busy === "save"} onPress={save}>
              <FloppyDisk className="h-4 w-4" /> 保存配置
            </Button>
          </div>
        }
      />

      <Card className="glass glass-hover">
        <CardBody className="flex flex-wrap items-end gap-3 py-4">
          <Input
            className="max-w-lg flex-1"
            label="DailyHotApi 地址"
            description="建议自部署：docker run -d -p 6688:6688 imsyy/dailyhot-api"
            value={apiUrl}
            onValueChange={setApiUrl}
          />
          {msg && <span className="pb-2 text-small text-muted">{msg}</span>}
        </CardBody>
      </Card>

      {/* 内置源：按分类分组 */}
      {Object.entries(categoryLabels).map(([cat, label]) => {
        const list = rows.filter((r) => !r.isCustom && BUILTIN_CATEGORY_OF[r.id] === cat);
        if (!list.length) return null;
        return (
          <Card key={cat} className="glass">
            <CardBody className="p-4">
              <div className="mb-3 flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent-soft bg-accent-soft text-base">
                  {CATEGORY_ICON[cat] ?? "📌"}
                </span>
                <span className="font-semibold">{label}</span>
                <span className="rounded-full bg-white/6 px-2 py-0.5 text-tiny text-muted">
                  {list.filter((r) => r.enabled).length}/{list.length} 启用
                </span>
              </div>
              <div className="grid gap-2.5 lg:grid-cols-2 2xl:grid-cols-3">
                {list.map((r) => (
                  <SourceTile key={r.id} row={r} onPatch={patchRow} />
                ))}
              </div>
            </CardBody>
          </Card>
        );
      })}

      {/* 自定义源 */}
      <Card className="glass">
        <CardBody className="p-4">
          <div className="mb-3 flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent-soft bg-accent-soft text-base">
              {CATEGORY_ICON.custom}
            </span>
            <span className="font-semibold">自定义源</span>
            <span className="text-tiny text-muted">通过 DailyHotApi 路由扩展（如 /kuaishou）</span>
          </div>
          <div className="grid gap-2.5 lg:grid-cols-2 2xl:grid-cols-3">
            {customRows.map((r) => (
              <SourceTile key={r.id} row={r} onPatch={patchRow} onRemove={removeRow} />
            ))}
            {customRows.length === 0 && (
              <div className="col-span-full rounded-2xl border border-dashed border-white/12 p-5 text-center text-small text-muted">
                暂无自定义源，在下方添加
              </div>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <Input className="w-36" label="名称" value={newCustom.name} onValueChange={(v) => setNewCustom((p) => ({ ...p, name: v }))} />
            <Input className="w-36" label="路由 如 /kuaishou" value={newCustom.route} onValueChange={(v) => setNewCustom((p) => ({ ...p, route: v }))} />
            <Input className="w-20" label="Emoji" value={newCustom.emoji} onValueChange={(v) => setNewCustom((p) => ({ ...p, emoji: v }))} />
            <Button
              variant="flat"
              isDisabled={!newCustom.name || !newCustom.route}
              onPress={() => {
                const route = newCustom.route.startsWith("/")
                  ? newCustom.route
                  : `/${newCustom.route}`;
                setRows((prev) => [
                  ...prev,
                  {
                    id: `c_${route.slice(1).replace(/\W/g, "_")}_${Date.now().toString(36)}`,
                    name: newCustom.name,
                    route,
                    emoji: newCustom.emoji || "📌",
                    enabled: true,
                    limit: 8,
                    isCustom: true,
                  },
                ]);
                setNewCustom({ name: "", route: "", emoji: "📌" });
              }}
            >
              ＋ 添加
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function SourceTile({
  row,
  onPatch,
  onRemove,
}: {
  row: SourceRow;
  onPatch: (id: string, patch: Partial<SourceRow>) => void;
  onRemove?: (id: string) => void;
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-2xl border p-3 transition-all duration-200 ${
        row.enabled ? "border-accent/25 bg-accent-soft/40" : "border-white/8 bg-white/3"
      }`}
    >
      <span
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg transition-all ${
          row.enabled ? "" : "opacity-40 grayscale"
        }`}
        style={{
          background: "linear-gradient(135deg, rgba(99,102,241,.18), rgba(217,70,239,.18))",
          border: "1px solid rgba(255,255,255,.10)",
        }}
      >
        {row.emoji}
      </span>
      <div className="min-w-0 flex-1">
        <div className={`truncate text-small font-semibold ${row.enabled ? "" : "text-muted"}`}>
          {row.name}
        </div>
        <div className="flex items-center gap-1.5 text-tiny text-muted">
          <span className="opacity-60">{row.route}</span>
          <span>·</span>
          <input
            type="number"
            className="w-11 rounded-md border border-white/10 bg-white/5 px-1 py-0.5 text-center text-tiny tabular-nums outline-none focus:border-accent/50"
            value={row.limit}
            onChange={(e) => onPatch(row.id, { limit: Number(e.target.value) || 5 })}
            title="卡片显示条数"
          />
          条
        </div>
      </div>
      <Switch isSelected={row.enabled} onValueChange={(v) => onPatch(row.id, { enabled: v })} />
      {onRemove && (
        <button
          className="rounded-lg px-2 py-1 text-small text-muted hover:bg-danger-soft hover:text-danger"
          onClick={() => onRemove(row.id)}
          title="删除该自定义源"
        >
          <X className="h-4 w-4" weight="bold" />
        </button>
      )}
    </div>
  );
}
