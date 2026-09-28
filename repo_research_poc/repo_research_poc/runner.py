"""One-shot repository question runner and local audit record."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from langsmith import tracing_context
from pydantic import BaseModel, ValidationError

from .agent import RETRIEVAL_TOOLS, build_agent
from .citations import Citation, validate_citations
from .snapshot import staged_snapshot, validate_request


class ResearchAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    unresolved_questions: list[str]


class ToolAudit(BaseCallbackHandler):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._starts: dict[str, tuple[float, dict[str, Any]]] = {}

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs) -> None:
        call = {
            "id": str(run_id),
            "name": serialized.get("name", "unknown"),
            "input": input_str,
            "status": "running",
            "duration_ms": None,
        }
        self.calls.append(call)
        self._starts[str(run_id)] = (time.monotonic(), call)

    def _finish(self, run_id, status: str, error: Exception | None = None) -> None:
        started = self._starts.pop(str(run_id), None)
        if started is None:
            return
        when, call = started
        call["status"] = status
        call["duration_ms"] = round((time.monotonic() - when) * 1000, 2)
        if error is not None:
            call["error"] = {"type": type(error).__name__, "message": str(error)}

    def on_tool_end(self, output, *, run_id, **kwargs) -> None:
        self._finish(run_id, "ok")

    def on_tool_error(self, error, *, run_id, **kwargs) -> None:
        self._finish(run_id, "error", error)


def _answer_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            if isinstance(message.content, str):
                return message.content
            return "".join(
                block.get("text", "") for block in message.content if isinstance(block, dict)
            )
    raise ValueError("agent returned no assistant answer")


def run_research(
    snapshot: Path,
    commit_sha: str,
    question: str,
    output_dir: Path,
    model_config: dict[str, Any],
    *,
    api_key: str | None = None,
    langsmith_project: str | None = None,
    allow_source_upload: bool = False,
    recursion_limit: int = 100,
    agent_factory: Callable[..., Any] = build_agent,
) -> dict[str, Any]:
    validate_request(snapshot, commit_sha, question, output_dir)
    if recursion_limit < 1:
        raise ValueError("recursion limit must be positive")
    if langsmith_project and not allow_source_upload:
        raise ValueError("LangSmith upload requires explicit allow_source_upload=True")
    run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    audit = ToolAudit()
    result: dict[str, Any] = {
        "schema_version": "repo-research-poc.v1",
        "run_id": run_id,
        "snapshot_path": str(snapshot.resolve()),
        "commit_sha": commit_sha.lower(),
        "question": question,
        "model": {key: model_config[key] for key in ("provider", "model", "temperature", "max_tokens", "base_url") if key in model_config},
        "exposed_tools": list(RETRIEVAL_TOOLS),
        "recursion_limit": recursion_limit,
        "started_at": started_at,
        "status": "error",
        "answer": None,
        "citations": [],
        "unresolved_questions": [],
        "citation_issues": [],
        "citation_attempts": [],
        "parse_attempts": [],
        "errors": [],
    }
    try:
        with staged_snapshot(snapshot) as staged:
            manifest_json = json.dumps(staged.manifest, sort_keys=True, separators=(",", ":"))
            result["source_manifest_sha256"] = hashlib.sha256(manifest_json.encode()).hexdigest()
            result["source_file_count"] = len(staged.manifest)
            agent = agent_factory(staged.root, model_config, api_key=api_key)
            prompt = (
                f"Repository is mounted at /repo. Commit SHA: {commit_sha}. "
                f"Question: {question}"
            )
            with tracing_context(
                enabled=bool(langsmith_project),
                project_name=langsmith_project,
                metadata={"experiment": "repo_research_poc", "run_id": run_id, "commit_sha": commit_sha},
            ):
                state = agent.invoke(
                    {"messages": [{"role": "user", "content": prompt}]},
                    config={"callbacks": [audit], "recursion_limit": recursion_limit},
                )
                for attempt in range(2):
                    response_text = _answer_text(state["messages"])
                    try:
                        answer = ResearchAnswer.model_validate_json(response_text)
                    except ValidationError as error:
                        result["parse_attempts"].append({
                            "error_type": type(error).__name__,
                            "reason": error.errors()[0]["type"],
                            "output_chars": len(response_text),
                        })
                        if attempt == 1:
                            result["status"] = "error"
                            raise
                        feedback = (
                            "Your previous response was invalid or truncated JSON. "
                            "Use evidence already gathered and produce a short valid JSON answer. "
                            "Keep the answer under 80 words, use at most four one-line exact quotes, "
                            "and put any uncovered points in unresolved_questions. "
                            "Do not call more tools unless essential. Return JSON only."
                        )
                        state = agent.invoke(
                            {"messages": [*state["messages"], HumanMessage(content=feedback)]},
                            config={"callbacks": [audit], "recursion_limit": recursion_limit},
                        )
                        continue
                    issues = validate_citations(snapshot, staged.manifest, answer.citations)
                    if answer.answer.strip() and not answer.citations:
                        issues.append({"index": -1, "code": "missing_citations", "detail": "answer has no citations"})
                    if not answer.answer.strip() and not answer.unresolved_questions:
                        issues.append({"index": -1, "code": "no_result", "detail": "no answer or unresolved question"})
                    issue_payload = [issue if isinstance(issue, dict) else vars(issue) for issue in issues]
                    result["citation_attempts"].append({"issues": issue_payload, "response": answer.model_dump()})
                    result["citation_issues"] = issue_payload
                    result["unresolved_questions"] = answer.unresolved_questions
                    if not issues:
                        result["status"] = "ok"
                        result["answer"] = answer.answer
                        result["citations"] = [
                            {**citation.model_dump(), "source_sha256": staged.manifest[citation.path]}
                            for citation in answer.citations
                        ]
                        break
                    result["status"] = "invalid_citations"
                    result["unverified_response"] = answer.model_dump()
                    if attempt == 0 and all(issue["code"] in {"quote_mismatch", "invalid_lines", "missing_citations", "no_result"} for issue in issue_payload):
                        feedback = (
                            f"Your answer to '{question}' failed deterministic citation checks: "
                            f"{json.dumps(issue_payload, ensure_ascii=False)}. "
                            "Re-read the cited file at the exact line with read_file. "
                            "Its offset is zero-based, but start_line/end_line are one-based. "
                            "Copy the source quote exactly and return corrected JSON only."
                        )
                        state = agent.invoke(
                            {"messages": [*state["messages"], HumanMessage(content=feedback)]},
                            config={"callbacks": [audit], "recursion_limit": recursion_limit},
                        )
                    else:
                        break
    except Exception as error:
        result["errors"].append({"type": type(error).__name__, "message": str(error)})
    finally:
        result["tool_calls"] = audit.calls
        result["duration_ms"] = round((time.monotonic() - start) * 1000, 2)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{run_id}.json"
        temporary = output_dir / f".{run_id}.tmp"
        result["result_path"] = str(path.resolve())
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    return result
