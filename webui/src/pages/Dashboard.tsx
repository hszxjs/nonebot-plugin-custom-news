import { useCallback, useEffect, useState } from "react";
import {
  Alarm,
  ArrowsClockwise,
  BookOpen,
  Broadcast,
  Image as ImageIcon,
  LinkSimple,
  MusicNote,
  Palette,
  PaperPlaneTilt,
  Play,
  Target,
  X,
} from "@phosphor-icons/react";
import { Button, Card, CardBody, Chip, PageHeader, Spinner, Tip } from "../ui";
import { api } from "../api";

interface MusicPreviewSong {
  song: string;
  artists: string;
  album: string;
  cover: string;
  audio: string;
  jump: string;
  comments_text: string;
}
interface MusicPreviewPlatform {
  platform: string;
  label: string;
  chart_text?: string;
  songs?: MusicPreviewSong[];
  error?: string;
}
import type { ConfigResponse } from "../types";

interface StatusItem {
  last_ok: string | null;
  items: number;
  last_error: string | null;
}

export default function DashboardPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [latest, setLatest] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<string, StatusItem>>({});
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [analysisImage, setAnalysisImage] = useState<string | null>(null);
  const [analysisModal, setAnalysisModal] = useState(false);
  const [musicPreview, setMusicPreview] = useState<MusicPreviewPlatform[] | null>(null);
  const [musicModal, setMusicModal] = useState(false);
  const [musicTab, setMusicTab] = useState("netease");

  const load = useCallback(async () => {
    const [cfg, st] = await Promise.all([api.getConfig(), api.sourcesStatus()]);
    setConfig(cfg);
    setStatus(st.status as never);
    api.getLatest().then((r) => setLatest(r.image)).catch(() => setLatest(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const withBusy = async (key: string, fn: () => Promise<string>) => {
    setBusy(key);
    setMsg("");
    try {
      setMsg(await fn());
      await load();
    } catch (e) {
      setMsg(`❌ ${e instanceof Error ? e.message : "操作失败"}`);
    } finally {
      setBusy("");
    }
  };

  if (!config) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner label="加载中…" />
      </div>
    );
  }

  const cfg = config.config;
  const enabledSources = Object.values(cfg.sources).filter((s) => s.enabled).length;
  const enabledTargets = cfg.push_targets.filter((t) => t.enabled).length;
  const enabledSchedules = cfg.schedules.filter((s) => s.enabled);
  const activeTheme = cfg.themes[cfg.active_theme_id];

  const stats = [
    { label: "启用数据源", value: `${enabledSources}`, sub: `/ ${Object.keys(cfg.sources).length + cfg.custom_sources.length} 个源`, icon: <Broadcast className="h-6 w-6 text-accent" weight="duotone" /> },
    { label: "推送目标", value: `${enabledTargets}`, sub: enabledTargets ? "定时推送中" : "发送「订阅热点」添加", icon: <Target className="h-6 w-6 text-accent" weight="duotone" /> },
    { label: "定时任务", value: `${enabledSchedules.length}`, sub: enabledSchedules.map((s) => `${String(s.hour).padStart(2, "0")}:${String(s.minute).padStart(2, "0")}`).join(" / ") || "未配置", icon: <Alarm className="h-6 w-6 text-accent" weight="duotone" /> },
    { label: "当前主题", value: activeTheme?.name ?? "—", sub: `共 ${Object.keys(cfg.themes).length} 套`, icon: <Palette className="h-6 w-6 text-accent" weight="duotone" /> },
  ];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="总览"
        desc="全网热点聚合 · 主题日报渲染 · 定时推送"
        actions={
          <div className="flex flex-wrap gap-2">
            <Tip content="用当前激活主题立即渲染一张日报图">
              <Button
                size="sm"
                isLoading={busy === "render"}
                onPress={() =>
                  withBusy("render", async () => {
                    const r = await api.renderPreview({});
                    setLatest(r.image);
                    return `渲染成功（${r.cards.length} 张卡片${r.failed.length ? `，失败：${r.failed.join("、")}` : ""}）`;
                  })
                }
              >
                <ImageIcon className="h-4 w-4" /> 立即渲染
              </Button>
            </Tip>
            <Tip content="向全部启用的推送目标发送日报">
              <Button
                size="sm"
                variant="flat"
                isLoading={busy === "push"}
                onPress={() =>
                  withBusy("push", async () => {
                    const r = await api.pushNow();
                    return r.message;
                  })
                }
              >
                <PaperPlaneTilt className="h-4 w-4" /> 立即推送
              </Button>
            </Tip>
            <Tip content="生成新歌榜聊天记录预览（实际发送用 QQ 命令「新歌榜」）">
              <Button
                size="sm"
                variant="flat"
                isLoading={busy === "music"}
                onPress={() =>
                  withBusy("music", async () => {
                    const r = await api.musicPreview();
                    setMusicPreview(r.platforms);
                    setMusicTab("netease");
                    setMusicModal(true);
                    return "新歌榜预览已生成";
                  })
                }
              >
                <MusicNote className="h-4 w-4" /> 新歌榜
              </Button>
            </Tip>
            <Tip content="抓取新闻原文，用大模型生成聊天记录风格的深度解读">
              <Button
                size="sm"
                variant="flat"
                isLoading={busy === "analyze"}
                onPress={() =>
                  withBusy("analyze", async () => {
                    const r = await api.llmAnalyze({});
                    setAnalysisImage(r.image);
                    setAnalysisModal(true);
                    const ok = r.items.filter((x) => x.ok).length;
                    return `深读完成（${ok}/${r.items.length} 条成功解析）`;
                  })
                }
              >
                <BookOpen className="h-4 w-4" /> 热点解析
              </Button>
            </Tip>
            <Button
              size="sm"
              variant="flat"
              isLoading={busy === "refresh"}
              onPress={() =>
                withBusy("refresh", async () => {
                  const r = await api.refreshSources();
                  return r.ok
                    ? `数据已刷新（${r.cards.length} 个源成功${r.failed.length ? `，失败：${r.failed.join("、")}` : ""}）`
                    : "全部源抓取失败";
                })
              }
            >
              <ArrowsClockwise className="h-4 w-4" /> 刷新数据
            </Button>
          </div>
        }
      />

      {msg && (
        <div className="glass rounded-2xl px-4 py-2.5 text-small text-muted">{msg}</div>
      )}

      {/* 数据源大面积失败提示：区分实例不可达 / 上游路由报错，只统计启用源 */}
      {config && (() => {
        const enabledIds = new Set(
          Object.entries(cfg.sources).filter(([, v]) => v.enabled).map(([k]) => k),
        );
        const entries = Object.entries(status).filter(([id]) => enabledIds.has(id));
        const failedEntries = entries.filter(([, st]) => st.last_error);
        if (entries.length < 5 || failedEntries.length / entries.length < 0.5) return null;
        const connectFails = failedEntries.filter(([, st]) =>
          String(st.last_error).includes("ConnectError"),
        ).length;
        const instanceDown = connectFails >= failedEntries.length * 0.8;
        return (
          <div className="rounded-2xl border border-warning/30 bg-warning-soft px-4 py-3 text-small">
            <div className="font-semibold text-warning">
              {failedEntries.length}/{entries.length} 个启用数据源抓取失败
            </div>
            <div className="mt-1 text-muted">
              {instanceDown ? (
                <>
                  疑似 DailyHotApi 实例不可达，建议自部署后在本页「数据源」更换地址：
                  <code className="ml-1 rounded bg-white/10 px-1.5 py-0.5 text-tiny">
                    docker run --restart always -d -p 6688:6688 imsyy/dailyhot-api:latest
                  </code>
                </>
              ) : (
                <>
                  多为对应平台反爬/接口变更导致的上游路由报错（悬停状态列可看具体原因），
                  与你的部署无关：可更新 DailyHotApi 镜像重试，或在「数据源」页停用长期失败的源。
                  <div className="mt-0.5 text-tiny opacity-80">
                    失败源：{failedEntries.map(([id]) => config.builtin_sources.find((b) => b.id === id)?.name ?? id).join("、")}
                  </div>
                </>
              )}
            </div>
          </div>
        );
      })()}

      {/* 统计卡 */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label} className="glass glass-hover">
            <CardBody className="flex items-center gap-3.5 p-4">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-accent-soft bg-accent-soft">
                {s.icon}
              </span>
              <div className="min-w-0">
                <div className="tnum truncate text-2xl font-bold">{s.value}</div>
                <div className="truncate text-tiny text-muted">
                  {s.label} · {s.sub}
                </div>
              </div>
            </CardBody>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="glass">
          <CardBody className="p-4">
            <div className="mb-3 flex items-center gap-2 font-semibold">
              <span className="h-4 w-1.5 rounded-full bg-accent" />
              最近渲染结果
            </div>
            {latest ? (
              <img
                src={`data:image/png;base64,${latest}`}
                alt="最近渲染的日报图"
                className="max-h-[560px] w-full rounded-xl object-contain"
              />
            ) : (
              <div className="flex h-48 items-center justify-center rounded-xl border border-dashed border-white/12 text-small text-muted">
                暂无渲染记录，点击「立即渲染」生成第一张日报图
              </div>
            )}
          </CardBody>
        </Card>

        <Card className="glass">
          <CardBody className="p-4">
            <div className="mb-3 flex items-center gap-2 font-semibold">
              <span className="h-4 w-1.5 rounded-full bg-accent" />
              数据源状态
            </div>
            <div className="max-h-[560px] overflow-y-auto pr-1">
              <table className="w-full text-small">
                <thead>
                  <tr className="border-b border-white/8 text-left text-tiny text-muted">
                    <th className="py-1.5">源</th>
                    <th>最近成功</th>
                    <th>条数</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(status).map(([id, st]) => {
                    const builtin = config.builtin_sources.find((b) => b.id === id);
                    const enabled = cfg.sources[id]?.enabled ?? true;
                    return (
                      <tr
                        key={id}
                        className={`border-b border-white/4 ${enabled ? "" : "opacity-40"}`}
                      >
                        <td className="py-1.5">
                          {builtin?.emoji ?? "📌"} {builtin?.name ?? id}
                        </td>
                        <td className="text-muted">
                          {st.last_ok ? st.last_ok.replace("T", " ") : "—"}
                        </td>
                        <td className="tabular-nums">{st.items || "—"}</td>
                        <td>
                          {st.last_error ? (
                            <Tip content={st.last_error}>
                              <Chip color="danger">异常</Chip>
                            </Tip>
                          ) : st.last_ok ? (
                            <Chip color="success">正常</Chip>
                          ) : (
                            <Chip>未抓取</Chip>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      </div>

      {musicModal && musicPreview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4 backdrop-blur-md"
          onClick={() => setMusicModal(false)}
        >
          <div
            className="glass flex max-h-[88vh] w-full max-w-lg flex-col rounded-2xl shadow-2xl"
            style={{ background: "linear-gradient(180deg,#161a26,#11141d)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-white/8 px-5 py-3">
              <span className="font-semibold">新歌榜 · 聊天记录预览（示意）</span>
              <button className="text-muted hover:text-foreground" onClick={() => setMusicModal(false)}>
                <X className="h-4 w-4" weight="bold" />
              </button>
            </div>
            <div className="flex gap-1 border-b border-white/8 px-4 py-2">
              {musicPreview.map((p) => (
                <button
                  key={p.platform}
                  onClick={() => setMusicTab(p.platform)}
                  className={`rounded-lg px-3 py-1 text-small ${musicTab === p.platform ? "bg-accent-soft font-semibold text-accent" : "text-muted"}`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {musicPreview
                .filter((p) => p.platform === musicTab)
                .map((p) =>
                  p.error ? (
                    <div key={p.platform} className="rounded-xl bg-danger-soft p-3 text-small text-danger">
                      {p.error}
                    </div>
                  ) : (
                    <div key={p.platform} className="space-y-3">
                      <div className="whitespace-pre-line rounded-2xl rounded-bl-md bg-white/6 p-3 text-small leading-relaxed">
                        {p.chart_text}
                      </div>
                      {(p.songs || []).map((s) => (
                        <div key={s.song} className="space-y-2">
                          <div className="flex items-center gap-3 rounded-2xl rounded-bl-md bg-white/6 p-2.5">
                            <img src={s.cover} alt="" className="h-12 w-12 rounded-xl object-cover" />
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-small font-semibold">{s.song}</div>
                              <div className="truncate text-tiny text-muted">{s.artists}</div>
                            </div>
                            <span className="text-muted">
                              {s.audio.includes(".mp3") ? (
                                <Play className="h-5 w-5 text-success" weight="fill" />
                              ) : (
                                <LinkSimple className="h-5 w-5" />
                              )}
                            </span>
                          </div>
                          <div className="ml-6 whitespace-pre-line rounded-2xl rounded-bl-md bg-white/4 p-2.5 text-tiny leading-relaxed text-muted">
                            {s.comments_text}
                          </div>
                        </div>
                      ))}
                    </div>
                  ),
                )}
            </div>
            <div className="border-t border-white/8 px-5 py-2.5 text-tiny text-muted">
              实际效果为 QQ 合并转发聊天记录（QQ 中发送「新歌榜」体验，卡片可点击播放）
            </div>
          </div>
        </div>
      )}

      {analysisModal && analysisImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4 backdrop-blur-md"
          onClick={() => setAnalysisModal(false)}
        >
          <div
            className="glass max-h-[88vh] w-full max-w-3xl overflow-y-auto rounded-2xl p-4 shadow-2xl"
            style={{ background: "linear-gradient(180deg,#161a26,#11141d)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="font-semibold">今日深读（AI 解析）</span>
              <button className="flex items-center gap-1 text-muted hover:text-foreground" onClick={() => setAnalysisModal(false)}>
                <X className="h-4 w-4" weight="bold" /> 关闭
              </button>
            </div>
            <img
              src={`data:image/png;base64,${analysisImage}`}
              alt="今日深读"
              className="w-full rounded-xl"
            />
          </div>
        </div>
      )}
    </div>
  );
}
