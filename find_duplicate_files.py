#!/usr/bin/env python3
"""
Find duplicate files in a directory by content hash.

Groups files by their SHA-256 hash. Reports sets of files that share
the same hash (byte-for-byte identical).

Usage:
    python find_dupes.py ./dir
    python find_dupes.py ./dir -r
    python find_dupes.py ./dir --algorithm md5
    python find_dupes.py ./dir --json dupes.json
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------

class C:
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    CYAN = "\033[1;36m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    enabled = True

    @classmethod
    def disable(cls):
        cls.enabled = False

    @classmethod
    def _wrap(cls, code, text):
        return f"{code}{text}{cls.RESET}" if cls.enabled else text

    @classmethod
    def green(cls, t):  return cls._wrap(cls.GREEN, t)
    @classmethod
    def yellow(cls, t): return cls._wrap(cls.YELLOW, t)
    @classmethod
    def red(cls, t):    return cls._wrap(cls.RED, t)
    @classmethod
    def cyan(cls, t):   return cls._wrap(cls.CYAN, t)
    @classmethod
    def dim(cls, t):    return cls._wrap(cls.DIM, t)
    @classmethod
    def bold(cls, t):   return cls._wrap(cls.BOLD, t)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

HASH_ALGOS = {
    "md5": hashlib.md5,
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
}

CHUNK_SIZE = 1024 * 1024  # 1 MB


def hash_file(path, algorithm="sha256", chunk_size=CHUNK_SIZE):
    """
    Hash a file's contents. Returns the hex digest, or None on error.
    Reads in chunks so it works on files bigger than RAM.
    """
    h = HASH_ALGOS[algorithm]()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
    except (OSError, PermissionError):
        return None
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Directory walker
# ---------------------------------------------------------------------------

def iter_files(root, recursive=False, follow_symlinks=False,
               skip_hidden=False):
    """Yield Paths to files under root."""
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")

    pattern = "**/*" if recursive else "*"
    for path in root.glob(pattern):
        # Skip directories
        if not path.is_file():
            continue
        # Skip symlinks if requested
        if not follow_symlinks and path.is_symlink():
            continue
        # Skip hidden files/dirs if requested
        if skip_hidden and any(part.startswith(".") for part in path.parts):
            continue
        yield path


# ---------------------------------------------------------------------------
# Human-readable sizes
# ---------------------------------------------------------------------------

def human_size(n):
    """Format a byte count as e.g. '4.2 MB'."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Find duplicate files in a directory by content hash."
    )
    parser.add_argument("directory", help="Directory to scan")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Descend into subdirectories")
    parser.add_argument("-a", "--algorithm",
                        choices=list(HASH_ALGOS.keys()), default="sha256",
                        help="Hash algorithm (default: sha256)")
    parser.add_argument("--follow-symlinks", action="store_true",
                        help="Include symlinked files (default: skipped)")
    parser.add_argument("--skip-hidden", action="store_true",
                        help="Skip files/dirs whose names start with '.'")
    parser.add_argument("--min-size", type=int, default=0,
                        help="Ignore files smaller than N bytes (default: 0)")
    parser.add_argument("--json", metavar="FILE",
                        help="Write duplicate groups to a JSON file")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable ANSI colors")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Only print the duplicate groups, no progress")
    parser.add_argument("--delete", action="store_true",
                        help="Prompt to delete all but the first file "
                             "in each duplicate group (DANGEROUS)")
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        C.disable()

    try:
        files = list(iter_files(
            args.directory,
            recursive=args.recursive,
            follow_symlinks=args.follow_symlinks,
            skip_hidden=args.skip_hidden,
        ))
    except NotADirectoryError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.min_size > 0:
        files = [f for f in files if f.stat().st_size >= args.min_size]

    if not files:
        print(f"No files found in {args.directory}", file=sys.stderr)
        sys.exit(1)

    total = len(files)

    if not args.quiet:
        print(C.bold(
            f"Hashing {total} file(s) in {args.directory} "
            f"[algorithm: {args.algorithm}]"
        ))
        print("=" * 72, flush=True)

    # hash -> [paths]
    by_hash = defaultdict(list)
    start_all = time.time()
    total_bytes = 0
    hashed = 0
    errors = 0

    for idx, path in enumerate(files, start=1):
        try:
            size = path.stat().st_size
        except OSError:
            errors += 1
            continue

        digest = hash_file(path, algorithm=args.algorithm)
        if digest is None:
            errors += 1
            if not args.quiet:
                print(f"[{idx}/{total}] {C.red('!')} {path} "
                      f"{C.dim('(unreadable)')}", flush=True)
            continue

        by_hash[digest].append(path)
        hashed += 1
        total_bytes += size

        if not args.quiet:
            # Progress line, overwritten in-place on the same line
            pct = idx / total * 100
            print(f"\r[{idx}/{total}] {pct:5.1f}%  "
                  f"{human_size(total_bytes)} hashed  "
                  f"{C.dim(str(path)[:40])}",
                  end="", flush=True)

    if not args.quiet:
        print()  # newline after the last progress line
        print("=" * 72)

    # ---- Group duplicates ----
    dup_groups = {h: paths for h, paths in by_hash.items() if len(paths) > 1}
    total_dupes = sum(len(paths) - 1 for paths in dup_groups.values())
    wasted_bytes = sum(
        (len(paths) - 1) * _safe_size(paths[0])
        for paths in dup_groups.values()
    )

    elapsed = time.time() - start_all

    # ---- Report ----
    if not dup_groups:
        print(C.green(f"✓ No duplicates found. "
                      f"({hashed} files hashed in {elapsed:.2f}s)"))
        if errors:
            print(C.yellow(f"  {errors} file(s) skipped (unreadable)"))
        if args.json:
            Path(args.json).write_text("{}", encoding="utf-8")
            print(f"  JSON written to {args.json}")
        sys.exit(0)

    print()
    print(C.bold(f"Found {len(dup_groups)} duplicate group(s) "
                 f"({total_dupes} redundant file(s), "
                 f"{human_size(wasted_bytes)} recoverable)"))
    print("=" * 72)

    for gi, (digest, paths) in enumerate(
            sorted(dup_groups.items(), key=lambda kv: -len(kv[1])), start=1):
        try:
            size = paths[0].stat().st_size
        except OSError:
            size = 0
        print()
        print(C.cyan(
            f"[Group {gi}] {len(paths)} copies  "
            f"· {human_size(size)} each  · "
            f"{args.algorithm}:{digest[:12]}…"
        ))
        for i, p in enumerate(paths):
            marker = C.green("keep") if i == 0 else C.yellow("dup ")
            print(f"  {marker}  {p}")

    # ---- Optional delete ----
    if args.delete:
        print()
        confirm = input(
            C.red(f"Delete {total_dupes} redundant file(s)? [y/N] ")
        ).strip().lower()
        if confirm == "y":
            deleted = 0
            for paths in dup_groups.values():
                for p in paths[1:]:
                    try:
                        p.unlink()
                        deleted += 1
                    except OSError as e:
                        print(C.red(f"  ! could not delete {p}: {e}"),
                              file=sys.stderr)
            print(C.green(f"✓ Deleted {deleted} file(s)"))
        else:
            print("Aborted.")

    # ---- JSON output ----
    if args.json:
        payload = {
            "algorithm": args.algorithm,
            "directory": str(args.directory),
            "groups": [
                {
                    "hash": h,
                    "files": [str(p) for p in paths],
                    "size": _safe_size(paths[0]),
                }
                for h, paths in dup_groups.items()
            ],
        }
        Path(args.json).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nJSON written to {args.json}")

    # ---- Summary ----
    print()
    print(C.bold("Summary"))
    print(f"  Files scanned:     {total}")
    print(f"  Files hashed:      {hashed}")
    print(f"  Unreadable:        {errors}")
    print(f"  Duplicate groups:  {len(dup_groups)}")
    print(f"  Redundant files:   {total_dupes}")
    print(f"  Recoverable space: {human_size(wasted_bytes)}")
    print(f"  Time:              {elapsed:.2f}s")

    sys.exit(1 if dup_groups else 0)


def _safe_size(p):
    try:
        return p.stat().st_size
    except OSError:
        return 0


if __name__ == "__main__":
    main()
