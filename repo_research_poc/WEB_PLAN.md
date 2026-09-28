# Repo Research Web Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a local Web entry point for fixed-snapshot source research without changing V1.

**Architecture:** A loopback-only standard-library HTTP server serves static assets and runs the existing research runner in one background worker. It reads completed JSON records from a dedicated output directory.

**Tech Stack:** Python 3.11 standard library, existing Deep Agents POC, pytest, static HTML/CSS/JS.

---

## Task 1: HTTP API

1. Add `tests/test_web.py` with failing HTTP tests for health, job submission, validation, history, and path rejection.
2. Run `uv run --locked pytest tests/test_web.py -q` and confirm expected failures.
3. Implement `repo_research_poc/web.py` with loopback binding, bounded JSON bodies, one worker, and audited run retrieval.
4. Re-run targeted tests.

## Task 2: Browser page

1. Add tests asserting the served page and assets expose the research form and results.
2. Confirm failure, then implement static HTML/CSS/JS with safe text rendering.
3. Re-run targeted tests and inspect the page in a browser at desktop and narrow widths.

## Task 3: Documentation and delivery

1. Update README with exact start command, default tools, privacy boundary, and known limitations.
2. Update project progress and save a screenshot in `docs/review/repo-research-web/`.
3. Run all POC tests, main project tests, lint, lock check, and `git diff --check`.
4. Stage only POC and relevant progress files, review staged diff, commit with a Chinese message, and push.
