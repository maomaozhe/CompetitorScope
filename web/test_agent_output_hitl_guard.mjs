import { chromium } from "@playwright/test";
import fs from "fs";

const FRONTEND = "http://127.0.0.1:3000";
const OUT_DIR = "/Users/yuzhe.mao/ai-product/docs/review/agent-output-hitl";

fs.mkdirSync(OUT_DIR, { recursive: true });

function sse(events) {
  return events
    .map((item) => `event: ${item.event}\ndata: ${JSON.stringify(item.data)}\n\n`)
    .join("");
}

function agents(active, completed = []) {
  return ["planner", "collector", "analyst", "comparator", "writer"].map((id) => ({
    id,
    status: completed.includes(id) ? "complete" : id === active ? "running" : "idle",
    message: id === active ? "处理中..." : completed.includes(id) ? "已完成" : "等待启动",
  }));
}

async function screenshot(page, name) {
  const path = `${OUT_DIR}/2026-05-14-${name}.png`;
  await page.screenshot({ path, fullPage: false });
  return path;
}

async function waitForExpectedText(page, expected, timeoutMs = 5000) {
  const start = Date.now();
  let text = "";
  while (Date.now() - start < timeoutMs) {
    text = await page.locator("body").innerText().catch(() => "");
    if (expected.every((item) => text.includes(item))) return text;
    await page.waitForTimeout(250);
  }
  return text || await page.locator("body").innerText().catch(() => "");
}

