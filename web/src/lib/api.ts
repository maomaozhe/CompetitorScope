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
  ): Promise<{ success: boolean }> {
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
  ): Promise<{ pending: Record<string, unknown> | null }> {
    const res = await fetch(`${BASE}/analysis/${runId}/hitl/pending`);
    if (!res.ok) throw new Error(`getPendingHitl failed: ${res.status}`);
    return res.json();
  },
};
