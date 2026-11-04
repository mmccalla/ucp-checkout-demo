"""Gate G1: lint, types, pins (AC-118), secret scan and PRODUCTION scan (AC-26).

Run: uv run python tools/gates/g1.py [--root DIR] [--report FILE] [--skip-tools]
Spec 17.3 (G1 "Lint, types"), T-91 (fail on any error), AC-26, AC-118.
"""

import argparse
import ast
import json
import pathlib
import re
import io
import subprocess
import sys
import tokenize
import tomllib

SKIP_DIRS = {
    ".git",
    ".venv",
    ".run",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
}
TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".json",
    ".md",
    ".yaml",
    ".yml",
    ".sh",
    ".js",
    ".html",
    ".env",
    ".txt",
    ".cfg",
    ".csv",
    "",
}
# Configuration that reaches the browser or the handler (AC-26).
CONFIG_GLOBS = [
    "contracts/fixtures/*.json",
    "business/profile/*.json",
    "deploy/**/*",
    "platform/web/**/*.js",
    "platform/web/**/*.html",
    "**/*.env",
]
GH_RE = re.compile(
    r"github\.com/Universal-Commerce-Protocol/([A-Za-z0-9_.-]+)/"
    r"(?:blob|tree|commit|raw)/([0-9a-f]{7,40})\b"
)
UCP_URL_RE = re.compile(r"ucp\.dev/((?:\d{4}-\d{2}-\d{2})|latest|draft)/")
GPAY_URL_RE = re.compile(r"pay\.google\.com/gp/p/ucp/(\d{4}-\d{2}-\d{2})/")
SECRET_RES = [
    re.compile(r"-----BEGIN (?:EC |RSA |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\"d\"\s*:\s*\"[A-Za-z0-9_-]{40,}\""),  # private JWK member
]
ALLOW_UNPINNED = "g1-allow-unpinned"
# T-108 (AC-118 clauses 2 to 4). The marker is a `#` comment on a `.py` line outside tools/gates/.
# The same comment cites this URL and AC-44 or AC-45. The marker skips only the `ucp.dev` version
# check of the August version. The expected number of marked lines is 3.
MARKER_VERSION = "2026-08-25"
MARKER_URL = (
    "https://ucp.dev/" + MARKER_VERSION + "/"
)  # built here: G1 must not flag its own constant
MARKER_AC_RE = re.compile(r"\bAC-4[45]\b")
MARKER_COMMENT_RE = re.compile(r"#\s*" + re.escape(ALLOW_UNPINNED) + r"\b")
EXPECTED_MARKS = 3
# T-116 (APPROVED by the project owner, 28 Oct 2026; docs/G1-alias-exception-APPROVED-T-116.md).
# A named exception for the refusal list in the schema registry. It is not the marker.
# G1 finds the 2 exempt strings with `ast`: whole string constants in the tuple or list named
# `FORBIDDEN` in ALIAS_REFUSAL_FILE. The exception skips only the alias check of that line.
# The GitHub commit check and the Google Pay check still run. The number of exempt strings must be 2.
ALIAS_REFUSAL_FILE = "libs/ucp_core/schema_registry.py"
ALIAS_REFUSAL_NAME = "FORBIDDEN"
ALIAS_REFUSAL_COUNT = 2
ALIAS_STRINGS = (  # built here from parts: G1 must not flag its own constants
    "https://ucp." + "dev/" + "latest/",
    "https://ucp." + "dev/" + "draft/",
)
ALLOW_SECRET = "g1-allow-secret-pattern"
ALLOW_PROD = "g1-allow-production-word"


def files(root: pathlib.Path) -> list[pathlib.Path]:
    out = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file():
            continue
        if p.suffix in TEXT_SUFFIXES and p.name != "uv.lock":
            out.append(p)
    return sorted(out)


