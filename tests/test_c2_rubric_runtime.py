"""C2 rubric must load when CWD is not the repo root (the Azure image case)."""

from pathlib import Path

from app.critique import rubric as rubric_module


def test_load_c2_works_when_cwd_is_not_the_repo_root(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rubric = rubric_module.load("c2")
    assert rubric.criterion_id == "c2"
    assert rubric.clauses
    assert not (tmp_path / "recruit_rubric_c2_motivation.md").exists()


def test_dockerfile_copies_c2_rubric_and_not_c3() -> None:
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    dockerignore = (root / ".dockerignore").read_text()
    assert "COPY recruit_rubric_c2_motivation.md" in dockerfile
    assert "recruit_rubric_c3" not in dockerfile
    assert "*.md" in dockerignore
    assert "!recruit_rubric_c2_motivation.md" in dockerignore
