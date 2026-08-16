"""Prove the schema's guarantees hold against a live database.

Four things the DDL claims, none of which are true merely because they are written down:

1. **Isolation.** The privacy constraint — documents are private per user, never shared —
   is enforced by database policy rather than application code. A policy that silently
   fails is worse than none, because the application is written believing it is
   protected. So this does not inspect the policies; it creates two real users, gives
   each documents, chunks and questions, and tries to read one user's data with the
   other's credentials. Anything returned is a leak.
2. **Constraints.** The check constraints on `questions` restate the application's
   verification gate. If they do not actually reject a malformed row, the second line of
   defence is decorative.
3. **Cascade.** Hard delete of an account must remove everything, in one statement,
   leaving no orphans.
4. **Coverage.** The view must move when a candidate answers a question, and must count
   only sections worth questioning.

    python scripts/verify_schema.py

Every user created here is deleted at the end, including on failure. Run against a
development project.
"""

import sys
import uuid

import httpx

from app.config import get_settings

PASSWORD = "badgeday-rls-probe-9d41f2"


class Api:
    def __init__(self, url: str, anon_key: str, service_key: str) -> None:
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.service_key = service_key
        self.client = httpx.Client(timeout=30)

    # --- auth ---------------------------------------------------------------

    def create_user(self, email: str) -> str:
        r = self.client.post(
            f"{self.url}/auth/v1/admin/users",
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
            },
            json={"email": email, "password": PASSWORD, "email_confirm": True},
        )
        r.raise_for_status()
        return r.json()["id"]

    def delete_user(self, user_id: str) -> None:
        self.client.delete(
            f"{self.url}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
            },
        )

    def sign_in(self, email: str) -> str:
        r = self.client.post(
            f"{self.url}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": self.anon_key},
            json={"email": email, "password": PASSWORD},
        )
        r.raise_for_status()
        return r.json()["access_token"]

    # --- data ---------------------------------------------------------------

    def insert_as_service(self, table: str, row: dict) -> dict:
        r = self.client.post(
            f"{self.url}/rest/v1/{table}",
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=row,
        )
        r.raise_for_status()
        return r.json()[0]

    def select_as_user(self, token: str, table: str, query: str = "select=*") -> list:
        r = self.client.get(
            f"{self.url}/rest/v1/{table}?{query}",
            headers={"apikey": self.anon_key, "Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()

    def insert_as_service_raw(self, table: str, row: dict) -> httpx.Response:
        """Insert without raising, for probing what the database refuses."""
        return self.client.post(
            f"{self.url}/rest/v1/{table}",
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
            },
            json=row,
        )

    def select_as_service(self, table: str, query: str) -> list:
        """Read past RLS, to see what is actually left in a table rather than what a
        given user is permitted to see. Checking for orphans as a user would be
        circular: RLS hides another user's surviving rows just as effectively as
        deletion removes them."""
        r = self.client.get(
            f"{self.url}/rest/v1/{table}?select=*&{query}",
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
            },
        )
        r.raise_for_status()
        return r.json()

    def coverage(self, document_id: str) -> list:
        r = self.client.get(
            f"{self.url}/rest/v1/document_coverage?document_id=eq.{document_id}",
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
            },
        )
        r.raise_for_status()
        return r.json()

    def insert_as_user(self, token: str, table: str, row: dict) -> httpx.Response:
        return self.client.post(
            f"{self.url}/rest/v1/{table}",
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=row,
        )


def _seed(api: Api, user_id: str, label: str) -> dict:
    document = api.insert_as_service(
        "documents",
        {
            "user_id": user_id,
            "filename": f"{label}.pdf",
            "storage_path": f"{user_id}/{label}.pdf",
            "status": "ready",
        },
    )
    chunk = api.insert_as_service(
        "chunks",
        {
            "id": str(uuid.uuid4()),
            "document_id": document["id"],
            "ordinal": 0,
            "kind": "outline",
            "section_path": ["PROCEDURE", "C"],
            "page_start": 1,
            "page_end": 1,
            "body": f"Confidential body text belonging to {label}.",
        },
    )
    question = api.insert_as_service(
        "questions",
        {
            "document_id": document["id"],
            "chunk_id": chunk["id"],
            "type": "true_false",
            "stem": f"A statement only {label} should ever see.",
            "explanation": "Because it is theirs.",
            "correct_answer": True,
        },
    )
    # Saved questions and jobs are seeded purely so the cascade has something to fail to
    # remove. An untouched table proves nothing about a delete that never reached it.
    api.insert_as_service(
        "saved_questions",
        {"user_id": user_id, "question_id": question["id"]},
    )
    api.insert_as_service(
        "jobs",
        {"kind": "ingest", "document_id": document["id"]},
    )
    return {"document": document, "chunk": chunk, "question": question}


