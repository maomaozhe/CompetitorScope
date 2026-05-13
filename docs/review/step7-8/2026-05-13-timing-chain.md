# Step 7/8 Timing Chain — 2026-05-13

## Summary

- Scenario: `Cursor IDE analysis`, one provided competitor, `hitl_mode=auto`
- Total wall time: **425.7s**
- Bottleneck: **Writer 255.9s**, about 60% of total time
- Event source: FastAPI SSE `/api/v1/analysis/{run_id}/stream`

## Event Timeline

| Time | Event | Node | Duration |
|------|-------|------|----------|
| 0.1s | start | planner_discover | - |
| 0.1s | complete | planner_discover | 0.0s |
| 0.1s | start | planner_outline | - |
| 24.0s | complete | planner_outline | 23.9s |
| 24.0s | start | collect_competitor | - |
| 58.0s | complete | collect_competitor | 33.9s |
| 58.0s | start | join_collectors | - |
| 58.0s | complete | join_collectors | 0.0s |
| 58.0s | start | analyze_competitor | - |
| 111.0s | complete | analyze_competitor | 53.1s |
| 111.0s | start | join_analysts | - |
| 111.0s | complete | join_analysts | 0.0s |
| 111.0s | start | comparator | - |
| 169.8s | complete | comparator | 58.7s |
| 169.8s | start | writer | - |
| 425.7s | complete | writer | 255.9s |
| 425.7s | report_chunk | writer output | - |
| 425.7s | complete | run complete | - |

## Diagnosis

- The frontend can show intermediate AgentFlow states because backend emits `agent_start` and `agent_complete` for each graph node.
- Planner and Collector transitions can be quick enough to miss if the screenshot waits on a long fixed timeout instead of event-driven milestones.
- The long response time is backend pipeline latency, not Next.js or EventSource latency.
- Writer dominates runtime because report generation asks the LLM to synthesize the full report in one call after all evidence is available.

## Follow-ups

- Add per-node duration fields to SSE event payloads so the UI can display actual elapsed time per agent.
- Stream writer output incrementally or split report writing into shorter sections.
- Reduce writer prompt/input size by limiting evidence passed to the final report.
- Consider a cheaper/faster model for analyst/comparator/writer during demo mode.
