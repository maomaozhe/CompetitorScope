"use client";

import { useState } from "react";
import { useAnalysis } from "@/contexts/AnalysisContext";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (response: Record<string, unknown>) => void;
  message: string;
}

interface CompetitorConfirmDialogProps extends DialogProps {
  candidates: Array<{ name: string; website?: string }>;
}

function CompetitorConfirmDialog({
  open,
  onClose,
  onSubmit,
  message,
  candidates,
}: CompetitorConfirmDialogProps) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(candidates.slice(0, 5).map((item) => item.name)),
  );
  const [customUrl, setCustomUrl] = useState("");

  if (!open) return null;

  const toggle = (name: string) => {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setSelected(next);
  };

  const handleSubmit = () => {
    onSubmit({
      competitors: [
        ...candidates.filter((c) => selected.has(c.name)),
        ...customUrl
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
          .map((url) => ({ name: url, website: url })),
      ],
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-zinc-700/50 bg-zinc-900/95 p-6 shadow-2xl">
        <h3 className="text-lg font-semibold text-zinc-100">确认竞品</h3>
        <p className="mt-2 text-sm text-zinc-400">{message}</p>

        <div className="mt-4 space-y-2">
          {candidates.map(c => (
            <label key={c.name} className="flex items-center gap-3 rounded-lg border border-zinc-700/50 bg-zinc-800/50 px-4 py-3 cursor-pointer hover:bg-zinc-800 transition-colors">
              <input
                type="checkbox"
                checked={selected.has(c.name)}
                onChange={() => toggle(c.name)}
                className="h-4 w-4 rounded border-zinc-600 bg-zinc-700 text-indigo-500 focus:ring-indigo-500/30"
              />
              <div>
                <p className="text-sm font-medium text-zinc-200">{c.name}</p>
                <p className="text-xs text-zinc-500">{c.website}</p>
              </div>
            </label>
          ))}
        </div>

        <div className="mt-4">
          <label className="text-xs text-zinc-500">补充竞品（逗号分隔 URL）</label>
          <input
            type="text"
            value={customUrl}
            onChange={e => setCustomUrl(e.target.value)}
            placeholder="https://example.com, ..."
            className="mt-1 w-full rounded-lg border border-zinc-700/50 bg-zinc-800/50 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
          />
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-zinc-700/50 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors">取消</button>
          <button onClick={handleSubmit} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-600 transition-colors">确认</button>
        </div>
      </div>
    </div>
  );
}

function OutlineConfirmDialog({ open, onClose, onSubmit, message }: DialogProps) {
  const [level, setLevel] = useState<"brief" | "standard" | "detailed">("standard");

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-zinc-700/50 bg-zinc-900/95 p-6 shadow-2xl">
        <h3 className="text-lg font-semibold text-zinc-100">确认报告大纲</h3>
        <p className="mt-2 text-sm text-zinc-400">{message}</p>

        <div className="mt-4 space-y-2">
          {(["brief", "standard", "detailed"] as const).map(l => (
            <button
              key={l}
              onClick={() => setLevel(l)}
              className={cn(
                "w-full rounded-lg border px-4 py-3 text-left text-sm transition-colors",
                level === l ? "border-indigo-500/50 bg-indigo-500/10 text-zinc-100" : "border-zinc-700/50 bg-zinc-800/50 text-zinc-300 hover:bg-zinc-800"
              )}
            >
              <p className="font-medium capitalize">{l === "brief" ? "简略" : l === "standard" ? "标准" : "详尽"}</p>
              <p className="text-xs text-zinc-500 mt-0.5">
                {l === "brief" ? "1000字以内，核心对比" : l === "standard" ? "2000字，覆盖4维度" : "4000字+，深度分析"}
              </p>
            </button>
          ))}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-zinc-700/50 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors">取消</button>
          <button onClick={() => onSubmit({ outline_level: level })} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-600 transition-colors">确认</button>
        </div>
      </div>
    </div>
  );
}

interface CollectorSupplementDialogProps extends DialogProps {
  lowSourceCompetitors: Array<{ competitor_id: string; name: string; source_count: number }>;
}

