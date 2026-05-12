import type { Metadata } from "next";
import "./globals.css";
import { AnalysisProvider } from "@/contexts/AnalysisContext";

export const metadata: Metadata = {
  title: "CompetitorScope — 竞品雷达",
  description: "多 Agent 协作的竞品分析系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh" className="dark">
      <body className="bg-zinc-950 text-zinc-100 antialiased">
        <AnalysisProvider>{children}</AnalysisProvider>
      </body>
    </html>
  );
}