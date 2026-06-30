import os
import glob
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from src.parsers import FilenameParser
from src.measurements import (
    PLMapMeasurement,
    g2Measurement,
    SpectrumMeasurement,
    StabilityMeasurement,
    SaturationMeasurement,
    LifetimeMeasurement,
)

OUTPUT_DIR = "data_processed"

POINT_TYPES = ['Spectrum', 'g2', 'Stability', 'Saturation', 'Lifetime']

ATTRS_MAP = {
    'power': 'Pow (μW)',
    'integration_time': 'Int (s)',
    'nd': 'ND',
    'filter': 'Filter',
}


def select_folder():
    """Prompt the user to choose a folder containing raw CSV data."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    selected_path = filedialog.askdirectory(title="Select Folder Containing TCSPC CSVs")
    root.destroy()
    return selected_path


def _is_missing(val):
    return (isinstance(val, float) and pd.isna(val)) or str(val).lower() == "none"


def _sort_key(meta):
    power = meta.power if not _is_missing(meta.power) else float('inf')
    int_time = meta.integration_time if not _is_missing(meta.integration_time) else float('inf')
    return (power, int_time)


def metas_at(all_meta, ex, ey, meas_type):
    """Return all metadata records for one emitter and measurement type."""
    return sorted(
        [
            m for m in all_meta
            if m.type == meas_type and round(m.x, 1) == ex and round(m.y, 1) == ey
        ],
        key=_sort_key,
    )


def format_plot_labels(metas, base_title, loc_x, loc_y):
    """
    Move shared parameters into the subplot title and return which attrs vary
    across traces (for legend labels).
    """
    unique_vals = {attr: set() for attr in ATTRS_MAP}
    for meta in metas:
        for attr in ATTRS_MAP:
            val = getattr(meta, attr, float('nan'))
            if not _is_missing(val):
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
        title += f"\n{param_str}"
    return title, varying_params


def trace_label(meta, varying_params):
    if not varying_params:
        return None
    parts = []
    for attr in varying_params:
        val = getattr(meta, attr)
        parts.append(f"{ATTRS_MAP[attr]}: {val}")
    return ", ".join(parts)


def _finalize_subplot(ax, metas, base_title, loc_x, loc_y, xlabel, ylabel, yscale=None):
    title, _ = format_plot_labels(metas, base_title, loc_x, loc_y)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if yscale:
        ax.set_yscale(yscale)

    handles, labels = ax.get_legend_handles_labels()
    if labels and any(labels):
        ax.legend(fontsize=8, loc='best')


def plot_spectrum_series(ax, metas, loc_x, loc_y, wavelength_limits=None):
    _, varying_params = format_plot_labels(metas, "Spectrum", loc_x, loc_y)
    for meta in metas:
        spec_obj = SpectrumMeasurement(meta)
        spec_obj.load()
        if wavelength_limits:
            spec_obj.crop(wavelength_limits[0], wavelength_limits[1])
        spec_obj.plot(ax=ax, label=trace_label(meta, varying_params), configure_axes=False)

    _finalize_subplot(ax, metas, "Spectrum", loc_x, loc_y, "Wavelength (nm)", "Intensity (a.u.)")


def plot_g2_series(ax, metas, loc_x, loc_y):
    _, varying_params = format_plot_labels(metas, "g(2) Correlation", loc_x, loc_y)
    for meta in metas:
        g2_obj = g2Measurement(meta)
        label = trace_label(meta, varying_params)
        g2_obj.plot(ax=ax, label=label, configure_axes=False)

    _finalize_subplot(ax, metas, "g(2) Correlation", loc_x, loc_y, "Delay (ns)", "Coincidences")


def plot_lifetime_series(ax, metas, loc_x, loc_y):
    _, varying_params = format_plot_labels(metas, "Lifetime Decay", loc_x, loc_y)
    for meta in metas:
        life_obj = LifetimeMeasurement(meta)
        label = trace_label(meta, varying_params)
        life_obj.plot(ax=ax, label=label, configure_axes=False)

    _finalize_subplot(
        ax, metas, "Lifetime Decay", loc_x, loc_y,
        "Time (ns)", "Counts (Log)", yscale='log',
    )


def plot_stability_series(ax, metas, loc_x, loc_y):
    _, varying_params = format_plot_labels(metas, "Stability", loc_x, loc_y)
    show_power = len(metas) == 1
    for meta in metas:
        stab_obj = StabilityMeasurement(meta)
        label = trace_label(meta, varying_params)
        stab_obj.plot(
            ax=ax,
            label=label,
            configure_axes=False,
            show_power=show_power,
        )

    _finalize_subplot(ax, metas, "Stability", loc_x, loc_y, "Time (s)", "Counts")
    ax.grid(True, alpha=0.3)


def plot_saturation_series(ax, metas, loc_x, loc_y):
    _, varying_params = format_plot_labels(metas, "Saturation", loc_x, loc_y)
    for meta in metas:
        sat_obj = SaturationMeasurement(meta)
        sat_obj.load()
        voltage = sat_obj.data.iloc[:, 0]
        counts = sat_obj.data.iloc[:, 2] if sat_obj.data.shape[1] > 2 else sat_obj.data.iloc[:, 1]
        label = trace_label(meta, varying_params) or "Saturation"
        ax.plot(voltage, counts, 'o', markersize=6, label=label, alpha=0.85)

    _finalize_subplot(ax, metas, "Saturation", loc_x, loc_y, "Power", "Counts")
    ax.grid(True, alpha=0.3)


def build_suptitle(all_point_metas, ex, ey):
    title, _ = format_plot_labels(all_point_metas, f"Emitter Profile", ex, ey)
    return title.replace("\n", " | ")


def generate_pdf_report(output_filename=None):
    data_folder = select_folder()
    if not data_folder:
        print("❌ No folder selected. Exiting.")
        return

    if output_filename is None:
        output_filename = os.path.join(OUTPUT_DIR, "Emitter Char (SIL).pdf")

    search_pattern = os.path.join(data_folder, "*.csv")
    files = glob.glob(search_pattern)
    print(f"Scanning {len(files)} files in {data_folder}...")

    all_meta = [FilenameParser.parse(f) for f in files]
    all_meta = [m for m in all_meta if m is not None]

    if not all_meta:
        print(f"❌ No valid TCSPC files found in {data_folder}")
        return

    emitters = []
    for meta in all_meta:
        if meta.type in POINT_TYPES:
            emitters.append((round(meta.x, 1), round(meta.y, 1)))

    unique_emitters = sorted(set(emitters))
    total_emitters = len(unique_emitters)
    print(f"🚀 Processing {total_emitters} unique emitters...")

    pl_scans = [PLMapMeasurement(m) for m in all_meta if m.type == 'PL']

    os.makedirs(os.path.dirname(output_filename), exist_ok=True)

    with PdfPages(output_filename) as pdf:
        for idx, (ex, ey) in enumerate(unique_emitters):
            print(f"   -> Rendering page {idx + 1}/{total_emitters} for Emitter at ({ex}, {ey})...")

            spec_metas = metas_at(all_meta, ex, ey, 'Spectrum')
            g2_metas = metas_at(all_meta, ex, ey, 'g2')
            life_metas = metas_at(all_meta, ex, ey, 'Lifetime')
            stab_metas = metas_at(all_meta, ex, ey, 'Stability')
            sat_metas = metas_at(all_meta, ex, ey, 'Saturation')

            match_pl = None
            min_dist = float('inf')
            for pl in pl_scans:
                ext = pl.get_extent()
                if ext[0] <= ex <= ext[1] and ext[2] <= ey <= ext[3]:
                    dist = (ex - pl.meta.x) ** 2 + (ey - pl.meta.y) ** 2
                    if dist < min_dist:
                        min_dist = dist
                        match_pl = pl

            active_plots = []
            if match_pl:
                active_plots.append('PL')
            if spec_metas:
                active_plots.append('Spec')
            if g2_metas:
                active_plots.append('g2')
            if life_metas:
                active_plots.append('Life')
            if stab_metas:
                active_plots.append('Stab')
            if sat_metas:
                active_plots.append('Sat')

            num_plots = len(active_plots)
            if num_plots == 0:
                continue

            if num_plots == 1:
                rows, cols = 1, 1
            elif num_plots == 2:
                rows, cols = 1, 2
            elif num_plots <= 4:
                rows, cols = 2, 2
            else:
                rows, cols = 2, 3

            fig = plt.figure(figsize=(15, 10))

            all_point_metas = spec_metas + g2_metas + life_metas + stab_metas + sat_metas
            plt.suptitle(build_suptitle(all_point_metas, ex, ey), fontsize=14, fontweight='bold')

            current_idx = 1

            if 'PL' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                if match_pl.data is None:
                    match_pl.load()
                ext = match_pl.get_extent()
                ax.imshow(match_pl.data, extent=ext, cmap='inferno', origin='lower')
                ax.plot(ex, ey, 'w+', markersize=15, markeredgewidth=2)
                ax.set_title("PL Map Location Overlay")
                ax.set_xlabel("X (μm)")
                ax.set_ylabel("Y (μm)")
                current_idx += 1

            if 'Spec' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                plot_spectrum_series(ax, spec_metas, ex, ey)
                current_idx += 1

            if 'g2' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                plot_g2_series(ax, g2_metas, ex, ey)
                current_idx += 1

            if 'Life' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                plot_lifetime_series(ax, life_metas, ex, ey)
                current_idx += 1

            if 'Stab' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                plot_stability_series(ax, stab_metas, ex, ey)
                current_idx += 1

            if 'Sat' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                plot_saturation_series(ax, sat_metas, ex, ey)
                current_idx += 1

            plt.tight_layout(rect=[0, 0.03, 1, 0.95])
            pdf.savefig(fig)
            plt.close(fig)

    print(f"\n✅ Report generated: {output_filename}")


if __name__ == "__main__":
    generate_pdf_report()
