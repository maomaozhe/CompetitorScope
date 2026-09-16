import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const listPage = readFileSync("src/app/observability/page.tsx", "utf8");
const detailPage = readFileSync("src/app/observability/[runId]/page.tsx", "utf8");
const analysisPage = readFileSync("src/app/analysis/[id]/page.tsx", "utf8");
const api = readFileSync("src/lib/api.ts", "utf8");

assert.match(listPage, /运行观测/);
assert.match(listPage, /getTraceRuns/);
assert.match(detailPage, /执行时间线/);
assert.match(detailPage, /决策记录/);
assert.match(detailPage, /快照/);
assert.match(detailPage, /Baseline \/ Candidate/);
assert.match(detailPage, /播放/);
assert.match(detailPage, /getArtifact/);
assert.match(analysisPage, /查看执行详情/);
assert.match(api, /getTraceEvents/);
assert.match(api, /createEvalExecution/);

console.log("observability UI source contract passed");
