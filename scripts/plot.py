#!/usr/bin/env python3
"""Plot selected CSV file(s) to one PNG each.

    python scripts/plot.py
    python scripts/plot.py a.csv b.csv
    python scripts/plot.py path/to/folder
    python scripts/plot.py --out DIR a.csv
"""

from __future__ import annotations

import argparse
import _repo  # noqa: F401

from tcspc.dialogs import pick_files
from tcspc.grouping import expand_csv_paths, print_unmatched
from tcspc.plotting import plot_paths


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Plot selected TCSPC CSV file(s) to PNG images (one per file)."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="CSV files and/or a folder of CSVs. If omitted, a file dialog opens.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output folder (default: data_processed/plots/<timestamp>/)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.paths:
        files, missing = expand_csv_paths(args.paths)
        for path in missing:
            print(f"❌ Not found: {path}")
    else:
        try:
            files = pick_files()
        except Exception as exc:
            print(f"❌ File dialog failed ({exc}). Pass file paths on the command line instead.")
            return 1

    if not files:
        print("❌ No files selected. Exiting.")
        return 1

    print(f"Plotting {len(files)} file(s)...")
    saved, unmatched, errors, out_dir = plot_paths(files, args.out)
    print_unmatched(unmatched)
    print(f"\n✅ Saved {len(saved)} PNG(s) → {out_dir}")
    if unmatched or errors:
        print(f"   Skipped {len(unmatched) + len(errors)} file(s).")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