def main() -> int:
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_service_role_key):
        sys.exit("Supabase is not configured; set SUPABASE_URL and the keys in .env.")

    api = Api(settings.supabase_url, settings.supabase_anon_key, settings.supabase_service_role_key)
    suffix = uuid.uuid4().hex[:8]
    alice_email = f"rls-probe-a-{suffix}@example.com"
    bob_email = f"rls-probe-b-{suffix}@example.com"
    alice_id = bob_id = None
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name}  {detail}")
            failures.append(name)

    try:
        alice_id = api.create_user(alice_email)
        bob_id = api.create_user(bob_email)
        alice = _seed(api, alice_id, "alice")
        bob = _seed(api, bob_id, "bob")
        alice_token = api.sign_in(alice_email)

        print("\nReading as Alice:\n")

        docs = api.select_as_user(alice_token, "documents")
        check(
            "sees only her own documents",
            [d["id"] for d in docs] == [alice["document"]["id"]],
            f"got {len(docs)} rows",
        )

        bobs_doc = api.select_as_user(
            alice_token, "documents", f"select=*&id=eq.{bob['document']['id']}"
        )
        check("cannot fetch Bob's document by id", bobs_doc == [], f"got {bobs_doc}")

        chunks = api.select_as_user(alice_token, "chunks")
        check(
            "sees only chunks under her own documents",
            [c["id"] for c in chunks] == [alice["chunk"]["id"]],
            f"got {len(chunks)} rows",
        )

        bobs_chunk = api.select_as_user(
            alice_token, "chunks", f"select=*&id=eq.{bob['chunk']['id']}"
        )
        check("cannot fetch Bob's chunk by id", bobs_chunk == [], f"got {bobs_chunk}")

        questions = api.select_as_user(alice_token, "questions")
        check(
            "sees only questions from her own documents",
            [q["id"] for q in questions] == [alice["question"]["id"]],
            f"got {len(questions)} rows",
        )

        jobs = api.select_as_user(alice_token, "jobs")
        check("cannot read the job queue at all", jobs == [], f"got {jobs}")

        profiles = api.select_as_user(alice_token, "profiles")
        check(
            "sees only her own profile",
            [p["id"] for p in profiles] == [alice_id],
            f"got {len(profiles)} rows",
        )

        print("\nWriting as Alice:\n")

        forged = api.insert_as_user(
            alice_token,
            "documents",
            {
                "user_id": bob_id,
                "filename": "forged.pdf",
                "storage_path": "forged.pdf",
            },
        )
        check(
            "cannot create a document owned by Bob",
            forged.status_code >= 400,
            f"status {forged.status_code}",
        )

        authored = api.insert_as_user(
            alice_token,
            "questions",
            {
                "document_id": alice["document"]["id"],
                "chunk_id": alice["chunk"]["id"],
                "type": "true_false",
                "stem": "A question the candidate wrote themselves.",
                "explanation": "Should not be permitted.",
                "correct_answer": True,
            },
        )
        check(
            "cannot author a question, even on her own document",
            authored.status_code >= 400,
            f"status {authored.status_code}",
        )

        # The store-billing equivalent of the profiles lesson in 0005. That migration
        # exists because a candidate could PATCH their own profile row to 'active' until
        # 2099 using nothing but their own token. store_purchases (0008) holds exactly the
        # same kind of value, so the refusal is verified against the live database rather
        # than assumed from the migration having been written.
        self_granted = api.insert_as_user(
            alice_token,
            "store_purchases",
            {
                "user_id": alice_id,
                "platform": "appstore",
                "product_id": "badgeday.promote.monthly",
                "purchase_identifier": "invented-by-the-candidate",
                "kind": "subscription",
                "status": "active",
            },
        )
        check(
            "cannot grant herself a store subscription",
            self_granted.status_code >= 400,
            f"status {self_granted.status_code}",
        )

        print("\nSignup trigger:\n")
        check("profile row was created automatically", len(profiles) == 1)

        # --- Constraints ---------------------------------------------------
        # These restate the verification gate at the database level. If they do not
        # reject, the second line of defence does nothing.
        print("\nMalformed rows are rejected:\n")

        malformed = [
            (
                "multiple choice with no options",
                "questions",
                {"type": "multiple_choice", "stem": "S", "explanation": "E"},
            ),
            (
                "multiple choice indexing past the last option",
                "questions",
                {
                    "type": "multiple_choice",
                    "stem": "S",
                    "explanation": "E",
                    "options": ["a", "b", "c"],
                    "correct_index": 9,
                },
            ),
            (
                "true/false carrying a model answer",
                "questions",
                {
                    "type": "true_false",
                    "stem": "S",
                    "explanation": "E",
                    "correct_answer": True,
                    "model_answer": "x",
                },
            ),
            (
                "short answer with no model answer",
                "questions",
                {"type": "short_answer", "stem": "S", "explanation": "E"},
            ),
        ]
        for name, table, payload in malformed:
            response = api.insert_as_service_raw(
                table,
                {
                    **payload,
                    "document_id": alice["document"]["id"],
                    "chunk_id": alice["chunk"]["id"],
                },
            )
            check(name, response.status_code >= 400, f"status {response.status_code}")

        backwards = api.insert_as_service_raw(
            "chunks",
            {
                "id": str(uuid.uuid4()),
                "document_id": alice["document"]["id"],
                "ordinal": 99,
                "kind": "outline",
                "section_path": [],
                "page_start": 5,
                "page_end": 2,
                "body": "x",
            },
        )
        check(
            "chunk ending before it starts",
            backwards.status_code >= 400,
            f"status {backwards.status_code}",
        )

        # --- Coverage ------------------------------------------------------
        print("\nCoverage tracking:\n")

        before = api.coverage(alice["document"]["id"])
        check(
            "counts the document's questionable sections",
            before and before[0]["sections_total"] == 1,
            f"got {before}",
        )
        check(
            "starts at zero exercised",
            before and before[0]["sections_exercised"] == 0,
            f"got {before}",
        )

        session = api.insert_as_service(
            "practice_sessions",
            {"user_id": alice_id, "document_id": alice["document"]["id"]},
        )
        api.insert_as_service(
            "responses",
            {
                "session_id": session["id"],
                "question_id": alice["question"]["id"],
                "user_id": alice_id,
                "answered_boolean": True,
                "is_correct": True,
            },
        )
        after = api.coverage(alice["document"]["id"])
        check(
            "advances once the section has been exercised",
            after and after[0]["sections_exercised"] == 1,
            f"got {after}",
        )

        # --- Cascade -------------------------------------------------------
        # "Delete account (hard-delete user content)" is a V1 scope commitment, and it
        # rests entirely on `on delete cascade` firing along every path out of
        # auth.users. A cascade that silently does not fire leaves a candidate's
        # documents in the database after their account is gone — the promise broken
        # quietly, with nothing in the application to notice.
        #
        # This runs last: it destroys the fixtures every check above depends on.
        print("\nAccount deletion:\n")

        api.delete_user(alice_id)
        alice_document_id = alice["document"]["id"]
        orphans = [
            ("profiles", f"id=eq.{alice_id}"),
            ("documents", f"user_id=eq.{alice_id}"),
            ("chunks", f"document_id=eq.{alice_document_id}"),
            ("questions", f"document_id=eq.{alice_document_id}"),
            ("practice_sessions", f"user_id=eq.{alice_id}"),
            ("responses", f"user_id=eq.{alice_id}"),
            ("saved_questions", f"user_id=eq.{alice_id}"),
            ("jobs", f"document_id=eq.{alice_document_id}"),
            # A store purchase outliving the account it belonged to is both a privacy
            # failure and a billing one: the row is personal data nobody can now reach,
            # and a renewal notification arriving later would update a purchase with no
            # owner rather than being noticed as unattributable.
            ("store_purchases", f"user_id=eq.{alice_id}"),
        ]
        for table, query in orphans:
            rows = api.select_as_service(table, query)
            check(f"leaves no {table} behind", rows == [], f"got {len(rows)} rows")

        # Over-deletion is as much a failure as under-deletion: a cascade wired to the
        # wrong column would take the other candidate's data with it.
        survivors = api.select_as_service("documents", f"user_id=eq.{bob_id}")
        check(
            "leaves the other candidate's documents untouched",
            len(survivors) == 1,
            f"got {len(survivors)} rows",
        )
        alice_id = None

    finally:
        for user_id in (alice_id, bob_id):
            if user_id:
                api.delete_user(user_id)
        print("\nTest users deleted.")

    if failures:
        print(f"\n{len(failures)} CHECK(S) FAILED — data is reachable across users.")
        return 1
    print("\nAll checks passed. Users are isolated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
