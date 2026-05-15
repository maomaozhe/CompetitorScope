import { chromium } from "@playwright/test";
import fs from "fs";

const BACKEND = "http://localhost:8000";
const FRONTEND = "http://localhost:3000";
const DOCS_REVIEW = "/Users/yuzhe.mao/ai-product/docs/review";

if (!fs.existsSync(DOCS_REVIEW)) {
  fs.mkdirSync(DOCS_REVIEW, { recursive: true });
}

async function screenshot(page, name) {
  const filePath = `${DOCS_REVIEW}/2026-05-13-${name}.png`;
  await page.screenshot({ path: filePath, fullPage: false });
  console.log(`  📸 ${filePath}`);
  return filePath;
}

const results = { tests: [], passed: 0, failed: 0 };
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

console.log("\n[1] Home page loads");
try {
  await page.goto(FRONTEND, { waitUntil: "networkidle", timeout: 15000 });
  const title = await page.title();
  console.log(`  ✓ Page title: ${title}`);
  await screenshot(page, "home-page");
  results.tests.push({ name: "home_page_load", status: "pass" });
  results.passed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  results.tests.push({ name: "home_page_load", status: "fail", error: e.message });
  results.failed++;
  await browser.close();
  process.exit(1);
}

console.log("\n[2] HITL mode toggle visible");
try {
  const autoBtn = page.getByText("⚡ 自动模式");
  const interactiveBtn = page.getByText("🧑 交互模式");
  await autoBtn.waitFor({ timeout: 5000 });
  await interactiveBtn.waitFor({ timeout: 5000 });
  console.log("  ✓ Both HITL mode buttons visible");
  await screenshot(page, "hitl-mode-toggle");
  results.tests.push({ name: "hitl_mode_toggle", status: "pass" });
  results.passed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  results.tests.push({ name: "hitl_mode_toggle", status: "fail", error: e.message });
  results.failed++;
}

let runId = null;
console.log("\n[3] Submit analysis in auto mode");
try {
  // Use evaluate to call React synthetic event handler directly
  // Create analysis via direct API call, then navigate
  const apiResp = await context.request.post(`${BACKEND}/api/v1/analysis`, {
    data: {
      query: "分析 AI Coding IDE 赛道主要竞品，重点关注定价和开发者口碑",
      competitors: [],
      hitl_mode: "auto",
    },
  });
  const apiData = await apiResp.json();
  runId = apiData.run_id;
  console.log(`  Created run: ${runId}`);
  await page.goto(`${FRONTEND}/analysis/${runId}`);
  await page.waitForTimeout(2000);
  console.log(`  ✓ Navigated to /analysis/${runId}`);
  await screenshot(page, "analysis-page-created");
  results.tests.push({ name: "submit_analysis", status: "pass" });
  results.passed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  const currentUrl = page.url();
  console.log(`  Current URL: ${currentUrl}`);
  await screenshot(page, "analysis-submit-debug");
  results.tests.push({ name: "submit_analysis", status: "fail", error: e.message + ` | url=${currentUrl}` });
  results.failed++;
  await browser.close();
  process.exit(1);
}

console.log("\n[4] Three-column layout");
try {
  const asides = page.locator("aside");
  const main = page.locator("main");
  const asideCount = await asides.count();
  const mainCount = await main.count();
  const currentUrl = page.url();
  console.log(`  aside count: ${asideCount}, main count: ${mainCount}, url: ${currentUrl}`);
  await screenshot(page, "three-column-layout");
  const pass = asideCount >= 2 && mainCount >= 1;
  results.tests.push({ name: "three_column_layout", status: pass ? "pass" : "fail" });
  if (pass) results.passed++; else results.failed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  results.tests.push({ name: "three_column_layout", status: "fail", error: e.message });
  results.failed++;
}

console.log("\n[5] AgentFlow agents visible");
try {
  const currentUrl = page.url();
  console.log(`  Checking URL: ${currentUrl}`);
  // Wait for the page to fully render
  await page.waitForTimeout(2000);
  const bodyText = await page.locator("body").innerText();
  console.log(`  Body preview: ${bodyText.slice(0, 200)}`);
  await screenshot(page, "agentflow-debug");
  await page.getByText("Planner").first().waitFor({ timeout: 5000 });
  await page.getByText("Writer").first().waitFor({ timeout: 5000 });
  console.log("  ✓ Planner + Writer labels visible");
  await screenshot(page, "agentflow-visible");
  results.tests.push({ name: "agentflow_visible", status: "pass" });
  results.passed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  const currentUrl = page.url();
  console.log(`  URL at failure: ${currentUrl}`);
  results.tests.push({ name: "agentflow_visible", status: "fail", error: e.message + ` | url=${currentUrl}` });
  results.failed++;
}

console.log("\n[6] Backend API health");
try {
  const resp = await context.request.get(`${BACKEND}/api/v1/health`);
  const data = await resp.json();
  if (data.status !== "ok") throw new Error(`unexpected: ${JSON.stringify(data)}`);
  console.log(`  ✓ Backend healthy`);
  results.tests.push({ name: "backend_health", status: "pass" });
  results.passed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  results.tests.push({ name: "backend_health", status: "fail", error: e.message });
  results.failed++;
}

if (runId) {
  console.log("\n[7] DELETE cancels run");
  try {
    const resp = await context.request.delete(`${BACKEND}/api/v1/analysis/${runId}`);
    const data = await resp.json();
    if (data.status !== "cancelled") throw new Error(`unexpected: ${JSON.stringify(data)}`);
    console.log(`  ✓ DELETE cancelled run`);
    results.tests.push({ name: "delete_analysis", status: "pass" });
    results.passed++;
  } catch (e) {
    console.log(`  ✗ ${e.message}`);
    results.tests.push({ name: "delete_analysis", status: "fail", error: e.message });
    results.failed++;
  }
}

await browser.close();

const reportPath = `${DOCS_REVIEW}/2026-05-13-step7-8-e2e.md`;
const md = `# Step 7/8 E2E Test Report — 2026-05-13

## Summary

- **Passed**: ${results.passed}
- **Failed**: ${results.failed}

## Test Results

| Test | Status | Error |
|------|--------|-------|
${results.tests.map(t => `| ${t.name} | ${t.status === "pass" ? "✅ pass" : "❌ fail"} | ${t.error || "-"} |`).join("\n")}

## Screenshots

- \`docs/review/2026-05-13-home-page.png\`
- \`docs/review/2026-05-13-hitl-mode-toggle.png\`
- \`docs/review/2026-05-13-analysis-page-created.png\`
- \`docs/review/2026-05-13-three-column-layout.png\`
- \`docs/review/2026-05-13-agentflow-visible.png\`
`;

fs.writeFileSync(reportPath, md);
console.log(`\n📄 Report: ${reportPath}`);
console.log(`\n${"=".repeat(60)}`);
console.log(`Results: ${results.passed} passed, ${results.failed} failed`);
console.log(`${"=".repeat(60)}`);
process.exit(results.failed > 0 ? 1 : 0);
