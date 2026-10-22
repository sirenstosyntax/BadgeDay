#!/usr/bin/env python3
"""Fail when a dependency license is not permissive.

Inventories:

- Python packages in the interpreter running this file. ``pip-licenses``
  (pinned in the workflow) is the cross-check that this scan did not drop
  a distribution.
- ``web/package-lock.json`` and ``mobile/ios/package-lock.json``, including
  devDependencies and optional platform packages. ``npm ci --ignore-scripts``
  installs them. ``license-checker-rseidelsohn`` (4.4.2, the release that
  still runs on Node 20) cross-checks the installed tree.
- ``mobile/ios/Gemfile.lock``, from RubyGems metadata. When that metadata is
  missing or not permissive, the license files in the published gem are read.

The allow list is ``.github/license-allowlist.txt``. Reviewed exceptions are
``license-exceptions.toml``. Nothing in that file is pre-approved.
"""

from __future__ import annotations

import gzip
import importlib.metadata as metadata
import io
import json
import os
import re
import subprocess
import sys
import sysconfig
import tarfile
import time
import tomllib
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO / ".github" / "license-allowlist.txt"
REVIEW_CONFIG_PATH = REPO / ".github" / "dependency-review-config.yml"
EXCEPTIONS_PATH = REPO / "license-exceptions.toml"
USER_AGENT = "badgeday-license-check"
CHECKER_PACKAGES = {"pip-licenses", "prettytable", "wcwidth"}
NPM_PROJECTS = (REPO / "web", REPO / "mobile" / "ios")
GEMFILE_LOCK = REPO / "mobile" / "ios" / "Gemfile.lock"
LICENSE_CHECKER = "license-checker-rseidelsohn@4.4.2"
COPYLEFT_WORD = re.compile(r"\b(AGPL|EUPL|EPL|GPL|LGPL|MPL|SSPL)\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"\(|\)|\bOR\b|\bAND\b|\bWITH\b|[A-Za-z0-9][A-Za-z0-9.+-]*")
UNKNOWN_IDS = {"", "UNKNOWN", "NOASSERTION", "UNLICENSED", "NONE", "SEE LICENSE IN LICENSE"}
VAGUE_IDS = {"BSD", "BSD-LICENSE", "LICENSE"}
# Longest first. Applied only to short license expressions, not to license prose.
REPLACEMENTS = (
    ("Mozilla Public License 2.0 (MPL 2.0)", "MPL-2.0"),
    ("Apache License, Version 2.0", "Apache-2.0"),
    ("Apache Software License", "Apache-2.0"),
    ("3-Clause BSD License", "BSD-3-Clause"),
    ("BSD 3-Clause", "BSD-3-Clause"),
    ("BSD 2-Clause", "BSD-2-Clause"),
    ("MIT License", "MIT"),
    ("Apache 2.0", "Apache-2.0"),
    ("Apache 2", "Apache-2.0"),
    ("ISC License", "ISC"),
    ("LGPL v3", "LGPL-3.0-only"),
    ("GPL-2.0", "GPL-2.0-only"),
    ("GPL-3.0", "GPL-3.0-only"),
    ("LGPL-2.1", "LGPL-2.1-only"),
    ("LGPL-3.0", "LGPL-3.0-only"),
    ("AGPL-3.0", "AGPL-3.0-only"),
)
# Replacements that must not rewrite an already-suffixed SPDX id.
SUFFIXED = ("GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
            "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
            "AGPL-3.0-only", "AGPL-3.0-or-later")
CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)": "LGPL-2.0-only",
    "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)": (
        "LGPL-3.0-only"
    ),
}


@dataclass
class Finding:
    ecosystem: str
    name: str
    version: str
    expression: str
    status: str
    role: str
    required_by: list[str] = field(default_factory=list)
    notes: str = ""

    def sort_key(self) -> tuple:
        order = {"fail": 0, "excepted": 1, "dual": 2, "pass": 3}
        return (order.get(self.status, 9), self.ecosystem, self.name.lower(), self.version)


def load_allowlist(path: Path) -> set[str]:
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.add(line)
    if "MIT" not in ids or "Apache-2.0" not in ids:
        raise SystemExit(f"{path} is missing the permissive licenses the policy names")
    return ids


def allowlist_in_review_config(path: Path) -> set[str]:
    ids: set[str] = set()
    in_block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].rstrip()
        if stripped.strip() == "allow-licenses:":
            in_block = True
            continue
        if not in_block:
            continue
        if stripped.startswith("  - "):
            ids.add(stripped[4:].strip().strip("'\""))
            continue
        if stripped.strip():
            break
    return ids


def assert_review_config(allow: set[str]) -> None:
    configured = allowlist_in_review_config(REVIEW_CONFIG_PATH)
    if configured != allow:
        missing = sorted(allow - configured)
        extra = sorted(configured - allow)
        raise SystemExit(
            "dependency-review allow-licenses drifted from license-allowlist.txt: "
            f"missing={missing} extra={extra}"
        )


@dataclass
class ExceptionRow:
    ecosystem: str
    package: str
    license: str
    reason: str
    reviewer: str
    date: str
    version: str


