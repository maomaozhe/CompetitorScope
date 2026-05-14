"use client";

import { useState } from "react";
import { AgentOutput } from "@/contexts/AnalysisContext";
import { cn } from "@/lib/utils";

const AGENT_LABELS: Record<string, string> = {
  planner: "Planner",
  collector: "Collector",
  analyst: "Analyst",
  comparator: "Comparator",
  writer: "Writer",
};

const TYPE_LABELS: Record<string, string> = {
  competitors: "竞品",
  outline: "计划",
  sources: "来源",
  profile: "分析",
  comparison: "对比",
  report: "报告",
  status: "状态",
};

function OutputItem({ output }: { output: AgentOutput }) {
  const [open, setOpen] = useState(true);
  const hasDetail = Boolean(output.detail?.trim());
  const time = new Date(output.created_at * 1000).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <article className="rounded-xl border border-zinc-800/70 bg-zinc-900/45">
      <button
        type="button"
        onClick={() => hasDetail && setOpen((value) => !value)}
        className="w-full px-4 py-3 text-left"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-indigo-500/10 px-2 py-0.5 text-xs font-medium text-indigo-300">
            {AGENT_LABELS[output.agent] || output.agent}
          </span>
          <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
            {TYPE_LABELS[output.artifact_type] || output.artifact_type}
          </span>
          <span className="ml-auto text-xs text-zinc-600">{time}</span>
        </div>
        <h3 className="mt-2 text-sm font-semibold text-zinc-200">{output.title}</h3>
        <p className="mt-1 text-sm leading-6 text-zinc-400">{output.summary}</p>
      </button>
      {open && hasDetail && (
        <pre className="max-h-72 overflow-auto border-t border-zinc-800/70 px-4 py-3 text-xs leading-6 text-zinc-400 whitespace-pre-wrap">
          {output.detail}
        </pre>
      )}
    </article>
  );
}

export function AgentOutputStream({
  outputs,
  className,
}: {
  outputs: AgentOutput[];
  className?: string;
}) {
  const orderedOutputs = outputs.slice().reverse();

  return (
    <section className={cn("flex h-full min-h-0 flex-col", className)}>
      <div className="border-b border-zinc-800 px-5 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-zinc-100">Agent 实时输出</h2>
            <p className="mt-1 text-xs text-zinc-500">展示各 agent 的阶段产物、来源摘要和人工确认上下文</p>
          </div>
          <span className="rounded-full border border-zinc-800 px-2.5 py-1 text-xs text-zinc-500">
            {outputs.length} 条
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {orderedOutputs.length > 0 ? (
          <div className="space-y-3">
            {orderedOutputs.map((output) => (
              <OutputItem key={output.id} output={output} />
            ))}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="text-4xl">🔍</div>
              <p className="mt-3 text-sm text-zinc-500">等待 agent 输出...</p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
