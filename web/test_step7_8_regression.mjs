import { chromium } from "@playwright/test";
import fs from "fs";

const BACKEND = "http://127.0.0.1:8000";
const FRONTEND = "http://127.0.0.1:3000";
const OUT_DIR = "/Users/yuzhe.mao/ai-product/docs/review/step7-8";

fs.mkdirSync(OUT_DIR, { recursive: true });

const results = [];

function pass(name, evidence, judgment) {
  results.push({ name, status: "PASS", evidence, judgment });
}

function fail(name, evidence, judgment) {
  results.push({ name, status: "FAIL", evidence, judgment });
}

async function screenshot(page, name) {
  const path = `${OUT_DIR}/2026-05-13-${name}.png`;
  await page.screenshot({ path, fullPage: false });
  return path;
}

async function deleteRun(context, runId) {
  if (!runId) return;
  try {
    await context.request.delete(`${BACKEND}/api/v1/analysis/${runId}`);
  } catch {}
}

async function waitForText(page, pattern, timeout = 90000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const text = await page.locator("body").innerText().catch(() => "");
    if (pattern.test(text)) return text;
    await page.waitForTimeout(1500);
  }
  return await page.locator("body").innerText().catch(() => "");
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });

  const health = await context.request.get(`${BACKEND}/api/v1/health`);
  const healthJson = await health.json().catch(() => ({}));
  if (health.ok() && healthJson.status === "ok") {
    pass("backend_health", "-", "FastAPI /api/v1/health returned status ok.");
  } else {
    fail("backend_health", "-", `Expected health ok, got HTTP ${health.status()} ${JSON.stringify(healthJson)}.`);
  }

  const rewriteHealth = await context.request.get(`${FRONTEND}/api/v1/health`);
  const rewriteHealthJson = await rewriteHealth.json().catch(() => ({}));
  if (rewriteHealth.ok() && rewriteHealthJson.status === "ok") {
    pass("next_rewrite_health", "-", "Next rewrite forwarded /api/v1/health to FastAPI.");
  } else {
    fail("next_rewrite_health", "-", `Expected rewrite health ok, got HTTP ${rewriteHealth.status()} ${JSON.stringify(rewriteHealthJson)}.`);
  }

  let homeRunId = null;
  const page = await context.newPage();
  try {
    await page.goto(FRONTEND, { waitUntil: "networkidle", timeout: 20000 });
    const homeShot = await screenshot(page, "home");
    const text = await page.locator("body").innerText();
    const hasForm = text.includes("需求描述") && text.includes("启动竞品分析");
    const hasModes = text.includes("自动模式") && text.includes("交互模式");
    if (hasForm && hasModes) {
      pass("home_ui", homeShot, "Screenshot shows the input form and both HITL mode controls.");
    } else {
      fail("home_ui", homeShot, `Missing expected home UI text. hasForm=${hasForm}, hasModes=${hasModes}`);
    }

    const textarea = page.locator("textarea").first();
    await textarea.click();
    await textarea.fill("");
    await textarea.pressSequentially("Cursor IDE analysis");
    const submit = page.locator('button[type="submit"]');
    await page.waitForFunction(() => {
      const button = document.querySelector('button[type="submit"]');
      return button && !button.hasAttribute("disabled");
    }, null, { timeout: 10000 });
    await submit.click();
    await page.waitForURL("**/analysis/**", { timeout: 20000 });
    homeRunId = page.url().split("/").pop();
    const analysisShot = await screenshot(page, "home-submit-analysis");
    const analysisText = await page.locator("body").innerText();
    const hasAgents = ["Planner", "Collector", "Analyst", "Comparator", "Writer"].every((item) => analysisText.includes(item));
    if (page.url().includes("/analysis/") && hasAgents) {
      pass("home_submit_rewrite", analysisShot, `Form POST reached FastAPI through Next rewrite and navigated to ${page.url()}.`);
    } else {
      fail("home_submit_rewrite", analysisShot, `Expected analysis URL plus all agents. url=${page.url()}, hasAgents=${hasAgents}`);
    }
  } catch (error) {
    const shot = await screenshot(page, "home-submit-error").catch(() => "-");
    fail("home_submit_rewrite", shot, error.message);
  } finally {
    await deleteRun(context, homeRunId);
    await page.close().catch(() => {});
  }

  let hitlRunId = null;
  const hitlPage = await context.newPage();
  try {
    const create = await context.request.post(`${FRONTEND}/api/v1/analysis`, {
      data: {
        query: "Cursor IDE analysis",
        competitors: ["Cursor", "GitHub Copilot"],
        hitl_mode: "interactive",
      },
    });
    if (!create.ok()) {
      throw new Error(`create interactive run failed: HTTP ${create.status()} ${await create.text()}`);
    }
    const created = await create.json();
    hitlRunId = created.run_id;
    await hitlPage.goto(`${FRONTEND}/analysis/${hitlRunId}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    const hitlText = await waitForText(hitlPage, /确认竞品|确认报告大纲|补充数据来源/, 45000);
    const hitlShot = await screenshot(hitlPage, "hitl-dialog");
    const hasDialog = /确认竞品|确认报告大纲|补充数据来源/.test(hitlText);
    if (hasDialog) {
      pass("hitl_dialog_from_sse", hitlShot, "SSE hitl_request opened a HITL dialog on the analysis page.");
    } else {
      fail("hitl_dialog_from_sse", hitlShot, "Expected a HITL dialog, but no dialog text appeared.");
    }

    const confirm = hitlPage.getByText("确认").last();
    await confirm.click({ timeout: 10000 });
    await hitlPage.waitForTimeout(2500);
    const afterSubmitShot = await screenshot(hitlPage, "hitl-after-submit");
    const pending = await context.request.get(`${BACKEND}/api/v1/analysis/${hitlRunId}/hitl/pending`);
    const pendingJson = await pending.json().catch(() => ({}));
    if (pending.ok() && (pendingJson.pending !== true || pendingJson.payload?.type !== "competitor_confirm")) {
      pass("hitl_submit_uses_run_id", afterSubmitShot, "Submitting the dialog used /analysis/{runId}/hitl and advanced beyond the competitor_confirm interrupt.");
    } else {
      fail("hitl_submit_uses_run_id", afterSubmitShot, `Pending interrupt was not cleared: ${JSON.stringify(pendingJson)}`);
    }
  } catch (error) {
    const shot = await screenshot(hitlPage, "hitl-error").catch(() => "-");
    fail("hitl_flow", shot, error.message);
  } finally {
    await deleteRun(context, hitlRunId);
    await hitlPage.close().catch(() => {});
  }

  let streamRunId = null;
  const streamPage = await context.newPage();
  try {
    const create = await context.request.post(`${FRONTEND}/api/v1/analysis`, {
      data: {
        query: "Cursor IDE analysis",
        competitors: ["Cursor"],
        hitl_mode: "auto",
      },
    });
    if (!create.ok()) {
      throw new Error(`create streaming run failed: HTTP ${create.status()} ${await create.text()}`);
    }
    const created = await create.json();
    streamRunId = created.run_id;
    await streamPage.goto(`${FRONTEND}/analysis/${streamRunId}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    const streamText = await waitForText(streamPage, /复制报告/, 420000);
    const streamShot = await screenshot(streamPage, "agentflow-collector");
    const collectorMoved = /Collector[\s\S]*完成/.test(streamText) && /5\/5 完成/.test(streamText);
    if (collectorMoved) {
      pass("agentflow_multiple_agents", streamShot, "AgentFlow reached final 5/5 state and Collector is complete.");
    } else {
      fail("agentflow_multiple_agents", streamShot, "Expected final AgentFlow state to show 5/5 complete with Collector complete.");
    }

    const completeText = streamText;
    const reportShot = await screenshot(streamPage, "report-complete");
    const hasReport = completeText.includes("复制报告");
    const evidenceResp = await context.request.get(`${BACKEND}/api/v1/reports/${streamRunId}/evidence`);
    const evidenceJson = await evidenceResp.json().catch(() => ({ evidence: [] }));
    const evidenceCount = Array.isArray(evidenceJson.evidence) ? evidenceJson.evidence.length : 0;
    if (hasReport && evidenceResp.ok() && evidenceCount > 0) {
      pass("report_and_evidence_loaded", reportShot, `Report UI reached completion state and evidence endpoint returned ${evidenceCount} item(s).`);
    } else {
      fail("report_and_evidence_loaded", reportShot, `Expected report completion and non-empty evidence. hasReport=${hasReport}, evidenceStatus=${evidenceResp.status()}, evidenceCount=${evidenceCount}`);
    }

    try {
      await streamPage.locator("aside").last().locator("button").first().click({ timeout: 10000 });
      await streamPage.waitForTimeout(500);
      const evidenceClickShot = await screenshot(streamPage, "evidence-click-detail");
      const detailText = await streamPage.locator("aside").last().innerText();
      const firstEvidence = evidenceJson.evidence?.[0];
      const showsDetail = Boolean(
        firstEvidence
        && detailText.includes(firstEvidence.competitor_id)
        && detailText.includes(firstEvidence.source_url),
      );
      if (showsDetail) {
        pass("evidence_detail_click", evidenceClickShot, "Clicked the first evidence item and EvidencePanel showed competitor detail plus source URL.");
      } else {
        fail("evidence_detail_click", evidenceClickShot, "Clicked an evidence item, but the detail panel did not show the expected competitor/source fields.");
      }
    } catch (error) {
      const shot = await screenshot(streamPage, "evidence-click-error").catch(() => "-");
      fail("evidence_detail_click", shot, error.message);
    }
  } catch (error) {
    const shot = await screenshot(streamPage, "stream-error").catch(() => "-");
    fail("stream_report_flow", shot, error.message);
  } finally {
    await deleteRun(context, streamRunId);
    await streamPage.close().catch(() => {});
  }

  await browser.close();

  const passed = results.filter((item) => item.status === "PASS").length;
  const failed = results.length - passed;
  const report = `# Step 7/8 Regression E2E — 2026-05-13

## Summary

- Passed: ${passed}/${results.length}
- Failed: ${failed}/${results.length}

## Self-Judged Results

| Test | Status | Evidence | Judgment |
|------|--------|----------|----------|
${results.map((item) => `| ${item.name} | ${item.status} | ${item.evidence} | ${item.judgment.replaceAll("|", "\\|")} |`).join("\n")}

## Verification Rule

Screenshots are evidence only. A test is marked PASS only when the DOM/API result and screenshot content support the expected behavior.
`;
  const reportPath = `${OUT_DIR}/2026-05-13-step7-8-regression.md`;
  fs.writeFileSync(reportPath, report);
  console.log(report);
  console.log(`Report: ${reportPath}`);
  process.exit(failed > 0 ? 1 : 0);
}

run();
