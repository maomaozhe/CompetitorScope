"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { api, TraceEvent, TraceRun, TraceSnapshot, TraceSpan } from "@/lib/api";

type Detail = { run: TraceRun; spans: TraceSpan[] };

const EVENT_COLORS: Record<string, string> = {
  "run.started": "bg-sky-400",
  "run.finished": "bg-emerald-400",
  "run.failed": "bg-red-400",
  "span.started": "bg-indigo-400",
  "span.finished": "bg-emerald-400",
  "decision.recorded": "bg-amber-400",
  "state.snapshot_created": "bg-purple-400",
  "llm.requested": "bg-cyan-400",
  "llm.completed": "bg-cyan-300",
  "tool.requested": "bg-pink-400",
  "tool.completed": "bg-pink-300",
};

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="overflow-auto whitespace-pre-wrap break-all rounded-lg bg-black/30 p-3 text-xs leading-5 text-zinc-400">{JSON.stringify(value, null, 2)}</pre>;
}

export default function ObservabilityDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [snapshots, setSnapshots] = useState<TraceSnapshot[]>([]);
  const [error, setError] = useState("");
  const [replayIndex, setReplayIndex] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [artifact, setArtifact] = useState<Record<string, unknown> | null>(null);
  const [caseId, setCaseId] = useState("");
  const [variantLabel, setVariantLabel] = useState("candidate-1");
  const [plannerModel, setPlannerModel] = useState("");
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextDetail, nextEvents, nextSnapshots] = await Promise.all([
        api.getTraceRun(runId), api.getTraceEvents(runId), api.getTraceSnapshots(runId),
      ]);
      setDetail(nextDetail);
      setEvents(nextEvents.events);
      setSnapshots(nextSnapshots.snapshots);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载失败");
    }
  }, [runId]);

  useEffect(() => {
    const initial = window.setTimeout(load, 0);
    const timer = window.setInterval(load, 2000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [load]);

  useEffect(() => {
    if (!playing || replayIndex === null) return;
    if (replayIndex >= events.length) return;
    const current = events[Math.max(0, replayIndex - 1)];
    const next = events[replayIndex];
    const delay = current ? Math.min(1500, Math.max(100, (next.occurred_at - current.occurred_at) * 1000 / speed)) : 100;
    const timer = window.setTimeout(() => setReplayIndex((value) => (value ?? 0) + 1), delay);
    return () => window.clearTimeout(timer);
  }, [playing, replayIndex, events, speed]);

  useEffect(() => {
    if (!caseId) return;
    const refresh = async () => setComparison(await api.compareEvalCase(caseId));
    const initial = window.setTimeout(refresh, 0);
    const timer = window.setInterval(refresh, 2500);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [caseId]);

  const visibleEvents = replayIndex === null ? events : events.slice(0, replayIndex);
  const decisions = visibleEvents.filter((event) => event.type === "decision.recorded");
  const metrics = useMemo(() => {
    const run = detail?.run;
    const observedEnd = run?.finished_at ?? events.at(-1)?.occurred_at ?? run?.started_at ?? 0;
    const duration = run ? (observedEnd - run.started_at) * 1000 : 0;
    return { duration, tokens: run?.token_total ?? 0, errors: events.filter((event) => event.type.endsWith("failed")).length, tools: events.filter((event) => event.type === "tool.completed").length };
  }, [detail, events]);

  const openArtifact = async (artifactId: string) => setArtifact(await api.getArtifact(artifactId));
  const createCase = async () => setCaseId((await api.createEvalCase(runId)).case_id);
  const runCandidate = async () => {
    if (!caseId) return;
    await api.createEvalExecution(caseId, {
      variant_label: variantLabel,
      model_overrides: plannerModel ? { planner: plannerModel } : {},
    });
    setComparison(await api.compareEvalCase(caseId));
  };

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="sticky top-0 z-20 border-b border-zinc-800 bg-zinc-950/90 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-5">
          <div className="min-w-0">
            <Link href="/observability" className="text-xs text-zinc-500 hover:text-zinc-300">← 运行观测</Link>
            <h1 className="mt-1 truncate text-lg font-semibold">{detail?.run.request.query || runId}</h1>
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="rounded-full border border-zinc-800 px-2 py-1">{detail?.run.status || "loading"}</span>
            <span className="font-mono">{runId}</span>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1600px] p-6">
        {error && <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>}
        <section className="mb-6 grid grid-cols-4 gap-3">
          {[['端到端耗时', `${(metrics.duration / 1000).toFixed(1)}s`], ['Tokens', metrics.tokens || '—'], ['工具调用', metrics.tools], ['错误事件', metrics.errors]].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"><p className="text-xs text-zinc-600">{label}</p><p className="mt-2 text-xl font-semibold text-zinc-200">{value}</p></div>
          ))}
        </section>

        <div className="grid grid-cols-[minmax(0,1.65fr)_minmax(320px,0.75fr)] gap-5">
          <div className="space-y-5">
            <section className="rounded-2xl border border-zinc-800 bg-zinc-900/35">
              <div className="flex flex-wrap items-center gap-3 border-b border-zinc-800 px-5 py-4">
                <div><h2 className="font-semibold">执行时间线</h2><p className="mt-1 text-xs text-zinc-600">{visibleEvents.length} / {events.length} events · {detail?.spans.length || 0} spans</p></div>
                <div className="ml-auto flex items-center gap-2">
                  <button onClick={() => { setReplayIndex(replayIndex === null ? 0 : null); setPlaying(false); }} className="rounded border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-400">{replayIndex === null ? "进入回放" : "返回实时"}</button>
                  {replayIndex !== null && <>
                    <button onClick={() => setPlaying((value) => !value)} className="rounded bg-indigo-500/20 px-2.5 py-1.5 text-xs text-indigo-300">{playing ? "暂停" : "播放"}</button>
                    <select value={speed} onChange={(event) => setSpeed(Number(event.target.value))} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs"><option value={1}>1×</option><option value={2}>2×</option><option value={5}>5×</option></select>
                    <input aria-label="回放进度" type="range" min={0} max={events.length} value={replayIndex} onChange={(event) => setReplayIndex(Number(event.target.value))} />
                  </>}
                </div>
              </div>
              <div className="max-h-[680px] overflow-y-auto p-4">
                {visibleEvents.map((event) => (
                  <article key={event.event_id} className="relative ml-2 border-l border-zinc-800 pb-5 pl-6 last:pb-0">
                    <span className={`absolute -left-1.5 top-1 h-3 w-3 rounded-full ring-4 ring-zinc-950 ${EVENT_COLORS[event.type] || "bg-zinc-600"}`} />
                    <div className="flex items-center gap-2"><span className="font-mono text-xs text-zinc-300">{event.type}</span><span className="text-xs text-zinc-700">#{event.seq}</span><span className="ml-auto text-xs text-zinc-600">{new Date(event.occurred_at * 1000).toLocaleTimeString("zh-CN")}</span></div>
                    {(event.agent || event.node) && <p className="mt-1 text-xs text-zinc-500">{event.agent} {event.node && `· ${event.node}`}</p>}
                    {Object.keys(event.payload).length > 0 && <details className="mt-2"><summary className="cursor-pointer text-xs text-zinc-600 hover:text-zinc-400">查看 payload</summary><div className="mt-2"><JsonBlock value={event.payload} /></div></details>}
                    {event.artifact_refs.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{event.artifact_refs.map((id) => <button key={id} onClick={() => openArtifact(id)} className="rounded bg-purple-500/10 px-2 py-1 font-mono text-[10px] text-purple-300">artifact {id.slice(0, 8)}</button>)}</div>}
                  </article>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-zinc-800 bg-zinc-900/35">
              <div className="border-b border-zinc-800 px-5 py-4"><h2 className="font-semibold">Baseline / Candidate</h2><p className="mt-1 text-xs text-zinc-600">固定外部工具结果，对比模型、Prompt 或参数变体</p></div>
              <div className="grid gap-3 p-5 md:grid-cols-3">
                <input value={variantLabel} onChange={(event) => setVariantLabel(event.target.value)} placeholder="Variant label" className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
                <input value={plannerModel} onChange={(event) => setPlannerModel(event.target.value)} placeholder="Planner model（可选）" className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
                {!caseId ? <button onClick={createCase} className="rounded-lg bg-indigo-500/20 px-3 py-2 text-sm text-indigo-300">固定为 Eval Case</button> : <button onClick={runCandidate} className="rounded-lg bg-emerald-500/20 px-3 py-2 text-sm text-emerald-300">运行 Candidate</button>}
              </div>
              {caseId && <div className="border-t border-zinc-800 p-5"><p className="mb-2 font-mono text-xs text-zinc-600">case {caseId}</p>{comparison ? <JsonBlock value={comparison} /> : <p className="text-xs text-zinc-600">等待比较结果…</p>}</div>}
            </section>
          </div>

          <aside className="space-y-5">
            <section className="rounded-2xl border border-zinc-800 bg-zinc-900/35"><div className="border-b border-zinc-800 px-5 py-4"><h2 className="font-semibold">决策记录</h2></div><div className="max-h-[420px] space-y-3 overflow-y-auto p-4">{decisions.length ? decisions.map((event) => <div key={event.event_id} className="rounded-xl border border-amber-500/15 bg-amber-500/5 p-3"><p className="text-xs font-medium text-amber-300">{String(event.payload.decision_point || "decision")}</p><p className="mt-2 text-xs leading-5 text-zinc-400">{String(event.payload.reason || "未提供理由摘要")}</p><details className="mt-2"><summary className="cursor-pointer text-xs text-zinc-600">候选与选择</summary><div className="mt-2"><JsonBlock value={{ candidates: event.payload.candidates, selected: event.payload.selected }} /></div></details></div>) : <p className="py-8 text-center text-xs text-zinc-600">暂无结构化决策</p>}</div></section>
            <section className="rounded-2xl border border-zinc-800 bg-zinc-900/35"><div className="border-b border-zinc-800 px-5 py-4"><h2 className="font-semibold">快照</h2></div><div className="max-h-[420px] space-y-2 overflow-y-auto p-4">{snapshots.map((snapshot) => <details key={snapshot.snapshot_id} className="rounded-lg border border-zinc-800 p-3"><summary className="cursor-pointer text-xs text-zinc-300">{snapshot.sequence}. {snapshot.boundary}</summary><p className="mt-2 text-[11px] text-zinc-600">changed: {snapshot.changed_keys.join(", ") || "none"}</p><div className="mt-2"><JsonBlock value={snapshot.state} /></div></details>)}</div></section>
          </aside>
        </div>
      </div>

      {artifact && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-8" onClick={() => setArtifact(null)}><div className="max-h-[85vh] w-full max-w-4xl overflow-auto rounded-2xl border border-zinc-700 bg-zinc-900 p-5" onClick={(event) => event.stopPropagation()}><div className="mb-4 flex items-center justify-between"><h2 className="font-semibold">Artifact</h2><button onClick={() => setArtifact(null)} className="text-zinc-500">关闭</button></div><JsonBlock value={artifact} /></div></div>}
    </main>
  );
}
