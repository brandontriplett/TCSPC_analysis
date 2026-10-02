#!/usr/bin/env python3
"""One PDF page per unique (X, Y) with all measurements at that spot.

    python scripts/report.py
    python scripts/report.py /path/to/csvs
    python scripts/report.py /path/to/csvs --out report.pdf
"""

from __future__ import annotations

import argparse
import _repo  # noqa: F401

from tcspc.dialogs import pick_folder
from tcspc.report import generate_pdf_report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a per-emitter PDF report from a folder of TCSPC CSVs."
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
        help="Output PDF path (default: data_processed/<folder_name>.pdf)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    folder = args.folder
    if not folder:
        try:
            folder = pick_folder()
        except Exception as exc:
            print(f"❌ Folder dialog failed ({exc}). Pass a folder on the command line instead.")
            return 1
    if not folder:
        print("❌ No folder selected. Exiting.")
        return 1
    result = generate_pdf_report(folder, output_filename=args.out)
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
