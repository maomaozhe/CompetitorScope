# HITL Done Guard Regression — 2026-05-13

## Summary

- Status: PASS
- Script: `web/test_hitl_done_guard.mjs`
- Screenshot: `docs/review/step7-8/2026-05-13-hitl-done-guard-no-popup.png`

## Scenario

The test mocks a completed run while intentionally returning stale HITL data:

- `GET /api/v1/analysis/{run_id}` returns `done=true`, `pending_hitl=true`, and all agents complete.
- `GET /api/v1/analysis/{run_id}/hitl/pending` returns `pending=true`.
- SSE sends `complete`, then sends a stale `hitl_request`.

## Self Judgment

PASS. The page shows `5/5 完成`, all agents are complete, and no HITL dialog is visible after waiting for polling and SSE handling.

This verifies that completed runs suppress stale HITL state from both polling and SSE.
