"use client";

import { useState, useEffect } from "react";
import { useAnalysis } from "@/contexts/AnalysisContext";
import { api } from "@/lib/api";

function useCountdown(timeoutSeconds: number, createdAt: number) {
  const [remaining, setRemaining] = useState(timeoutSeconds);

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Date.now() / 1000 - createdAt;
      const left = Math.max(0, timeoutSeconds - elapsed);
      setRemaining(Math.floor(left));
      if (left <= 0) clearInterval(interval);
    }, 1000);

    return () => clearInterval(interval);
  }, [timeoutSeconds, createdAt]);

  return remaining;
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

interface DialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (response: Record<string, unknown>) => void;
  message: string;
  remaining?: number;
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
  remaining,
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
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-zinc-100">确认竞品</h3>
          {remaining !== undefined && (
            <div className="text-sm text-zinc-400">
              剩余时间: <span className={remaining <= 10 ? "text-red-400 font-semibold" : "text-zinc-300"}>{formatTime(remaining)}</span>
            </div>
          )}
        </div>
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

interface OutlineConfirmDialogProps extends DialogProps {
  outline: string;
  dimensions: string[];
}

function OutlineConfirmDialog({
  open,
  onClose,
  onSubmit,
  message,
  outline,
  dimensions,
  remaining,
}: OutlineConfirmDialogProps) {
  const [draftOutline, setDraftOutline] = useState(outline);
  const [draftDimensions, setDraftDimensions] = useState(dimensions.join(", "));

  if (!open) return null;

  const handleSubmit = () => {
    onSubmit({
      outline: draftOutline,
      dimensions: draftDimensions
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-zinc-700/50 bg-zinc-900/95 p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-zinc-100">确认报告大纲与分析计划</h3>
          {remaining !== undefined && (
            <div className="text-sm text-zinc-400">
              剩余时间: <span className={remaining <= 10 ? "text-red-400 font-semibold" : "text-zinc-300"}>{formatTime(remaining)}</span>
            </div>
          )}
        </div>
        <p className="mt-2 text-sm text-zinc-400">{message}</p>

        <div className="mt-4 space-y-4">
          <div>
            <label className="text-xs font-medium text-zinc-500">分析维度（逗号分隔）</label>
            <input
              type="text"
              value={draftDimensions}
              onChange={(e) => setDraftDimensions(e.target.value)}
              className="mt-1 w-full rounded-lg border border-zinc-700/50 bg-zinc-800/50 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-zinc-500">报告大纲 / 执行计划</label>
            <textarea
              value={draftOutline}
              onChange={(e) => setDraftOutline(e.target.value)}
              rows={10}
              className="mt-1 w-full resize-none rounded-lg border border-zinc-700/50 bg-zinc-800/50 px-3 py-2 font-mono text-xs leading-5 text-zinc-200 placeholder-zinc-500"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-zinc-700/50 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors">取消</button>
          <button onClick={handleSubmit} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-600 transition-colors">确认</button>
        </div>
      </div>
    </div>
  );
}

interface ComparisonPlanDialogProps extends DialogProps {
  comparisonDimensions: string[];
  focusNotes: string;
}

function ComparisonPlanDialog({
  open,
  onClose,
  onSubmit,
  message,
  comparisonDimensions,
  focusNotes,
  remaining,
}: ComparisonPlanDialogProps) {
  const [draftDimensions, setDraftDimensions] = useState(comparisonDimensions.join(", "));
  const [draftFocus, setDraftFocus] = useState(focusNotes);

  if (!open) return null;

  const handleSubmit = () => {
    onSubmit({
      comparison_dimensions: draftDimensions
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      focus_notes: draftFocus,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-2xl border border-zinc-700/50 bg-zinc-900/95 p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-zinc-100">确认对比重点</h3>
          {remaining !== undefined && (
            <div className="text-sm text-zinc-400">
              剩余时间: <span className={remaining <= 10 ? "text-red-400 font-semibold" : "text-zinc-300"}>{formatTime(remaining)}</span>
            </div>
          )}
        </div>
        <p className="mt-2 text-sm text-zinc-400">{message}</p>

        <div className="mt-4 space-y-4">
          <div>
            <label className="text-xs font-medium text-zinc-500">主要比较维度（逗号分隔）</label>
            <input
              type="text"
              value={draftDimensions}
              onChange={(e) => setDraftDimensions(e.target.value)}
              className="mt-1 w-full rounded-lg border border-zinc-700/50 bg-zinc-800/50 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-zinc-500">比较重点</label>
            <textarea
              value={draftFocus}
              onChange={(e) => setDraftFocus(e.target.value)}
              rows={6}
              className="mt-1 w-full resize-none rounded-lg border border-zinc-700/50 bg-zinc-800/50 px-3 py-2 text-sm leading-6 text-zinc-200 placeholder-zinc-500"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-zinc-700/50 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors">取消</button>
          <button onClick={handleSubmit} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-600 transition-colors">确认</button>
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
  remaining,
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
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-zinc-100">补充数据来源</h3>
          {remaining !== undefined && (
            <div className="text-sm text-zinc-400">
              剩余时间: <span className={remaining <= 10 ? "text-red-400 font-semibold" : "text-zinc-300"}>{formatTime(remaining)}</span>
            </div>
          )}
        </div>
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

  const timeoutSeconds = hitl.timeout_seconds || 120;
  const createdAt = hitl.created_at || Date.now() / 1000;
  const remaining = useCountdown(timeoutSeconds, createdAt);

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
  const outline = hitl.outline || String(hitl.default_response?.outline || "");
  const dimensions = hitl.dimensions || (
    Array.isArray(hitl.default_response?.dimensions) ? hitl.default_response.dimensions as string[] : []
  );
  const comparisonDimensions = hitl.comparison_dimensions || (
    Array.isArray(hitl.default_response?.comparison_dimensions)
      ? hitl.default_response.comparison_dimensions as string[]
      : []
  );
  const focusNotes = hitl.focus_notes || String(hitl.default_response?.focus_notes || "");

  return (
    <>
      {hitl.type === "competitor_confirm" && (
        <CompetitorConfirmDialog
          open={true}
          onClose={handleClose}
          onSubmit={handleSubmit}
          message={hitl.message || "请确认要分析的竞品"}
          candidates={candidates}
          remaining={remaining}
        />
      )}
      {hitl.type === "outline_confirm" && (
        <OutlineConfirmDialog
          open={true}
          onClose={handleClose}
          onSubmit={handleSubmit}
          message={hitl.message || "请选择报告详略程度"}
          outline={outline}
          dimensions={dimensions}
          remaining={remaining}
        />
      )}
      {hitl.type === "comparison_plan_confirm" && (
        <ComparisonPlanDialog
          open={true}
          onClose={handleClose}
          onSubmit={handleSubmit}
          message={hitl.message || "请确认横向对比重点"}
          comparisonDimensions={comparisonDimensions}
          focusNotes={focusNotes}
          remaining={remaining}
        />
      )}
      {hitl.type === "collector_supplement" && (
        <CollectorSupplementDialog
          open={true}
          onClose={handleClose}
          onSubmit={handleSubmit}
          message={hitl.message || "部分竞品数据较少，请补充来源"}
          lowSourceCompetitors={lowSourceCompetitors}
          remaining={remaining}
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