def text(p: pathlib.Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def marker_uses(rel: pathlib.Path, src: str) -> dict[int, str]:
    """Return line number -> comment text for each use of the marker as a `#` comment.

    In a `.py` file the comment comes from `tokenize`, so text in a string or a docstring is not a
    use. If the file cannot be tokenized, the regex is used. In other files a `#` followed by the
    marker is a use (prose that names the marker without `#` is not a use).
    """
    uses: dict[int, str] = {}
    if rel.suffix == ".py":
        try:
            for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                if tok.type == tokenize.COMMENT and ALLOW_UNPINNED in tok.string:
                    uses[tok.start[0]] = tok.string
            return uses
        except (tokenize.TokenError, IndentationError, SyntaxError):
            uses = {}
    for n, line in enumerate(src.splitlines(), 1):
        m = MARKER_COMMENT_RE.search(line)
        if m:
            uses[n] = line[m.start() :]
    return uses


def marker_allowed_here(rel: pathlib.Path) -> bool:
    """Clause (a): a `.py` file outside tools/gates/."""
    return rel.suffix == ".py" and rel.parts[:2] != ("tools", "gates")


def check_marker(rel: pathlib.Path, uses: dict[int, str]) -> tuple[set[int], list[str], int]:
    """Check each use of the marker in one file.

    Returns the lines where the marker is valid, the errors (file:line), and the number of marked
    lines that count for clause 4.
    """
    valid: set[int] = set()
    errors: list[str] = []
    counted = 0
    for n, comment in sorted(uses.items()):
        if not marker_allowed_here(rel):
            errors.append(
                f"{rel}:{n}: the marker {ALLOW_UNPINNED} is allowed only in .py files outside tools/gates/"
            )
            continue
        counted += 1
        if MARKER_URL not in comment:
            errors.append(
                f"{rel}:{n}: the marker {ALLOW_UNPINNED} needs a {MARKER_URL} URL in the same comment"
            )
        elif not MARKER_AC_RE.search(comment):
            errors.append(
                f"{rel}:{n}: the marker {ALLOW_UNPINNED} needs AC-44 or AC-45 in the same comment"
            )
        else:
            valid.add(n)
    return valid, errors, counted


def alias_exempt_lines(rel: pathlib.Path, src: str) -> tuple[set[int], list[str]]:
    """Return the exempt line numbers (T-116) and the errors for one file.

    Only ALIAS_REFUSAL_FILE can have exempt lines. A line is exempt if it holds one whole string
    constant that is exactly one of ALIAS_STRINGS, inside the tuple or list named FORBIDDEN, and
    nothing else except a comma. A comment on the line (for example the marker) removes the
    exemption.
    """
    if rel.as_posix() != ALIAS_REFUSAL_FILE:
        return set(), []
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return set(), [f"{rel}: cannot parse the file for the alias exception (T-116): {exc.msg}"]
    lines = src.splitlines()
    exempt: set[int] = set()
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == ALIAS_REFUSAL_NAME for t in node.targets
        ):
            value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == ALIAS_REFUSAL_NAME
        ):
            value = node.value
        if not isinstance(value, (ast.Tuple, ast.List)):
            continue
        for el in value.elts:
            if not (
                isinstance(el, ast.Constant)
                and isinstance(el.value, str)
                and el.value in ALIAS_STRINGS
            ):
                continue
            if el.lineno != el.end_lineno:
                continue
            line = lines[el.lineno - 1].strip()
            if line in (f'"{el.value}",', f"'{el.value}',", f'"{el.value}"', f"'{el.value}'"):
                exempt.add(el.lineno)
    return exempt, []


def alias_exemptions(root: pathlib.Path) -> list[str]:
    """List the exempt lines as file:line, for the G1 report."""
    out: list[str] = []
    p = root / ALIAS_REFUSAL_FILE
    if p.is_file():
        rel = p.relative_to(root)
        out = [f"{rel}:{n}" for n in sorted(alias_exempt_lines(rel, text(p))[0])]
    return out


def check_pins(
    root: pathlib.Path,
    expected_marks: int = EXPECTED_MARKS,
    expected_aliases: int = ALIAS_REFUSAL_COUNT,
) -> list[str]:
    pins = tomllib.loads((root / "pins/PINS.toml").read_text())
    repo_commits = {
        "ucp": pins["ucp"]["commit"],
        "samples": pins["samples"]["commit"],
        "conformance": pins["conformance"]["commit"],
        "python-sdk": pins["ucp_sdk"]["commit"],
        "ucp-schema": pins["ucp_schema"]["commit"],
    }
    ucp_versions = {pins["ucp"]["version"]}
    if "ucp_mixed_version" in pins:
        ucp_versions.add(pins["ucp_mixed_version"]["version"])
    gpay_version = pins["gpay_handler"]["version"]
    errors: list[str] = []
    marked = 0
    exempt_total = 0
    for p in files(root):
        rel = p.relative_to(root)
        in_tests = rel.parts[0] == "tests"
        if rel.parts[0] == "contracts" and p.suffix == ".json" and "fixtures" not in rel.parts:
            continue  # upstream bytes: the sha256 manifest pins them (G2, AC-88)
        src = text(p)
        valid, marker_errors, counted = check_marker(rel, marker_uses(rel, src))
        errors += marker_errors
        marked += counted
        exempt, alias_errors = alias_exempt_lines(rel, src)
        errors += alias_errors
        exempt_total += len(exempt)
        for n, line in enumerate(src.splitlines(), 1):
            for repo, sha in GH_RE.findall(line):
                want = repo_commits.get(repo)
                if want and not want.startswith(sha):
                    errors.append(f"{rel}:{n}: {repo} commit {sha} is not the pin {want[:12]}")
            for ver in UCP_URL_RE.findall(line):
                if ver in ("latest", "draft"):
                    if n in exempt:
                        continue  # T-116: the refusal list in the schema registry, only this check
                    if not in_tests:  # tests use the aliases to prove the refusal (AC-87)
                        errors.append(f"{rel}:{n}: ucp.dev/{ver}/ alias is not pinned")
                elif ver not in ucp_versions:
                    if n in valid and ver == MARKER_VERSION:
                        continue  # T-108: the marker skips only this check, only for this version
                    errors.append(f"{rel}:{n}: ucp.dev/{ver}/ is not a pinned UCP version")
            for ver in GPAY_URL_RE.findall(line):
                if ver != gpay_version:
                    errors.append(f"{rel}:{n}: Google Pay handler {ver} is not {gpay_version}")
    if marked != expected_marks:
        errors.append(
            f"the marker {ALLOW_UNPINNED} is on {marked} lines in .py files; the expected number is "
            f"{expected_marks} (AC-118, T-108)"
        )
    if exempt_total != expected_aliases:
        errors.append(
            f"the alias exception (T-116) covers {exempt_total} strings in {ALIAS_REFUSAL_FILE}; "
            f"the expected number is {expected_aliases} (AC-118)"
        )
    errors += check_dependency_pins(root, pins)
    return errors


