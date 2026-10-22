"""Migration 0019, as text. It is not applied to a database here.

The live project already rejects a mismatched p_user_id in start_recruit_board
and submit_queued_recruit_attempt. This file pins the lockdown that keeps that
behavior, lets the service role through, and does not revoke the RPCs the app
calls with the candidate's token.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "0019_lock_definer_execute.sql"


def _body() -> str:
    lines = []
    for line in MIGRATION.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(stripped)
    return "\n".join(lines).lower()


def test_review_view_is_security_invoker_and_still_filters_the_caller() -> None:
    body = _body()
    assert "with (security_invoker = true)" in body
    assert "security_invoker = false" not in body
    assert "create view public.answered_questions" in body
    assert "select * from public.answered_question_rows()" in body
    assert "where r.user_id = auth.uid()" in body
    # Granting the answer columns back would reopen the 0004 hole.
    assert "grant select (" not in body
    assert "on public.questions" not in body


def test_trigger_and_internal_functions_are_not_client_rpcs() -> None:
    body = _body()
    assert (
        "revoke all on function public.enqueue_ingest_job() from public, anon, authenticated"
        in body
    )
    assert (
        "revoke all on function public.handle_new_user() from public, anon, authenticated" in body
    )
    assert (
        "revoke all on function public.attach_recruit_board_attempt(uuid, uuid, integer)"
        in body
    )
    assert "from public, anon, authenticated" in body
    # The helper is not a client RPC either.
    assert (
        "revoke all on function public.reject_unless_self_or_service(uuid) "
        "from public, anon, authenticated"
        in body
    )


def test_entitlement_rpcs_lose_anon_and_keep_authenticated() -> None:
    body = _body()
    for name in (
        "public.has_access(uuid)",
        "public.has_module_access(uuid, text)",
        "public.has_recruit_access(uuid)",
    ):
        assert f"revoke all on function {name} from public, anon" in body
        assert f"grant execute on function {name} to authenticated, service_role" in body
        assert f"revoke all on function {name} from public, anon, authenticated" not in body


def _revoke_targets(function_name: str) -> str:
    """The role list on the first revoke of this function, lowercased."""
    body = _body()
    marker = f"revoke all on function {function_name}"
    start = body.index(marker)
    window = body[start : start + 500]
    revoke = window.split(";", 1)[0]
    return revoke


def test_app_rpcs_stay_executable_by_the_signed_in_candidate() -> None:
    """Revoking these is how the oral board and the quiz stop working."""
    body = _body()
    for name in (
        "public.start_recruit_board",
        "public.submit_queued_recruit_attempt",
    ):
        revoke = _revoke_targets(name)
        assert "authenticated" not in revoke
        assert "anon" in revoke
    assert "public.abandon_recruit_board" not in body
    assert "public.submit_response" not in body
    assert (
        "grant execute on function public.start_recruit_board(uuid, uuid, timestamptz, jsonb)"
        in body
    )
    assert "to authenticated, service_role" in body
    assert "grant execute on function public.submit_queued_recruit_attempt(" in body


def test_user_id_arguments_reject_a_different_caller_unless_service_role() -> None:
    body = _body()
    assert "coalesce(auth.role(), '') = 'service_role'" in body
    assert "p_user_id is distinct from auth.uid()" in body
    assert "raise exception 'not allowed' using errcode = '42501'" in body
    # Every writer and reader that accepts a user id calls the guard,
    # inside that function, not merely somewhere in the file.
    for name in (
        "public.has_access",
        "public.has_module_access",
        "public.has_recruit_access",
        "public.start_recruit_board",
        "public.submit_queued_recruit_attempt",
        "public.persist_recruit_completed_attempt",
    ):
        start = body.index(f"function {name}")
        chunk = body[start : start + 1800]
        assert "perform public.reject_unless_self_or_service(" in chunk, name
    # persist stays off the client. The worker uses service_role.
    assert (
        "revoke all on function public.persist_recruit_completed_attempt(" in body
    )
    assert "from public, anon, authenticated" in body
    assert (
        "grant execute on function public.persist_recruit_completed_attempt(" in body
    )


def test_promote_store_purchases_still_do_not_open_recruit() -> None:
    body = _body()
    assert "sp.module = 'promote'" in body
    assert "has_module_access(candidate, 'recruit')" in body


def test_search_path_is_fixed_on_the_two_flagged_functions() -> None:
    body = _body()
    assert "alter function public.touch_updated_at() set search_path = public" in body
    assert "alter function public.claim_job(text) set search_path = public" in body


def test_review_still_reads_the_view_by_name() -> None:
    source = (ROOT / "app" / "storage" / "practice.py").read_text()
    assert 'db.table("answered_questions")' in source
    assert "answered_question_rows" in source