function CollectorSupplementDialog({
  open,
  onSubmit,
  message,
  lowSourceCompetitors,
}: CollectorSupplementDialogProps) {
  const [urlsByCompetitor, setUrlsByCompetitor] = useState<Record<string, string>>({});

  if (!open) return null;

  const supplementUrls = Object.fromEntries(
    Object.entries(urlsByCompetitor)
      .map(([competitorId, value]) => [
        competitorId,
        value.split(",").map((item) => item.trim()).filter(Boolean),
      ])
      .filter(([, urls]) => Array.isArray(urls) && urls.length > 0),
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-zinc-700/50 bg-zinc-900/95 p-6 shadow-2xl">
        <h3 className="text-lg font-semibold text-zinc-100">补充数据来源</h3>
        <p className="mt-2 text-sm text-zinc-400">{message}</p>

        <div className="mt-4 space-y-3">
          {lowSourceCompetitors.map((competitor) => (
            <div key={competitor.competitor_id} className="rounded-lg border border-zinc-700/50 bg-zinc-800/40 p-3">
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="font-medium text-zinc-300">{competitor.name}</span>
                <span className="text-zinc-500">{competitor.source_count} 条来源</span>
              </div>
              <input
                type="text"
                value={urlsByCompetitor[competitor.competitor_id] || ""}
                onChange={(e) => setUrlsByCompetitor((prev) => ({
                  ...prev,
                  [competitor.competitor_id]: e.target.value,
                }))}
                placeholder="补充 URL（可多个，逗号分隔）"
                className="w-full rounded-lg border border-zinc-700/50 bg-zinc-900/50 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
              />
            </div>
          ))}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button onClick={() => onSubmit({ action: "continue" })} className="rounded-lg border border-zinc-700/50 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors">继续</button>
          <button onClick={() => onSubmit({ action: "skip" })} className="rounded-lg border border-zinc-700/50 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors">跳过</button>
          <button onClick={() => onSubmit({ action: "supplement", supplement_urls: supplementUrls })} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-600 transition-colors">确认补充</button>
        </div>
      </div>
    </div>
  );
}

export function HITLDialog() {
  const { runId, pendingHitl, setPendingHitl } = useAnalysis();
  const [localHitl, setLocalHitl] = useState<typeof pendingHitl>(null);
  const [error, setError] = useState("");

  if (!pendingHitl && !localHitl) return null;

  const hitl = pendingHitl || localHitl;
  if (!hitl) return null;

  const handleClose = () => {
    setError("");
    setPendingHitl(null);
  };
  const handleSubmit = async (response: Record<string, unknown>) => {
    if (!runId) {
      setError("Run ID missing");
      return;
    }
    setLocalHitl(hitl);
    setError("");
    try {
      await api.submitHitl(runId, response);
      setPendingHitl(null);
      setLocalHitl(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
      setLocalHitl(null);
    }
  };
  const candidates = hitl.candidates || [];
  const lowSourceCompetitors = hitl.low_source_competitors || [];

  return (
    <>
      {hitl.type === "competitor_confirm" && (
        <CompetitorConfirmDialog
          open={true}
          onClose={handleClose}
          onSubmit={handleSubmit}
          message={hitl.message || "请确认要分析的竞品"}
          candidates={candidates}
        />
      )}
      {hitl.type === "outline_confirm" && (
        <OutlineConfirmDialog
          open={true}
          onClose={handleClose}
          onSubmit={handleSubmit}
          message={hitl.message || "请选择报告详略程度"}
        />
      )}
      {hitl.type === "collector_supplement" && (
        <CollectorSupplementDialog
          open={true}
          onClose={handleClose}
          onSubmit={handleSubmit}
          message={hitl.message || "部分竞品数据较少，请补充来源"}
          lowSourceCompetitors={lowSourceCompetitors}
        />
      )}
      {error && (
        <div className="fixed bottom-4 left-1/2 z-[60] -translate-x-1/2 rounded-lg border border-red-500/30 bg-red-950/90 px-4 py-2 text-sm text-red-200 shadow-xl">
          {error}
        </div>
      )}
    </>
  );
}
