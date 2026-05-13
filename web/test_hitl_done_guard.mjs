import { chromium } from "@playwright/test";
import fs from "fs";

const FRONTEND = "http://127.0.0.1:3000";
const RUN_ID = "mock-complete-hitl-guard";
const OUT_DIR = "/Users/yuzhe.mao/ai-product/docs/review/step7-8";
const SCREENSHOT = `${OUT_DIR}/2026-05-13-hitl-done-guard-no-popup.png`;

fs.mkdirSync(OUT_DIR, { recursive: true });

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  await page.route(`**/api/v1/analysis/${RUN_ID}/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache",
      },
      body: [
        "event: complete",
        'data: {"done":true}',
        "",
        "event: hitl_request",
        'data: {"type":"competitor_confirm","interrupt_id":"stale","message":"stale hitl","candidates":[{"name":"Cursor"}]}',
        "",
      ].join("\n"),
    });
  });

  await page.route(`**/api/v1/analysis/${RUN_ID}/hitl/pending`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        pending: true,
        payload: {
          type: "competitor_confirm",
          interrupt_id: "stale",
          message: "stale hitl",
          candidates: [{ name: "Cursor" }],
        },
      }),
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
        pending_hitl: true,
        agents: ["planner", "collector", "analyst", "comparator", "writer"].map((id) => ({
          id,
          status: "complete",
          message: "已完成",
        })),
      }),
    });
  });

  await page.route(`**/api/v1/reports/${RUN_ID}/evidence`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ evidence: [] }),
    });
  });

  await page.goto(`${FRONTEND}/analysis/${RUN_ID}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3500);
  const text = await page.locator("body").innerText();
  await page.screenshot({ path: SCREENSHOT, fullPage: false });
  await browser.close();

  const hasStaleDialog = text.includes("确认竞品") || text.includes("确认报告大纲") || text.includes("补充数据来源");
  const isComplete = text.includes("5/5 完成");
  console.log(JSON.stringify({ isComplete, hasStaleDialog, screenshot: SCREENSHOT }, null, 2));
  if (!isComplete || hasStaleDialog) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
