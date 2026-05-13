"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAnalysis } from "@/contexts/AnalysisContext";

type HitlRequest = {
  type: string;
  interrupt_id: string;
  message: string;
  options?: Record<string, unknown>;
  default_response?: Record<string, unknown>;
  timeout_seconds?: number;
};

export function useSSE(runId: string | null) {
  const { updateAgent, appendReport, setComplete, setPendingHitl } = useAnalysis();
  const esRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (!runId || esRef.current) return;
    const es = new EventSource(`http://localhost:8000/api/v1/analysis/${runId}/stream`);
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

    es.addEventListener("complete", (e: MessageEvent) => {
      setComplete();
      updateAgent("writer", { status: "complete", message: "已完成" });
    });

    es.addEventListener("error", (e: Event) => {
      // Connection errors are expected when the stream ends
    });
  }, [runId, updateAgent, appendReport, setComplete, setPendingHitl]);

  useEffect(() => {
    connect();
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, [connect]);
}
