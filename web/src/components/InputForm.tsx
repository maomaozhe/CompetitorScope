"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAnalysis } from "@/contexts/AnalysisContext";
import { cn } from "@/lib/utils";

export function InputForm() {
  const [query, setQuery] = useState("");
  const [competitors, setCompetitors] = useState("");
  const [hitlMode, setHitlMode] = useState<"auto" | "interactive">("interactive");
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();
  const { setRunId } = useAnalysis();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setIsLoading(true);

    try {
      const res = await fetch("/api/v1/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          competitors: competitors ? competitors.split(",").map((c) => c.trim()) : [],
          hitl_mode: hitlMode,
        }),
      });

      if (!res.ok) throw new Error("Failed to create analysis");
      const data = await res.json();
      setRunId(data.run_id);
      router.push(`/analysis/${data.run_id}`);
    } catch (err) {
      console.error(err);
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl space-y-5">
      {/* Query Input */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-zinc-300">需求描述</label>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="例如：帮我分析 AI Coding IDE 赛道的头部玩家，重点了解定价和开发者口碑"
          rows={3}
          className="w-full rounded-xl border border-zinc-700/50 bg-zinc-800/60 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 backdrop-blur-sm transition-colors focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30 resize-none"
        />
      </div>

      {/* Competitors Input */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-zinc-300">
          补充竞品（可选）
          <span className="ml-2 text-xs text-zinc-500">用逗号分隔</span>
        </label>
        <input
          type="text"
          value={competitors}
          onChange={(e) => setCompetitors(e.target.value)}
          placeholder="Cursor, GitHub Copilot, Windsurf..."
          className="w-full rounded-xl border border-zinc-700/50 bg-zinc-800/60 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 backdrop-blur-sm transition-colors focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
        />
      </div>

      {/* HITL Mode Toggle */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-zinc-300">交互模式</label>
        <div className="flex gap-3">
          {(["auto", "interactive"] as const).map(mode => (
            <button
              key={mode}
              type="button"
              onClick={() => setHitlMode(mode)}
              className={cn(
                "flex-1 rounded-xl border px-4 py-3 text-sm font-medium transition-all",
                hitlMode === mode
                  ? "border-indigo-500/50 bg-indigo-500/10 text-indigo-300"
                  : "border-zinc-700/50 bg-zinc-800/40 text-zinc-400 hover:bg-zinc-800/60"
              )}
            >
              {mode === "auto" ? "⚡ 自动模式" : "🧑 交互模式"}
            </button>
          ))}
        </div>
        <p className="text-xs text-zinc-500">
          {hitlMode === "auto" ? "全自动运行，快速得到报告" : "人工确认关键节点，可干预分析方向"}
        </p>
      </div>

      {/* Submit Button */}
      <button
        type="submit"
        disabled={isLoading || !query.trim()}
        className="w-full rounded-xl bg-gradient-to-r from-indigo-500 to-purple-500 px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition-all duration-200 hover:shadow-xl hover:shadow-indigo-500/30 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:shadow-lg"
      >
        {isLoading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            启动分析...
          </span>
        ) : (
          "🚀 启动竞品分析"
        )}
      </button>
    </form>
  );
}
