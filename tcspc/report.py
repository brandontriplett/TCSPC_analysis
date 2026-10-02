"""Emitter-mode PDF: one page per unique (X, Y)."""

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from .grouping import match_pl, metas_at, parse_folder, print_unmatched, unique_emitters
from .measurements import PLMapMeasurement
from .plotting import (
    TYPE_TITLES,
    format_plot_labels,
    measurement_from_meta,
    repo_root,
    trace_label,
)


def default_report_path(source_folder: Path) -> Path:
    out_dir = repo_root() / "data_processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{source_folder.name}.pdf"
    if dest.exists():
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        dest = out_dir / f"{source_folder.name}_{stamp}.pdf"
    return dest


def _finalize_subplot(ax, metas, base_title, loc_x, loc_y, xlabel, ylabel, yscale=None):
    title, _ = format_plot_labels(metas, base_title, loc_x, loc_y)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if yscale:
        ax.set_yscale(yscale)
    handles, labels = ax.get_legend_handles_labels()
    if labels and any(labels):
        ax.legend(fontsize=8, loc="best")


def plot_spectrum_series(ax, metas, loc_x, loc_y, wavelength_limits=None):
    _, varying_params = format_plot_labels(metas, TYPE_TITLES["Spectrum"], loc_x, loc_y)
    for meta in metas:
        spec_obj = measurement_from_meta(meta)
        spec_obj.load()
        if wavelength_limits:
            spec_obj.crop(wavelength_limits[0], wavelength_limits[1])
        spec_obj.plot(ax=ax, label=trace_label(meta, varying_params), configure_axes=False)
    _finalize_subplot(ax, metas, TYPE_TITLES["Spectrum"], loc_x, loc_y, "Wavelength (nm)", "Intensity (a.u.)")


def plot_g2_series(ax, metas, loc_x, loc_y):
    _, varying_params = format_plot_labels(metas, TYPE_TITLES["g2"], loc_x, loc_y)
    for meta in metas:
        g2_obj = measurement_from_meta(meta)
        g2_obj.plot(ax=ax, label=trace_label(meta, varying_params), configure_axes=False)
    _finalize_subplot(ax, metas, TYPE_TITLES["g2"], loc_x, loc_y, "Delay (ns)", "Coincidences")


def plot_lifetime_series(ax, metas, loc_x, loc_y):
    _, varying_params = format_plot_labels(metas, TYPE_TITLES["Lifetime"], loc_x, loc_y)
    for meta in metas:
        life_obj = measurement_from_meta(meta)
        life_obj.plot(ax=ax, label=trace_label(meta, varying_params), configure_axes=False)
    _finalize_subplot(
        ax, metas, TYPE_TITLES["Lifetime"], loc_x, loc_y,
        "Time (ns)", "Counts (Log)", yscale="log",
    )


def plot_stability_series(ax, metas, loc_x, loc_y):
    _, varying_params = format_plot_labels(metas, TYPE_TITLES["Stability"], loc_x, loc_y)
    show_power = len(metas) == 1
    for meta in metas:
        stab_obj = measurement_from_meta(meta)
        stab_obj.plot(
            ax=ax,
            label=trace_label(meta, varying_params),
            configure_axes=False,
            show_power=show_power,
        )
    _finalize_subplot(ax, metas, TYPE_TITLES["Stability"], loc_x, loc_y, "Time (s)", "Counts")
    ax.grid(True, alpha=0.3)


def plot_saturation_series(ax, metas, loc_x, loc_y):
    _, varying_params = format_plot_labels(metas, TYPE_TITLES["Saturation"], loc_x, loc_y)
    for meta in metas:
        sat_obj = measurement_from_meta(meta)
        sat_obj.plot(ax=ax, label=trace_label(meta, varying_params) or "Saturation", configure_axes=False)
    _finalize_subplot(ax, metas, TYPE_TITLES["Saturation"], loc_x, loc_y, "Power", "Counts")
    ax.grid(True, alpha=0.3)


def plot_pl_overlay(ax, pl_map, ex, ey):
    if pl_map.data is None:
        pl_map.load()
    ext = pl_map.get_extent()
    ax.imshow(pl_map.data, extent=ext, cmap="inferno", origin="lower")
    ax.plot(ex, ey, "w+", markersize=15, markeredgewidth=2)
    ax.set_title("PL Map Location Overlay")
    ax.set_xlabel("X (μm)")
    ax.set_ylabel("Y (μm)")


