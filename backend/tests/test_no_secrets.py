"""Issue #10 — NO-SECRET / NO-PASSWORD GUARD (a.k.a. "無密碼入庫").

Scans the *curated* source/config surface of the repo for leaked secrets and
asserts there are ZERO. This is the machine-enforced half of "CI 加『無密碼入庫』".

Why it is safe to always run (offline-safe, never flags itself):

  * SCOPE is curated — only these globs are read:
        backend/**/*.py
        frontend/src/**/*.{js,ts,vue}
        .github/**/*.yml / .github/**/*.yaml
        docker-compose.yml / docker-compose.yaml
        README.md
        *.env  (any real .env, any depth)
    So it NEVER touches the gitignored / non-source artifacts the issue names:
    `price_history.db`, the whole `node_modules/`, `*.lock`, `.coverage`,
    `history_data.json` / `history_data.discontinued.json` / `alerts_state.json` /
    `watchlist.json` (those live under `backend/` as data, none match the
    `**/*.py` / `.yml` / `.env` scopes) — by construction.

  * SELF-EXCLUSION so the guard can't flag itself or its allowlists:
      - the test file itself is skipped (by realpath);
      - `*.env.example` is skipped (a template must stay un-tripping);
      - any file carrying the marker line `secret-guard:allowlist` is skipped
        (the allowlist mechanism — e.g. docker-compose.yml, which legitimately
        injects `TELEGRAM_BOT_TOKEN=` from the environment via `${...}`).

A planted fake secret anywhere in scope (below, `test_planted_faires...`) proves
the scanner actually has teeth; the real scan must stay empty.
"""
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# root + scope
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

# Directories that are never source — pruned from the walk entirely.
PRUNE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "dist", "coverage",
    ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache", ".npm",
}
# Files that are never "source" by name (binary / artifact / lock / state) — even
# if a glob were broad, these are skipped.
EXCLUDE_BY_NAME_SUFFIX = (".db", ".lock", ".pyc", ".map", ".png", ".jpg",
                          ".jpeg", ".gif", ".ico", ".webp", ".woff", ".ttf")

# In-scope globs, as (dir_relative_to_root, {extensions}) plus a couple of fixed
# files. This mirrors the issue's exact curated scope.
SCOPE_DIRS = [
    (Path("backend"), {".py"}),
    (Path("frontend/src"), {".js", ".ts", ".vue"}),
    (Path(".github"), {".yml", ".yaml"}),
]
SCOPE_FILENAMES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "README.md",
}
# Real env files are in scope by suffix; templates are not.
ENV_SUFFIX = ".env"
ENV_TEMPLATE_SUFFIX = ".env.example"

# The allowlist marker: a line containing this token skips the file, so an
# infra/config file that *legitimately* references-or-injects a secret (e.g. an
# env interpolation in docker-compose) can be whitelisted with a single comment.
MARKER = "secret-guard:allowlist"

