"use client";

import {
  Children,
  ReactNode,
  useState,
} from "react";
import { useAnalysis } from "@/contexts/AnalysisContext";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function ReferenceAnchors({ children }: { children: ReactNode }) {
  // Highlight [1], [2], etc. as clickable anchors
  const { selectEvidence, evidenceItems } = useAnalysis();

  const renderReferences = (content: string, keyPrefix: string) => {
    const parts = content.split(/(\[\d+\])/g);
    return parts.map((part, i) => {
      if (/^\[\d+\]$/.test(part)) {
        const idx = parseInt(part.slice(1, -1));
        const item = evidenceItems[idx - 1];
        return (
          <button
            key={`${keyPrefix}-${i}`}
            className="mx-0.5 inline-flex items-center gap-0.5 rounded bg-amber-500/10 px-1 py-0.5 text-amber-400/80 hover:bg-amber-500/20 hover:text-amber-300 transition-colors text-xs font-mono"
            onClick={() => item && selectEvidence(item)}
          >
            {part}
          </button>
        );
      }
      return <span key={`${keyPrefix}-${i}`}>{part}</span>;
    });
  };

  const renderText = (content: string, keyPrefix: string) => {
    const parts = content.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      const match = part.match(/^\*\*([^*]+)\*\*$/);
      if (!match) {
        return (
          <span key={`${keyPrefix}-${i}`}>
            {renderReferences(part, `${keyPrefix}-${i}`)}
          </span>
        );
      }
      return (
        <strong key={`${keyPrefix}-${i}`} className="text-zinc-200 font-semibold">
          {renderReferences(match[1], `${keyPrefix}-${i}-strong`)}
        </strong>
      );
    });
  };

  const renderNode = (node: ReactNode, keyPrefix: string): ReactNode => {
    if (typeof node === "string" || typeof node === "number") {
      return renderText(String(node), keyPrefix);
    }
    return node;
  };

  return (
    <>
      {Children.toArray(children).map((child, i) => renderNode(child, `ref-${i}`))}
    </>
  );
}

export function ReportView() {
  const { reportContent, isComplete } = useAnalysis();
  const [activeTab, setActiveTab] = useState<"report" | "sources">("report");

  if (!reportContent && !isComplete) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center space-y-3">
          <div className="text-4xl">🔍</div>
          <p className="text-sm text-zinc-500">报告生成中，请稍候...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-zinc-800 px-4 pt-4">
        {[
          { key: "report", label: "报告" },
          { key: "sources", label: "证据链" },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as "report" | "sources")}
            className={cn(
              "relative px-4 pb-3 text-sm transition-colors",
              activeTab === tab.key ? "text-indigo-400" : "text-zinc-500 hover:text-zinc-300"
            )}
          >
            {tab.label}
            {activeTab === tab.key && (
              <span className="absolute bottom-0 left-0 right-0 h-px bg-indigo-500" />
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {activeTab === "report" ? (
          <div className="prose prose-sm prose-invert prose-zinc max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => <h1 className="text-2xl font-bold text-zinc-100 mb-4 pb-2 border-b border-zinc-800">{children}</h1>,
                h2: ({ children }) => <h2 className="text-lg font-semibold text-zinc-200 mt-6 mb-3">{children}</h2>,
                h3: ({ children }) => <h3 className="text-base font-medium text-zinc-300 mt-4 mb-2">{children}</h3>,
                p: ({ children }) => <p className="text-zinc-400 leading-relaxed mb-3"><ReferenceAnchors>{children}</ReferenceAnchors></p>,
                ul: ({ children }) => <ul className="space-y-1.5 text-zinc-400 mb-3 list-none">{children}</ul>,
                li: ({ children }) => <li className="flex items-start gap-2"><span className="text-indigo-400 mt-1">▸</span><span><ReferenceAnchors>{children}</ReferenceAnchors></span></li>,
                strong: ({ children }) => <strong className="text-zinc-200 font-semibold"><ReferenceAnchors>{children}</ReferenceAnchors></strong>,
                table: ({ children }) => (
                  <div className="overflow-x-auto mb-4 rounded-lg border border-zinc-800">
                    <table className="w-full border-collapse">{children}</table>
                  </div>
                ),
                th: ({ children }) => <th className="px-3 py-2 text-left text-xs font-semibold text-zinc-400 bg-zinc-900/60 border-b border-zinc-800">{children}</th>,
                td: ({ children }) => <td className="px-3 py-2 text-xs text-zinc-300 border-b border-zinc-800/50"><ReferenceAnchors>{children}</ReferenceAnchors></td>,
              }}
            >
              {reportContent}
            </ReactMarkdown>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-zinc-500">证据链功能开发中...</p>
          </div>
        )}
      </div>

      {/* Footer actions */}
      {isComplete && (
        <div className="border-t border-zinc-800 p-4 flex items-center gap-3">
          <button
            onClick={() => navigator.clipboard.writeText(reportContent)}
            className="flex items-center gap-2 rounded-lg border border-zinc-700/50 bg-zinc-800/50 px-4 py-2 text-sm text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
          >
            📋 复制报告
          </button>
          <button className="flex items-center gap-2 rounded-lg bg-indigo-500/20 px-4 py-2 text-sm text-indigo-300 transition-colors hover:bg-indigo-500/30">
            📄 导出 Markdown
          </button>
        </div>
      )}
    </div>
  );
}
