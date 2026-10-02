"""Batch lifetime / g2 fitting → summary CSVs."""

from pathlib import Path
import warnings

import pandas as pd
from tqdm import tqdm

from .fitting import fit_g2, fit_lifetime
from .grouping import parse_folder, print_unmatched
from .measurements import LifetimeMeasurement, g2Measurement, histogram_axis
from .plotting import repo_root

warnings.filterwarnings("ignore")


def _counts(meas):
    """Full histogram column (not a single bin)."""
    return meas.data.iloc[:, 0].values


def run_pipeline(folder_selected, output_dir=None):
    """Fit Lifetime and g2 files in ``folder_selected``. Returns list of written paths."""
    folder_selected = Path(folder_selected)
    metas, unmatched = parse_folder(folder_selected)
    print(f"🚀 Starting Batch Process on {len(metas)} parsed file(s) from {folder_selected}...")
    print_unmatched(unmatched)

    if not metas and not unmatched:
        print(f"❌ No CSV files found in {folder_selected}. Exiting pipeline.")
        return None

    results_lifetime = []
    results_g2 = []

    for meta in tqdm(metas):
        if meta.type == "Lifetime":
            meas = LifetimeMeasurement(meta)
            meas.load()
            if meas.data is None:
                print(f"🚨 No data: {meta.filepath}")
                continue
            y = _counts(meas)
            x = histogram_axis(meta, len(y), centered=False)
            fit_res = fit_lifetime(x, y)
            results_lifetime.append({
                "Filename": meta.filepath,
                "X": meta.x,
                "Y": meta.y,
                "Power": meta.power,
                "Tau1": fit_res.get("tau1"),
                "Tau2": fit_res.get("tau2"),
                "Success": fit_res.get("success"),
            })
        elif meta.type == "g2":
            meas = g2Measurement(meta)
            meas.load()
            if meas.data is None:
                print(f"🚨 No data: {meta.filepath}")
                continue
            y = _counts(meas)
            x = histogram_axis(meta, len(y), centered=True)
            res = fit_g2(x, y)
            results_g2.append({
                "Filename": meta.filepath,
                "X": meta.x,
                "Y": meta.y,
                "g2_0": res["g2_0"],
                "SinglePhoton": res["is_single_photon"],
            })

    out_dir = Path(output_dir) if output_dir else repo_root() / "data_processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    if results_lifetime:
        dest = out_dir / "summary_lifetime.csv"
        pd.DataFrame(results_lifetime).to_csv(dest, index=False)
        print(f"✅ Saved {len(results_lifetime)} Lifetime results → {dest}")
        written.append(dest)

    if results_g2:
        dest = out_dir / "summary_g2.csv"
        pd.DataFrame(results_g2).to_csv(dest, index=False)
        print(f"✅ Saved {len(results_g2)} g2 results → {dest}")
        written.append(dest)

    if not written:
        print("⚠️  No Lifetime or g2 files were processed.")

    return written
