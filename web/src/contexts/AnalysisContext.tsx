"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from "react";

export type AgentStatus = "idle" | "running" | "complete" | "error";

export interface AgentInfo {
  id: string;
  name: string;
  emoji: string;
  status: AgentStatus;
  message: string;
}

interface AnalysisContextType {
  runId: string | null;
  agents: AgentInfo[];
  reportContent: string;
  isComplete: boolean;
  setRunId: (id: string | null) => void;
  updateAgent: (id: string, update: Partial<AgentInfo>) => void;
  appendReport: (chunk: string) => void;
  setComplete: () => void;
  reset: () => void;
}

const DEFAULT_AGENTS: AgentInfo[] = [
  { id: "planner", name: "Planner", emoji: "🧭", status: "idle", message: "等待启动" },
  { id: "collector", name: "Collector", emoji: "🕷️", status: "idle", message: "等待启动" },
  { id: "analyst", name: "Analyst", emoji: "📊", status: "idle", message: "等待启动" },
  { id: "comparator", name: "Comparator", emoji: "🆚", status: "idle", message: "等待启动" },
  { id: "writer", name: "Writer", emoji: "✍️", status: "idle", message: "等待启动" },
];

const AnalysisContext = createContext<AnalysisContextType | null>(null);

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [runId, setRunIdState] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>(DEFAULT_AGENTS);
  const [reportContent, setReportContent] = useState("");
  const [isComplete, setIsComplete] = useState(false);

  const setRunId = useCallback((id: string | null) => {
    setRunIdState(id);
    setReportContent("");
    setIsComplete(false);
    if (id) {
      setAgents(DEFAULT_AGENTS.map(a => ({ ...a, status: "idle" as AgentStatus, message: "等待启动" })));
    }
  }, []);

  const updateAgent = useCallback((id: string, update: Partial<AgentInfo>) => {
    setAgents(prev =>
      prev.map(a => (a.id === id ? { ...a, ...update } : a))
    );
  }, []);

  const appendReport = useCallback((chunk: string) => {
    setReportContent(prev => prev + chunk);
  }, []);

  const setComplete = useCallback(() => setIsComplete(true), []);

  const reset = useCallback(() => {
    setRunIdState(null);
    setReportContent("");
    setIsComplete(false);
    setAgents(DEFAULT_AGENTS.map(a => ({ ...a, status: "idle" as AgentStatus, message: "等待启动" })));
  }, []);

  return (
    <AnalysisContext.Provider value={{ runId, agents, reportContent, isComplete, setRunId, updateAgent, appendReport, setComplete, reset }}>
      {children}
    </AnalysisContext.Provider>
  );
}

export function useAnalysis() {
  const ctx = useContext(AnalysisContext);
  if (!ctx) throw new Error("useAnalysis must be used within AnalysisProvider");
  return ctx;
}