def load_exceptions(path: Path, allow: set[str]) -> list[ExceptionRow]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_rows = data.get("exception", [])
    if not isinstance(raw_rows, list):
        raise SystemExit("license-exceptions.toml: exception must be a list of tables")
    rows: list[ExceptionRow] = []
    required = ("ecosystem", "package", "license", "reason", "date")
    for index, row in enumerate(raw_rows, start=1):
        if not isinstance(row, dict):
            raise SystemExit(f"license-exceptions.toml row {index} is not a table")
        unknown = set(row) - set(required) - {"version", "reviewer", "approved_by"}
        if unknown:
            fields = ", ".join(sorted(unknown))
            raise SystemExit(f"license-exceptions.toml row {index} has unknown fields: {fields}")
        for key in required:
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                raise SystemExit(f"license-exceptions.toml row {index} is missing {key}")
        approved_by = row.get("approved_by", row.get("reviewer", ""))
        reviewer_field = row.get("reviewer", "")
        if not isinstance(approved_by, str) or not approved_by.strip():
            raise SystemExit(f"license-exceptions.toml row {index} is missing approved_by")
        if (
            isinstance(reviewer_field, str)
            and reviewer_field.strip()
            and reviewer_field.strip() != approved_by.strip()
        ):
            raise SystemExit(
                f"license-exceptions.toml row {index} approved_by and reviewer disagree"
            )
        if row["ecosystem"] not in {"pypi", "npm", "gem"}:
            raise SystemExit(
                f"license-exceptions.toml row {index} ecosystem must be pypi, npm, or gem"
            )
        if len(row["reason"].strip()) < 20:
            raise SystemExit(
                f"license-exceptions.toml row {index} reason is too short to be a review"
            )
        try:
            date.fromisoformat(row["date"])
        except ValueError as exc:
            raise SystemExit(
                f"license-exceptions.toml row {index} date must be YYYY-MM-DD"
            ) from exc
        try:
            parse_expression(row["license"])
        except ValueError as exc:
            raise SystemExit(f"license-exceptions.toml row {index} license: {exc}") from exc
        canonical = canonical_expression(row["license"])
        if _satisfiable(parse_expression(row["license"]), allow) and " OR " not in canonical:
            raise SystemExit(
                f"license-exceptions.toml row {index} is already on the allow list ({canonical})"
            )
        version = row.get("version", "")
        if not isinstance(version, str) or not version.strip():
            raise SystemExit(
                f"license-exceptions.toml row {index} version is required and pins the review"
            )
        rows.append(
            ExceptionRow(
                ecosystem=row["ecosystem"],
                package=row["package"].strip(),
                license=canonical,
                reason=row["reason"].strip(),
                reviewer=approved_by.strip(),
                date=row["date"],
                version=version.strip() if isinstance(version, str) else "",
            )
        )
    return rows


