"""The GitHub deploy button: config copy, setup script and workflow. No secrets needed."""

from pathlib import Path

from scripts.github_deploy_env import (
    direct_project_ref,
    pooler_candidates,
    pooler_url,
    read_env_value,
    replace_env_value,
    url_for_github,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
SETUP = ROOT / "deploy" / "setup_github_deploy.sh"

DIRECT = "postgresql://postgres:s3cr%40t@db.abcref.supabase.co:5432/postgres"
POOLER = "postgresql://postgres.abcref:s3cr%40t@aws-0-us-east-1.pooler.supabase.com:5432/postgres"


# --- Reading and rewriting .env ---------------------------------------------------------


def test_reads_a_value_the_way_the_deploy_script_does() -> None:
    text = "# c\nexport SUPABASE_DB_URL=\"postgresql://x\"\nOTHER=1\n"
    assert read_env_value(text, "SUPABASE_DB_URL") == "postgresql://x"
    assert read_env_value(text, "MISSING") is None
    assert read_env_value("SUPABASE_DB_URL=\n", "SUPABASE_DB_URL") is None


def test_rewrites_only_the_one_line() -> None:
    text = "A=1\nSUPABASE_DB_URL=old\n# SUPABASE_DB_URL in a comment\nB=2"
    out = replace_env_value(text, "SUPABASE_DB_URL", "new")
    assert out == "A=1\nSUPABASE_DB_URL=new\n# SUPABASE_DB_URL in a comment\nB=2"


# --- Direct host -> session pooler ------------------------------------------------------


def test_recognises_only_the_direct_host() -> None:
    assert direct_project_ref(DIRECT) == "abcref"
    assert direct_project_ref(POOLER) is None
    assert direct_project_ref("postgresql://u:p@localhost:5432/db") is None


def test_pooler_url_keeps_the_password_encoded_and_adds_the_ref_to_the_user() -> None:
    assert pooler_url(DIRECT, "abcref", "aws-0-us-east-1.pooler.supabase.com") == POOLER
    # A user that already carries the ref is not given it twice.
    assert pooler_url(POOLER, "abcref", "aws-0-us-east-1.pooler.supabase.com") == POOLER


def test_tries_both_pooler_generations_in_every_region() -> None:
    hosts = [c.split("@")[1].split(":")[0] for c in pooler_candidates(DIRECT, "abcref")]
    assert "aws-0-us-east-1.pooler.supabase.com" in hosts
    assert "aws-1-us-east-1.pooler.supabase.com" in hosts
    assert len(hosts) == len(set(hosts))


def test_a_url_that_is_not_the_direct_host_is_kept(monkeypatch) -> None:
    monkeypatch.setattr("scripts.github_deploy_env._connects", lambda _u: 1 / 0)
    assert url_for_github(POOLER) == POOLER


def test_an_ipv6_only_direct_host_is_swapped_for_the_pooler_that_answers(monkeypatch) -> None:
    monkeypatch.setattr("scripts.github_deploy_env.has_ipv4", lambda _h: False)
    tried: list[str] = []

    def _connects(url: str) -> bool:
        tried.append(url)
        return "aws-1-us-east-2" in url

    monkeypatch.setattr("scripts.github_deploy_env._connects", _connects)
    out = url_for_github(DIRECT)
    assert "@aws-1-us-east-2.pooler.supabase.com:5432/" in out
    assert out.startswith("postgresql://postgres.abcref:s3cr%40t@")
    assert tried[-1] == out


def test_no_pooler_answering_keeps_the_direct_url(monkeypatch) -> None:
    monkeypatch.setattr("scripts.github_deploy_env.has_ipv4", lambda _h: False)
    monkeypatch.setattr("scripts.github_deploy_env._connects", lambda _u: False)
    assert url_for_github(DIRECT) == DIRECT


def test_a_direct_host_with_ipv4_is_kept(monkeypatch) -> None:
    monkeypatch.setattr("scripts.github_deploy_env.has_ipv4", lambda _h: True)
    monkeypatch.setattr("scripts.github_deploy_env._connects", lambda _u: 1 / 0)
    assert url_for_github(DIRECT) == DIRECT


# --- Setup script and workflow shape ----------------------------------------------------


def test_setup_sends_every_secret_and_never_echoes_one() -> None:
    body = SETUP.read_text()
    assert '"$ENV_COPY" | gh secret set BADGEDAY_ENV' in body
    assert 'gh secret set BADGEDAY_WEB_ENV --repo "$REPO" < "$WEB_ENV_FILE"' in body
    assert '"$AZURE_CREDS" | gh secret set AZURE_CREDENTIALS' in body
    # The deploy identity reaches the BadgeDay resource group, not the subscription.
    assert '--scopes "/subscriptions/${SUB_ID}/resourceGroups/${RESOURCE_GROUP}"' in body
    assert "cat $ENV_FILE" not in body and 'cat "$ENV_FILE"' not in body


def test_workflow_runs_by_hand_from_main_and_migrates_before_deploying() -> None:
    body = WORKFLOW.read_text()
    assert "workflow_dispatch:" in body
    assert "push:" not in body and "pull_request:" not in body
    assert "if: github.ref == 'refs/heads/main'" in body
    assert body.index("python scripts/apply_migrations.py") < body.index("azure/login@v2")
    assert body.index("azure/login@v2") < body.index("./deploy/azure-deploy.sh")
    assert "cancel-in-progress: false" in body
    assert "rm -f .env web/.env.local" in body
