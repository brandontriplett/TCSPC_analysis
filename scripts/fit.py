#!/usr/bin/env python3
"""Batch-fit lifetime and g2 CSVs in a folder to summary CSVs.

    python scripts/fit.py
    python scripts/fit.py /path/to/csvs
    python scripts/fit.py /path/to/csvs --out DIR
"""

from __future__ import annotations

import argparse
import _repo  # noqa: F401

from tcspc.batch import run_pipeline
from tcspc.dialogs import pick_folder


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fit lifetime and g2 CSVs in a folder; write summary CSVs."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Folder of CSV files. If omitted, a folder dialog opens.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output folder for summary CSVs (default: data_processed/)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    folder = args.folder
    if not folder:
        try:
            folder = pick_folder(title="Select Folder Containing Raw CSV Data")
        except Exception as exc:
            print(f"❌ Folder dialog failed ({exc}). Pass a folder on the command line instead.")
            return 1
    if not folder:
        print("❌ No folder selected. Exiting pipeline.")
        return 1
    result = run_pipeline(folder, output_dir=args.out)
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
