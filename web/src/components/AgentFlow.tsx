"use client";

import { useAnalysis, AgentInfo } from "@/contexts/AnalysisContext";
import { cn } from "@/lib/utils";

const STATUS_CONFIG = {
  idle: { color: "text-zinc-500", bg: "bg-zinc-800/40", dot: "bg-zinc-600", label: "等待" },
  running: { color: "text-indigo-400", bg: "bg-indigo-500/10", dot: "bg-indigo-500 animate-pulse", label: "运行中" },
  complete: { color: "text-emerald-400", bg: "bg-emerald-500/10", dot: "bg-emerald-500", label: "完成" },
  error: { color: "text-red-400", bg: "bg-red-500/10", dot: "bg-red-500", label: "错误" },
} as const;

function AgentCard({ agent, index }: { agent: AgentInfo; index: number }) {
  const cfg = STATUS_CONFIG[agent.status];

  return (
    <div className="relative">
      {/* Timeline connector */}
      {index < 4 && (
        <div className="absolute left-[18px] top-full h-6 w-px bg-gradient-to-b from-zinc-700 to-transparent z-10" />
      )}

      <div
        className={cn(
          "flex items-center gap-3.5 rounded-xl border px-4 py-3.5 transition-all duration-300",
          agent.status === "running" && "border-indigo-500/40 bg-indigo-500/5 shadow-lg shadow-indigo-500/10",
          agent.status === "complete" && "border-emerald-500/30 bg-emerald-500/5",
          agent.status === "idle" && "border-zinc-800/60 bg-zinc-900/40",
          agent.status === "error" && "border-red-500/40 bg-red-500/5",
        )}
      >
        {/* Emoji Avatar */}
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-lg backdrop-blur-sm transition-all duration-300",
            agent.status === "running" && "bg-indigo-500/20 ring-2 ring-indigo-500/40 animate-bounce-subtle",
            agent.status === "complete" && "bg-emerald-500/20",
            agent.status === "idle" && "bg-zinc-800/60",
            agent.status === "error" && "bg-red-500/20",
          )}
        >
          {agent.emoji}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <span className={cn("text-sm font-medium", cfg.color)}>{agent.name}</span>
            <span className={cn("text-xs", cfg.color)}>{cfg.label}</span>
          </div>
          <p className="mt-0.5 truncate text-xs text-zinc-500">{agent.message}</p>
        </div>

        {/* Status dot */}
        <div className={cn("h-2 w-2 rounded-full shrink-0", cfg.dot)} />
      </div>
    </div>
  );
}

export function AgentFlow() {
  const { agents } = useAnalysis();
  const completedCount = agents.filter((a) => a.status === "complete").length;
  const progress = (completedCount / agents.length) * 100;

  return (
    <div className="flex h-full flex-col gap-5 p-5">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-200">Agent 工作流</h2>
          <span className="text-xs text-zinc-500">{completedCount}/5 完成</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-700"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Agent Cards */}
      <div className="relative space-y-3">
        {agents.map((agent, i) => (
          <AgentCard key={agent.id} agent={agent} index={i} />
        ))}
      </div>

      {/* Legend */}
      <div className="mt-auto space-y-1.5 rounded-xl border border-zinc-800/60 bg-zinc-900/40 p-3">
        <p className="text-xs text-zinc-600 font-medium mb-2">图例</p>
        {[
          { emoji: "🧭", name: "Planner", desc: "解析需求·发现竞品" },
          { emoji: "🕷️", name: "Collector", desc: "并发采集多源数据" },
          { emoji: "📊", name: "Analyst", desc: "结构化提取分析" },
          { emoji: "🆚", name: "Comparator", desc: "横向对比洞察" },
          { emoji: "✍️", name: "Writer", desc: "生成Markdown报告" },
        ].map((item) => (
          <div key={item.name} className="flex items-center gap-2.5 text-xs text-zinc-500">
            <span>{item.emoji}</span>
            <span className="font-medium text-zinc-400">{item.name}</span>
            <span>·</span>
            <span>{item.desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}