def preprocess(expression: str) -> str:
    text = " ".join(expression.replace(";", " OR ").split())
    # Keep already-precise ids stable while the shorter aliases are replaced.
    shields: dict[str, str] = {}
    for index, token in enumerate(SUFFIXED):
        marker = f"__SPDX{index}__"
        if token in text:
            shields[marker] = token
            text = text.replace(token, marker)
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    for marker, token in shields.items():
        text = text.replace(marker, token)
    text = re.sub(
        r"\b(or|and|with)\b",
        lambda match: match.group(1).upper(),
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def parse_expression(expression: str) -> list[list[tuple[str, str | None]]]:
    """Return disjunctive normal form: OR of AND-groups of (id, exception)."""
    text = preprocess(expression)
    if not text:
        raise ValueError("empty license expression")
    tokens = TOKEN_RE.findall(text)
    if not tokens:
        raise ValueError(f"unparseable license expression: {expression!r}")
    # Reject leftover characters so "MIT, Apache" cannot pass as MIT.
    consumed = TOKEN_RE.sub("", text)
    if consumed.strip():
        raise ValueError(f"unparseable license expression: {expression!r}")
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def eat(expected: str | None = None) -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError(f"truncated license expression: {expression!r}")
        token = tokens[pos]
        pos += 1
        if expected is not None and token != expected:
            raise ValueError(f"expected {expected} in {expression!r}")
        return token

    def parse_or() -> list[list[tuple[str, str | None]]]:
        groups = parse_and()
        while peek() == "OR":
            eat("OR")
            groups.extend(parse_and())
        return groups

    def parse_and() -> list[list[tuple[str, str | None]]]:
        groups = parse_with()
        while peek() == "AND":
            eat("AND")
            # Parse the right-hand side once. Calling it inside the
            # comprehension would consume tokens once per left-hand group.
            right = parse_with()
            groups = [left + extra for left in groups for extra in right]
        return groups

    def parse_with() -> list[list[tuple[str, str | None]]]:
        groups = parse_primary()
        if peek() == "WITH":
            eat("WITH")
            exception = eat()
            if exception in {"OR", "AND", "WITH", "(", ")"}:
                raise ValueError(f"WITH without an exception in {expression!r}")
            if len(groups) != 1 or len(groups[0]) != 1:
                raise ValueError(f"WITH must follow a single license in {expression!r}")
            ident, _ = groups[0][0]
            groups = [[(ident, exception)]]
        return groups

    def parse_primary() -> list[list[tuple[str, str | None]]]:
        token = eat()
        if token == "(":
            groups = parse_or()
            eat(")")
            return groups
        if token in {"OR", "AND", "WITH", ")"}:
            raise ValueError(f"unexpected {token} in {expression!r}")
        return [[(token, None)]]

    groups = parse_or()
    if pos != len(tokens):
        raise ValueError(f"trailing tokens in {expression!r}")
    return groups


def canonical_expression(expression: str) -> str:
    groups = []
    for group in parse_expression(expression):
        atoms = []
        for ident, exception in group:
            atoms.append(ident if exception is None else f"{ident} WITH {exception}")
        rendered = " AND ".join(sorted(atoms))
        groups.append(rendered)
    unique_groups = sorted(set(groups))
    if len(unique_groups) == 1:
        return unique_groups[0]
    parts = []
    for group in unique_groups:
        parts.append(f"({group})" if " AND " in group else group)
    return " OR ".join(parts)


def _satisfiable(groups: list[list[tuple[str, str | None]]], allow: set[str]) -> bool:
    return any(all(ident in allow for ident, _exception in group) for group in groups)


def _unknown(groups: list[list[tuple[str, str | None]]]) -> bool:
    for group in groups:
        for ident, _exception in group:
            if ident.upper() in UNKNOWN_IDS or ident.startswith("LicenseRef-"):
                return True
    return False


def classify(expression: str, allow: set[str]) -> tuple[str, str]:
    """Return (status, canonical). status is pass, dual, or fail."""
    try:
        groups = parse_expression(expression)
        canonical = canonical_expression(expression)
    except ValueError:
        return "fail", expression.strip() or "UNKNOWN"
    if _unknown(groups) or not _satisfiable(groups, allow):
        return "fail", canonical
    idents = {ident for group in groups for ident, _exception in group}
    if len(idents) > 1:
        return "dual", canonical
    return "pass", canonical


def self_test(allow: set[str]) -> None:
    expected = {
        "MIT": ("pass", "MIT"),
        "Apache-2.0 OR BSD-3-Clause": ("dual", "Apache-2.0 OR BSD-3-Clause"),
        "BSD 3-Clause OR Apache-2.0": ("dual", "Apache-2.0 OR BSD-3-Clause"),
        "LGPL-3.0-only": ("fail", "LGPL-3.0-only"),
        "MIT OR GPL-2.0-only": ("dual", "GPL-2.0-only OR MIT"),
        "GPL-2.0-only OR Ruby": ("fail", "GPL-2.0-only OR Ruby"),
        "MIT AND GPL-2.0-only": ("fail", "GPL-2.0-only AND MIT"),
        "MPL-2.0": ("fail", "MPL-2.0"),
        "UNKNOWN": ("fail", "UNKNOWN"),
        "BSD-2-Clause OR Ruby": ("dual", "BSD-2-Clause OR Ruby"),
        "(BSD-2-Clause OR Ruby) AND (EPL-2.0 OR LGPL-2.1-only)": (
            "fail",
            "(BSD-2-Clause AND EPL-2.0) OR (BSD-2-Clause AND LGPL-2.1-only) OR "
            "(EPL-2.0 AND Ruby) OR (LGPL-2.1-only AND Ruby)",
        ),
        "(MIT OR Apache-2.0) AND BSD-3-Clause": (
            "dual",
            "(Apache-2.0 AND BSD-3-Clause) OR (BSD-3-Clause AND MIT)",
        ),
        "Python-2.0": ("pass", "Python-2.0"),
        "PSF-2.0": ("pass", "PSF-2.0"),
        "0BSD": ("pass", "0BSD"),
        "ISC": ("pass", "ISC"),
        "Unlicense": ("pass", "Unlicense"),
        "SSPL-1.0": ("fail", "SSPL-1.0"),
        "AGPL-3.0-only": ("fail", "AGPL-3.0-only"),
        "EPL-2.0": ("fail", "EPL-2.0"),
    }
    for expression, want in expected.items():
        got = classify(expression, allow)
        if got != want:
            raise SystemExit(f"license parser self-test failed for {expression!r}: {got} != {want}")
    forbidden_ids = (
        "GPL-3.0-only",
        "AGPL-3.0-only",
        "LGPL-2.1-only",
        "MPL-2.0",
        "Ruby",
        "SSPL-1.0",
    )
    for forbidden in forbidden_ids:
        if forbidden in allow:
            raise SystemExit(f"{forbidden} must not be on the allow list")
    _assert_version_pin()


def _assert_version_pin() -> None:
    """An exception version matches that release only."""
    pinned = Finding(
        ecosystem="pypi",
        name="certifi",
        version="2026.10.19",
        expression="MPL-2.0",
        status="fail",
        role="transitive",
    )
    other = Finding(
        ecosystem="pypi",
        name="certifi",
        version="2099.1.1",
        expression="MPL-2.0",
        status="fail",
        role="transitive",
    )
    row = ExceptionRow(
        ecosystem="pypi",
        package="certifi",
        license="MPL-2.0",
        reason="Mozilla CA bundle, used unmodified.",
        reviewer="Grant",
        date="2026-10-22",
        version="2026.10.19",
    )
    problems = apply_exceptions([pinned, other], [row])
    if pinned.status != "excepted" or other.status != "fail" or problems:
        raise SystemExit(f"version pin self-test failed: {pinned.status} {other.status} {problems}")


def fetch_bytes(url: str) -> bytes:
    delay = 0.5
    last: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise
        except urllib.error.URLError as exc:
            last = exc
            if attempt == 3:
                raise
        time.sleep(delay)
        delay *= 2
    assert last is not None
    raise last


def fetch_json(url: str) -> object:
    return json.loads(fetch_bytes(url).decode("utf-8"))


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def detect_license_ids(text: str) -> list[str]:
    ids: list[str] = []
    for match in re.finditer(r"SPDX-License-Identifier:\s*([^\n*]+)", text, flags=re.IGNORECASE):
        ids.append(match.group(1).strip().rstrip("*/ ").strip())
    if "Permission is hereby granted, free of charge" in text and (
        "The above copyright notice and this permission notice" in text
        or "The above copyright notice and this permission notice shall be included" in text
    ):
        ids.append("MIT")
    if "Apache License" in text and "Version 2.0, January 2004" in text:
        ids.append("Apache-2.0")
    if "Redistribution and use in source and binary forms" in text:
        if re.search(r"\badvertis", text, flags=re.IGNORECASE):
            ids.append("BSD-4-Clause")
        elif (
            "Neither the name" in text
            or "used to endorse" in text
            or "may be used to endorse" in text
        ):
            ids.append("BSD-3-Clause")
        else:
            ids.append("BSD-2-Clause")
    if "Boost Software License" in text:
        ids.append("BSL-1.0")
    return unique(ids)


def join_license_ids(ids: list[str]) -> str:
    cleaned = unique(ids)
    if not cleaned:
        return "UNKNOWN"
    if len(cleaned) == 1:
        return cleaned[0]
    return " OR ".join(cleaned)


def _read_dist_file(dist: metadata.Distribution, entry: metadata.PackagePath) -> str:
    try:
        return entry.read_text(encoding="utf-8")
    except UnicodeError:
        try:
            # PackagePath is a PurePosixPath: read_binary, not pathlib's read_bytes.
            return entry.read_binary().decode("utf-8", "replace")
        except OSError as exc:
            raise SystemExit(
                f"unreadable license file {entry} in {dist.metadata['Name']}: {exc}"
            ) from exc
    except OSError as exc:
        raise SystemExit(
            f"unreadable license file {entry} in {dist.metadata['Name']}: {exc}"
        ) from exc


def _is_license_path(rel: str) -> tuple[bool, bool]:
    """Return (is a license file, lives in the dist-info licenses directory)."""
    normalized = rel.replace("\\", "/").lower()
    base = normalized.rsplit("/", 1)[-1]
    if base in {"notice", "notice.md", "notice.txt", "notice.rst"}:
        return False, False
    named = "license" in base or base in {"copying", "copying.txt"}
    in_license_dir = "/licenses/" in f"/{normalized}" or normalized.startswith("licenses/")
    # ``*.dist-info/LICENSE`` is the distribution's license. A LICENSE file
    # nested in the package tree is vendored and is not unioned in.
    parent = normalized.rsplit("/", 1)[0]
    distinfo_root = parent.endswith(".dist-info")
    in_distinfo = ".dist-info/licenses/" in f"/{normalized}" or (named and distinfo_root)
    return named or in_license_dir, in_distinfo


def python_expression(dist: metadata.Distribution, allow: set[str]) -> tuple[str, str]:
    raw = " ".join((dist.metadata.get("License") or "").split())
    declared = (dist.metadata.get("License-Expression") or "").strip()
    field_expression = ""
    precise = ""
    if not declared and raw and len(raw) <= 160 and not raw.lower().startswith("copyright"):
        if re.search(r"\b(or|and|with)\b", raw, flags=re.IGNORECASE):
            field_expression = raw
        else:
            token = preprocess(raw)
            if token not in VAGUE_IDS and " " not in token:
                precise = token
    distinfo_ids: list[str] = []
    package_ids: list[str] = []
    if dist.files:
        for entry in dist.files:
            is_license, in_distinfo = _is_license_path(str(entry))
            if not is_license:
                continue
            found = detect_license_ids(_read_dist_file(dist, entry))
            if in_distinfo:
                distinfo_ids.extend(found)
            else:
                package_ids.extend(found)
    distinfo_ids = unique(distinfo_ids)
    package_ids = unique(package_ids)
    class_ids = unique(
        CLASSIFIERS[item]
        for item in (dist.metadata.get_all("Classifier") or [])
        if item in CLASSIFIERS and CLASSIFIERS[item] not in VAGUE_IDS
    )
    vague_bsd = any(
        CLASSIFIERS.get(item) == "BSD" for item in (dist.metadata.get_all("Classifier") or [])
    )
    notes = ""
    if declared:
        expression = declared
    elif field_expression:
        expression = field_expression
    elif precise:
        expression = precise
        # Classifiers name a second license the License field omitted (uvloop
        # is MIT in the field and also ships Apache-2.0). Vendored LICENSE
        # files under the package tree do not, or a BSD notice inside an
        # Apache project would look like a dual license.
        added = [ident for ident in class_ids if ident not in expression]
        permissive = [ident for ident in added if classify(ident, allow)[0] != "fail"]
        if permissive:
            expression = join_license_ids([expression, *permissive])
    elif distinfo_ids:
        expression = join_license_ids(distinfo_ids)
    elif class_ids:
        expression = join_license_ids(class_ids)
    else:
        # The License field sometimes holds the full license text (isodate)
        # rather than an SPDX id. Classify that text before the generic
        # "BSD License" classifier, which does not say which clause.
        detected = detect_license_ids(raw) if raw else []
        if detected:
            expression = join_license_ids(detected)
        elif vague_bsd:
            expression = "BSD"
            notes = "Trove classifier is the generic BSD license, with no SPDX identifier"
        else:
            expression = "UNKNOWN"
            notes = "no license metadata"
    hostile = [
        ident
        for ident in unique(distinfo_ids + package_ids + class_ids)
        if ident not in expression and classify(ident, allow)[0] == "fail"
    ]
    if hostile:
        extra = " AND ".join(hostile)
        if " " in expression:
            expression = f"({expression}) AND {extra}"
        else:
            expression = f"{expression} AND {extra}"
        notes = (notes + " non-permissive license file in the distribution").strip()
    return expression, notes


def assert_readable_tree(root: Path) -> None:
    """Fail if a directory in an installed tree cannot be listed or stated.

    ``os.walk`` skips unreadable directories unless ``onerror`` is set. A
    skipped folder would hide whatever package was inside it.
    """
    if not root.is_dir():
        raise SystemExit(f"dependency tree is not a directory: {root}")
    problems: list[str] = []

    def onerror(err: OSError) -> None:
        filename = getattr(err, "filename", None) or root
        problems.append(f"{filename}: {err.strerror or err}")

    for dirpath, _dirnames, filenames in os.walk(root, onerror=onerror):
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                path.stat()
            except OSError as exc:
                problems.append(f"{path}: {exc.strerror or exc}")
    if problems:
        shown = "\n".join(problems[:40])
        extra = ""
        if len(problems) > 40:
            extra = f"\n(+{len(problems) - 40} more)"
        raise SystemExit(f"unreadable path under {root} (not skipped):\n{shown}{extra}")


def _same_directory(left: str, right: Path) -> bool:
    """True when both paths are the same directory.

    An unreadable path fails the run. Treating it as "different" would skip
    the failure and could hide the package that lives there.
    """
    try:
        return Path(left).resolve() == right.resolve()
    except OSError as exc:
        raise SystemExit(f"unreadable package path {left}: {exc}") from exc


def environment_roots() -> list[Path]:
    roots: list[Path] = []
    for key in ("purelib", "platlib"):
        path = Path(sysconfig.get_paths()[key])
        if path.is_dir() and path not in roots:
            roots.append(path)
    if not roots:
        raise SystemExit("Python site-packages could not be located")
    return roots


def project_name() -> str:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["name"]).lower()


