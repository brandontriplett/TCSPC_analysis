"""Shared matplotlib helpers for file-mode PNGs and the emitter PDF report."""

from datetime import datetime
from pathlib import Path

import pandas as pd

from .measurements import (
    LifetimeMeasurement,
    PLMapMeasurement,
    SaturationMeasurement,
    SpectrumMeasurement,
    StabilityMeasurement,
    g2Measurement,
)

TYPE_TO_CLASS = {
    "PL": PLMapMeasurement,
    "Spectrum": SpectrumMeasurement,
    "Lifetime": LifetimeMeasurement,
    "g2": g2Measurement,
    "Stability": StabilityMeasurement,
    "Saturation": SaturationMeasurement,
}

TYPE_TITLES = {
    "PL": "PL Map",
    "Spectrum": "Spectrum",
    "Lifetime": "Lifetime Decay",
    "g2": "g(2) Correlation",
    "Stability": "Stability",
    "Saturation": "Saturation",
}

ATTRS_MAP = {
    "power": "Pow (μW)",
    "integration_time": "Int (s)",
    "nd": "ND",
    "filter": "Filter",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def is_missing(val) -> bool:
    return (isinstance(val, float) and pd.isna(val)) or str(val).lower() == "none"


def measurement_from_meta(meta):
    cls = TYPE_TO_CLASS.get(meta.type)
    if cls is None:
        raise ValueError(f"Unknown measurement type: {meta.type}")
    return cls(meta)


def title_for_file(meta) -> str:
    """Self-describing title for a single-file plot."""
    title = f"{TYPE_TITLES.get(meta.type, meta.type)} @ ({meta.x}, {meta.y})"
    parts = []
    for attr, label in ATTRS_MAP.items():
        val = getattr(meta, attr, float("nan"))
        if is_missing(val):
            continue
        parts.append(f"{label}: {val}")
    if parts:
        title += "\n" + " | ".join(parts)
    return title


def format_plot_labels(metas, base_title, loc_x, loc_y, html=False):
    """
    Put parameters that are shared across traces into the title.
    Return which attrs vary (for legend labels).

    ``html=True`` uses a Plotly subtitle (``<br><sup>…</sup>``) instead of a newline.
    """
    unique_vals = {attr: set() for attr in ATTRS_MAP}
    for meta in metas:
        for attr in ATTRS_MAP:
            val = getattr(meta, attr, float("nan"))
            if not is_missing(val):
                unique_vals[attr].add(val)

    static_params = {}
    varying_params = []
    for attr, label in ATTRS_MAP.items():
        if len(unique_vals[attr]) == 1:
            static_params[label] = list(unique_vals[attr])[0]
        elif len(unique_vals[attr]) > 1:
            varying_params.append(attr)

    title = f"{base_title} @ ({loc_x}, {loc_y})"
    if static_params:
        param_str = " | ".join(f"{label}: {value}" for label, value in static_params.items())
        title += f"<br><sup>{param_str}</sup>" if html else f"\n{param_str}"
    return title, varying_params


def trace_label(meta, varying_params):
    if not varying_params:
        return None
    parts = []
    for attr in varying_params:
        val = getattr(meta, attr)
        parts.append(f"{ATTRS_MAP[attr]}: {val}")
    return ", ".join(parts)


def plots_output_dir(explicit=None) -> Path:
    """Default: <repo>/data_processed/plots/<timestamp>/. ``explicit`` uses that folder as-is."""
    if explicit:
        path = Path(explicit)
    else:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = repo_root() / "data_processed" / "plots" / stamp
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_png(fig, path, dpi=150):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    return path


def plot_one(meta, out_dir: Path) -> Path:
    """Render one measurement to ``<stem>.png`` in ``out_dir``."""
    import matplotlib.pyplot as plt

    meas = measurement_from_meta(meta)
    fig, ax = plt.subplots(figsize=(8, 5))
    meas.plot(ax=ax, configure_axes=True)
    ax.set_title(title_for_file(meta), fontsize=11)
    fig.tight_layout()
    dest = Path(out_dir) / f"{Path(meta.filepath).stem}.png"
    save_png(fig, dest)
    plt.close(fig)
    return dest


def plot_paths(filepaths, out_dir=None):
    """Plot each parsed file to a PNG. Returns (saved, unmatched, errors, out_dir)."""
    from .grouping import parse_files

    out_dir = plots_output_dir(out_dir)
    metas, unmatched = parse_files(filepaths)
    saved = []
    errors = []
    for meta in metas:
        try:
            saved.append(plot_one(meta, out_dir))
        except Exception as exc:
            errors.append((meta.filepath, exc))
            print(f"🚨 Failed to plot {meta.filepath}: {exc}")
    return saved, unmatched, errors, out_dir
