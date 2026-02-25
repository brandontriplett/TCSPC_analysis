import pandas as pd
import numpy as np
import glob
import os
import tkinter as tk
from tkinter import filedialog
from tqdm import tqdm # Progress bar
from src.parsers import FilenameParser
from src.measurements import LifetimeMeasurement, g2Measurement
from src.fitting import fit_lifetime, fit_g2
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

def run_pipeline():
    # 1. Setup - Prompt for folder
    root = tk.Tk()
    root.withdraw() # Hide the small default tkinter window
    
    print("Waiting for folder selection...")
    folder_selected = filedialog.askdirectory(title="Select Folder Containing Raw CSV Data")
    
    if not folder_selected:
        print("❌ No folder selected. Exiting pipeline.")
        return

    # Create search path based on user selection
    search_path = os.path.join(folder_selected, "*.csv")
    files = glob.glob(search_path)
    
    if not files:
        print(f"❌ No CSV files found in {folder_selected}. Exiting pipeline.")
        return
        
    results_lifetime = []
    results_g2 = []
    
    print(f"🚀 Starting Batch Process on {len(files)} files from {folder_selected}...")
    
    # 2. The Main Loop
    for f in tqdm(files):
        meta = FilenameParser.parse(f)
        if not meta: continue
        
        # --- LIFETIME PROCESSING ---
        if meta.type == 'Lifetime':
            meas = LifetimeMeasurement(meta)
            meas.load()
            
            # Extract Arrays (using logic from our Measurement class)
            # We reconstruct the axis here for fitting
            y = meas.data.iloc[0].values
            tac = meta.tac_range if not pd.isna(meta.tac_range) else 50.0
            gain = meta.gain if not pd.isna(meta.gain) else 1.0
            x = np.linspace(0, tac/gain, len(y))
            
            # Fit
            fit_res = fit_lifetime(x, y)
            
            # Save Record
            record = {
                'Filename': f,
                'X': meta.x, 'Y': meta.y, 'Power': meta.power,
                'Tau1': fit_res.get('tau1'),
                'Tau2': fit_res.get('tau2'),
                'Success': fit_res.get('success')
            }
            results_lifetime.append(record)

        # --- g2 PROCESSING ---
        elif meta.type == 'g2':
            meas = g2Measurement(meta)
            meas.load()
            y = meas.data.iloc[0].values
            
            # Simple axis for g2
            x = np.arange(len(y)) 
            
            res = fit_g2(x, y)
            
            record = {
                'Filename': f,
                'X': meta.x, 'Y': meta.y,
                'g2_0': res['g2_0'],
                'SinglePhoton': res['is_single_photon']
            }
            results_g2.append(record)

    # 3. Save Summary
    # Ensure the output directory exists so to_csv doesn't throw a FileNotFoundError
    os.makedirs("data_processed", exist_ok=True)
    
    if results_lifetime:
        df_life = pd.DataFrame(results_lifetime)
        df_life.to_csv("data_processed/summary_lifetime.csv", index=False)
        print(f"✅ Saved {len(df_life)} Lifetime results.")
        
    if results_g2:
        df_g2 = pd.DataFrame(results_g2)
        df_g2.to_csv("data_processed/summary_g2.csv", index=False)
        print(f"✅ Saved {len(df_g2)} g2 results.")

if __name__ == "__main__":
    run_pipeline()