def requirement_parts(spec: str) -> tuple[str, set[str], str | None]:
    body, _, marker = spec.partition(";")
    match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*(?:\[([^\]]*)\])?", body)
    if not match:
        return "", set(), None
    name = match.group(1).lower()
    extras = {item.strip().lower() for item in (match.group(2) or "").split(",") if item.strip()}
    extra_match = re.search(r"extra\s*==\s*['\"]([^'\"]+)['\"]", marker)
    marker_extra = extra_match.group(1).lower() if extra_match else None
    return name, extras, marker_extra


def scan_python(allow: set[str]) -> list[Finding]:
    print("scanning Python environment", file=sys.stderr)
    for root in environment_roots():
        assert_readable_tree(root)
    ours = project_name()
    distributions = {dist.metadata["Name"].lower(): dist for dist in metadata.distributions()}
    distributions.pop(ours, None)
    for checker in CHECKER_PACKAGES:
        distributions.pop(checker, None)

    requires: dict[str, list[tuple[str, set[str], str | None]]] = {}
    for name, dist in distributions.items():
        parsed = []
        for spec in dist.requires or []:
            dep, extras, marker_extra = requirement_parts(spec)
            if dep:
                parsed.append((dep, extras, marker_extra))
        requires[name] = parsed
    project = metadata.distribution(ours)
    project_reqs = []
    for spec in project.requires or []:
        dep, extras, marker_extra = requirement_parts(spec)
        if dep:
            project_reqs.append((dep, extras, marker_extra))

    def walk(dev_roots: bool) -> set[str]:
        enabled: dict[str, set[str]] = defaultdict(set)
        seen: set[str] = set()
        queue: list[str] = []
        for dep, extras, marker_extra in project_reqs:
            is_dev = marker_extra == "dev"
            if dev_roots != is_dev:
                continue
            if marker_extra not in (None, "dev"):
                continue
            enabled[dep].update(extras)
            queue.append(dep)
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            seen.add(name)
            for dep, extras, marker_extra in requires.get(name, []):
                if marker_extra and marker_extra not in enabled[name]:
                    continue
                enabled[dep].update(extras)
                queue.append(dep)
        return seen

    runtime = walk(dev_roots=False)
    dev = walk(dev_roots=True)
    direct_runtime = {dep for dep, _extras, marker in project_reqs if marker is None}
    direct_dev = {dep for dep, _extras, marker in project_reqs if marker == "dev"}

    required_by: dict[str, list[str]] = defaultdict(list)
    for name, specs in requires.items():
        for dep, _extras, _marker in specs:
            required_by[dep].append(name)
    for dep, _extras, _marker in project_reqs:
        required_by[dep].append(ours)

    inventory = json.loads(
        subprocess.check_output(
            [sys.executable, "-m", "piplicenses", "--format=json", "--with-system", "--from=mixed"],
            text=True,
        )
    )
    seen_by_tool = {str(row["Name"]).lower() for row in inventory}
    skipped = sorted(seen_by_tool - set(distributions) - CHECKER_PACKAGES - {ours})
    if skipped:
        raise SystemExit(f"pip-licenses reported packages the metadata scan dropped: {skipped}")

    findings: list[Finding] = []
    by_name: dict[str, Finding] = {}
    for name, dist in sorted(distributions.items()):
        expression, notes = python_expression(dist, allow)
        status, canonical = classify(expression, allow)
        if name in direct_runtime:
            role = "direct"
        elif name in runtime:
            role = "transitive"
        elif name in direct_dev:
            role = "direct-dev"
        elif name in dev:
            role = "transitive-dev"
        else:
            role = "environment"
        finding = Finding(
            ecosystem="pypi",
            name=dist.metadata["Name"],
            version=dist.version,
            expression=canonical,
            status=status,
            role=role,
            required_by=sorted(set(required_by.get(name, []))),
            notes=notes,
        )
        findings.append(finding)
        by_name[name] = finding

    for row in inventory:
        name = str(row["Name"]).lower()
        if name in CHECKER_PACKAGES or name == ours or name not in by_name:
            continue
        tool_license = str(row.get("License") or "")
        if COPYLEFT_WORD.search(tool_license) and by_name[name].status in {"pass", "dual"}:
            by_name[name].status = "fail"
            by_name[name].notes = (
                f"pip-licenses reports {tool_license!r} but metadata classified as "
                f"{by_name[name].expression}"
            )
    return findings


