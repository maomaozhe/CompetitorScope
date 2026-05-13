import { chromium } from "@playwright/test";
import fs from "fs";

const BACKEND = "http://127.0.0.1:8000";
const FRONTEND = "http://127.0.0.1:3000";
const OUT_DIR = "/Users/yuzhe.mao/ai-product/docs/review/step7-8";

fs.mkdirSync(OUT_DIR, { recursive: true });

const rows = [];

function record(name, status, evidence, judgment) {
  rows.push({ name, status, evidence, judgment });
}

async function screenshot(page, name) {
  const path = `${OUT_DIR}/2026-05-13-${name}.png`;
  await page.screenshot({ path, fullPage: false });
  return path;
}

async function bodyText(page) {
  return page.locator("body").innerText().catch(() => "");
}

async function waitFor(page, predicate, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const text = await bodyText(page);
    if (predicate(text)) return text;
    await page.waitForTimeout(500);
  }
  return bodyText(page);
}

async function deleteRun(context, runId) {
  if (!runId) return;
  await context.request.delete(`${BACKEND}/api/v1/analysis/${runId}`).catch(() => {});
}

function hasAgentState(text, agent, state) {
  const idx = text.indexOf(agent);
  if (idx < 0) return false;
  return text.slice(idx, idx + 120).includes(state);
}

async function runAutoTransitions(context) {
  const page = await context.newPage();
  let runId = null;
  try {
    const create = await context.request.post(`${FRONTEND}/api/v1/analysis`, {
      data: { query: "Cursor IDE analysis", competitors: ["Cursor"], hitl_mode: "auto" },
    });
    const created = await create.json();
    runId = created.run_id;
    await page.goto(`${FRONTEND}/analysis/${runId}`, { waitUntil: "domcontentloaded", timeout: 20000 });

    const transitions = [
      {
        name: "transition_planner_to_collector",
        file: "transition-01-planner-complete-collector-running",
        previous: "Planner",
        next: "Collector",
        predicate: (text) => hasAgentState(text, "Planner", "完成") && hasAgentState(text, "Collector", "运行中"),
        timeout: 300000,
      },
      {
        name: "transition_collector_to_analyst",
        file: "transition-02-collector-complete-analyst-running",
        previous: "Collector",
        next: "Analyst",
        predicate: (text) => hasAgentState(text, "Collector", "完成") && hasAgentState(text, "Analyst", "运行中"),
        timeout: 300000,
      },
      {
        name: "transition_analyst_to_comparator",
        file: "transition-03-analyst-complete-comparator-running",
        previous: "Analyst",
        next: "Comparator",
        predicate: (text) => hasAgentState(text, "Analyst", "完成") && hasAgentState(text, "Comparator", "运行中"),
        timeout: 300000,
      },
      {
        name: "transition_comparator_to_writer",
        file: "transition-04-comparator-complete-writer-running",
        previous: "Comparator",
        next: "Writer",
        predicate: (text) => hasAgentState(text, "Comparator", "完成") && hasAgentState(text, "Writer", "运行中"),
        timeout: 300000,
      },
    ];

    for (const item of transitions) {
      const text = await waitFor(page, item.predicate, item.timeout);
      const shot = await screenshot(page, item.file);
      if (item.predicate(text)) {
        record(item.name, "PASS", shot, `${item.previous} is complete and ${item.next} is running.`);
      } else {
        record(item.name, "FAIL", shot, `Did not observe ${item.previous} complete followed by ${item.next} running.`);
      }
    }

    const finalText = await waitFor(page, (text) => /5\/5 完成/.test(text) && text.includes("复制报告"), 600000);
    const finalShot = await screenshot(page, "transition-05-final-5-of-5-report");
    if (/5\/5 完成/.test(finalText) && ["Planner", "Collector", "Analyst", "Comparator", "Writer"].every((agent) => hasAgentState(finalText, agent, "完成"))) {
      record("transition_final_all_complete", "PASS", finalShot, "All five agents show complete and the report actions are visible.");
    } else {
      record("transition_final_all_complete", "FAIL", finalShot, "Final page did not show 5/5 complete with all agents complete.");
    }
  } finally {
    await deleteRun(context, runId);
    await page.close().catch(() => {});
  }
}

