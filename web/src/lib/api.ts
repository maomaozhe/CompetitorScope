/** API client for CompetitorScope backend. */

export interface CreateAnalysisBody {
  query: string;
  competitors?: string[];
  dimensions?: string[];
  hitl_mode?: "auto" | "interactive";
}

export interface CreateAnalysisResponse {
  run_id: string;
  status: string;
  stream_url: string;
}

export interface AnalysisStatus {
  run_id: string;
  stage: string;
  status: string;
  done: boolean;
  pending_hitl: boolean;
  agents?: Array<{
    id: string;
    status: "idle" | "running" | "complete" | "error";
    message: string;
  }>;
  agent_outputs?: Array<{
    id: string;
    agent: string;
    node: string;
    title: string;
    summary: string;
    detail: string;
    artifact_type: string;
    created_at: number;
  }>;
}

export interface ReportResponse {
  report_id: string;
  title: string;
  markdown: string;
  bibliography: Array<{ url: string; title: string }>;
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

export interface TraceRun {
  run_id: string;
  request: { query?: string; hitl_mode?: string; competitors?: unknown[]; dimensions?: string[] };
  versions: Record<string, unknown>;
  status: string;
  started_at: number;
  finished_at?: number | null;
  token_total: number;
  estimated_cost?: number | null;
  replayable: boolean;
  degraded: boolean;
  pinned: boolean;
  error_message?: string | null;
}

export interface TraceSpan {
  span_id: string;
  parent_span_id?: string | null;
  name: string;
  kind: string;
  agent?: string | null;
  node?: string | null;
  status: string;
  started_at: number;
  finished_at?: number | null;
  attributes: Record<string, unknown>;
}

export interface TraceEvent {
  event_id: string;
  run_id: string;
  seq: number;
  span_id?: string | null;
  parent_span_id?: string | null;
  type: string;
  occurred_at: number;
  agent?: string | null;
  node?: string | null;
  status?: string | null;
  payload: Record<string, unknown>;
  artifact_refs: string[];
}

export interface TraceSnapshot {
  snapshot_id: string;
  boundary: string;
  sequence: number;
  state: Record<string, unknown>;
  changed_keys: string[];
  artifact_refs: string[];
  created_at: number;
}

const BASE = "/api/v1";

export const api = {
  async createAnalysis(body: CreateAnalysisBody): Promise<CreateAnalysisResponse> {
    const res = await fetch(`${BASE}/analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`createAnalysis failed: ${res.status}`);
    return res.json();
  },

  async getAnalysis(runId: string): Promise<AnalysisStatus> {
    const res = await fetch(`${BASE}/analysis/${runId}`);
    if (!res.ok) throw new Error(`getAnalysis failed: ${res.status}`);
    return res.json();
  },

  async deleteAnalysis(runId: string): Promise<{ run_id: string; status: string }> {
    const res = await fetch(`${BASE}/analysis/${runId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`deleteAnalysis failed: ${res.status}`);
    return res.json();
  },

  async getReport(runId: string): Promise<ReportResponse> {
    const res = await fetch(`${BASE}/reports/${runId}`);
    if (!res.ok) throw new Error(`getReport failed: ${res.status}`);
    return res.json();
  },

  async getReportMarkdown(runId: string): Promise<string> {
    const res = await fetch(`${BASE}/reports/${runId}/markdown`);
    if (!res.ok) throw new Error(`getReportMarkdown failed: ${res.status}`);
    return res.text();
  },

  async getEvidence(runId: string): Promise<{ evidence: EvidenceItem[] }> {
    const res = await fetch(`${BASE}/reports/${runId}/evidence`);
    if (!res.ok) throw new Error(`getEvidence failed: ${res.status}`);
    return res.json();
  },

  async submitHitl(
    runId: string,
    response: Record<string, unknown>,
  ): Promise<{ run_id: string; status: string }> {
    const res = await fetch(`${BASE}/analysis/${runId}/hitl`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ response }),
    });
    if (!res.ok) throw new Error(`submitHitl failed: ${res.status}`);
    return res.json();
  },

  async getPendingHitl(
    runId: string,
  ): Promise<{ pending: boolean; payload?: Record<string, unknown>; created_at?: number }> {
    const res = await fetch(`${BASE}/analysis/${runId}/hitl/pending`);
    if (!res.ok) throw new Error(`getPendingHitl failed: ${res.status}`);
    return res.json();
  },

  async getTraceRuns(): Promise<{ runs: TraceRun[] }> {
    const res = await fetch(`${BASE}/observability/runs`, { cache: "no-store" });
    if (!res.ok) throw new Error(`getTraceRuns failed: ${res.status}`);
    return res.json();
  },

  async getTraceRun(runId: string): Promise<{ run: TraceRun; spans: TraceSpan[] }> {
    const res = await fetch(`${BASE}/observability/runs/${runId}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`getTraceRun failed: ${res.status}`);
    return res.json();
  },

  async getTraceEvents(runId: string, afterSeq = 0): Promise<{ events: TraceEvent[] }> {
    const res = await fetch(
      `${BASE}/observability/runs/${runId}/events?after_seq=${afterSeq}&limit=5000`,
      { cache: "no-store" },
    );
    if (!res.ok) throw new Error(`getTraceEvents failed: ${res.status}`);
    return res.json();
  },

  async getTraceSnapshots(runId: string): Promise<{ snapshots: TraceSnapshot[] }> {
    const res = await fetch(`${BASE}/observability/runs/${runId}/snapshots`, { cache: "no-store" });
    if (!res.ok) throw new Error(`getTraceSnapshots failed: ${res.status}`);
    return res.json();
  },

  async getArtifact(artifactId: string): Promise<Record<string, unknown>> {
    const res = await fetch(`${BASE}/observability/artifacts/${artifactId}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`getArtifact failed: ${res.status}`);
    return res.json();
  },

  async createEvalCase(runId: string, label = "baseline"): Promise<{ case_id: string }> {
    const res = await fetch(`${BASE}/observability/runs/${runId}/eval-cases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label }),
    });
    if (!res.ok) throw new Error(`createEvalCase failed: ${res.status}`);
    return res.json();
  },

  async createEvalExecution(
    caseId: string,
    body: {
      variant_label: string;
      model_overrides?: Record<string, string>;
      parameter_overrides?: Record<string, unknown>;
      prompt_overrides?: Record<string, string>;
      live_tools?: boolean;
    },
  ): Promise<{ execution_id: string; status: string }> {
    const res = await fetch(`${BASE}/observability/eval-cases/${caseId}/executions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`createEvalExecution failed: ${res.status}`);
    return res.json();
  },

  async compareEvalCase(caseId: string): Promise<Record<string, unknown>> {
    const res = await fetch(`${BASE}/observability/eval-cases/${caseId}/compare`, { cache: "no-store" });
    if (!res.ok) throw new Error(`compareEvalCase failed: ${res.status}`);
    return res.json();
  },
};
