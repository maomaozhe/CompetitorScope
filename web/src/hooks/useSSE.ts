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
  comparison_dimensions?: string[];
  focus_notes?: string;
  low_source_competitors?: Array<{ competitor_id: string; name: string; source_count: number }>;
  options?: Record<string, unknown>;
  default_response?: Record<string, unknown>;
  timeout_seconds?: number;
  created_at?: number;
};

type AgentOutput = {
  id: string;
  agent: string;
  node: string;
  title: string;
  summary: string;
  detail: string;
  artifact_type: string;
  created_at: number;
};

export function useSSE(runId: string | null) {
  const {
    updateAgent,
    appendAgentOutput,
    appendReport,
    setComplete,
    setPendingHitl,
    setEvidenceItems,
    isComplete,
  } = useAnalysis();
  const esRef = useRef<EventSource | null>(null);
  const isCompleteRef = useRef(isComplete);

  useEffect(() => {
    isCompleteRef.current = isComplete;
    if (isComplete) {
      setPendingHitl(null);
    }
  }, [isComplete, setPendingHitl]);

  const refreshPendingHitl = useCallback(() => {
    if (!runId) return;
    if (isCompleteRef.current) {
      setPendingHitl(null);
      return;
    }
    api.getPendingHitl(runId)
      .then((data) => {
        if (isCompleteRef.current) {
          setPendingHitl(null);
          return;
        }
        setPendingHitl(data.pending && data.payload ? {
          ...(data.payload as HitlRequest),
          created_at: typeof data.created_at === "number"
            ? data.created_at
            : (data.payload as HitlRequest).created_at,
        } : null);
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
        data.agent_outputs?.forEach((output) => {
          appendAgentOutput(output);
        });
        if (data.done) {
          setPendingHitl(null);
        }
        if (data.done && !isCompleteRef.current) {
          try {
            const evidence = await api.getEvidence(runId);
            setEvidenceItems(evidence.evidence);
          } catch {}
          setComplete();
          updateAgent("writer", { status: "complete", message: "已完成" });
        }
      })
      .catch(() => {});
  }, [runId, updateAgent, appendAgentOutput, setComplete, setEvidenceItems, setPendingHitl]);

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

    es.addEventListener("agent_output", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as AgentOutput;
        appendAgentOutput(data);
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
        if (isCompleteRef.current) return;
        const data = JSON.parse(e.data) as HitlRequest;
        // 保留服务端 created_at，只在首次设置（服务端没传时用客户端时间）
        setPendingHitl({
          ...data,
          created_at: data.created_at ?? Date.now() / 1000,
        });
      } catch {}
    });

    es.addEventListener("hitl_resumed", () => {
      refreshPendingHitl();
    });

    es.addEventListener("hitl_timeout", () => {
      refreshPendingHitl();
    });

    es.addEventListener("complete", async () => {
      es.close();
      if (esRef.current === es) {
        esRef.current = null;
      }
      setPendingHitl(null);
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
    appendAgentOutput,
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
    if (isComplete) {
      setPendingHitl(null);
      return;
    }
    refreshPendingHitl();
    refreshAnalysisStatus();
    const interval = window.setInterval(() => {
      if (isCompleteRef.current) {
        setPendingHitl(null);
        return;
      }
      refreshPendingHitl();
      refreshAnalysisStatus();
    }, 2500);
    return () => window.clearInterval(interval);
  }, [runId, isComplete, setPendingHitl, refreshPendingHitl, refreshAnalysisStatus]);
}
