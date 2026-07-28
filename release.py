#!/usr/bin/env python3
"""Cut a new release of the add-on.

    python release.py            # 1.0.0 -> 1.0.1
    python release.py 1.1.0      # or say which version

It runs the tests, bumps `human_version`, builds the .ankiaddon, commits, tags,
pushes, and creates the GitHub release with the package attached. Any
interpreter with `requests` will do — it reuses itself for the suite and the
build — and it works from any directory.

AnkiWeb is the one step left by hand: it has no API, so the script finishes by
printing what to upload where.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "anki_translate_popup" / "manifest.json"
PACKAGE = ROOT / "anki_translate_popup.ankiaddon"
BRANCH = "main"


def run(*args: str, capture: bool = False) -> str:
    """Run a command in the repo, aborting the release if it fails."""
    result = subprocess.run(
        args, cwd=ROOT, text=True, capture_output=capture, check=False
    )
    if result.returncode != 0:
        raise SystemExit(f"failed ({result.returncode}): {' '.join(args)}")
    return (result.stdout or "").strip()


def parse_version(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise SystemExit(f"version must look like 1.2.3, got {value!r}")
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def next_patch(version: str) -> str:
    major, minor, patch = parse_version(version)
    return f"{major}.{minor}.{patch + 1}"


def set_version(path: Path, version: str) -> None:
    """Rewrite human_version in place, leaving the rest of the file untouched."""
    text = path.read_text(encoding="utf-8")
    new, count = re.subn(
        r'("human_version"\s*:\s*)"[^"]*"', rf'\g<1>"{version}"', text, count=1
    )
    if count != 1:
        raise SystemExit(f"no human_version field in {path}")
    path.write_text(new, encoding="utf-8", newline="\n")


def check_history_is_clean(previous_tag: str) -> None:
    """Refuse to publish commits carrying an AI co-author trailer.

    Editors add these back by default, and a public repo is the wrong place to
    discover one.
    """
    span = f"{previous_tag}..HEAD" if previous_tag else "HEAD"
    log = run("git", "log", span, "--format=%B%n%an %ae", capture=True)
    hits = [line for line in log.splitlines() if re.search(r"co-authored-by", line, re.I)]
    if hits:
        raise SystemExit(
            "co-author trailer found in the commits being released:\n  "
            + "\n  ".join(hits)
            + "\nRewrite those messages (git rebase -i) before releasing."
        )


def main(requested: str | None) -> int:
    if find_spec("requests") is None:
        raise SystemExit(f"{sys.executable} has no requests — the tests need it")

    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD", capture=True)
    if branch != BRANCH:
        raise SystemExit(f"on {branch}, releases are cut from {BRANCH}")
    if run("git", "status", "--porcelain", capture=True):
        raise SystemExit("working tree is dirty — commit or stash first")

    current = json.loads(MANIFEST.read_text(encoding="utf-8"))["human_version"]
    version = requested or next_patch(current)
    tag = f"v{version}"
    if parse_version(version) <= parse_version(current):
        raise SystemExit(f"{version} is not newer than the released {current}")
    print(f"releasing {current} -> {version}")

    tags = run("git", "tag", "--list", tag, capture=True)
    if tags:
        raise SystemExit(f"tag {tag} already exists")

    previous = run("git", "tag", "--list", "--sort=-v:refname", capture=True)
    check_history_is_clean(previous.splitlines()[0] if previous else "")

    # Tests before the bump, so a failure leaves the tree exactly as it was.
    run(sys.executable, "-m", "unittest", "discover", "-s", "anki_translate_popup/tests", "-t", ".")

    set_version(MANIFEST, version)
    run(sys.executable, "build_ankiaddon.py")

    run("git", "add", str(MANIFEST.relative_to(ROOT)))
    run("git", "commit", "-m", f"chore: release {tag}")
    run("git", "tag", tag)
    run("git", "push", "--follow-tags")
    run("gh", "release", "create", tag, str(PACKAGE), "--title", tag, "--generate-notes")

    print(
        f"\n{tag} is on GitHub. One step left, by hand — AnkiWeb has no API:\n"
        f"  1. open https://ankiweb.net/shared/addons/ and pick this add-on\n"
        f"  2. upload {PACKAGE}\n"
        f"  Re-upload on the existing listing, not a new one, or nobody gets the update."
    )
    return 0


def self_check() -> int:
    import tempfile

    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("10.0.11") > parse_version("9.99.99")
    assert next_patch("1.0.0") == "1.0.1"
    assert next_patch("1.9.9") == "1.9.10"  # patch counts up, it does not carry
    for bad in ("1.2", "v1.2.3", "1.2.3a", ""):
        try:
            parse_version(bad)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"{bad!r} should have been rejected")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        path.write_text(
            '{\n    "package": "x",\n    "human_version": "1.0.0",\n'
            '    "conflicts": ["human_version"]\n}\n',
            encoding="utf-8",
        )
        set_version(path, "2.0.1")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["human_version"] == "2.0.1", data
        # only the field is touched, not a string that merely looks like it
        assert data["conflicts"] == ["human_version"], data

        path.write_text('{"package": "x"}', encoding="utf-8")
        try:
            set_version(path, "2.0.1")
        except SystemExit:
            pass
        else:
            raise AssertionError("missing human_version should have been rejected")

    print("self-check ok")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2:
        raise SystemExit(__doc__)
    argument = sys.argv[1] if len(sys.argv) == 2 else None
    if argument == "--self-check":
        raise SystemExit(self_check())
    raise SystemExit(main(argument))
