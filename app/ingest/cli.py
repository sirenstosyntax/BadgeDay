"""Command-line pipeline: file -> chunks -> questions.

CLI-first by design. The whole pipeline is exercisable against a real document before any
UI, any database, or any auth exists — which is what makes it possible to look at what
the chunker and generator actually produce rather than at what their tests assert.

    badgeday-ingest path/to/sog.pdf
    badgeday-ingest path/to/sog.pdf --generate --count 3
    badgeday-ingest path/to/sog.pdf --generate --section 304.2.1
"""

import argparse
import logging
import sys
from pathlib import Path

from app.config import get_settings
from app.generate.generator import generate_for_chunk
from app.ingest.analyzer import get_analyzer
from app.ingest.chunker import chunk_document


def _print_chunks(chunks: list) -> None:
    print(f"\n{len(chunks)} chunks\n")
    for chunk in chunks:
        title = chunk.section_title or ""
        print(f"{chunk.ordinal:>3}  {chunk.kind:<8}  {chunk.location():<24}  {title}")


def _print_questions(outcome, chunk) -> None:
    header = f"{chunk.location()}  {chunk.section_title or ''}".strip()
    print(f"\n=== {header} ===")

    if outcome.skipped:
        print(f"  skipped: {outcome.skipped_reason}")
        return

    for rejection in outcome.rejections:
        print(f"  rejected [{rejection.code}] {rejection.detail}")

    for question in outcome.questions:
        print(f"\n  [{question.type}] {question.stem}")
        if question.options:
            for index, option in enumerate(question.options):
                marker = "*" if index == question.correct_index else " "
                print(f"     {marker} {option}")
        if question.correct_answer is not None:
            print(f"     answer: {question.correct_answer}")
        if question.model_answer:
            print(f"     model answer: {question.model_answer}")
        print(f"     cite: {question.citation.display()}")
        print(f"     why : {question.explanation}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="badgeday-ingest",
        description="Analyze a document, chunk it, and optionally generate questions.",
    )
    parser.add_argument("path", type=Path, help="PDF or DOCX to ingest")
    parser.add_argument(
        "--generate", action="store_true", help="also generate questions per section"
    )
    parser.add_argument("--count", type=int, default=4, help="questions to request per section")
    parser.add_argument("--section", help="generate for one section number only, e.g. 304.2.1")
    parser.add_argument("--document-id", default="cli", help="document id for chunk IDs")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    # The Azure SDK logs every HTTP exchange at INFO, which buries our own output.
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not args.path.exists():
        print(f"No such file: {args.path}", file=sys.stderr)
        return 1

    settings = get_settings()
    if not settings.azure_docintel_configured:
        print(
            "Azure Document Intelligence is not configured; falling back to fixtures. "
            "Set AZURE_DOCINTEL_ENDPOINT and AZURE_DOCINTEL_KEY in .env to analyze a "
            "real document.",
            file=sys.stderr,
        )

    document = get_analyzer(settings).analyze(args.path)
    chunks = chunk_document(document, args.document_id)
    _print_chunks(chunks)

    if not args.generate:
        return 0

    if not settings.anthropic_api_key:
        print("\nANTHROPIC_API_KEY is not set; cannot generate.", file=sys.stderr)
        return 1

    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)

    targets = chunks
    if args.section:
        targets = [c for c in chunks if c.section_label == args.section]
        if not targets:
            print(f"\nNo section {args.section} in this document.", file=sys.stderr)
            return 1

    total = 0
    for chunk in targets:
        outcome = generate_for_chunk(chunk, client, settings, target_count=args.count)
        _print_questions(outcome, chunk)
        total += len(outcome.questions)

    print(f"\n{total} questions generated across {len(targets)} sections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
