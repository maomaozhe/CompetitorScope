"use client";

import { use } from "react";
import { useSSE } from "@/hooks/useSSE";
import { AgentFlow } from "@/components/AgentFlow";
import { ReportView } from "@/components/ReportView";
import { useAnalysis } from "@/contexts/AnalysisContext";

export default function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { runId, setRunId } = useAnalysis();

  // Sync runId into context on mount
  if (!runId) {
    setRunId(id);
  }

  // Connect SSE
  useSSE(id);

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      {/* Left sidebar — Agent Flow */}
      <aside className="w-72 shrink-0 border-r border-zinc-800/60 bg-zinc-990/30">
        <AgentFlow />
      </aside>

      {/* Main content — Report */}
      <main className="flex-1 overflow-hidden">
        <ReportView />
      </main>
    </div>
  );
}