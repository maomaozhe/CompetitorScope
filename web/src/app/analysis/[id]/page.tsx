"use client";

import { use, useEffect } from "react";
import { useSSE } from "@/hooks/useSSE";
import { AgentFlow } from "@/components/AgentFlow";
import { ReportView } from "@/components/ReportView";
import { EvidencePanel } from "@/components/EvidencePanel";
import { HITLDialog } from "@/components/HITLDialog";
import { useAnalysis } from "@/contexts/AnalysisContext";
import Link from "next/link";

export default function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { runId, setRunId } = useAnalysis();

  // Sync runId into context via useEffect (not render phase)
  useEffect(() => {
    if (runId !== id) {
      setRunId(id);
    }
  }, [id, runId, setRunId]);

  // Connect SSE
  useSSE(runId === id ? id : null);

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <Link
        href={`/observability/${encodeURIComponent(id)}`}
        className="fixed right-4 top-3 z-30 rounded-lg border border-zinc-700 bg-zinc-900/90 px-3 py-1.5 text-xs text-zinc-400 shadow-lg backdrop-blur hover:text-zinc-200"
      >
        查看执行详情
      </Link>
      {/* Left sidebar — Agent Flow */}
      <aside className="w-72 shrink-0 border-r border-zinc-800/60 bg-zinc-900/30">
        <AgentFlow />
      </aside>

      {/* Center — Report */}
      <main className="flex-1 overflow-hidden">
        <ReportView />
      </main>

      {/* Right — Evidence Panel */}
      <aside className="w-80 shrink-0 border-l border-zinc-800/60 bg-zinc-900/30">
        <EvidencePanel />
      </aside>

      {/* HITL Dialogs */}
      <HITLDialog />
    </div>
  );
}
