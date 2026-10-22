"""0014 and 0015 can be missing from schema_migrations while their objects exist.

Re-running those files fails. The runner records them when the probe matches
and does not execute the SQL.
"""

import builtins
from pathlib import Path

import pytest

from scripts.apply_migrations import LEDGER_GAPS, _connect, ledger_gap_already_present

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "apply_migrations.py"
DEPLOY = ROOT / "deploy" / "azure-deploy.sh"


class _Cursor:
    def __init__(self, value: bool) -> None:
        self.value = value
        self.sql = ""

    def execute(self, sql: str) -> None:
        self.sql = sql

    def fetchone(self):
        return (self.value,)


def test_a_missing_ledger_row_is_recorded_only_when_the_objects_exist() -> None:
    boards = _Cursor(True)
    assert ledger_gap_already_present(boards, "0014_recruit_boards.sql") is True
    assert "recruit_boards" in boards.sql

    missing = _Cursor(False)
    assert ledger_gap_already_present(missing, "0015_store_purchases_module.sql") is False
    assert "store_purchases" in missing.sql
    assert "module" in missing.sql

    other = _Cursor(True)
    assert ledger_gap_already_present(other, "0016_migration_ledger_is_not_public.sql") is False
    assert other.sql == ""


def test_the_runner_records_the_gap_instead_of_reapplying_it() -> None:
    text = RUNNER.read_text()
    assert set(LEDGER_GAPS) == {
        "0014_recruit_boards.sql",
        "0015_store_purchases_module.sql",
    }
    assert "ledger_gap_already_present" in text
    assert "Recorded without re-running the SQL" in text
    readme = (ROOT / "deploy" / "README.md").read_text()
    assert "0014_recruit_boards.sql" in readme
    assert "0015_store_purchases_module.sql" in readme


def test_the_deploy_default_location_is_centralus() -> None:
    assert 'LOCATION="${LOCATION:-centralus}"' in DEPLOY.read_text()


def test_missing_ops_extra_names_the_install(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def blocked(name: str, *args: object, **kwargs: object):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ImportError("No module named psycopg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(SystemExit, match=r"ops extra") as caught:
        _connect("postgresql://example")
    assert 'pip install -e ".[ops]"' in str(caught.value)