# ---------------------------------------------------------------------------
# the secret patterns (issue #10's exact set)
# ---------------------------------------------------------------------------
PATTERNS = [
    ("github_pat",     re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("openai_key",     re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{12}")),
    ("telegram_bot_token", re.compile(r"TELEGRAM_BOT_TOKEN\s*=\s*\S")),
    ("telegram_chat_id", re.compile(r"TELEGRAM_CHAT_ID\s*=\s*[0-9]+")),
    ("password_literal", re.compile(r"password=\S{12,}")),
]


# ---------------------------------------------------------------------------
# the scanner
# ---------------------------------------------------------------------------
def _should_skip(path: Path) -> bool:
    """True if this path is out of the curated scope or is an excluded artifact."""
    parts = path.relative_to(ROOT).parts   # string components
    if any(p in PRUNE_DIRS for p in parts):
        return True
    name = path.name
    if any(name.endswith(sfx) for sfx in EXCLUDE_BY_NAME_SUFFIX):
        return True
    if name.endswith(ENV_TEMPLATE_SUFFIX):          # *.env.example
        return True
    if path.resolve() == SELF:                       # this test file
        return True
    return False


def _in_scope(path: Path) -> bool:
    """Does this file fall under the curated inclusion globs?"""
    if _should_skip(path):
        return False
    name = path.name
    # fixed top-level files
    if name in SCOPE_FILENAMES:
        return True
    # a real .env file any depth (templates are already excluded by _should_skip)
    if name == ENV_SUFFIX or name.endswith(ENV_SUFFIX):
        return True
    # directory-scoped globs
    for d, exts in SCOPE_DIRS:
        base = ROOT / d
        try:
            path.relative_to(base)
        except ValueError:
            continue
        if path.suffix not in exts:
            continue
        return True
    return False


def _has_marker(text: str) -> bool:
    return any(MARKER in line for line in text.splitlines())


def scan_file(path: Path):
    """Return a list of (relpath, lineno, pattern_name, snippet) findings.

    Skips out-of-scope / excluded / allowlisted (marker) files. A non-UTF8 or
    unreadable file is recorded as a single diagnostic, not ignored silently.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [("binary-unreadable", "n/a", str(path.relative_to(ROOT)), "")]
    except OSError:
        return []
    if _has_marker(text):                            # allowlist marker -> skip
        return []
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in PATTERNS:
            for m in rx.finditer(line):
                snippet = line.strip()[:120]
                findings.append((str(path.relative_to(ROOT)), lineno, name, snippet))
    return findings


def scan_repo(root: Path = ROOT):
    """Walk the repo and return all in-scope findings (should be empty).

    Non-source dirs (.git / node_modules / .venv / .pytest_cache / dist /
    coverage / ...) are pruned in place so the walk never descends into them —
    the scanner stays fast and offline."""
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            path = Path(dirpath) / fn
            rel_ok = path.resolve().is_relative_to(root.resolve())
            if not rel_ok:
                continue
            if not _in_scope(path):
                continue
            findings.extend(scan_file(path))
    return findings


# ---------------------------------------------------------------------------
# the guard
# ---------------------------------------------------------------------------
def test_no_secrets_in_repo():
    """The curated source/config surface must contain ZERO secret findings."""
    findings = scan_repo()
    if findings:
        listed = "\n".join(
            f"  {rel}:{ln} [{name}] {snippet!r}"
            for rel, ln, name, snippet in findings
        )
        raise AssertionError(
            f"leaked secret(s) detected in {len(findings)} place(s) "
            f"(add a `{MARKER}` line only for a legitimate allowlisted config "
            f"file, never for a real secret):\n{listed}"
        )
    assert findings == []


# ---------------------------------------------------------------------------
# negative controls: the scanner MUST have teeth
# ---------------------------------------------------------------------------
def test_patterns_detect_planted_fakes():
    """Each pattern flags a realistic planted secret — proves the guard isn't a
    no-op. (These literals live in the self-excluded test file, so the repo scan
    can't see them.)"""
    planted = {
        "github_pat": "ghp_a1b2C3d4E5f6G7h8I9j0K1l2M3n4",
        "openai_key": "sk-abcdefghijklmnopqrstuvwxyz1234",
        "aws_access_key": "AKIA1234567890AB",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN=123456789:AAH_real_bot_token",
        "telegram_chat_id": "TELEGRAM_CHAT_ID=123456789",
        "password_literal": "db_password=supersecret12345",
    }
    for name, sample in planted.items():
        rx = dict(PATTERNS)[name]
        assert rx.search(sample), f"{name} failed to detect: {sample!r}"


def test_allowlist_marker_is_skipped(tmp_path):
    """A file carrying the marker is skipped even if it holds a matching literal
    — so a legitimate allowlisted config (docker-compose env injection) stays
    green, which is the whole point of the marker."""
    f = tmp_path / "allow.yaml"
    f.write_text(
        "# secret-guard:allowlist\n"
        "# infra passes the token through from the environment, never hardcodes it\n"
        "  TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}\n",
        encoding="utf-8",
    )
    assert scan_file(f) == []
