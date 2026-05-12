"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAnalysis } from "@/contexts/AnalysisContext";

type SSEEvent =
  | { type: "agent_start"; agent: string; avatar: string; message: string }
  | { type: "agent_complete"; agent: string }
  | { type: "report_chunk"; content: string }
  | { type: "complete" }
  | { type: "error"; message: string };

export function useSSE(runId: string | null) {
  const { updateAgent, appendReport, setComplete } = useAnalysis();
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
        }
      } catch {}
    };
  }, [runId, updateAgent, appendReport, setComplete]);

  useEffect(() => {
    connect();
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, [connect]);
}