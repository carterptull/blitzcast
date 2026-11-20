"""Every requirement in the postseason spec is proven by a test that cites its ID."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "superpowers" / "specs" / "2026-11-19-postseason-design.md"
ID_RE = re.compile(r"\bPS-[A-Z]+\d+\b")

# Requirements not implemented yet. Each task removes its IDs as its tests land.
PENDING: set[str] = set()


def spec_ids() -> set[str]:
    return set(ID_RE.findall(SPEC.read_text(encoding="utf-8")))


def _test_files() -> list[Path]:
    here = Path(__file__).resolve()
    files = [p for p in (REPO / "backend" / "tests").rglob("*.py") if p.resolve() != here]
    src = REPO / "frontend" / "src"
    if src.exists():
        files += [p for p in src.rglob("*") if p.is_file() and "__tests__" in p.parts]
        files += [p for p in src.rglob("*.test.*") if "__tests__" not in p.parts]
    return files


def cited_ids() -> set[str]:
    found: set[str] = set()
    for path in _test_files():
        found |= set(ID_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return found


def test_every_implemented_requirement_has_a_test():
    missing = (spec_ids() - PENDING) - cited_ids()
    assert not missing, f"requirements with no citing test: {sorted(missing)}"


def test_pending_ids_have_no_test_yet():
    landed = PENDING & cited_ids()
    assert not landed, f"tests exist; remove these from PENDING: {sorted(landed)}"


def test_all_requirements_traced():
    assert PENDING == set()


def test_pending_ids_exist_in_spec():
    unknown = PENDING - spec_ids()
    assert not unknown, f"PENDING names IDs the spec does not have: {sorted(unknown)}"
