import { useCallback, useEffect, useState } from "react";
import { FloppyDisk, X } from "@phosphor-icons/react";
import { Button, Card, CardBody, Chip, Input, PageHeader, Select, Switch } from "../ui";
import { api } from "../api";
import type { ConfigResponse, PushTargetItem, ScheduleItem } from "../types";

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

export default function PushPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [schedules, setSchedules] = useState<ScheduleItem[]>([]);
  const [targets, setTargets] = useState<PushTargetItem[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const cfg = await api.getConfig();
    setConfig(cfg);
    setSchedules(structuredClone(cfg.config.schedules));
    setTargets(structuredClone(cfg.config.push_targets));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      await api.updateConfig({ schedules, push_targets: targets });
      setMsg("✅ 推送配置已保存，定时任务即时生效");
      await load();
    } catch (e) {
      setMsg(`❌ ${e instanceof Error ? e.message : "保存失败"}`);
    } finally {
      setBusy(false);
    }
  };

  if (!config) return <div className="p-8 text-center text-muted">加载中…</div>;

  const themes = Object.values(config.config.themes);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="推送管理"
        desc="在群/私聊发送「订阅热点」即可加入列表 · 定时任务保存后即时生效"
        actions={
          <Button size="sm" isLoading={busy} onPress={save}>
            <FloppyDisk className="h-4 w-4" /> 保存推送配置
          </Button>
        }
      />
      {msg && <div className="glass rounded-2xl px-4 py-2.5 text-small text-muted">{msg}</div>}

      <Card className="glass glass-hover">
        <CardBody className="p-4">
          <div className="mb-2 font-semibold">推送目标（{targets.length}）</div>
          {targets.length === 0 ? (
            <div className="rounded-xl bg-surface-secondary/60 p-6 text-center text-small text-muted">
              暂无推送目标。在机器人所在的群/私聊发送「订阅热点」，或通过 API 添加。
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {targets.map((t, i) => (
                <div key={t.id} className="flex items-center gap-3 rounded-xl bg-surface-secondary/60 p-3">
                  <Switch
                    size="sm"
                    isSelected={t.enabled}
                    onValueChange={(v) =>
                      setTargets((prev) => prev.map((x, j) => (j === i ? { ...x, enabled: v } : x)))
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-small font-medium">🎯 {t.label}</div>
                    <div className="text-tiny text-muted">
                      添加于 {t.added_at || "未知时间"} · 平台 {String(t.target?.platform ?? "unknown")}
                    </div>
                  </div>
                  {t.enabled && <Chip color="success">启用</Chip>}
                  <Button
                    size="sm"
                    variant="light"
                    color="danger"
                    isIconOnly
                    onPress={() => setTargets((prev) => prev.filter((_, j) => j !== i))}
                  >
                    <X className="h-4 w-4" weight="bold" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      <Card className="glass glass-hover">
        <CardBody className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="font-semibold">定时任务（{schedules.length}）</span>
            <Button
              size="sm"
              variant="flat"
              onPress={() =>
                setSchedules((prev) => [
                  ...prev,
                  {
                    id: `sched_${Date.now().toString(36)}`,
                    label: "新时段",
                    hour: 12,
                    minute: 0,
                    weekdays: [0, 1, 2, 3, 4, 5, 6],
                    theme_id: null,
                    enabled: true,
                  },
                ])
              }
            >
              ＋ 添加时段
            </Button>
          </div>
          <div className="flex flex-col gap-2">
            {schedules.map((s, i) => (
              <div key={s.id} className="flex flex-wrap items-end gap-3 rounded-xl bg-surface-secondary/60 p-3">
                <Switch
                  size="sm"
                  isSelected={s.enabled}
                  onValueChange={(v) =>
                    setSchedules((prev) => prev.map((x, j) => (j === i ? { ...x, enabled: v } : x)))
                  }
                />
                <Input
                  size="sm"
                  className="w-28"
                  label="名称"
                  value={s.label}
                  onValueChange={(v) =>
                    setSchedules((prev) => prev.map((x, j) => (j === i ? { ...x, label: v } : x)))
                  }
                />
                <div className="flex items-end gap-1">
                  <Input
                    size="sm"
                    className="w-16"
                    type="number"
                    label="时"
                    value={String(s.hour)}
                    onValueChange={(v) =>
                      setSchedules((prev) =>
                        prev.map((x, j) =>
                          j === i ? { ...x, hour: Math.max(0, Math.min(23, Number(v) || 0)) } : x,
                        ),
                      )
                    }
                  />
                  <span className="pb-2">:</span>
                  <Input
                    size="sm"
                    className="w-16"
                    type="number"
                    label="分"
                    value={String(s.minute)}
                    onValueChange={(v) =>
                      setSchedules((prev) =>
                        prev.map((x, j) =>
                          j === i ? { ...x, minute: Math.max(0, Math.min(59, Number(v) || 0)) } : x,
                        ),
                      )
                    }
                  />
                </div>
                <Select
                  className="w-40"
                  label="主题"
                  value={s.theme_id ?? ""}
                  onChange={(v) =>
                    setSchedules((prev) =>
                      prev.map((x, j) => (j === i ? { ...x, theme_id: v === "" ? null : v } : x)),
                    )
                  }
                  options={[
                    { value: "", label: "跟随激活主题" },
                    ...themes.map((tt) => ({ value: tt.id, label: tt.name })),
                  ]}
                />
                <div className="flex flex-wrap items-center gap-1 pb-1">
                  {WEEKDAYS.map((wd, di) => {
                    const day = di; // 0=周一
                    const on = s.weekdays.includes(day);
                    return (
                      <button
                        key={wd}
                        className={`h-7 w-7 rounded-full text-tiny transition-colors ${
                          on ? "bg-accent text-accent-foreground" : "bg-surface-secondary text-muted"
                        }`}
                        onClick={() =>
                          setSchedules((prev) =>
                            prev.map((x, j) => {
                              if (j !== i) return x;
                              const days = on
                                ? x.weekdays.filter((d) => d !== day)
                                : [...x.weekdays, day];
                              return { ...x, weekdays: days.sort() };
                            }),
                          )
                        }
                      >
                        {wd}
                      </button>
                    );
                  })}
                </div>
                <Button
                  size="sm"
                  variant="light"
                  color="danger"
                  isIconOnly
                  onPress={() => setSchedules((prev) => prev.filter((_, j) => j !== i))}
                >
                  <X className="h-4 w-4" weight="bold" />
                </Button>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
