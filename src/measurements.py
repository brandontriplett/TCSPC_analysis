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
    def plot(self, ax=None):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        x = self.data.iloc[:, 0]
        y = self.data.iloc[:, 1]

        ax.plot(x, y, color='purple')
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