def npm_license_to_expression(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, str):
        guessed = "*" in value
        cleaned = value.replace("*", "").strip()
        if not cleaned:
            return "UNKNOWN"
        if guessed:
            return cleaned
        return cleaned
    if isinstance(value, dict):
        return str(value.get("type") or "UNKNOWN")
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("type") or "UNKNOWN"))
            else:
                parts.append(str(item))
        return " AND ".join(parts) if parts else "UNKNOWN"
    return "UNKNOWN"


def lockfile_packages(lock_path: Path) -> list[dict]:
    document = json.loads(lock_path.read_text(encoding="utf-8"))
    rows = []
    for key, meta in document.get("packages", {}).items():
        if not key.startswith("node_modules/"):
            continue
        name = key.split("node_modules/")[-1]
        version = meta.get("version")
        if not version:
            continue
        rows.append(
            {
                "name": name,
                "version": str(version),
                "license": meta.get("license"),
                "dev": bool(meta.get("dev")),
                "optional": bool(meta.get("optional")),
                "depends": list(meta.get("dependencies") or {}),
            }
        )
    return rows


def scan_npm(allow: set[str]) -> list[Finding]:
    print("scanning npm lockfiles", file=sys.stderr)
    wanted: dict[tuple[str, str], dict] = {}
    for project in NPM_PROJECTS:
        lock = project / "package-lock.json"
        if not lock.exists():
            raise SystemExit(f"missing {lock}")
        if not (project / "node_modules").exists():
            raise SystemExit(f"{project} has no node_modules; run npm ci before the license check")
        assert_readable_tree(project / "node_modules")
        manifest = json.loads((project / "package.json").read_text(encoding="utf-8"))
        direct = set(manifest.get("dependencies") or {})
        direct_dev = set(manifest.get("devDependencies") or {})
        for row in lockfile_packages(lock):
            slot = wanted.setdefault(
                (row["name"], row["version"]),
                {**row, "projects": set(), "direct": set(), "dev_flags": [], "opt_flags": []},
            )
            slot["projects"].add(project.name if project.name != "ios" else "capacitor-ios")
            slot["dev_flags"].append(row["dev"])
            slot["opt_flags"].append(row["optional"])
            if row["name"] in direct:
                slot["direct"].add("direct")
            elif row["name"] in direct_dev:
                slot["direct"].add("direct-dev")
            else:
                slot["direct"].add("transitive")

    def registry_license(item: tuple[str, str]) -> tuple[tuple[str, str], str, str]:
        name, version = item
        url = f"https://registry.npmjs.org/{name.replace('/', '%2f')}/{version}"
        try:
            payload = fetch_json(url)
        except urllib.error.HTTPError as exc:
            return item, "UNKNOWN", f"npm registry HTTP {exc.code}"
        if not isinstance(payload, dict):
            return item, "UNKNOWN", "npm registry returned no metadata"
        return item, npm_license_to_expression(payload.get("license")), ""

    licenses: dict[tuple[str, str], tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(registry_license, key) for key in wanted]
        for future in as_completed(futures):
            key, expression, note = future.result()
            licenses[key] = (expression, note)

    checker_notes = cross_check_npm(licenses)
    findings = []
    for key, row in sorted(wanted.items()):
        expression, note = licenses[key]
        if key in checker_notes:
            checker_expression, checker_note = checker_notes[key]
            checker_status, _canonical = classify(checker_expression, allow)
            our_status, _canonical = classify(expression, allow)
            if checker_status == "fail" and our_status != "fail":
                expression = checker_expression
                note = checker_note
            elif checker_note and checker_expression.replace("*", "") != expression:
                note = (note + " " + checker_note).strip()
        status, canonical = classify(expression, allow)
        if "direct" in row["direct"]:
            role = "direct"
        elif "direct-dev" in row["direct"]:
            role = "direct-dev"
        elif row["dev_flags"] and all(row["dev_flags"]):
            role = "transitive-dev"
        else:
            role = "transitive"
        if row["opt_flags"] and all(row["opt_flags"]):
            role += "-optional"
        findings.append(
            Finding(
                ecosystem="npm",
                name=row["name"],
                version=row["version"],
                expression=canonical,
                status=status,
                role=role,
                required_by=sorted(row["projects"]),
                notes=note,
            )
        )
    return findings


