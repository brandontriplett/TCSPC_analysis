import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from .parsers import MeasurementMetadata

class Measurement:
    """Base class for all experiments."""
    def __init__(self, metadata: MeasurementMetadata):
        self.meta = metadata
        self.data = None

    def load(self):
        try:
            # Read as Tab-Separated, No Header
            df = pd.read_csv(self.meta.filepath, sep='\t', header=None)
            
            # CHECK: Is it a single row (Histogram)?
            if df.shape[0] == 1 and df.shape[1] > 10:
                self.data = df.T 
                self.data.columns = ['Counts']
            else:
                self.data = df
                
        except Exception as e:
            print(f"Error loading {self.meta.filepath}: {e}")

    def plot(self, ax=None):
        raise NotImplementedError("Subclasses must implement plot")
    
    def get_extent(self):
        """Returns the bounding box of the scan in stage coordinates."""
        half_size = self.meta.scan_size / 2
        return [
            self.meta.x - half_size, # Left
            self.meta.x + half_size, # Right
            self.meta.y - half_size, # Bottom
            self.meta.y + half_size  # Top
        ]

# ==========================================
# SPECIFIC MEASUREMENT TYPES
# ==========================================

class LifetimeMeasurement(Measurement):
    def plot(self, ax=None):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        y = self.data.iloc[:, 0].values 
        
        tac = self.meta.tac_range if not pd.isna(self.meta.tac_range) else 50.0
        gain = self.meta.gain if not pd.isna(self.meta.gain) else 1.0
        true_time_window = tac / gain
        
        x = np.linspace(0, true_time_window, len(y))

        ax.semilogy(x, y, label=f"Pos: {self.meta.x:.1f}, {self.meta.y:.1f}")
        ax.set_xlabel("Time (ns)")
        ax.set_ylabel("Counts (Log)")
        ax.set_title(f"Lifetime (Range: {true_time_window:.1f} ns)")
        return ax

class g2Measurement(Measurement):
    def plot(self, ax=None):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        y = self.data.iloc[:, 0].values
        
        tac = self.meta.tac_range if not pd.isna(self.meta.tac_range) else 50.0
        gain = self.meta.gain if not pd.isna(self.meta.gain) else 1.0
        true_time_window = tac / gain
        
        # Centered Delay Axis
        x = np.linspace(-true_time_window/2, true_time_window/2, len(y))
        
        ax.plot(x, y, color='green', alpha=0.8)
        ax.set_xlabel("Delay (ns)")
        ax.set_ylabel("Coincidences")
        ax.set_title(f"g2 (Range: {true_time_window:.1f} ns)")
        return ax

class SpectrumMeasurement(Measurement):
    def crop(self, x_min, x_max):
        """Filters the dataframe to only include wavelengths between x_min and x_max."""
        if self.data is not None:
            # Column 0 is Wavelength
            mask = (self.data.iloc[:, 0] >= x_min) & (self.data.iloc[:, 0] <= x_max)
            self.data = self.data[mask]

    def plot(self, ax=None):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        x = self.data.iloc[:, 0]
        y = self.data.iloc[:, 1]

        ax.plot(x, y, color='purple', linewidth=1.5)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity (a.u.)")
        ax.set_title(f"Spectrum (Power: {self.meta.power} uW)")
        return ax

class PLMapMeasurement(Measurement):
    def plot(self, ax=None):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        im = ax.imshow(self.data, cmap='inferno', origin='lower')
        plt.colorbar(im, ax=ax, label="Intensity")
        
        ax.set_title(f"PL Map (Size: {self.meta.scan_size}um)")
        ax.set_xlabel("X (pixels)")
        ax.set_ylabel("Y (pixels)")
        return ax

class StabilityMeasurement(Measurement):
    def plot(self, ax=None):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        # Extract data safely (forcing to float to ignore any string headers)
        # 1st column (index 0): Laser Power
        # 2nd column (index 1): Counts
        power = pd.to_numeric(self.data.iloc[:, 0], errors='coerce')
        counts = pd.to_numeric(self.data.iloc[:, 1], errors='coerce')
        
        # Legacy check: if there is a 3rd column, sum it with the 2nd column
        if self.data.shape[1] > 2:
            ch2 = pd.to_numeric(self.data.iloc[:, 2], errors='coerce')
            counts = counts.fillna(0) + ch2.fillna(0)
            
        # 1. Determine time step (dt)
        original_len = len(counts)
        if pd.isna(self.meta.integration_time):
            dt = 0.1  # Fallback: Assume 100ms (0.1s) per bin
        else:
            dt = self.meta.integration_time / original_len
            
        # 2. Throw away the first 5 data points (artifacts)
        if original_len > 10:
            counts = counts.iloc[5:].reset_index(drop=True)
            power = power.iloc[5:].reset_index(drop=True)
            
        # 3. Build the new time array
        time = np.arange(len(counts)) * dt
        
        # 4. Plotting
        # Plot Counts on the primary (Left) Y-axis
        l1 = ax.plot(time, counts, color='blue', label='Counts')
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Counts", color='blue')
        ax.tick_params(axis='y', labelcolor='blue')
        
        # Plot Laser Power on a secondary (Right) Y-axis
        ax2 = ax.twinx()
        l2 = ax2.plot(time, power, color='red', linestyle='--', alpha=0.8, label='Laser Power')
        ax2.set_ylabel("Laser Power (μW)", color='red')
        ax2.tick_params(axis='y', labelcolor='red')

        # Combine legends so they don't overlap
        lines = l1 + l2
        labels = [l.get_label() for l in lines]
        ax.legend(lines, labels, loc='best')

        ax.set_title(f"Stability (Avg Power: {self.meta.power} μW)")
        ax.grid(True, alpha=0.3)
        return ax

class SaturationMeasurement(Measurement):
    def plot(self, ax=None):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        # Column 0 is Voltage/Power
        power = self.data.iloc[:, 0]
        
        # Fallback logic: Use column index 2 if it's a 3-column file, otherwise index 1
        counts = self.data.iloc[:, 2] if self.data.shape[1] > 2 else self.data.iloc[:, 1]

        ax.plot(power, counts, 'bo', markersize=6)
        ax.set_xlabel("Power")
        ax.set_ylabel("Counts")
        ax.set_title("Saturation")
        ax.grid(True)
        return ax