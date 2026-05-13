# SSE Streaming E2E Test Report — 2026-05-13

## Summary

- **Passed**: 2/2
- **Failed**: 0/2

## Test Results

| Test | Status | Error |
|------|--------|-------|
| sse_planner_complete | ✅ pass | - |
| sse_events_emitted | ✅ pass | - |

## Screenshots

| File | Description |
|------|-------------|
| `2026-05-13-sse-page-loaded.png` | Analysis page after SSE connection (3s) — Planner shows "运行中" / "生成大纲中..." (SSE connected!) |
| `2026-05-13-sse-planner-complete.png` | Planner shows "1/5 完成", Planner "完成" / "已完成", Collector "运行中" / "采集数据中..." |

## Bug Fixes (3 bugs)

1. **`web/src/hooks/useSSE.ts`** — `es.onmessage` only fires for untyped SSE messages. Named events (`event: agent_start`) go to `addEventListener("agent_start", ...)` — not `onmessage`. Fix: use `es.addEventListener()` for named event types.

2. **`web/src/app/analysis/[id]/page.tsx`** — `setRunId(id)` called directly in render body (not in `useEffect`). React throws "Cannot update a component while rendering another" and bails. Fix: wrap in `useEffect()`.

3. **`web/src/hooks/useSSE.ts`** — EventSource URL was relative `/api/v1/analysis/.../stream`. Next.js App Router intercepted as internal route → 404. Fix: use absolute URL `http://localhost:8000/api/v1/analysis/.../stream`.

## SSE Events Verified

Events emitted by `astream + Queue` streaming:
- `agent_start`: planner_discover begins
- `agent_complete`: planner_discover finishes
- `agent_start`: planner_outline begins
- `report_chunk`: writer output (when pipeline reaches writer)
- `complete`: pipeline finishes
