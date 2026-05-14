"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from "react";

export type AgentStatus = "idle" | "running" | "complete" | "error";
export type HitlType = "competitor_confirm" | "outline_confirm" | "collector_supplement" | "comparison_plan_confirm" | null;

export interface AgentInfo {
  id: string;
  name: string;
  emoji: string;
  status: AgentStatus;
  message: string;
}

export interface HitlRequest {
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
}

export interface AgentOutput {
  id: string;
  agent: string;
  node: string;
  title: string;
  summary: string;
  detail: string;
  artifact_type: string;
  created_at: number;
}

export interface EvidenceItem {
  evidence_id: string;
  source_id: string;
  source_url: string;
  excerpt: string;
  extracted_fact: string;
  fact_type: string;
  confidence: number;
  competitor_id: string;
}

interface AnalysisContextType {
  runId: string | null;
  agents: AgentInfo[];
  reportContent: string;
  agentOutputs: AgentOutput[];
  isComplete: boolean;
  pendingHitl: HitlRequest | null;
  evidenceItems: EvidenceItem[];
  selectedEvidence: EvidenceItem | null;
  setRunId: (id: string | null) => void;
  updateAgent: (id: string, update: Partial<AgentInfo>) => void;
  appendAgentOutput: (output: AgentOutput) => void;
  appendReport: (chunk: string) => void;
  setComplete: () => void;
  setPendingHitl: (req: HitlRequest | null) => void;
  setEvidenceItems: (items: EvidenceItem[]) => void;
  selectEvidence: (item: EvidenceItem | null) => void;
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
  const [agentOutputs, setAgentOutputs] = useState<AgentOutput[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [pendingHitl, setPendingHitlState] = useState<HitlRequest | null>(null);
  const [evidenceItems, setEvidenceItemsState] = useState<EvidenceItem[]>([]);
  const [selectedEvidence, setSelectedEvidenceState] = useState<EvidenceItem | null>(null);

  const setRunId = useCallback((id: string | null) => {
    setRunIdState(id);
    setReportContent("");
    setAgentOutputs([]);
    setIsComplete(false);
    setPendingHitlState(null);
    setEvidenceItemsState([]);
    setSelectedEvidenceState(null);
    if (id) {
      setAgents(DEFAULT_AGENTS.map(a => ({ ...a, status: "idle" as AgentStatus, message: "等待启动" })));
    }
  }, []);

  const updateAgent = useCallback((id: string, update: Partial<AgentInfo>) => {
    setAgents(prev =>
      prev.map(a => (a.id === id ? { ...a, ...update } : a))
    );
  }, []);

  const appendAgentOutput = useCallback((output: AgentOutput) => {
    setAgentOutputs(prev => {
      if (prev.some(item => item.id === output.id)) return prev;
      return [...prev, output].slice(-80);
    });
  }, []);

  const appendReport = useCallback((chunk: string) => {
    setReportContent(prev => prev + chunk);
  }, []);

  const setComplete = useCallback(() => setIsComplete(true), []);

  const setPendingHitl = useCallback((req: HitlRequest | null) => {
    setPendingHitlState(req);
  }, []);

  const setEvidenceItems = useCallback((items: EvidenceItem[]) => {
    setEvidenceItemsState(items);
  }, []);

  const selectEvidence = useCallback((item: EvidenceItem | null) => {
    setSelectedEvidenceState(item);
  }, []);

  const reset = useCallback(() => {
    setRunIdState(null);
    setReportContent("");
    setAgentOutputs([]);
    setIsComplete(false);
    setPendingHitlState(null);
    setEvidenceItemsState([]);
    setSelectedEvidenceState(null);
    setAgents(DEFAULT_AGENTS.map(a => ({ ...a, status: "idle" as AgentStatus, message: "等待启动" })));
  }, []);

  return (
    <AnalysisContext.Provider value={{
      runId, agents, reportContent, agentOutputs, isComplete,
      pendingHitl, evidenceItems, selectedEvidence,
      setRunId, updateAgent, appendAgentOutput, appendReport, setComplete,
      setPendingHitl, setEvidenceItems, selectEvidence, reset
    }}>
      {children}
    </AnalysisContext.Provider>
  );
}

export function useAnalysis() {
  const ctx = useContext(AnalysisContext);
  if (!ctx) throw new Error("useAnalysis must be used within AnalysisProvider");
  return ctx;
}