def check_dependency_pins(root: pathlib.Path, pins: dict) -> list[str]:  # type: ignore[type-arg]
    errors = []
    proj = tomllib.loads((root / "pyproject.toml").read_text())
    deps = list(proj["project"]["dependencies"])
    for group in proj.get("dependency-groups", {}).values():
        deps += group
    for d in deps:
        if "==" not in d:
            errors.append(f"pyproject.toml: dependency {d!r} is not pinned with ==")
        if d.startswith("ucp-sdk") and not d.endswith("==" + pins["ucp_sdk"]["version"]):
            errors.append(f"pyproject.toml: {d} is not ucp-sdk=={pins['ucp_sdk']['version']}")
    lock = root / "uv.lock"
    if lock.exists():
        r = subprocess.run(["uv", "lock", "--check"], cwd=root, capture_output=True, text=True)
        if r.returncode:
            errors.append("uv lock --check: " + (r.stdout + r.stderr).strip()[-400:])
    return errors


def check_secrets(root: pathlib.Path) -> list[str]:
    errors = []
    for p in files(root):
        for n, line in enumerate(text(p).splitlines(), 1):
            if ALLOW_SECRET in line:
                continue
            if any(rx.search(line) for rx in SECRET_RES):
                errors.append(f"{p.relative_to(root)}:{n}: possible secret")
    return errors


def check_production(root: pathlib.Path) -> list[str]:
    errors = []
    seen = set()
    for g in CONFIG_GLOBS:
        for p in root.glob(g):
            rel = p.relative_to(root)
            if not p.is_file() or p in seen or any(x in SKIP_DIRS for x in rel.parts):
                continue
            seen.add(p)
            for n, line in enumerate(text(p).splitlines(), 1):
                if "PRODUCTION" in line and ALLOW_PROD not in line:
                    errors.append(f"{rel}:{n}: PRODUCTION value")
    return errors


def run_tool(cmd: list[str], root: pathlib.Path) -> list[str]:
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    return [] if r.returncode == 0 else [(r.stdout + r.stderr).strip()[-3000:]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parents[2]))
    ap.add_argument("--report")
    ap.add_argument("--skip-tools", action="store_true", help="skip ruff and mypy (tests only)")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    checks = {
        "pins (AC-118)": check_pins(root),
        "secret-scan": check_secrets(root),
        "no-PRODUCTION (AC-26)": check_production(root),
    }
    if not a.skip_tools:
        checks["ruff"] = run_tool(["uv", "run", "--no-sync", "ruff", "check", "."], root)
        checks["ruff-format"] = run_tool(
            ["uv", "run", "--no-sync", "ruff", "format", "--check", "."], root
        )
        checks["mypy --strict"] = run_tool(["uv", "run", "--no-sync", "mypy"], root)
        extra = root / "tools/gates/g1_vendored.py"
        if extra.exists():
            checks["mypy vendored baseline (T-103)"] = run_tool(
                ["uv", "run", "--no-sync", "python", str(extra)], root
            )
    ok = all(not v for v in checks.values())
    for name, errs in checks.items():
        print(f"{'PASS' if not errs else 'FAIL'} {name}")
        for e in errs:
            print(f"   {e}")
    for ref in alias_exemptions(root):
        print(f"EXEMPT (T-116, alias check only) {ref}")
    print(f"G1 {'PASS' if ok else 'FAIL'}")
    if a.report:
        pathlib.Path(a.report).write_text(
            json.dumps(
                {"gate": "G1", "status": "PASS" if ok else "FAIL", "checks": checks}, indent=2
            )
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
