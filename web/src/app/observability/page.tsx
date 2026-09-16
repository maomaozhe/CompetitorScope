"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, TraceRun } from "@/lib/api";

const STATUS_STYLE: Record<string, string> = {
  running: "border-indigo-500/30 bg-indigo-500/10 text-indigo-300",
  completed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  failed: "border-red-500/30 bg-red-500/10 text-red-300",
  cancelled: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  interrupted: "border-orange-500/30 bg-orange-500/10 text-orange-300",
};

function duration(run: TraceRun) {
  if (!run.finished_at) return "运行中";
  const end = run.finished_at;
  return `${Math.max(0, end - run.started_at).toFixed(1)}s`;
}

export default function ObservabilityPage() {
  const [runs, setRuns] = useState<TraceRun[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setRuns((await api.getTraceRuns()).runs);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(load, 0);
    const timer = window.setInterval(load, 2500);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [load]);

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-8 text-zinc-100">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8 flex items-end justify-between gap-4">
          <div>
            <Link href="/" className="text-xs text-zinc-500 hover:text-zinc-300">← CompetitorScope</Link>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight">运行观测</h1>
            <p className="mt-2 text-sm text-zinc-500">持久化 Trace、决策、快照与评测运行</p>
          </div>
          <button onClick={load} className="rounded-lg border border-zinc-800 px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-900">
            刷新
          </button>
        </header>

        {error && <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>}
        <section className="overflow-hidden rounded-2xl border border-zinc-800/80 bg-zinc-900/35">
          <div className="grid grid-cols-[minmax(0,2fr)_120px_100px_100px_110px] gap-4 border-b border-zinc-800 px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-600">
            <span>Run / Query</span><span>状态</span><span>耗时</span><span>Tokens</span><span>开始时间</span>
          </div>
          {runs.length ? runs.map((run) => (
            <Link
              key={run.run_id}
              href={`/observability/${encodeURIComponent(run.run_id)}`}
              className="grid grid-cols-[minmax(0,2fr)_120px_100px_100px_110px] gap-4 border-b border-zinc-800/60 px-5 py-4 transition-colors last:border-0 hover:bg-zinc-800/35"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-zinc-200">{run.request.query || "Untitled run"}</div>
                <div className="mt-1 truncate font-mono text-xs text-zinc-600">{run.run_id}</div>
              </div>
              <div><span className={`rounded-full border px-2 py-1 text-xs ${STATUS_STYLE[run.status] || "border-zinc-700 text-zinc-400"}`}>{run.status}</span></div>
              <span className="text-sm text-zinc-400">{duration(run)}</span>
              <span className="text-sm text-zinc-400">{run.token_total || "—"}</span>
              <span className="text-xs text-zinc-500">{new Date(run.started_at * 1000).toLocaleTimeString("zh-CN")}</span>
            </Link>
          )) : (
            <div className="px-5 py-16 text-center text-sm text-zinc-600">还没有持久化运行</div>
          )}
        </section>
      </div>
    </main>
  );
}
