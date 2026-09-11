"""C2 rubric must load when CWD is not the repo root (the Azure image case)."""

from pathlib import Path

from app.critique import rubric as rubric_module


def test_load_c2_works_when_cwd_is_not_the_repo_root(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rubric = rubric_module.load("c2")
    assert rubric.criterion_id == "c2"
    assert rubric.clauses
    assert not (tmp_path / "recruit_rubric_c2_motivation.md").exists()


def test_dockerfile_copies_live_c1_through_c5_rubrics() -> None:
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    dockerignore = (root / ".dockerignore").read_text()
    for name in (
        "recruit_rubric_c1_answer_construction.md",
        "recruit_rubric_c2_motivation.md",
        "recruit_rubric_c3_teamwork.md",
        "recruit_rubric_c4_integrity_ethics.md",
        "recruit_rubric_c5_judgment_composure.md",
    ):
        assert f"COPY {name}" in dockerfile
        assert f"!{name}" in dockerignore
    assert "*.md" in dockerignore
