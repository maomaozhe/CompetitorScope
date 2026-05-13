# Step 7/8 Regression E2E — 2026-05-13

## Summary

- Passed: 9/9
- Failed: 0/9

## Self-Judged Results

| Test | Status | Evidence | Judgment |
|------|--------|----------|----------|
| backend_health | PASS | - | FastAPI /api/v1/health returned status ok. |
| next_rewrite_health | PASS | - | Next rewrite forwarded /api/v1/health to FastAPI. |
| home_ui | PASS | /Users/yuzhe.mao/ai-product/docs/review/step7-8/2026-05-13-home.png | Screenshot shows the input form and both HITL mode controls. |
| home_submit_rewrite | PASS | /Users/yuzhe.mao/ai-product/docs/review/step7-8/2026-05-13-home-submit-analysis.png | Form POST reached FastAPI through Next rewrite and navigated to http://127.0.0.1:3000/analysis/Cursor-IDE-a-0cb479e4. |
| hitl_dialog_from_sse | PASS | /Users/yuzhe.mao/ai-product/docs/review/step7-8/2026-05-13-hitl-dialog.png | SSE hitl_request opened a HITL dialog on the analysis page. |
| hitl_submit_uses_run_id | PASS | /Users/yuzhe.mao/ai-product/docs/review/step7-8/2026-05-13-hitl-after-submit.png | Submitting the dialog used /analysis/{runId}/hitl and advanced beyond the competitor_confirm interrupt. |
| agentflow_multiple_agents | PASS | /Users/yuzhe.mao/ai-product/docs/review/step7-8/2026-05-13-agentflow-collector.png | AgentFlow reached final 5/5 state and Collector is complete. |
| report_and_evidence_loaded | PASS | /Users/yuzhe.mao/ai-product/docs/review/step7-8/2026-05-13-report-complete.png | Report UI reached completion state and evidence endpoint returned 16 item(s). |
| evidence_detail_click | PASS | /Users/yuzhe.mao/ai-product/docs/review/step7-8/2026-05-13-evidence-click-detail.png | Clicked the first evidence item and EvidencePanel showed competitor detail plus source URL. |

## Verification Rule

Screenshots are evidence only. A test is marked PASS only when the DOM/API result and screenshot content support the expected behavior.
