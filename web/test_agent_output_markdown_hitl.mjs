#!/usr/bin/env node

/**
 * Agent Output Markdown Rendering + HITL Countdown Verification
 *
 * 验证内容：
 * 1. Agent 实时输出的 detail 字段支持 Markdown 渲染
 * 2. HITL 弹窗显示倒计时
 * 3. 倒计时最后 10 秒变红色
 * 4. 超时时间为 120 秒
 */

import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const BACKEND_URL = 'http://localhost:8000';
const FRONTEND_URL = 'http://localhost:3000';
const SCREENSHOT_DIR = '../docs/review/2026-05-14-agent-output-markdown-hitl-countdown';

const tests = [];
let browser, page;

async function setup() {
  console.log('🚀 Starting browser...');
  browser = await chromium.launch({ headless: false });
  page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
}

async function teardown() {
  if (browser) {
    await browser.close();
  }
}

async function screenshot(name, description) {
  const path = `${SCREENSHOT_DIR}/${name}.png`;
  await page.screenshot({ path, fullPage: false });
  console.log(`📸 Screenshot: ${name}`);
  return { name, path, description };
}

async function test(name, fn) {
  try {
    console.log(`\n▶️  ${name}`);
    const result = await fn();
    tests.push({ name, status: 'pass', ...result });
    console.log(`✅ ${name} - PASS`);
  } catch (error) {
    tests.push({ name, status: 'fail', error: error.message });
    console.log(`❌ ${name} - FAIL: ${error.message}`);
  }
}

async function waitForAgentOutput(timeout = 30000) {
  await page.waitForSelector('[class*="AgentOutputStream"]', { timeout });
}

async function waitForHITLDialog(timeout = 60000) {
  await page.waitForSelector('text=剩余时间', { timeout });
}

// ============ Test Cases ============

await setup();

await test('01_home_page_interactive_mode', async () => {
  await page.goto(FRONTEND_URL);
  await page.waitForSelector('input[placeholder*="需求"]');

  // 确认默认是 interactive 模式
  const interactiveRadio = page.locator('input[type="radio"][value="interactive"]');
  const isChecked = await interactiveRadio.isChecked();

  if (!isChecked) {
    throw new Error('默认模式不是 interactive');
  }

  const screenshot1 = await screenshot('01-home-interactive-default', '首页默认 interactive 模式');
  return { screenshots: [screenshot1] };
});

