from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def ok(message: str) -> None:
    print(f"[OK] {message}")


def fail(message: str) -> None:
    ERRORS.append(message)
    print(f"[FAIL] {message}")


# 1) Python syntax
py_files = [p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts and ".venv" not in p.parts]
for path in py_files:
    try:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except Exception as exc:
        fail(f"Python syntax: {path.relative_to(ROOT)} -> {exc}")
if not any(e.startswith("Python syntax:") for e in ERRORS):
    ok(f"Python syntax {len(py_files)} files")

# 2) URL names and template references
urls_path = ROOT / "dashboard" / "urls.py"
url_text = urls_path.read_text(encoding="utf-8-sig")
url_names = set(re.findall(r'name=["\']([^"\']+)["\']', url_text))
template_refs: list[tuple[Path, str]] = []
for path in (ROOT / "dashboard" / "templates").rglob("*.html"):
    text = path.read_text(encoding="utf-8-sig")
    for name in re.findall(r"\{%\s*url\s+['\"]([^'\"]+)['\"]", text):
        template_refs.append((path, name))
missing_urls = sorted({name for _, name in template_refs if name not in url_names})
if missing_urls:
    fail("Missing template URL names: " + ", ".join(missing_urls))
else:
    ok(f"Template URL refs {len(template_refs)} / URL names {len(url_names)}")

# 3) Template block balance (simple structural check)
pairs = [("if", "endif"), ("for", "endfor"), ("block", "endblock")]
for path in (ROOT / "dashboard" / "templates").rglob("*.html"):
    text = path.read_text(encoding="utf-8-sig")
    for start, end in pairs:
        starts = len(re.findall(r"\{%\s*" + start + r"\b", text))
        ends = len(re.findall(r"\{%\s*" + end + r"\b", text))
        if starts != ends:
            fail(f"Template block mismatch: {path.relative_to(ROOT)} {start}={starts}, {end}={ends}")
if not any(e.startswith("Template block mismatch:") for e in ERRORS):
    ok("Template structural balance")

# 4) Migration chain
migration_dir = ROOT / "dashboard" / "migrations"
migrations = sorted(p for p in migration_dir.glob("[0-9][0-9][0-9][0-9]_*.py"))
numbers = [int(p.name[:4]) for p in migrations]
expected = list(range(1, max(numbers) + 1)) if numbers else []
if numbers != expected:
    fail(f"Migration numbers not continuous: {numbers}")
else:
    ok(f"Migration chain 0001~{numbers[-1]:04d}" if numbers else "No migrations")

# 5) Required Stage 01~04 model/features exist
models_text = (ROOT / "dashboard" / "models.py").read_text(encoding="utf-8-sig")
required_model_tokens = {
    "assignment_type": "Assignment type",
    "class StudentAssignmentSubmission": "Individual assignment submission model",
    "class AdminStudentComment": "Admin-to-student comment model",
    "affiliation =": "Student affiliation field",
    "role =": "Team member role field",
    "class SelfProjectReview": "Self project review model",
}
for token, label in required_model_tokens.items():
    if token not in models_text:
        fail(f"Missing feature: {label}")
if not any(e.startswith("Missing feature:") for e in ERRORS):
    ok("Stage01~04 data model features")

# 6) Key student/admin pages exist
required_templates = [
    "student/home.html",
    "student/assignment_info.html",
    "student/results.html",
    "student/self_review.html",
    "student/team_info.html",
    "admin_ui/dashboard.html",
    "admin_ui/round_detail.html",
    "admin_ui/student_detail.html",
]
for rel in required_templates:
    if not (ROOT / "dashboard" / "templates" / rel).exists():
        fail(f"Missing template: {rel}")
if not any(e.startswith("Missing template:") for e in ERRORS):
    ok("Key student/admin templates")

# 7) Secrets/build artifacts should not be in a distributable copy
bad = []
for path in ROOT.rglob("*"):
    if any(part in {".venv", "venv", "__pycache__", ".git"} for part in path.parts):
        continue
    rel = path.relative_to(ROOT)
    if path.is_file() and (path.name == ".env" or path.suffix == ".pyc"):
        bad.append(str(rel))
if bad:
    fail("Sensitive/cache files present: " + ", ".join(bad[:20]))
else:
    ok("No .env / pyc in release tree")

print()
if ERRORS:
    print(f"[FAIL] pre-release check: {len(ERRORS)} issue(s)")
    sys.exit(1)
print("[PASS] pre-release static check completed")
