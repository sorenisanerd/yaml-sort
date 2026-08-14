"""yaml-sort command-line interface."""

from __future__ import annotations

import argparse
import difflib
import os
import sys

from .core import sort_text


def _parse_list_indent(value: str):
    if value == "keep":
        return None
    try:
        n = int(value)
    except ValueError:
        sys.exit(f"error: --list-indent must be 'keep' or an integer, got {value!r}")
    if n < 0:
        sys.exit("error: --list-indent must be >= 0")
    return n


def normalize(path: str, list_indent) -> bytes:
    with open(path, "rb") as f:
        return sort_text(f.read().decode("utf-8"), list_indent).encode("utf-8")


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Deterministic YAML key sorter — eliminates merge-conflict noise.",
    )
    ap.add_argument("files", nargs="*", metavar="FILE", help="YAML file(s) to sort")
    ap.add_argument("--check", action="store_true", help="Exit 0 if sorted, 1 if not")
    ap.add_argument("--diff", action="store_true", help="Show diff without writing")
    ap.add_argument("--stdin", action="store_true", help="Read stdin, write sorted to stdout")
    ap.add_argument("--list-indent", default="keep", metavar="N|keep",
                    help="Sequence item indent relative to parent key "
                         "(0=aligned, 2=indented). 'keep' preserves existing "
                         "indentation (default).")
    return ap


def main(argv=None) -> None:
    ap = _build_parser()
    args = ap.parse_args(argv)

    list_indent = _parse_list_indent(args.list_indent)

    if args.stdin:
        if args.check or args.diff:
            sys.exit("error: --stdin incompatible with --check / --diff")
        sys.stdout.write(sort_text(sys.stdin.read(), list_indent))
        return

    if not args.files:
        ap.print_help()
        sys.exit(1)

    exit_code = 0
    for path in args.files:
        if not os.path.isfile(path):
            print(f"error: not a file — {path}", file=sys.stderr)
            exit_code = 1
            continue
        normalized = normalize(path, list_indent)
        with open(path, "rb") as f:
            original = f.read()
        if args.check:
            if original != normalized:
                print(f"not sorted — {path}", file=sys.stderr)
                exit_code = 1
            continue
        if args.diff:
            if original != normalized:
                t1 = original.decode("utf-8").splitlines(keepends=True)
                t2 = normalized.decode("utf-8").splitlines(keepends=True)
                sys.stdout.writelines(difflib.unified_diff(t1, t2,
                    fromfile=f"a/{path}", tofile=f"b/{path}"))
            continue
        if original == normalized:
            continue
        with open(path, "wb") as f:
            f.write(normalized)
        print(f"sorted — {path}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