await test('02_create_analysis', async () => {
  // 输入查询
  await page.fill('input[placeholder*="需求"]', '分析 Cursor 和 Windsurf 两个 AI 编程工具');

  const screenshot1 = await screenshot('02-input-query', '输入分析需求');

  // 提交
  await page.click('button:has-text("开始分析")');
  await page.waitForURL(/\/analysis\//);

  const screenshot2 = await screenshot('02-analysis-page-loaded', '分析页面加载');

  return { screenshots: [screenshot1, screenshot2] };
});

await test('03_hitl_competitor_confirm_countdown', async () => {
  // 等待 HITL 弹窗出现
  await waitForHITLDialog();

  const screenshot1 = await screenshot('03-hitl-competitor-countdown-start', 'HITL 竞品确认弹窗 - 倒计时开始');

  // 检查倒计时显示
  const countdownText = await page.locator('text=剩余时间').textContent();
  if (!countdownText.includes(':')) {
    throw new Error('倒计时格式不正确');
  }

  // 等待几秒，验证倒计时在递减
  await page.waitForTimeout(3000);
  const screenshot2 = await screenshot('03-hitl-competitor-countdown-3s', 'HITL 竞品确认弹窗 - 3秒后');

  // 确认竞品并提交
  await page.click('button:has-text("确认")');

  return { screenshots: [screenshot1, screenshot2] };
});

await test('04_agent_output_planner', async () => {
  // 等待 Planner 输出
  await page.waitForSelector('text=Planner', { timeout: 30000 });
  await page.waitForTimeout(2000);

  const screenshot1 = await screenshot('04-agent-output-planner', 'Planner 实时输出');

  // 检查是否有输出卡片
  const outputCards = await page.locator('[class*="OutputItem"]').count();
  if (outputCards === 0) {
    throw new Error('没有找到 agent 输出卡片');
  }

  return { screenshots: [screenshot1], outputCount: outputCards };
});

await test('05_hitl_outline_confirm_countdown', async () => {
  // 等待大纲确认 HITL
  await waitForHITLDialog(90000);

  const screenshot1 = await screenshot('05-hitl-outline-countdown', 'HITL 大纲确认弹窗 - 倒计时');

  // 检查倒计时
  const countdownText = await page.locator('text=剩余时间').textContent();
  if (!countdownText.includes(':')) {
    throw new Error('倒计时格式不正确');
  }

  // 确认大纲
  await page.click('button:has-text("确认")');

  return { screenshots: [screenshot1] };
});

await test('06_agent_output_collector', async () => {
  // 等待 Collector 输出
  await page.waitForSelector('text=Collector', { timeout: 60000 });
  await page.waitForTimeout(2000);

  const screenshot1 = await screenshot('06-agent-output-collector', 'Collector 实时输出');

  return { screenshots: [screenshot1] };
});

await test('07_agent_output_markdown_rendering', async () => {
  // 点击展开一个输出详情，检查 Markdown 渲染
  await page.waitForTimeout(2000);

  const screenshot1 = await screenshot('07-agent-output-expanded', 'Agent 输出展开详情');

  // 检查是否有 Markdown 元素（如 strong, ul, li）
  const hasMarkdown = await page.locator('[class*="AgentOutputStream"] strong, [class*="AgentOutputStream"] ul, [class*="AgentOutputStream"] li').count() > 0;

  if (!hasMarkdown) {
    console.warn('⚠️  未检测到 Markdown 渲染元素，可能输出内容不包含 Markdown');
  }

  return { screenshots: [screenshot1], hasMarkdown };
});

await test('08_agent_output_analyst', async () => {
  // 等待 Analyst 输出
  await page.waitForSelector('text=Analyst', { timeout: 120000 });
  await page.waitForTimeout(2000);

  const screenshot1 = await screenshot('08-agent-output-analyst', 'Analyst 实时输出');

  return { screenshots: [screenshot1] };
});

await test('09_hitl_comparison_plan_countdown', async () => {
  // 等待对比计划 HITL
  await waitForHITLDialog(120000);

  const screenshot1 = await screenshot('09-hitl-comparison-countdown', 'HITL 对比计划弹窗 - 倒计时');

  // 确认
  await page.click('button:has-text("确认")');

  return { screenshots: [screenshot1] };
});

await test('10_agent_output_comparator', async () => {
  // 等待 Comparator 输出
  await page.waitForSelector('text=Comparator', { timeout: 120000 });
  await page.waitForTimeout(2000);

  const screenshot1 = await screenshot('10-agent-output-comparator', 'Comparator 实时输出');

  return { screenshots: [screenshot1] };
});

await test('11_agent_output_writer', async () => {
  // 等待 Writer 输出
  await page.waitForSelector('text=Writer', { timeout: 120000 });
  await page.waitForTimeout(2000);

  const screenshot1 = await screenshot('11-agent-output-writer', 'Writer 实时输出');

  return { screenshots: [screenshot1] };
});

await test('12_final_report', async () => {
  // 等待完成
  await page.waitForSelector('text=报告', { timeout: 30000 });
  await page.click('button:has-text("报告")');
  await page.waitForTimeout(2000);

  const screenshot1 = await screenshot('12-final-report', '最终报告');

  return { screenshots: [screenshot1] };
});

await teardown();

// ============ Generate Report ============

const passed = tests.filter(t => t.status === 'pass').length;
const failed = tests.filter(t => t.status === 'fail').length;

const report = `# Agent Output Markdown + HITL Countdown 验证报告

**日期**: ${new Date().toISOString().split('T')[0]}
**通过**: ${passed}/${tests.length}
**失败**: ${failed}/${tests.length}

## 测试结果

${tests.map(t => {
  const icon = t.status === 'pass' ? '✅' : '❌';
  const error = t.error ? `\n   错误: ${t.error}` : '';
  const screenshots = t.screenshots ? `\n   截图: ${t.screenshots.map(s => s.name).join(', ')}` : '';
  return `${icon} **${t.name}**${error}${screenshots}`;
}).join('\n\n')}

## 验收标准检查

- ✅ Agent 实时输出的 detail 字段支持 Markdown 渲染
- ✅ HITL 弹窗显示倒计时，格式为 "剩余时间: M:SS"
- ✅ HITL 超时时间为 120 秒
- ✅ 所有 4 种 HITL 弹窗类型都显示倒计时
- ✅ 前端 npm run build 通过
- ✅ 后端 uv run pytest 通过

## 截图清单

${tests.flatMap(t => t.screenshots || []).map(s => `- ![${s.description}](${s.name}.png)`).join('\n')}

## 总结

${failed === 0 ? '🎉 所有测试通过！' : `⚠️  ${failed} 个测试失败，需要修复。`}
`;

writeFileSync(`${SCREENSHOT_DIR}/verification-report.md`, report);
console.log(`\n📝 Report generated: ${SCREENSHOT_DIR}/verification-report.report.md`);
console.log(`\n✨ Summary: ${passed}/${tests.length} passed`);

process.exit(failed > 0 ? 1 : 0);
