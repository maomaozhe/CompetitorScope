"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAnalysis } from "@/contexts/AnalysisContext";
import { api } from "@/lib/api";

type HitlRequest = {
  type: string;
  interrupt_id: string;
  message: string;
  run_id?: string;
  candidates?: Array<{ name: string; website?: string }>;
  outline?: string;
  dimensions?: string[];
  low_source_competitors?: Array<{ competitor_id: string; name: string; source_count: number }>;
  options?: Record<string, unknown>;
  default_response?: Record<string, unknown>;
  timeout_seconds?: number;
};

export function useSSE(runId: string | null) {
  const {
    updateAgent,
    appendReport,
    setComplete,
    setPendingHitl,
    setEvidenceItems,
    isComplete,
  } = useAnalysis();
  const esRef = useRef<EventSource | null>(null);

  const refreshPendingHitl = useCallback(() => {
    if (!runId) return;
    api.getPendingHitl(runId)
      .then((data) => {
        setPendingHitl(data.pending && data.payload ? data.payload as HitlRequest : null);
      })
      .catch(() => {});
  }, [runId, setPendingHitl]);

  const refreshAnalysisStatus = useCallback(() => {
    if (!runId) return;
    api.getAnalysis(runId)
      .then(async (data) => {
        data.agents?.forEach((agent) => {
          updateAgent(agent.id, { status: agent.status, message: agent.message });
        });
        if (data.done && !isComplete) {
          try {
            const evidence = await api.getEvidence(runId);
            setEvidenceItems(evidence.evidence);
          } catch {}
          setComplete();
          updateAgent("writer", { status: "complete", message: "已完成" });
        }
      })
      .catch(() => {});
  }, [runId, updateAgent, isComplete, setComplete, setEvidenceItems]);

  const connect = useCallback(() => {
    if (!runId || esRef.current) return;
    refreshPendingHitl();

    const es = new EventSource(`/api/v1/analysis/${runId}/stream`);
    esRef.current = es;

    // Use addEventListener (not on<event> properties) for named SSE events.
    // EventSource dispatches `event: agent_start` to addEventListener("agent_start", ...).
    es.addEventListener("agent_start", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        updateAgent(data.agent, { status: "running", message: data.message });
      } catch {}
    });

    es.addEventListener("agent_complete", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        updateAgent(data.agent, { status: "complete", message: "已完成" });
      } catch {}
    });

    es.addEventListener("report_chunk", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        appendReport(data.content);
      } catch {}
    });

    es.addEventListener("hitl_request", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as HitlRequest;
        setPendingHitl(data);
      } catch {}
    });

    es.addEventListener("hitl_resumed", () => {
      refreshPendingHitl();
    });

    es.addEventListener("hitl_timeout", () => {
      refreshPendingHitl();
    });

    es.addEventListener("complete", async () => {
      try {
        const data = await api.getEvidence(runId);
        setEvidenceItems(data.evidence);
      } catch {}
      setComplete();
      updateAgent("writer", { status: "complete", message: "已完成" });
    });

    es.addEventListener("error", (e: Event) => {
      if ("data" in e && typeof e.data === "string") {
        try {
          const data = JSON.parse(e.data);
          updateAgent(data.agent || "planner", { status: "error", message: data.message || "运行失败" });
        } catch {}
      }
    });
  }, [
    runId,
    updateAgent,
    appendReport,
    setComplete,
    setPendingHitl,
    setEvidenceItems,
    refreshPendingHitl,
  ]);

  useEffect(() => {
    connect();
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, [connect]);

  useEffect(() => {
    if (!runId) return;
    refreshPendingHitl();
    refreshAnalysisStatus();
    const interval = window.setInterval(() => {
      if (isComplete) return;
      refreshPendingHitl();
      refreshAnalysisStatus();
    }, 2500);
    return () => window.clearInterval(interval);
  }, [runId, isComplete, refreshPendingHitl, refreshAnalysisStatus]);
}
