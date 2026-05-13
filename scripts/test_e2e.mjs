import { chromium } from "@playwright/test";
import fs from "fs";
import path from "path";

const BACKEND = "http://localhost:8000";
const FRONTEND = "http://localhost:3000";
const DOCS_REVIEW = "docs/review";

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
  const textarea = page.locator("textarea").first();
  await textarea.fill("分析 AI Coding IDE 赛道主要竞品，重点关注定价和开发者口碑");

  const submitBtn = page.getByText("🚀 启动竞品分析");
  await submitBtn.click();

  await page.waitForURL("**/analysis/**", { timeout: 10000 });
  const url = page.url();
  runId = url.split("/").pop();
  console.log(`  ✓ Navigated to /analysis/${runId}`);
  await screenshot(page, "analysis-page-created");
  results.tests.push({ name: "submit_analysis", status: "pass" });
  results.passed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  results.tests.push({ name: "submit_analysis", status: "fail", error: e.message });
  results.failed++;
  await browser.close();
  process.exit(1);
}

console.log("\n[4] Three-column layout");
try {
  const asides = page.locator("aside");
  const main = page.locator("main");
  const asideCount = await asides.count();
  console.log(`  aside count: ${asideCount}, main count: ${await main.count()}`);
  await screenshot(page, "three-column-layout");
  results.tests.push({ name: "three_column_layout", status: asideCount >= 2 && (await main.count()) >= 1 ? "pass" : "fail" });
  if (asideCount >= 2 && (await main.count()) >= 1) results.passed++; else results.failed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  results.tests.push({ name: "three_column_layout", status: "fail", error: e.message });
  results.failed++;
}

console.log("\n[5] AgentFlow agents visible");
try {
  await page.getByText("Planner").first().waitFor({ timeout: 5000 });
  await page.getByText("Writer").first().waitFor({ timeout: 5000 });
  console.log("  ✓ Planner + Writer labels visible");
  await screenshot(page, "agentflow-visible");
  results.tests.push({ name: "agentflow_visible", status: "pass" });
  results.passed++;
} catch (e) {
  console.log(`  ✗ ${e.message}`);
  results.tests.push({ name: "agentflow_visible", status: "fail", error: e.message });
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