def build_suptitle(all_point_metas, ex, ey):
    title, _ = format_plot_labels(all_point_metas, "Emitter Profile", ex, ey)
    return title.replace("\n", " | ")


def _grid_shape(num_plots):
    if num_plots <= 1:
        return 1, 1
    if num_plots == 2:
        return 1, 2
    if num_plots <= 4:
        return 2, 2
    return 2, 3


def _safe_subplot(ax, fn, *args, **kwargs):
    try:
        fn(ax, *args, **kwargs)
    except Exception as exc:
        ax.set_title("Plot failed")
        ax.text(0.5, 0.5, str(exc), ha="center", va="center", wrap=True, transform=ax.transAxes)
        print(f"     🚨 subplot error: {exc}")


def render_emitter_page(pdf, all_meta, pl_scans, ex, ey):
    spec_metas = metas_at(all_meta, ex, ey, "Spectrum")
    g2_metas = metas_at(all_meta, ex, ey, "g2")
    life_metas = metas_at(all_meta, ex, ey, "Lifetime")
    stab_metas = metas_at(all_meta, ex, ey, "Stability")
    sat_metas = metas_at(all_meta, ex, ey, "Saturation")
    matched_pl = match_pl(pl_scans, ex, ey)

    slots = []
    if matched_pl:
        slots.append(("PL", lambda ax: plot_pl_overlay(ax, matched_pl, ex, ey)))
    if spec_metas:
        slots.append(("Spec", lambda ax: plot_spectrum_series(ax, spec_metas, ex, ey)))
    if g2_metas:
        slots.append(("g2", lambda ax: plot_g2_series(ax, g2_metas, ex, ey)))
    if life_metas:
        slots.append(("Life", lambda ax: plot_lifetime_series(ax, life_metas, ex, ey)))
    if stab_metas:
        slots.append(("Stab", lambda ax: plot_stability_series(ax, stab_metas, ex, ey)))
    if sat_metas:
        slots.append(("Sat", lambda ax: plot_saturation_series(ax, sat_metas, ex, ey)))

    if not slots:
        return False

    rows, cols = _grid_shape(len(slots))
    fig = plt.figure(figsize=(15, 10))
    all_point_metas = spec_metas + g2_metas + life_metas + stab_metas + sat_metas
    plt.suptitle(build_suptitle(all_point_metas, ex, ey), fontsize=14, fontweight="bold")

    for idx, (_name, renderer) in enumerate(slots, start=1):
        ax = fig.add_subplot(rows, cols, idx)
        _safe_subplot(ax, renderer)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)
    return True


def generate_pdf_report(data_folder, output_filename=None):
    """Write a per-emitter PDF from a folder of CSVs. Returns the output path, or None."""
    data_folder = Path(data_folder)
    all_meta, unmatched = parse_folder(data_folder)
    print(f"Scanning {data_folder}... parsed {len(all_meta)}, skipped {len(unmatched)}")
    print_unmatched(unmatched)

    if not all_meta:
        print(f"❌ No valid TCSPC files found in {data_folder}")
        return None

    emitters = unique_emitters(all_meta)
    if not emitters:
        print("⚠️  No point measurements (Spectrum, g2, Lifetime, Stability, Saturation) found.")
        return None
    print(f"🚀 Processing {len(emitters)} unique emitters...")

    pl_scans = [PLMapMeasurement(m) for m in all_meta if m.type == "PL"]

    if output_filename is None:
        output_filename = default_report_path(data_folder)
    else:
        output_filename = Path(output_filename)
        output_filename.parent.mkdir(parents=True, exist_ok=True)

    pages = 0
    with PdfPages(output_filename) as pdf:
        for idx, (ex, ey) in enumerate(emitters):
            print(f"   -> Rendering page {idx + 1}/{len(emitters)} for Emitter at ({ex}, {ey})...")
            try:
                if render_emitter_page(pdf, all_meta, pl_scans, ex, ey):
                    pages += 1
            except Exception as exc:
                print(f"     🚨 skipped emitter ({ex}, {ey}): {exc}")
                plt.close("all")

    print(f"\n✅ Report generated ({pages} page(s)): {output_filename}")
    return str(output_filename)
