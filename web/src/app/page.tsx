import { InputForm } from "@/components/InputForm";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-20 relative overflow-hidden">
      {/* Background gradient blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 -left-32 w-96 h-96 rounded-full bg-indigo-500/10 blur-3xl" />
        <div className="absolute bottom-1/4 -right-32 w-96 h-96 rounded-full bg-purple-500/10 blur-3xl" />
      </div>

      {/* Hero */}
      <div className="relative z-10 w-full max-w-2xl text-center space-y-8 mb-12">
        <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-sm text-indigo-300 mb-4">
          <span className="h-2 w-2 rounded-full bg-indigo-400 animate-pulse" />
          多 Agent 协作 · 证据链可追溯
        </div>

        <h1 className="text-5xl font-bold tracking-tight bg-gradient-to-b from-white via-zinc-200 to-zinc-500 bg-clip-text text-transparent pb-2">
          CompetitorScope
        </h1>
        <p className="text-lg text-zinc-400 leading-relaxed max-w-xl mx-auto">
          竞品雷达 — 多 Agent 并发采集，自动结构化分析，
          <br />
          生成带证据链可追溯的 Markdown 报告
        </p>

        {/* Agent icons preview */}
        <div className="flex items-center justify-center gap-4 pt-2">
          {["🧭", "🕷️", "📊", "🆚", "✍️"].map((emoji, i) => (
            <div
              key={i}
              className="flex items-center justify-center h-12 w-12 rounded-xl bg-zinc-900/80 border border-zinc-800/60 backdrop-blur-sm text-2xl shadow-lg"
            >
              {emoji}
            </div>
          ))}
        </div>
        <p className="text-xs text-zinc-600">5 个专业 Agent 并发协作</p>
      </div>

      {/* Form */}
      <div className="relative z-10 w-full max-w-2xl">
        <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900/40 p-8 shadow-2xl shadow-black/20 backdrop-blur-sm">
          <InputForm />
        </div>
      </div>

      {/* Footer */}
      <footer className="relative z-10 mt-16 text-center text-xs text-zinc-600">
        Built with LangGraph + Next.js · Anthropic Claude
      </footer>
    </main>
  );
}