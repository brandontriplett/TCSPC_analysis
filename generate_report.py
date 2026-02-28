import os
import glob
import tkinter as tk
from tkinter import filedialog
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# Importing the classes we built in previous steps
from src.parsers import FilenameParser
from src.measurements import PLMapMeasurement, g2Measurement, SpectrumMeasurement, StabilityMeasurement, SaturationMeasurement, LifetimeMeasurement

def select_folder():
    """Opens a native Mac folder selection dialog."""
    root = tk.Tk()
    root.withdraw()  # Hide the tiny main tkinter window
    root.attributes('-topmost', True)  # Bring the dialog to the front
    selected_path = filedialog.askdirectory(title="Select Folder Containing TCSPC CSVs")
    root.destroy()
    return selected_path

def generate_pdf_report(output_filename="data_processed/0225_autoscan.pdf"):
    # 1. User Inputs: Folder and Crop Range
    data_folder = select_folder()
    if not data_folder:
        print("❌ No folder selected. Exiting.")
        return

    print("\n" + "="*40)
    crop_input = input("Enter wavelength crop range (min, max in nm) or Enter for full: ")
    wavelength_limits = None
    if crop_input.strip():
        try:
            wavelength_limits = [float(val) for val in crop_input.split(',')]
            print(f"✂️ Spectra will be cropped to: {wavelength_limits[0]} - {wavelength_limits[1]} nm")
        except ValueError:
            print("⚠️ Invalid format. Using full spectrum.")

    # 2. Gather and Parse all files
    files = glob.glob(os.path.join(data_folder, "*.csv"))
    all_meta = [FilenameParser.parse(f) for f in files]
    all_meta = [m for m in all_meta if m is not None]

    if not all_meta:
        print(f"❌ No valid TCSPC files found in {data_folder}")
        return

    # 3. Identify Unique Emitters (Added Lifetime to the search)
    emitters = []
    for m in all_meta:
        if m.type in ['Spectrum', 'g2', 'Stability', 'Saturation', 'Lifetime']:
            emitters.append((round(m.x, 1), round(m.y, 1)))
    
    unique_emitters = sorted(list(set(emitters)))
    total_emitters = len(unique_emitters)
    print(f"🚀 Processing {total_emitters} unique emitters...")

    # 4. Separate PL Scans for search logic
    pl_scans = [PLMapMeasurement(m) for m in all_meta if m.type == 'PL']

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)

    with PdfPages(output_filename) as pdf:
        for idx, (ex, ey) in enumerate(unique_emitters):
            print(f"   -> Rendering page {idx + 1}/{total_emitters} for Emitter at ({ex}, {ey})...")
            
            # Match data for THIS specific emitter
            this_g2 = next((m for m in all_meta if m.type == 'g2' and round(m.x, 1) == ex and round(m.y, 1) == ey), None)
            this_spec = next((m for m in all_meta if m.type == 'Spectrum' and round(m.x, 1) == ex and round(m.y, 1) == ey), None)
            this_life = next((m for m in all_meta if m.type == 'Lifetime' and round(m.x, 1) == ex and round(m.y, 1) == ey), None)
            this_stab = next((m for m in all_meta if m.type == 'Stability' and round(m.x, 1) == ex and round(m.y, 1) == ey), None)
            this_sat = next((m for m in all_meta if m.type == 'Saturation' and round(m.x, 1) == ex and round(m.y, 1) == ey), None)
            
            # Find the best PL scan (most centered)
            match_pl = None
            min_dist = float('inf')
            
            for pl in pl_scans:
                ext = pl.get_extent()
                if ext[0] <= ex <= ext[1] and ext[2] <= ey <= ext[3]:
                    dist = (ex - pl.meta.x)**2 + (ey - pl.meta.y)**2
                    if dist < min_dist:
                        min_dist = dist
                        match_pl = pl

            # --- DYNAMIC LAYOUT LOGIC ---
            active_plots = []
            if match_pl: active_plots.append('PL')
            if this_spec: active_plots.append('Spec')
            if this_g2: active_plots.append('g2')
            if this_life: active_plots.append('Life')
            if this_stab: active_plots.append('Stab')
            if this_sat: active_plots.append('Sat')
            
            num_plots = len(active_plots)
            if num_plots == 0:
                continue

            # Determine grid dimensions
            if num_plots == 1: rows, cols = 1, 1
            elif num_plots == 2: rows, cols = 1, 2
            elif num_plots <= 4: rows, cols = 2, 2
            else: rows, cols = 2, 3 # Maxes out perfectly at 6 plots!

            # Set up the figure
            fig = plt.figure(figsize=(15, 10))
            
            # Build the dynamic slide title
            env_file = this_g2 or this_spec or this_life or this_stab or this_sat
            power_val = f"{env_file.power} μW" if env_file and not pd.isna(env_file.power) else 'N/A'
            filter_val = env_file.filter if env_file else 'N/A'
            nd_val = env_file.nd if env_file and not pd.isna(env_file.nd) else 'N/A'
            
            suptitle_text = f"Emitter Profile: X={ex}, Y={ey} | Power: {power_val} | Filter: {filter_val} | ND: {nd_val}"
            plt.suptitle(suptitle_text, fontsize=16, fontweight='bold')

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
                spec_obj = SpectrumMeasurement(this_spec)
                if wavelength_limits:
                    spec_obj.load() 
                    spec_obj.crop(wavelength_limits[0], wavelength_limits[1])
                spec_obj.plot(ax=ax)
                
                # Append integration time to title
                int_time = this_spec.integration_time if not pd.isna(this_spec.integration_time) else "N/A"
                ax.set_title(f"Spectrum (Int: {int_time}s)")
                current_idx += 1

            if 'g2' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                g2_obj = g2Measurement(this_g2)
                g2_obj.plot(ax=ax)
                
                # Append integration time to title
                int_time = this_g2.integration_time if not pd.isna(this_g2.integration_time) else "N/A"
                ax.set_title(f"g(2) Correlation (Int: {int_time}s)")
                current_idx += 1

            if 'Life' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                life_obj = LifetimeMeasurement(this_life)
                life_obj.plot(ax=ax)
                
                # Append integration time to title
                int_time = this_life.integration_time if not pd.isna(this_life.integration_time) else "N/A"
                ax.set_title(f"Lifetime Decay (Int: {int_time}s)")
                current_idx += 1

            if 'Stab' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                stab_obj = StabilityMeasurement(this_stab)
                stab_obj.plot(ax=ax)
                current_idx += 1

            if 'Sat' in active_plots:
                ax = fig.add_subplot(rows, cols, current_idx)
                sat_obj = SaturationMeasurement(this_sat)
                sat_obj.plot(ax=ax)
                current_idx += 1

            # Adjust layout and save the page
            plt.tight_layout(rect=[0, 0.03, 1, 0.95])
            pdf.savefig(fig)
            plt.close(fig)

    print(f"\n✅ Report generated: {output_filename}")

if __name__ == "__main__":
    generate_pdf_report()