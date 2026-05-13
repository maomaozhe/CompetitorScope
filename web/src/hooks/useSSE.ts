"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAnalysis } from "@/contexts/AnalysisContext";

type SSEEvent =
  | { type: "agent_start"; agent: string; avatar: string; message: string }
  | { type: "agent_complete"; agent: string }
  | { type: "report_chunk"; content: string }
  | { type: "complete" }
  | { type: "error"; message: string }
  | { type: "hitl_request"; payload: import("@/contexts/AnalysisContext").HitlRequest }
  | { type: "hitl_resumed"; }
  | { type: "hitl_timeout"; response: Record<string, unknown>; interrupt: Record<string, unknown> };

// Import type lazily to avoid circular
type HitlRequest = {
  type: string;
  interrupt_id: string;
  message: string;
  options?: Record<string, unknown>;
  default_response?: Record<string, unknown>;
  timeout_seconds?: number;
};

export function useSSE(runId: string | null) {
  const { updateAgent, appendReport, setComplete, setPendingHitl, setEvidenceItems } = useAnalysis();
  const esRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (!runId || esRef.current) return;
    const es = new EventSource(`/api/v1/analysis/${runId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        switch (event.type) {
          case "agent_start":
            updateAgent(event.agent, { status: "running", message: event.message });
            break;
          case "agent_complete":
            updateAgent(event.agent, { status: "complete", message: "已完成" });
            break;
          case "report_chunk":
            appendReport(event.content);
            break;
          case "complete":
            setComplete();
            updateAgent("writer", { status: "complete", message: "已完成" });
            break;
          case "error":
            updateAgent("planner", { status: "error", message: event.message });
            break;
          case "hitl_request":
            setPendingHitl(event.payload as HitlRequest);
            break;
          case "hitl_resumed":
          case "hitl_timeout":
            setPendingHitl(null);
            break;
        }
      } catch {}
    };
  }, [runId, updateAgent, appendReport, setComplete, setPendingHitl]);

  useEffect(() => {
    connect();
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, [connect]);
}