#!/usr/bin/env python3
"""Package the add-on as an installable .ankiaddon file.

    python build_ankiaddon.py

An .ankiaddon is a plain zip of the add-on folder's *contents* (manifest.json
must sit at the archive root, not inside a subfolder).

Excluded on purpose:
  meta.json   - Anki writes the user's saved config there, including the API key
  user_files/ - the local translation cache
  __pycache__ - build artefacts
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "anki_translate_popup"
OUTPUT = ROOT / "anki_translate_popup.ankiaddon"
LICENCE = ROOT / "LICENSE"

EXCLUDED_DIRS = {"__pycache__", "user_files", ".pytest_cache", ".mypy_cache"}
EXCLUDED_NAMES = {"meta.json", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".ankiaddon"}


def should_include(path: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.relative_to(SOURCE).parts):
        return False
    if path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES:
        return False
    return True


def main() -> int:
    if not (SOURCE / "manifest.json").is_file():
        raise SystemExit(f"manifest.json not found in {SOURCE}")

    files = sorted(p for p in SOURCE.rglob("*") if p.is_file() and should_include(p))
    if not files:
        raise SystemExit("nothing to package")

    OUTPUT.unlink(missing_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            # Store paths relative to the add-on folder, with forward slashes,
            # so the archive installs correctly on every platform.
            arcname = path.relative_to(SOURCE).as_posix()
            archive.write(path, arcname)
        # AGPL: the licence travels with the distributed work, and it lives one
        # level up from the add-on folder.
        archive.write(LICENCE, LICENCE.name)

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Wrote {OUTPUT.name} ({len(files)} files, {size_kb:.1f} KiB)")
    for path in files:
        print(f"  {path.relative_to(SOURCE).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
