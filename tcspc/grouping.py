"""Group parsed measurements by stage coordinate for the emitter report."""

from pathlib import Path

import pandas as pd

from .parsers import FilenameParser


POINT_TYPES = ("Spectrum", "g2", "Stability", "Saturation", "Lifetime")


def _is_missing(val) -> bool:
    return (isinstance(val, float) and pd.isna(val)) or str(val).lower() == "none"


def parse_files(filepaths):
    """Parse an iterable of paths. Returns (metas, unmatched_paths)."""
    metas = []
    unmatched = []
    for raw in filepaths:
        path = str(raw)
        meta = FilenameParser.parse(path)
        if meta is None:
            unmatched.append(path)
        else:
            metas.append(meta)
    return metas, unmatched


def parse_folder(folder):
    """Parse ``*.csv`` in ``folder`` (not recursive). Returns (metas, unmatched)."""
    folder = Path(folder)
    files = sorted(folder.glob("*.csv"))
    return parse_files(files)


def expand_csv_paths(raw_paths):
    """Expand files and directories (non-recursive *.csv). Returns (files, missing)."""
    files = []
    missing = []
    for raw in raw_paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.glob("*.csv")))
        elif path.is_file():
            files.append(path)
        else:
            missing.append(str(path))
    return files, missing


def round_coord(value) -> float:
    return round(float(value), 1)


def unique_emitters(metas):
    """Sorted unique (x, y) pairs for point measurements, rounded to 0.1 µm."""
    seen = set()
    for meta in metas:
        if meta.type in POINT_TYPES:
            seen.add((round_coord(meta.x), round_coord(meta.y)))
    return sorted(seen)


def _sort_key(meta):
    power = meta.power if not _is_missing(meta.power) else float("inf")
    int_time = meta.integration_time if not _is_missing(meta.integration_time) else float("inf")
    return (power, int_time)


def metas_at(all_meta, ex, ey, meas_type):
    """Metadata records for one emitter and measurement type, sorted by power then int time."""
    return sorted(
        [
            m
            for m in all_meta
            if m.type == meas_type and round_coord(m.x) == ex and round_coord(m.y) == ey
        ],
        key=_sort_key,
    )


def match_pl(pl_scans, ex, ey):
    """Nearest PL map whose extent contains (ex, ey), or None.

    ``pl_scans`` is an iterable of objects with ``get_extent()`` and ``meta``.
    """
    match = None
    min_dist = float("inf")
    for pl in pl_scans:
        try:
            ext = pl.get_extent()
        except (TypeError, ValueError):
            continue
        if any(pd.isna(v) for v in ext):
            continue
        if ext[0] <= ex <= ext[1] and ext[2] <= ey <= ext[3]:
            dist = (ex - pl.meta.x) ** 2 + (ey - pl.meta.y) ** 2
            if dist < min_dist:
                min_dist = dist
                match = pl
    return match


def print_unmatched(unmatched, limit=20):
    if not unmatched:
        return
    print(f"⚠️  Skipped {len(unmatched)} file(s) that did not match a known filename pattern:")
    for path in unmatched[:limit]:
        print(f"    - {Path(path).name}")
    extra = len(unmatched) - limit
    if extra > 0:
        print(f"    … and {extra} more")