def cross_check_npm(
    licenses: dict[tuple[str, str], tuple[str, str]],
) -> dict[tuple[str, str], tuple[str, str]]:
    notes: dict[tuple[str, str], tuple[str, str]] = {}
    for project in NPM_PROJECTS:
        print(f"license-checker {project.relative_to(REPO)}", file=sys.stderr)
        # --ignore-scripts: installing the checker must not run package scripts.
        # Do not pass --production or --excludePrivatePackages. Dev dependencies
        # are in scope, and a third-party private/UNLICENSED package must fail.
        # The repo's own root is skipped below by path, because package.json
        # here is private and has no SPDX license.
        completed = subprocess.run(
            [
                "npx",
                "--ignore-scripts",
                "--yes",
                LICENSE_CHECKER,
                "--json",
                "--start",
                str(project),
            ],
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(
                f"license-checker failed in {project}:\n{completed.stderr}\n{completed.stdout}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"license-checker did not return JSON in {project}: {exc}") from exc
        for raw_name, meta in payload.items():
            if "@" not in raw_name or not isinstance(meta, dict):
                continue
            name, version = raw_name.rsplit("@", 1)
            # Scoped packages look like @scope/name@version; rsplit keeps the scope.
            if name.startswith("@") and "/" not in name:
                continue
            package_path = meta.get("path")
            if isinstance(package_path, str) and _same_directory(package_path, project):
                # First-party root (private: true / UNLICENSED). Not a dependency.
                continue
            key = (name, version)
            if key not in licenses:
                continue
            value = meta.get("licenses")
            expression = npm_license_to_expression(value)
            guessed = isinstance(value, str) and "*" in value
            ours, _note = licenses[key]
            if guessed and expression == ours:
                continue
            if preprocess(expression) != preprocess(ours):
                notes[key] = (
                    expression,
                    f"license-checker reports {expression!r}; registry reports {ours!r}",
                )
    return notes


def parse_gemfile_lock(path: Path) -> tuple[dict[str, str], dict[str, list[str]], set[str]]:
    versions: dict[str, str] = {}
    depends: dict[str, list[str]] = {}
    direct: set[str] = set()
    current: str | None = None
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith(" "):
            section = line.strip()
            current = None
            continue
        if section == "DEPENDENCIES":
            if line.startswith("  "):
                direct.add(line.strip().split()[0])
            continue
        if section != "GEM":
            continue
        spec = re.match(r"^    (\S+) \(([^)]+)\)\s*$", line)
        if spec:
            current = spec.group(1)
            versions[current] = spec.group(2)
            depends[current] = []
            continue
        dep = re.match(r"^      (\S+)", line)
        if dep and current:
            depends[current].append(dep.group(1))
    return versions, depends, direct


def open_gem(blob: bytes) -> tarfile.TarFile:
    outer = tarfile.open(fileobj=io.BytesIO(blob), mode="r:")
    member = outer.extractfile("data.tar.gz")
    if member is None:
        raise ValueError("gem has no data.tar.gz")
    raw = gzip.decompress(member.read())
    return tarfile.open(fileobj=io.BytesIO(raw), mode="r:")


def gem_markers(archive: tarfile.TarFile) -> dict[str, bool]:
    markers = {
        "mpl_data": False,
        "epl_lgpl": False,
        "spdx": "",
        "bsd_or_ruby": False,
        "gpl_or_ruby": False,
        "bsd_text": False,
        "mit_text": False,
        "gpl_text": False,
    }
    spdx_found: list[str] = []
    for member in archive.getmembers():
        if not member.isfile() or member.size > 5_000_000:
            continue
        extracted = archive.extractfile(member)
        if extracted is None:
            continue
        data = extracted.read()
        name = member.name.rsplit("/", 1)[-1].lower()
        if name == "public_suffix_list.dat" and b"Mozilla Public" in data:
            markers["mpl_data"] = True
        # License phrases, not substrings. "epl" inside ordinary words is ignored.
        head = data[:8000]
        if b"EPL 2.0/LGPL 2.1" in head or (
            b"Eclipse Public License" in head and b"Lesser General Public License" in head
        ):
            markers["epl_lgpl"] = True
        if b"GNU GENERAL PUBLIC LICENSE" in head:
            markers["gpl_text"] = True
        if b"SPDX-License-Identifier:" in head:
            text = head.decode("utf-8", "replace")
            match = re.search(r"SPDX-License-Identifier:\s*([^\n*]+)", text)
            if match:
                spdx_found.append(match.group(1).strip())
        license_name = name in {
            "copying",
            "license",
            "license.txt",
            "license.md",
            "mit-license",
            "bsdl",
            "legal",
        }
        if license_name or "license" in name:
            text = data.decode("utf-8", "replace")
            if "2-clause BSDL" in text and re.search(r"\beither\b", text, flags=re.IGNORECASE):
                markers["bsd_or_ruby"] = True
            if re.search(r"GPL Version 2", text) and re.search(r"Ruby", text) and re.search(
                r"choice|either", text, flags=re.IGNORECASE
            ):
                markers["gpl_or_ruby"] = True
            if "Redistribution and use in source and binary forms" in text:
                markers["bsd_text"] = True
            if "Permission is hereby granted, free of charge" in text:
                markers["mit_text"] = True
    if spdx_found:
        markers["spdx"] = spdx_found[0]
    return markers


def decide_gem(
    declared: list[str],
    markers: dict[str, bool] | None,
    allow: set[str],
) -> tuple[str, str]:
    normalized = unique(preprocess(item) for item in declared if item and str(item).strip())
    permissive = [item for item in normalized if item in allow]
    if normalized and len(permissive) == len(normalized):
        note = "gemspec lists more than one permissive license" if len(normalized) > 1 else ""
        return join_license_ids(normalized), note
    if markers is None:
        joined = " AND ".join(normalized) if normalized else "UNKNOWN"
        return joined, "could not read the published gem"
    if markers["spdx"]:
        expression = markers["spdx"]
        note = "SPDX-License-Identifier in the published gem"
        if markers["mpl_data"] and "MPL-2.0" not in expression:
            expression = f"({expression}) AND MPL-2.0"
            note += "; vendors an MPL-2.0 public suffix list"
        return expression, note
    if markers["bsd_or_ruby"]:
        expression = "BSD-2-Clause OR Ruby"
        note = "COPYING offers BSD-2-Clause or the Ruby license"
        if markers["epl_lgpl"]:
            expression = f"({expression}) AND (EPL-2.0 OR LGPL-2.1-only)"
            note += "; JRuby sources in the gem are EPL-2.0 or LGPL-2.1"
        if markers["mpl_data"]:
            expression = f"({expression}) AND MPL-2.0"
            note += "; vendors an MPL-2.0 public suffix list"
        return expression, note
    if markers["gpl_or_ruby"] or (markers["gpl_text"] and "Ruby" in normalized):
        return "GPL-2.0-only OR Ruby", "license text offers GPL-2.0-only or the Ruby license"
    if markers["mpl_data"]:
        ids = unique(normalized + ["MPL-2.0"])
        return " AND ".join(ids), "vendors data/public_suffix_list.dat under MPL-2.0"
    ruby_family = set(normalized) <= {"Ruby", "BSD-2-Clause", "BSD-3-Clause"} and bool(normalized)
    if ruby_family and markers["bsd_text"] and not markers["gpl_text"] and not markers["epl_lgpl"]:
        return join_license_ids(normalized), (
            "Ruby default gem; shipped license file is BSD and gemspec also names Ruby"
        )
    if not normalized and markers["mit_text"]:
        return "MIT", "gemspec has no license; LICENSE file in the gem is MIT"
    if not normalized and markers["bsd_text"]:
        return "BSD-2-Clause", "gemspec has no license; LICENSE file is a BSD license"
    if normalized:
        return " AND ".join(normalized), "gemspec licenses treated as all applying"
    return "UNKNOWN", "no license in the gemspec or the license files"


def scan_gems(allow: set[str]) -> list[Finding]:
    print("scanning RubyGems", file=sys.stderr)
    versions, depends, direct = parse_gemfile_lock(GEMFILE_LOCK)
    required_by: dict[str, list[str]] = defaultdict(list)
    for parent, children in depends.items():
        for child in children:
            required_by[child].append(parent)

    def one(name: str, version: str) -> tuple[str, list[str], str]:
        url = f"https://rubygems.org/api/v2/rubygems/{name}/versions/{version}.json"
        try:
            payload = fetch_json(url)
        except urllib.error.HTTPError as exc:
            return name, [], f"rubygems HTTP {exc.code}"
        if not isinstance(payload, dict):
            return name, [], "rubygems returned no metadata"
        raw = payload.get("licenses")
        if raw is None:
            declared: list[str] = []
        elif isinstance(raw, list):
            declared = [str(item) for item in raw if item]
        else:
            declared = [str(raw)]
        return name, declared, ""

    declared_by: dict[str, tuple[list[str], str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(one, name, version) for name, version in versions.items()]
        for future in as_completed(futures):
            name, declared, note = future.result()
            declared_by[name] = (declared, note)

    def inspect(name: str, version: str) -> tuple[str, dict[str, bool] | None]:
        try:
            archive = open_gem(fetch_bytes(f"https://rubygems.org/gems/{name}-{version}.gem"))
        except (
            urllib.error.URLError,
            ValueError,
            tarfile.TarError,
            gzip.BadGzipFile,
            OSError,
        ) as exc:
            print(f"gem read failed for {name}-{version}: {exc}", file=sys.stderr)
            return name, None
        try:
            return name, gem_markers(archive)
        finally:
            archive.close()

    to_inspect = []
    for name, (declared, _note) in declared_by.items():
        normalized = [preprocess(item) for item in declared]
        if not normalized or any(item not in allow for item in normalized):
            to_inspect.append((name, versions[name]))
    markers_by: dict[str, dict[str, bool] | None] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(inspect, name, version) for name, version in to_inspect]
        for future in as_completed(futures):
            name, markers = future.result()
            markers_by[name] = markers

    findings = []
    for name, version in sorted(versions.items()):
        declared, fetch_note = declared_by[name]
        expression, note = decide_gem(declared, markers_by.get(name), allow)
        if fetch_note:
            note = (note + " " + fetch_note).strip()
        status, canonical = classify(expression, allow)
        findings.append(
            Finding(
                ecosystem="gem",
                name=name,
                version=version,
                expression=canonical,
                status=status,
                role="direct" if name in direct else "transitive",
                required_by=sorted(set(required_by.get(name, []))),
                notes=note,
            )
        )
    return findings


def package_key(ecosystem: str, name: str) -> str:
    if ecosystem == "pypi":
        return name.casefold()
    return name


def apply_exceptions(findings: list[Finding], rows: list[ExceptionRow]) -> list[str]:
    unused = {index: row for index, row in enumerate(rows)}
    problems: list[str] = []
    for finding in findings:
        for index, row in enumerate(rows):
            if row.ecosystem != finding.ecosystem:
                continue
            same_package = package_key(row.ecosystem, row.package) == package_key(
                finding.ecosystem, finding.name
            )
            if not same_package:
                continue
            # A version on the row pins the review. A different release stays
            # unreviewed, and the row fails as unused if that release is gone.
            if row.version and row.version != finding.version:
                continue
            if row.license != finding.expression:
                problems.append(
                    f"exception for {row.ecosystem}:{row.package} names {row.license} "
                    f"but the tree has {finding.expression}"
                )
                unused.pop(index, None)
                continue
            unused.pop(index, None)
            if finding.status == "fail":
                finding.status = "excepted"
                finding.notes = (
                    f"approved by {row.reviewer} on {row.date}: {row.reason}"
                )
            elif finding.status != "excepted":
                problems.append(
                    f"exception for {row.ecosystem}:{row.package} is unnecessary; "
                    f"{finding.expression} is already allowed"
                )
    for row in unused.values():
        problems.append(
            f"exception for {row.ecosystem}:{row.package} does not match any scanned package"
        )
    return problems


def markdown_table(findings: list[Finding]) -> str:
    lines = [
        "| ecosystem | package | version | license | role | required by |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for finding in findings:
        required = ", ".join(finding.required_by[:8]) or "—"
        if len(finding.required_by) > 8:
            required += f" (+{len(finding.required_by) - 8})"
        notes = f" — {finding.notes}" if finding.notes else ""
        lines.append(
            f"| {finding.ecosystem} | {finding.name} | {finding.version} | "
            f"{finding.expression}{notes} | {finding.role} | {required} |"
        )
    return "\n".join(lines)


def report(findings: list[Finding], problems: list[str]) -> int:
    fails = [item for item in findings if item.status == "fail"]
    duals = [item for item in findings if item.status == "dual"]
    excepted = [item for item in findings if item.status == "excepted"]
    passed = [item for item in findings if item.status == "pass"]
    lines = [
        f"scanned {len(findings)} packages: {len(passed)} permissive, "
        f"{len(duals)} dual-licensed with a permissive alternative, "
        f"{len(excepted)} reviewed exceptions, {len(fails)} failing",
    ]
    if problems:
        lines.append("")
        lines.append("exception file problems:")
        lines.extend(f"- {problem}" for problem in problems)
    if fails:
        lines.append("")
        lines.append("FAIL (not permissive, no reviewed exception):")
        for finding in sorted(fails, key=lambda item: item.sort_key()):
            required = ", ".join(finding.required_by[:8]) or "—"
            note = f" [{finding.notes}]" if finding.notes else ""
            lines.append(
                f"- {finding.ecosystem} {finding.name} {finding.version} "
                f"{finding.expression} ({finding.role}; required by {required}){note}"
            )
    if duals:
        lines.append("")
        lines.append("DUAL (passes: a permissive alternative is on the allow list):")
        for finding in sorted(duals, key=lambda item: item.sort_key()):
            note = f" [{finding.notes}]" if finding.notes else ""
            lines.append(
                f"- {finding.ecosystem} {finding.name} {finding.version} "
                f"{finding.expression} ({finding.role}){note}"
            )
    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write("## License check\n\n")
            handle.write(lines[0] + "\n\n")
            if fails:
                handle.write("### Failing packages\n\n")
                handle.write(markdown_table(sorted(fails, key=lambda item: item.sort_key())))
                handle.write("\n\n")
            if duals:
                handle.write("### Dual-licensed, permissive alternative available\n\n")
                handle.write(markdown_table(sorted(duals, key=lambda item: item.sort_key())))
                handle.write("\n")
    report_path = os.environ.get("LICENSE_REPORT_PATH")
    if report_path:
        Path(report_path).write_text(text + "\n", encoding="utf-8")
    if problems or fails:
        return 1
    return 0


def assert_install_commands() -> None:
    """The workflow must not run package install scripts while building the tree."""
    workflow = (REPO / ".github" / "workflows" / "licenses.yml").read_text(encoding="utf-8")
    if re.search(r"npm ci(?! --ignore-scripts)", workflow):
        raise SystemExit("licenses workflow must install npm trees with npm ci --ignore-scripts")
    if "--only-binary=:all:" not in workflow:
        raise SystemExit("licenses workflow must pip-install with --only-binary=:all:")
    if re.search(r"pip install(?![^\n]*--only-binary)", workflow):
        raise SystemExit("a pip install in the licenses workflow is missing --only-binary")
    for extra_list in re.findall(r"\.\[([^\]]+)\]", workflow):
        names = {part.strip() for part in extra_list.split(",") if part.strip()}
        if "ops" in names:
            raise SystemExit("licenses workflow must not install the ops extra")


def assert_scan_scope(findings: list[Finding]) -> None:
    """Dev dependencies are findings. First-party private roots are not.

    Dropping dev dependencies (npm ``--production``, a Python install without
    the ``dev`` extra) would still look like a successful scan of whatever
    remained. Including ``badgeday`` / ``web`` / ``badgeday-ios`` would fail
    those roots as UNLICENSED even though they are this repo.
    """
    pypi_names = {
        item.name.lower().replace("_", "-") for item in findings if item.ecosystem == "pypi"
    }
    npm_names = {item.name for item in findings if item.ecosystem == "npm"}
    problems: list[str] = []
    ours = project_name().replace("_", "-")
    if ours in pypi_names:
        problems.append(
            f"first-party Python project {ours!r} was scanned "
            "(private / UNLICENSED root, not a dependency)"
        )
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    extras = pyproject.get("project", {}).get("optional-dependencies", {})
    for spec in extras.get("dev", []):
        name = requirement_parts(spec)[0].replace("_", "-")
        if name and name not in pypi_names:
            problems.append(f"Python dev extra {name!r} was not scanned")
    for spec in extras.get("ops", []):
        name = requirement_parts(spec)[0].replace("_", "-")
        if name and name in pypi_names:
            problems.append(
                f"ops extra {name!r} is installed; the license job must not install ops"
            )
    for project in NPM_PROJECTS:
        manifest = json.loads((project / "package.json").read_text(encoding="utf-8"))
        root_name = manifest.get("name")
        if manifest.get("private") is True and root_name in npm_names:
            problems.append(
                f"first-party npm package {root_name!r} was scanned "
                "(private: true / UNLICENSED root, not a dependency)"
            )
        relative = project.relative_to(REPO)
        for name in manifest.get("devDependencies") or {}:
            if name not in npm_names:
                problems.append(f"npm devDependency {name!r} ({relative}) was not scanned")
    if problems:
        detail = "\n".join(f"- {problem}" for problem in problems)
        raise SystemExit(f"scan scope does not match LICENSE-POLICY.md:\n{detail}")


def main() -> int:
    allow = load_allowlist(ALLOWLIST_PATH)
    assert_review_config(allow)
    assert_install_commands()
    self_test(allow)
    if "--self-test" in sys.argv:
        print("license parser self-test passed")
        return 0
    exceptions = load_exceptions(EXCEPTIONS_PATH, allow)
    findings = scan_python(allow) + scan_npm(allow) + scan_gems(allow)
    assert_scan_scope(findings)
    problems = apply_exceptions(findings, exceptions)
    return report(findings, problems)


if __name__ == "__main__":
    sys.exit(main())
