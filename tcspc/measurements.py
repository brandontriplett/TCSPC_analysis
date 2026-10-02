import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from .parsers import MeasurementMetadata


def histogram_axis(meta, n, centered=False):
    """Time (ns) axis for lifetime/g2 histograms from TAC range and gain."""
    tac = meta.tac_range if not pd.isna(meta.tac_range) else 50.0
    gain = meta.gain if not pd.isna(meta.gain) else 1.0
    window = tac / gain
    if centered:
        return np.linspace(-window / 2, window / 2, n)
    return np.linspace(0, window, n)


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

    def plot(self, ax=None, label=None, configure_axes=True):
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
    def plot(self, ax=None, label=None, configure_axes=True):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        y = self.data.iloc[:, 0].values
        x = histogram_axis(self.meta, len(y), centered=False)
        window = x[-1] - x[0] if len(x) > 1 else 0.0

        trace_label = label or f"Pos: {self.meta.x:.1f}, {self.meta.y:.1f}"
        ax.semilogy(x, y, label=trace_label, alpha=0.85)
        if configure_axes:
            ax.set_xlabel("Time (ns)")
            ax.set_ylabel("Counts (Log)")
            ax.set_title(f"Lifetime (Range: {window:.1f} ns)")
        return ax

class g2Measurement(Measurement):
    def plot(self, ax=None, label=None, configure_axes=True):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        y = self.data.iloc[:, 0].values
        x = histogram_axis(self.meta, len(y), centered=True)
        window = (x[-1] - x[0]) if len(x) > 1 else 0.0

        trace_label = label or "g(2)"
        ax.plot(x, y, label=trace_label, alpha=0.85)
        if configure_axes:
            ax.set_xlabel("Delay (ns)")
            ax.set_ylabel("Coincidences")
            ax.set_title(f"g2 (Range: {window:.1f} ns)")
        return ax

class SpectrumMeasurement(Measurement):
    def crop(self, x_min, x_max):
        """Filters the dataframe to only include wavelengths between x_min and x_max."""
        if self.data is not None:
            # Column 0 is Wavelength
            mask = (self.data.iloc[:, 0] >= x_min) & (self.data.iloc[:, 0] <= x_max)
            self.data = self.data[mask]

    def plot(self, ax=None, label=None, configure_axes=True):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        x = self.data.iloc[:, 0]
        y = self.data.iloc[:, 1]

        trace_label = label or f"Pow: {self.meta.power} uW"
        ax.plot(x, y, label=trace_label, linewidth=1.5, alpha=0.85)
        if configure_axes:
            ax.set_xlabel("Wavelength (nm)")
            ax.set_ylabel("Intensity (a.u.)")
            ax.set_title(f"Spectrum (Power: {self.meta.power} uW)")
        return ax

class PLMapMeasurement(Measurement):
    def plot(self, ax=None, label=None, configure_axes=True):
        if self.data is None: self.load()
        if ax is None: _, ax = plt.subplots()

        extent = None
        if self.meta.scan_size is not None and not pd.isna(self.meta.scan_size):
            extent = self.get_extent()

        im = ax.imshow(self.data, cmap='inferno', origin='lower', extent=extent)
        if configure_axes:
            plt.colorbar(im, ax=ax, label="Intensity")
            ax.set_title(f"PL Map (Size: {self.meta.scan_size}um)")
            if extent is not None:
                ax.set_xlabel("X (μm)")
                ax.set_ylabel("Y (μm)")
            else:
                ax.set_xlabel("X (pixels)")
                ax.set_ylabel("Y (pixels)")
        return ax

class StabilityMeasurement(Measurement):
    def series(self):
        """Return ``(time, counts, power)`` after the same cleaning as ``plot``."""
        if self.data is None:
            self.load()
        power = pd.to_numeric(self.data.iloc[:, 0], errors='coerce')
        counts = pd.to_numeric(self.data.iloc[:, 1], errors='coerce')
        if self.data.shape[1] > 2:
            ch2 = pd.to_numeric(self.data.iloc[:, 2], errors='coerce')
            counts = counts.fillna(0) + ch2.fillna(0)
        original_len = len(counts)
        if pd.isna(self.meta.integration_time):
            dt = 0.1  # Fallback: Assume 100ms (0.1s) per bin
        else:
            dt = self.meta.integration_time / original_len
        if original_len > 10:
            counts = counts.iloc[5:].reset_index(drop=True)
            power = power.iloc[5:].reset_index(drop=True)
        time = np.arange(len(counts)) * dt
        return time, counts, power

    def plot(self, ax=None, label=None, configure_axes=True, show_power=True):
        if ax is None: _, ax = plt.subplots()
        time, counts, power = self.series()

        trace_label = label or "Counts"
        l1 = ax.plot(time, counts, label=trace_label, alpha=0.85)

        if configure_axes:
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Counts")
            ax.set_title(f"Stability (Avg Power: {self.meta.power} μW)")

        if show_power and configure_axes:
            ax2 = ax.twinx()
            l2 = ax2.plot(time, power, color='red', linestyle='--', alpha=0.8, label='Laser Power')
            ax2.set_ylabel("Laser Power (μW)", color='red')
            ax2.tick_params(axis='y', labelcolor='red')
            lines = l1 + l2
            ax.legend(lines, [line.get_label() for line in lines], loc='best')
        elif configure_axes:
            ax.legend(loc='best')

        if configure_axes:
            ax.grid(True, alpha=0.3)
        return ax

class SaturationMeasurement(Measurement):
    def series(self):
        """Return ``(voltage_or_power, counts)``."""
        if self.data is None:
            self.load()
        power = self.data.iloc[:, 0]
        counts = self.data.iloc[:, 2] if self.data.shape[1] > 2 else self.data.iloc[:, 1]
        return power, counts

    def plot(self, ax=None, label=None, configure_axes=True):
        if ax is None: _, ax = plt.subplots()
        power, counts = self.series()

        trace_label = label or "Saturation"
        ax.plot(power, counts, 'o', markersize=6, label=trace_label, alpha=0.85)
        if configure_axes:
            ax.set_xlabel("Power")
            ax.set_ylabel("Counts")
            ax.set_title("Saturation")
            ax.grid(True)
            ax.legend(loc='best')
        return ax