import numpy as np
from scipy.optimize import curve_fit

def biexponential(t, a1, t1, a2, t2, c):
    """
    Model: I(t) = A1 * exp(-t/t1) + A2 * exp(-t/t2) + C
    """
    return a1 * np.exp(-t / t1) + a2 * np.exp(-t / t2) + c

def fit_lifetime(time_axis, counts, model='biexp'):
    """
    Fits a decay curve.
    1. Finds the peak (max count).
    2. Cuts off the 'rising edge' (data before the peak).
    3. Fits the tail.
    """
    # 1. Find the Peak (Start of decay)
    peak_idx = np.argmax(counts)
    
    # 2. Slice the data (Tail only)
    # We start slightly after the peak to avoid IRF convolution issues
    start_idx = peak_idx + 2 
    t_slice = time_axis[start_idx:]
    y_slice = counts[start_idx:]
    
    # Shift time so the start is t=0 for the math
    t_offset = t_slice - t_slice[0]

    # 3. Initial Guesses (Crucial for curve_fit)
    # Amplitude ~ Max Counts
    # Offset ~ Average of last 10 points (background)
    # Tau1 ~ Fast (e.g., 10% of window)
    # Tau2 ~ Slow (e.g., 50% of window)
    
    offset_guess = np.mean(y_slice[-10:])
    amp_guess = (np.max(y_slice) - offset_guess) / 2
    tau_guess = (t_slice[-1] - t_slice[0]) / 5
    
    p0 = [amp_guess, tau_guess/2, amp_guess, tau_guess*2, offset_guess]
    
    try:
        # 4. Run the Fit
        popt, pcov = curve_fit(biexponential, t_offset, y_slice, p0=p0, maxfev=5000)
        
        # Unpack results
        return {
            'a1': popt[0], 'tau1': popt[1],
            'a2': popt[2], 'tau2': popt[3],
            'background': popt[4],
            'success': True
        }
    except RuntimeError:
        return {'success': False}
    except ValueError:
        return {'success': False}

def fit_g2(delay_axis, coincidences):
    """
    Simple analysis of g2 dip.
    Returns g2(0) value and the width of the dip.
    """
    # For now, let's just find the minimum value near zero delay
    # We assume the dip is at the center of the window
    
    center_idx = len(delay_axis) // 2
    window = 10 # Look +/- 10 bins around center
    
    center_slice = coincidences[center_idx - window : center_idx + window]
    
    # Simple Min/Max ratio (g2(0))
    # We estimate 'Normalization' (g2=1 level) from the edges
    baseline = np.mean(np.concatenate((coincidences[:20], coincidences[-20:])))
    min_val = np.min(center_slice)
    
    g2_at_zero = min_val / baseline
    
    return {
        'g2_0': g2_at_zero,
        'baseline': baseline,
        'is_single_photon': g2_at_zero < 0.5
    }