async function runHitlEvidence(context) {
  const page = await context.newPage();
  let runId = null;
  try {
    const create = await context.request.post(`${FRONTEND}/api/v1/analysis`, {
      data: {
        query: "Cursor IDE analysis",
        competitors: ["Cursor", "GitHub Copilot"],
        hitl_mode: "interactive",
      },
    });
    const created = await create.json();
    runId = created.run_id;
    await page.goto(`${FRONTEND}/analysis/${runId}`, { waitUntil: "domcontentloaded", timeout: 20000 });

    const competitorText = await waitFor(page, (text) => text.includes("确认竞品") && text.includes("Cursor") && text.includes("GitHub Copilot"), 45000);
    const competitorShot = await screenshot(page, "hitl-evidence-01-competitor-confirm");
    const pendingBefore = await (await context.request.get(`${BACKEND}/api/v1/analysis/${runId}/hitl/pending`)).json();
    if (competitorText.includes("确认竞品") && pendingBefore.pending === true && pendingBefore.payload?.type === "competitor_confirm") {
      record("hitl_competitor_pending_and_dialog", "PASS", competitorShot, `Dialog is visible and backend pending type is ${pendingBefore.payload.type}.`);
    } else {
      record("hitl_competitor_pending_and_dialog", "FAIL", competitorShot, `Expected competitor_confirm pending; got ${JSON.stringify(pendingBefore)}.`);
    }

    await page.getByText("确认").last().click({ timeout: 10000 });
    const outlineText = await waitFor(page, (text) => text.includes("确认报告大纲"), 90000);
    const outlineShot = await screenshot(page, "hitl-evidence-02-outline-confirm-after-click");
    const pendingAfter = await (await context.request.get(`${BACKEND}/api/v1/analysis/${runId}/hitl/pending`)).json();
    if (outlineText.includes("确认报告大纲") && pendingAfter.pending === true && pendingAfter.payload?.type === "outline_confirm") {
      record("hitl_submit_advances_to_outline", "PASS", outlineShot, `After clicking confirm, backend pending advanced to ${pendingAfter.payload.type}.`);
    } else {
      record("hitl_submit_advances_to_outline", "FAIL", outlineShot, `Expected outline_confirm pending after click; got ${JSON.stringify(pendingAfter)}.`);
    }

    await page.getByText("确认").last().click({ timeout: 10000 });
    await page.waitForTimeout(1500);
    const resumedShot = await screenshot(page, "hitl-evidence-03-after-outline-submit");
    const pendingResumed = await (await context.request.get(`${BACKEND}/api/v1/analysis/${runId}/hitl/pending`)).json();
    if (pendingResumed.pending !== true || pendingResumed.payload?.type !== "outline_confirm") {
      record("hitl_outline_submit_resumes_run", "PASS", resumedShot, "After outline confirmation, the outline_confirm interrupt is cleared and the run resumes.");
    } else {
      record("hitl_outline_submit_resumes_run", "FAIL", resumedShot, `outline_confirm still pending: ${JSON.stringify(pendingResumed)}.`);
    }
  } finally {
    await deleteRun(context, runId);
    await page.close().catch(() => {});
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  await runHitlEvidence(context);
  await runAutoTransitions(context);

  await browser.close();

  const passed = rows.filter((row) => row.status === "PASS").length;
  const failed = rows.length - passed;
  const report = `# Step 7/8 Transition + HITL Evidence — 2026-05-13

## Summary

- Passed: ${passed}/${rows.length}
- Failed: ${failed}/${rows.length}

## Self-Judged Evidence

| Check | Status | Evidence | Judgment |
|-------|--------|----------|----------|
${rows.map((row) => `| ${row.name} | ${row.status} | ${row.evidence} | ${row.judgment.replaceAll("|", "\\|")} |`).join("\n")}

## Notes

- Transition screenshots are captured from the actual analysis page, not mocked state.
- HITL screenshots include both UI dialog evidence and backend pending type checks.
`;
  const reportPath = `${OUT_DIR}/2026-05-13-transition-hitl-evidence.md`;
  fs.writeFileSync(reportPath, report);
  console.log(report);
  console.log(`Report: ${reportPath}`);
  process.exit(failed > 0 ? 1 : 0);
}

main();
