#!/usr/bin/env node

/**
 * 交互式验证脚本 - 手动操作，自动截图
 */

import { chromium } from 'playwright';
import { readFileSync } from 'fs';

const FRONTEND_URL = 'http://localhost:3000';
const SCREENSHOT_DIR = '../docs/review/2026-05-14-agent-output-markdown-hitl-countdown';

let browser, page;

async function setup() {
  console.log('🚀 启动浏览器...');
  browser = await chromium.launch({
    headless: false,
    slowMo: 500  // 慢速模式，方便观察
  });
  page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
}

async function screenshot(name) {
  const path = `${SCREENSHOT_DIR}/${name}.png`;
  await page.screenshot({ path, fullPage: false });
  console.log(`📸 已保存截图: ${name}.png`);
}

async function waitForUser(message) {
  console.log(`\n⏸️  ${message}`);
  console.log('按 Enter 继续...');
  await new Promise(resolve => {
    process.stdin.once('data', () => resolve());
  });
}

console.log('='.repeat(60));
console.log('Agent Output Markdown + HITL Countdown 交互式验证');
console.log('='.repeat(60));

await setup();

// 1. 首页
console.log('\n📍 步骤 1: 首页验证');
await page.goto(FRONTEND_URL);
await page.waitForLoadState('networkidle');
await screenshot('01-home-interactive-default');
await waitForUser('请确认首页默认选择 interactive 模式');

// 2. 创建分析
console.log('\n📍 步骤 2: 创建分析任务');
await page.fill('input[placeholder*="需求"]', '分析 Cursor 和 Windsurf 两个 AI 编程工具');
await screenshot('02-input-query');
await page.click('button:has-text("开始分析")');
await page.waitForURL(/\/analysis\//);
await page.waitForTimeout(2000);
await screenshot('02-analysis-page-loaded');
console.log('✅ 分析任务已创建');

// 3. HITL 竞品确认
console.log('\n📍 步骤 3: HITL 竞品确认 - 倒计时验证');
console.log('等待 HITL 弹窗...');
await page.waitForSelector('text=剩余时间', { timeout: 90000 });
await screenshot('03-hitl-competitor-countdown-start');
await waitForUser('请确认倒计时显示约 2:00，然后等待 10 秒');
await page.waitForTimeout(10000);
await screenshot('03-hitl-competitor-countdown-10s-later');
await waitForUser('请点击"确认"按钮');

// 4. Agent 输出 - Planner
console.log('\n📍 步骤 4: Agent 实时输出 - Planner');
await page.waitForSelector('text=Planner', { timeout: 60000 });
await page.waitForTimeout(3000);
await screenshot('04-agent-output-planner');
await waitForUser('请查看 Planner 输出，确认 Markdown 渲染（粗体、列表等）');

// 5. HITL 大纲确认
console.log('\n📍 步骤 5: HITL 大纲确认 - 倒计时验证');
console.log('等待大纲确认 HITL 弹窗...');
await page.waitForSelector('text=剩余时间', { timeout: 90000 });
await screenshot('05-hitl-outline-countdown');
await waitForUser('请确认倒计时显示，然后点击"确认"');

// 6. Agent 输出 - Collector
console.log('\n📍 步骤 6: Agent 实时输出 - Collector');
await page.waitForSelector('text=Collector', { timeout: 90000 });
await page.waitForTimeout(3000);
await screenshot('06-agent-output-collector');
await waitForUser('请查看 Collector 输出，确认 Markdown 渲染');

// 7. Agent 输出 - Analyst
console.log('\n📍 步骤 7: Agent 实时输出 - Analyst');
await page.waitForSelector('text=Analyst', { timeout: 120000 });
await page.waitForTimeout(3000);
await screenshot('07-agent-output-analyst');
await waitForUser('请查看 Analyst 输出，确认 Markdown 渲染');

// 8. HITL 对比计划确认
console.log('\n📍 步骤 8: HITL 对比计划确认 - 倒计时验证');
console.log('等待对比计划 HITL 弹窗...');
await page.waitForSelector('text=剩余时间', { timeout: 120000 });
await screenshot('08-hitl-comparison-countdown');
await waitForUser('请确认倒计时显示，然后点击"确认"');

// 9. Agent 输出 - Comparator
console.log('\n📍 步骤 9: Agent 实时输出 - Comparator');
await page.waitForSelector('text=Comparator', { timeout: 120000 });
await page.waitForTimeout(3000);
await screenshot('09-agent-output-comparator');
await waitForUser('请查看 Comparator 输出，确认 Markdown 渲染');

// 10. Agent 输出 - Writer
console.log('\n📍 步骤 10: Agent 实时输出 - Writer');
await page.waitForSelector('text=Writer', { timeout: 120000 });
await page.waitForTimeout(3000);
await screenshot('10-agent-output-writer');
await waitForUser('请查看 Writer 输出，确认 Markdown 渲染');

// 11. 最终报告
console.log('\n📍 步骤 11: 最终报告');
await page.click('button:has-text("报告")');
await page.waitForTimeout(2000);
await screenshot('11-final-report');
await waitForUser('请确认报告完整显示');

console.log('\n✅ 验证完成！');
console.log(`\n📁 截图已保存到: ${SCREENSHOT_DIR}/`);
console.log('\n请查看截图并填写 MANUAL_VERIFICATION_GUIDE.md 中的验证结果');

await browser.close();
process.exit(0);
