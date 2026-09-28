from pathlib import Path

from repo_research_poc.citations import Citation, capture_manifest, validate_citations


def test_valid_exact_line_citation(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("def price():\n    return 42\n", encoding="utf-8")
    manifest = capture_manifest(tmp_path)
    issues = validate_citations(
        tmp_path, manifest, [Citation(path="module.py", start_line=2, end_line=2, quote="return 42")]
    )
    assert issues == []


def test_path_traversal_cannot_cite_file_outside_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (tmp_path / "answer.py").write_text("secret answer", encoding="utf-8")
    manifest = capture_manifest(snapshot)
    issues = validate_citations(
        snapshot, manifest, [Citation(path="../answer.py", start_line=1, end_line=1, quote="secret answer")]
    )
    assert issues[0].code == "invalid_path"


def test_quote_at_wrong_line_is_rejected_even_if_present_elsewhere(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("correct here\nother line\n", encoding="utf-8")
    issues = validate_citations(
        tmp_path,
        capture_manifest(tmp_path),
        [Citation(path="module.py", start_line=2, end_line=2, quote="correct here")],
    )
    assert issues[0].code == "quote_mismatch"


def test_modified_file_cannot_replay_old_quote(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("return 42\n", encoding="utf-8")
    manifest = capture_manifest(tmp_path)
    source.write_text("return 43\n", encoding="utf-8")
    issues = validate_citations(
        tmp_path, manifest, [Citation(path="module.py", start_line=1, end_line=1, quote="return 43")]
    )
    assert issues[0].code == "source_changed"


def test_symlink_cannot_cite_outside_file(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("answer", encoding="utf-8")
    link = snapshot / "link.py"
    try:
        link.symlink_to(outside)
    except OSError:
        return  # Windows installations without symlink privileges
    issues = validate_citations(
        snapshot,
        capture_manifest(snapshot),
        [Citation(path="link.py", start_line=1, end_line=1, quote="answer")],
    )
    assert issues[0].code == "invalid_path"


def test_binary_file_cannot_be_used_as_text_evidence(tmp_path: Path) -> None:
    (tmp_path / "data.bin").write_bytes(b"\xff\xfe\x00")
    issues = validate_citations(
        tmp_path,
        capture_manifest(tmp_path),
        [Citation(path="data.bin", start_line=1, end_line=1, quote="answer")],
    )
    assert issues[0].code == "unreadable_source"
