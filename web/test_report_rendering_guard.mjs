import { chromium } from "@playwright/test";
import fs from "fs";

const FRONTEND = "http://127.0.0.1:3000";
const RUN_ID = "mock-report-rendering-guard";
const OUT_DIR = "/Users/yuzhe.mao/ai-product/docs/review/step7-8";
const SCREENSHOT = `${OUT_DIR}/2026-05-14-report-rendering-guard.png`;

fs.mkdirSync(OUT_DIR, { recursive: true });

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  await page.route(`**/api/v1/analysis/${RUN_ID}/stream`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 100));
    await route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache",
      },
      body: [
        "event: report_chunk",
        `data: ${JSON.stringify({
          content: [
            "# Report",
            "",
            "**Alpha** supports Autocomplete [1].",
            "",
            "**第一梯队（万亿级规模）**以字节跳动为代表 [1]。",
            "",
            "| Feature | Status |",
            "| --- | --- |",
            "| **Autocomplete** | Available [1] |",
          ].join("\n"),
        })}`,
        "",
        "event: complete",
        'data: {"done":true}',
        "",
      ].join("\n"),
    });
  });

  await page.route(`**/api/v1/analysis/${RUN_ID}`, async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        stage: "complete",
        status: "Pipeline complete",
        done: true,
        pending_hitl: false,
        agents: ["planner", "collector", "analyst", "comparator", "writer"].map((id) => ({
          id,
          status: "complete",
          message: "已完成",
        })),
      }),
    });
  });

  await page.route(`**/api/v1/analysis/${RUN_ID}/hitl/pending`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ pending: false }),
    });
  });

  await page.route(`**/api/v1/reports/${RUN_ID}/evidence`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        evidence: [{
          evidence_id: "evidence-1",
          source_id: "source-1",
          source_url: "https://alpha.example/source",
          excerpt: "Alpha supports Autocomplete.",
          extracted_fact: "Alpha supports Autocomplete.",
          fact_type: "feature",
          confidence: 0.9,
          competitor_id: "alpha",
        }],
      }),
    });
  });

  await page.goto(`${FRONTEND}/analysis/${RUN_ID}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: "报告", exact: true }).click({ timeout: 5000 });
  await page.waitForTimeout(300);

  const reportText = await page.locator("main").innerText();
  const firstReference = page.locator("main button", { hasText: "[1]" }).first();
  const referenceCount = await page.locator("main button", { hasText: "[1]" }).count();
  const tableCount = await page.locator("main table").count();
  const strongCount = await page.locator("main strong").count();
  if (referenceCount > 0) {
    await firstReference.click({ timeout: 5000 });
  }
  await page.waitForTimeout(300);
  const evidenceText = await page.locator("aside").last().innerText();
  await page.screenshot({ path: SCREENSHOT, fullPage: false });
  await browser.close();

  const result = {
    hasObjectObject: reportText.includes("[object Object]"),
    hasExpectedText: reportText.includes("Alpha")
      && reportText.includes("Autocomplete")
      && reportText.includes("[1]"),
    referenceCount,
    tableCount,
    strongCount,
    evidenceOpened: evidenceText.includes("alpha")
      && evidenceText.includes("https://alpha.example/source"),
    screenshot: SCREENSHOT,
  };
  console.log(JSON.stringify(result, null, 2));
  if (
    result.hasObjectObject
    || !result.hasExpectedText
    || result.referenceCount === 0
    || result.tableCount === 0
    || result.strongCount === 0
    || !result.evidenceOpened
  ) {
    console.log(JSON.stringify({ reportText, evidenceText }, null, 2));
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
