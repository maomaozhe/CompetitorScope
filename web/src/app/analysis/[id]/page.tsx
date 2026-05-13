"use client";

import { use, useEffect } from "react";
import { useSSE } from "@/hooks/useSSE";
import { AgentFlow } from "@/components/AgentFlow";
import { ReportView } from "@/components/ReportView";
import { EvidencePanel } from "@/components/EvidencePanel";
import { HITLDialog } from "@/components/HITLDialog";
import { useAnalysis } from "@/contexts/AnalysisContext";

export default function AnalysisPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { runId, setRunId } = useAnalysis();

  // Sync runId into context via useEffect (not render phase)
  useEffect(() => {
    if (!runId) {
      setRunId(id);
    }
  }, [id, runId, setRunId]);

  // Connect SSE
  useSSE(id);

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
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