async function runStage(browser, stage) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const runId = `mock-${stage.name}`;

  await context.route(`${FRONTEND}/api/v1/analysis/${runId}/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache",
      },
      body: sse(stage.events),
    });
  });

  await context.route(`${FRONTEND}/api/v1/analysis/${runId}/hitl/pending`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(stage.pending ? { pending: true, payload: stage.pending } : { pending: false }),
    });
  });

  await context.route(`${FRONTEND}/api/v1/analysis/${runId}`, async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        stage: stage.apiStage,
        status: stage.pending ? "Waiting for human input" : "Running",
        done: Boolean(stage.done),
        pending_hitl: Boolean(stage.pending),
        agents: stage.agents,
      }),
    });
  });

  await context.route(`${FRONTEND}/api/v1/reports/${runId}/evidence`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ evidence: [] }),
    });
  });

  const page = await context.newPage();
  await page.goto(`${FRONTEND}/analysis/${runId}`, { waitUntil: "domcontentloaded" });
  const textBeforeClick = await waitForExpectedText(page, stage.expected, stage.waitMs || 5000);

  if (stage.clickTab) {
    await page.getByRole("button", { name: stage.clickTab, exact: true }).click();
    await waitForExpectedText(page, stage.expected, stage.waitMs || 5000);
  }

  const text = stage.clickTab
    ? await page.locator("body").innerText()
    : textBeforeClick;
  const liveHeadingBox = await page.getByRole("heading", { name: "Agent 实时输出" }).boundingBox().catch(() => null);
  const evidence = await screenshot(page, stage.name);
  await context.close();

  const missing = stage.expected.filter((item) => !text.includes(item));
  return {
    name: stage.name,
    status: missing.length === 0 && (!stage.requiresMainOutput || Boolean(liveHeadingBox && liveHeadingBox.x > 288))
      ? "PASS"
      : "FAIL",
    evidence,
    missing,
    outputInMainPanel: Boolean(liveHeadingBox && liveHeadingBox.x > 288),
  };
}

async function main() {
  const browser = await chromium.launch({ headless: true });

  const homeContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const home = await homeContext.newPage();
  await home.goto(FRONTEND, { waitUntil: "domcontentloaded" });
  const homeText = await home.locator("body").innerText();
  const homeShot = await screenshot(home, "stage-00-home-interactive-default");
  await homeContext.close();

  const stages = [
    {
      name: "stage-01-planner-output-main",
      apiStage: "planning",
      agents: agents("planner"),
      requiresMainOutput: true,
      expected: ["Agent 实时输出", "候选竞品已确认", "Cursor", "GitHub Copilot"],
      events: [{
        event: "agent_output",
        data: {
          id: "planner-candidates",
          agent: "planner",
          node: "planner_discover",
          title: "候选竞品已确认",
          summary: "确认 2 家竞品：Cursor, GitHub Copilot",
          detail: "- Cursor: https://cursor.com\n- GitHub Copilot: https://github.com/features/copilot",
          artifact_type: "competitors",
          created_at: 1778760000,
        },
      }],
    },
    {
      name: "stage-02-collector-output-main",
      apiStage: "collecting",
      agents: agents("collector", ["planner"]),
      requiresMainOutput: true,
      expected: ["Agent 实时输出", "数据采集完成", "cursor 收集到 3 条来源", "https://cursor.com/pricing"],
      events: [{
        event: "agent_output",
        data: {
          id: "collector-sources",
          agent: "collector",
          node: "collect_competitor",
          title: "数据采集完成",
          summary: "cursor 收集到 3 条来源",
          detail: "- Cursor Pricing\n  https://cursor.com/pricing\n- Cursor Docs\n  https://docs.cursor.com\n- Cursor Blog\n  https://cursor.com/blog",
          artifact_type: "sources",
          created_at: 1778760010,
        },
      }],
    },
    {
      name: "stage-03-analyst-output-main",
      apiStage: "analyzing",
      agents: agents("analyst", ["planner", "collector"]),
      requiresMainOutput: true,
      expected: ["Agent 实时输出", "结构化分析完成", "Cursor 产出 profile", "功能：AI autocomplete"],
      events: [{
        event: "agent_output",
        data: {
          id: "analyst-profile",
          agent: "analyst",
          node: "analyze_competitor",
          title: "结构化分析完成",
          summary: "Cursor 产出 profile，证据 4 条",
          detail: "定位：AI coding IDE\n技术形态：Desktop IDE\n功能：AI autocomplete, codebase chat\n好评：fast, useful\n吐槽：pricing",
          artifact_type: "profile",
          created_at: 1778760020,
        },
      }],
    },
    {
      name: "stage-04-comparator-output-main",
      apiStage: "comparing",
      agents: agents("comparator", ["planner", "collector", "analyst"]),
      requiresMainOutput: true,
      expected: ["Agent 实时输出", "横向对比完成", "生成 2 条关键洞察", "Cursor 定价更偏团队协作"],
      events: [{
        event: "agent_output",
        data: {
          id: "comparator-result",
          agent: "comparator",
          node: "comparator",
          title: "横向对比完成",
          summary: "生成 2 条关键洞察",
          detail: "- Cursor 定价更偏团队协作\n- Copilot 生态优势更强",
          artifact_type: "comparison",
          created_at: 1778760030,
        },
      }],
    },
    {
      name: "stage-05-comparison-hitl-modal",
      apiStage: "comparing",
      agents: agents("comparator", ["planner", "collector", "analyst"]),
      requiresMainOutput: true,
      expected: ["Agent 实时输出", "确认对比重点", "主要比较维度", "比较重点"],
      pending: {
        type: "comparison_plan_confirm",
        interrupt_id: "cmp-1",
        message: "确认横向对比的主要维度和重点",
        comparison_dimensions: ["features", "pricing"],
        focus_notes: "Focus on pricing gaps.",
        default_response: {
          comparison_dimensions: ["features", "pricing"],
          focus_notes: "Focus on pricing gaps.",
        },
      },
      events: [{
        event: "agent_output",
        data: {
          id: "comparison-plan",
          agent: "comparator",
          node: "comparator",
          title: "等待确认对比重点",
          summary: "维度：features, pricing",
          detail: "Focus on pricing gaps.",
          artifact_type: "comparison",
          created_at: 1778760040,
        },
      }],
    },
    {
      name: "stage-06-writer-report-complete",
      apiStage: "complete",
      agents: agents("writer", ["planner", "collector", "analyst", "comparator"]),
      done: true,
      clickTab: "报告",
      expected: ["报告", "竞品分析报告", "复制报告"],
      events: [
        {
          event: "agent_output",
          data: {
            id: "writer-report",
            agent: "writer",
            node: "writer",
            title: "报告生成完成",
            summary: "Markdown 报告 1200 字符",
            detail: "# 竞品分析报告\n## 执行摘要",
            artifact_type: "report",
            created_at: 1778760050,
          },
        },
        {
          event: "report_chunk",
          data: { content: "# 竞品分析报告\n\n## 执行摘要\n\nCursor 与 GitHub Copilot 在定价和生态上形成差异。" },
        },
        { event: "complete", data: { done: true } },
      ],
    },
  ];

  const results = [{
    name: "stage-00-home-interactive-default",
    status: homeText.includes("人工确认关键节点，可干预分析方向") ? "PASS" : "FAIL",
    evidence: homeShot,
    missing: homeText.includes("人工确认关键节点，可干预分析方向") ? [] : ["interactive default helper text"],
    outputInMainPanel: null,
  }];

  for (const stage of stages) {
    results.push(await runStage(browser, stage));
  }

  await browser.close();

  const failed = results.filter((item) => item.status !== "PASS");
  const reportPath = `${OUT_DIR}/2026-05-14-agent-output-hitl-stage-evidence.md`;
  const report = `# Agent Output + HITL Stage Evidence — 2026-05-14

## Summary

- Passed: ${results.length - failed.length}/${results.length}
- Failed: ${failed.length}/${results.length}

## Stage Screenshots

| Stage | Status | Main Panel | Evidence | Missing |
|-------|--------|------------|----------|---------|
${results.map((item) => `| ${item.name} | ${item.status} | ${item.outputInMainPanel === null ? "-" : item.outputInMainPanel ? "yes" : "no"} | ${item.evidence} | ${item.missing.join(", ")} |`).join("\n")}
`;
  fs.writeFileSync(reportPath, report);
  console.log(report);
  console.log(`Report: ${reportPath}`);
  if (failed.length > 0) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
