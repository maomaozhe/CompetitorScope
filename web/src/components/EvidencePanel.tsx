"use client";

import { useAnalysis } from "@/contexts/AnalysisContext";
import { cn } from "@/lib/utils";

export function EvidencePanel() {
  const { selectedEvidence, evidenceItems, selectEvidence, isComplete } = useAnalysis();

  if (!isComplete && !selectedEvidence) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-zinc-500">报告生成后将显示证据链</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-200">证据链</h2>
      </div>

      {/* Evidence list */}
      <div className="flex-1 overflow-y-auto p-4">
        {evidenceItems.length === 0 ? (
          <p className="text-sm text-zinc-500">暂无证据数据</p>
        ) : selectedEvidence ? (
          <div className="space-y-4">
            {/* Selected evidence detail */}
            <div className="space-y-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs text-amber-400/80 font-medium">{selectedEvidence.competitor_id}</p>
                  <p className="mt-1 text-xs text-zinc-400">{selectedEvidence.extracted_fact}</p>
                </div>
                <button
                  onClick={() => selectEvidence(null)}
                  className="shrink-0 text-zinc-500 hover:text-zinc-300 text-lg"
                >
                  ×
                </button>
              </div>
              <div className="rounded-lg border border-zinc-700/50 bg-zinc-800/30 p-3">
                <p className="text-xs text-zinc-400 leading-relaxed italic">"{selectedEvidence.excerpt}"</p>
              </div>
              <div className="flex items-center justify-between">
                <a
                  href={selectedEvidence.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-indigo-400/80 hover:text-indigo-300 hover:underline truncate max-w-[180px]"
                >
                  {selectedEvidence.source_url}
                </a>
                <span className={cn(
                  "ml-2 rounded px-1.5 py-0.5 text-xs",
                  selectedEvidence.confidence > 0.8 ? "bg-emerald-500/10 text-emerald-400" :
                  selectedEvidence.confidence > 0.5 ? "bg-amber-500/10 text-amber-400" :
                  "bg-red-500/10 text-red-400"
                )}>
                  {selectedEvidence.confidence.toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        ) : (
          /* Evidence list */
          <div className="space-y-2">
            {evidenceItems.map(item => (
              <button
                key={item.evidence_id}
                onClick={() => selectEvidence(item)}
                className="w-full rounded-lg border border-zinc-700/40 bg-zinc-800/30 p-3 text-left transition-colors hover:border-zinc-600/50 hover:bg-zinc-800/50"
              >
                <div className="flex items-start gap-2">
                  <span className="shrink-0 mt-0.5 text-xs text-amber-400/60">[{item.evidence_id.slice(0, 4)}]</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-zinc-300 line-clamp-2">{item.extracted_fact}</p>
                    <p className="mt-1 text-xs text-zinc-500 truncate">{item.source_url}</p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
