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
from src.measurements import PLMapMeasurement, g2Measurement, SpectrumMeasurement

def select_folder():
    """Opens a native Mac folder selection dialog."""
    root = tk.Tk()
    root.withdraw()  # Hide the tiny main tkinter window
    root.attributes('-topmost', True)  # Bring the dialog to the front
    selected_path = filedialog.askdirectory(title="Select Folder Containing TCSPC CSVs")
    root.destroy()
    return selected_path

def generate_pdf_report(output_filename="data_processed/Emitter_Report_Peigang.pdf"):
    # 1. User Inputs: Folder and Crop Range
    data_folder = select_folder()
    if not data_folder:
        print("❌ No folder selected. Exiting.")
        return

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

    # 3. Identify Unique Emitters (By coordinate)
    # Using Spectrum and g2 as the primary indicators of a point-of-interest
    emitters = []
    for m in all_meta:
        if m.type in ['Spectrum', 'g2']:
            emitters.append((round(m.x, 1), round(m.y, 1)))
    
    unique_emitters = sorted(list(set(emitters)))
    print(f"🚀 Processing {len(unique_emitters)} unique emitters...")

    # 4. Separate PL Scans for search logic
    pl_scans = [PLMapMeasurement(m) for m in all_meta if m.type == 'PL']

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)

    with PdfPages(output_filename) as pdf:
        for ex, ey in unique_emitters:
            # Match data for THIS specific emitter
            this_g2 = next((m for m in all_meta if m.type == 'g2' and round(m.x, 1) == ex and round(m.y, 1) == ey), None)
            this_spec = next((m for m in all_meta if m.type == 'Spectrum' and round(m.x, 1) == ex and round(m.y, 1) == ey), None)
            
            # Find the best PL scan that contains this coordinate
            match_pl = None
            for pl in pl_scans:
                ext = pl.get_extent()
                if ext[0] <= ex <= ext[1] and ext[2] <= ey <= ext[3]:
                    match_pl = pl
                    break

            # --- PLOTTING ---
            fig = plt.figure(figsize=(11, 8.5))
            plt.suptitle(f"Emitter Profile: X={ex}, Y={ey}", fontsize=16, fontweight='bold')

            # Subplot 1: PL Map Context
            ax1 = fig.add_subplot(2, 2, 1)
            if match_pl:
                match_pl.load()
                ext = match_pl.get_extent()
                ax1.imshow(match_pl.data, extent=ext, cmap='inferno', origin='lower')
                ax1.plot(ex, ey, 'w+', markersize=15, markeredgewidth=2) # Overlay crosshair
                ax1.set_title("PL Map Location Overlay")
                ax1.set_xlabel("X (μm)")
                ax1.set_ylabel("Y (μm)")
            else:
                ax1.text(0.5, 0.5, "No matching PL scan found", ha='center', va='center')

            # Subplot 2: g2
            ax2 = fig.add_subplot(2, 2, 2)
            if this_g2:
                g2_obj = g2Measurement(this_g2)
                g2_obj.plot(ax=ax2)
            else:
                ax2.text(0.5, 0.5, "g2 Data Missing", ha='center', va='center')

            # Subplot 3: Spectrum
            ax3 = fig.add_subplot(2, 2, 3)
            if this_spec:
                spec_obj = SpectrumMeasurement(this_spec)
                spec_obj.load()
                if wavelength_limits:
                    spec_obj.crop(wavelength_limits[0], wavelength_limits[1])
                spec_obj.plot(ax=ax3)
            else:
                ax3.text(0.5, 0.5, "Spectrum Data Missing", ha='center', va='center')

            # Subplot 4: Summary Table
            ax4 = fig.add_subplot(2, 2, 4)
            ax4.axis('off')
            
            summary_text = (
                f"COORDINATES: ({ex}, {ey})\n\n"
                f"--- Environment (g2 file) ---\n"
                f"Power:  {this_g2.power if this_g2 else 'N/A'} μW\n"
                f"Filter: {this_g2.filter if this_g2 else 'N/A'}\n"
                f"ND:     {this_g2.nd if this_g2 else 'N/A'}\n\n"
                f"--- Source Files ---\n"
                f"g2:   {os.path.basename(this_g2.filepath) if this_g2 else 'None'}\n"
                f"Spec: {os.path.basename(this_spec.filepath) if this_spec else 'None'}"
            )
            
            ax4.text(0.05, 0.85, summary_text, fontsize=10, verticalalignment='top', 
                     fontfamily='monospace', linespacing=1.6,
                     bbox=dict(boxstyle='round,pad=1', facecolor='azure', edgecolor='steelblue', alpha=0.3))

            plt.tight_layout(rect=[0, 0.03, 1, 0.95])
            pdf.savefig(fig)
            plt.close(fig)

    print(f"\n✅ Report generated: {output_filename}")

if __name__ == "__main__":
    generate_pdf_report()