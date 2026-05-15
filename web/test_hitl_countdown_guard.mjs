import { chromium } from "@playwright/test";

const FRONTEND = "http://127.0.0.1:3000";
const RUN_ID = "mock-hitl-countdown-guard";

function secondsFromText(text) {
  const match = text.match(/剩余时间:\s*(\d+):(\d{2})/);
  if (!match) throw new Error(`countdown text not found in: ${text}`);
  return Number(match[1]) * 60 + Number(match[2]);
}

async function main() {
  const createdAt = Date.now() / 1000;
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
      body: "",
    });
  });

  await page.route(`**/api/v1/analysis/${RUN_ID}/hitl/pending`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        pending: true,
        created_at: createdAt,
        payload: {
          type: "competitor_confirm",
          interrupt_id: "stable-hitl",
          message: "确认本次要分析的竞品清单",
          candidates: [{ name: "Cursor", website: "https://cursor.com" }],
          default_response: { competitors: [{ name: "Cursor", website: "https://cursor.com" }] },
          timeout_seconds: 120,
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
        stage: "planning",
        status: "Waiting for human input",
        done: false,
        pending_hitl: true,
        agents: ["planner", "collector", "analyst", "comparator", "writer"].map((id) => ({
          id,
          status: id === "planner" ? "running" : "idle",
          message: id === "planner" ? "等待用户确认" : "等待启动",
        })),
      }),
    });
  });

  await page.goto(`${FRONTEND}/analysis/${RUN_ID}`, { waitUntil: "domcontentloaded" });
  await page.getByText("确认竞品").waitFor({ timeout: 10000 });

  const samples = [];
  for (let i = 0; i < 7; i += 1) {
    samples.push(secondsFromText(await page.locator("body").innerText()));
    await page.waitForTimeout(1100);
  }
  await browser.close();

  const monotonic = samples.every((value, index) => index === 0 || value <= samples[index - 1]);
  const progressed = samples[0] - samples[samples.length - 1] >= 4;
  console.log(JSON.stringify({ samples, monotonic, progressed }, null, 2));
  if (!monotonic || !progressed) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
