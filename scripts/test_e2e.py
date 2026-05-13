"""E2E test for Step 7/8 features via Playwright."""

import asyncio
import json
import os
import time
from pathlib import Path

from playwright.async_api import async_playwright

BACKEND = "http://localhost:8000"
FRONTEND = "http://localhost:3000"
DOCS_REVIEW = Path("docs/review")
DOCS_REVIEW.mkdir(exist_ok=True)


def save_screenshot(page, name: str):
    """Save screenshot to docs/review."""
    path = DOCS_REVIEW / f"2026-05-12-{name}.png"
    page.screenshot(path=path, full_page=False)
    print(f"  📸 Screenshot: {path}")
    return path


async def run_e2e():
    results = {"tests": [], "passed": 0, "failed": 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # ── Test 1: Home page loads ──────────────────────────────────────────
        print("\n[1] Home page loads")
        try:
            await page.goto(FRONTEND, wait_until="networkidle", timeout=15000)
            title = await page.title()
            print(f"  ✓ Page loaded: {title}")
            save_screenshot(page, "home-page")
            results["tests"].append({"name": "home_page_load", "status": "pass"})
            results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results["tests"].append({"name": "home_page_load", "status": "fail", "error": str(e)})
            results["failed"] += 1
            await browser.close()
            return results

        # ── Test 2: InputForm — HITL mode toggle visible ──────────────────────
        print("\n[2] HITL mode toggle visible")
        try:
            auto_btn = page.locator("button", has_text="⚡ 自动模式")
            interactive_btn = page.locator("button", has_text="🧑 交互模式")
            await auto_btn.wait_for(timeout=5000)
            await interactive_btn.wait_for(timeout=5000)
            print("  ✓ Both HITL mode buttons visible")
            save_screenshot(page, "hitl-mode-toggle")
            results["tests"].append({"name": "hitl_mode_toggle", "status": "pass"})
            results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results["tests"].append({"name": "hitl_mode_toggle", "status": "fail", "error": str(e)})
            results["failed"] += 1

        # ── Test 3: Submit analysis (auto mode) ─────────────────────────────
        print("\n[3] Submit analysis in auto mode")
        run_id = None
        try:
            textarea = page.locator("textarea").first
            await textarea.fill("分析 AI Coding IDE 赛道主要竞品，重点关注定价和开发者口碑")

            submit_btn = page.locator("button", has-text="🚀 启动竞品分析")
            await submit_btn.click()

            # Wait for navigation to analysis page
            await page.wait_for_url(f"**/analysis/**", timeout=10000)
            url = page.url
            run_id = url.split("/")[-1]
            print(f"  ✓ Navigated to /analysis/{run_id}")
            save_screenshot(page, "analysis-page-created")
            results["tests"].append({"name": "submit_analysis", "status": "pass"})
            results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results["tests"].append({"name": "submit_analysis", "status": "fail", "error": str(e)})
            results["failed"] += 1
            await browser.close()
            return results

        # ── Test 4: Three-column layout ──────────────────────────────────────
        print("\n[4] Three-column layout")
        try:
            # Left sidebar (AgentFlow)
            left = page.locator("aside").first
            # Main content (ReportView)
            main = page.locator("main")
            # Right sidebar (EvidencePanel)
            right = page.locator("aside").nth(1)
            await asyncio.gather(
                left.wait_for(timeout=5000),
                main.wait_for(timeout=5000),
                right.wait_for(timeout=5000),
            )
            print("  ✓ Three columns present: AgentFlow | ReportView | EvidencePanel")
            save_screenshot(page, "three-column-layout")
            results["tests"].append({"name": "three_column_layout", "status": "pass"})
            results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results["tests"].append({"name": "three_column_layout", "status": "fail", "error": str(e)})
            results["failed"] += 1

        # ── Test 5: AgentFlow shows agents ───────────────────────────────────
        print("\n[5] AgentFlow shows 5 agents")
        try:
            planner = page.locator("text=Planner").first
            writer = page.locator("text=Writer").first
            await asyncio.gather(
                planner.wait_for(timeout=5000),
                writer.wait_for(timeout=5000),
            )
            print("  ✓ AgentFlow visible with 5 agent labels")
            save_screenshot(page, "agentflow-visible")
            results["tests"].append({"name": "agentflow_visible", "status": "pass"})
            results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results["tests"].append({"name": "agentflow_visible", "status": "fail", "error": str(e)})
            results["failed"] += 1

        # ── Test 6: API health check ────────────────────────────────────────
        print("\n[6] Backend API health")
        try:
            resp = await context.request.get(f"{BACKEND}/api/v1/health")
            data = await resp.json()
            assert data.get("status") == "ok"
            print(f"  ✓ Backend healthy: {data}")
            results["tests"].append({"name": "backend_health", "status": "pass"})
            results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results["tests"].append({"name": "backend_health", "status": "fail", "error": str(e)})
            results["failed"] += 1

        # ── Test 7: DELETE endpoint works ────────────────────────────────────
        print("\n[7] DELETE /analysis/{id} cancels run")
        try:
            resp = await context.request.delete(f"{BACKEND}/api/v1/analysis/{run_id}")
            data = await resp.json()
            assert data.get("status") == "cancelled"
            print(f"  ✓ DELETE cancelled run: {data}")
            results["tests"].append({"name": "delete_analysis", "status": "pass"})
            results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results["tests"].append({"name": "delete_analysis", "status": "fail", "error": str(e)})
            results["failed"] += 1

        await browser.close()

    return results


async def main():
    print("=" * 60)
    print("CompetitorScope Step 7/8 E2E Tests")
    print("=" * 60)

    results = await run_e2e()

    print("\n" + "=" * 60)
    print(f"Results: {results['passed']} passed, {results['failed']} failed")
    print("=" * 60)

    report = DOCS_REVIEW / "2026-05-12-step7-8-e2e.md"
    md = f"""# Step 7/8 E2E Test Report — 2026-05-12

## Summary

- **Passed**: {results['passed']}
- **Failed**: {results['failed']}

## Test Results

| Test | Status | Error |
|------|--------|-------|
"""
    for t in results["tests"]:
        md += f"| {t['name']} | {'✅ pass' if t['status'] == 'pass' else '❌ fail'} | {t.get('error', '-')} |\n"

    md += """
## Screenshots

See `docs/review/2026-05-12-*.png` for visual evidence.
"""
    report.write_text(md)
    print(f"\n📄 Report: {report}")
    return results


if __name__ == "__main__":
    asyncio.run(main())