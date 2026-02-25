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
    peak_idx = np.argmax(counts)
    start_idx = peak_idx + 2 
    t_slice = time_axis[start_idx:]
    y_slice = counts[start_idx:]
    
    t_offset = t_slice - t_slice[0]

    offset_guess = np.mean(y_slice[-10:])
    amp_guess = (np.max(y_slice) - offset_guess) / 2
    tau_guess = (t_slice[-1] - t_slice[0]) / 5
    
    p0 = [amp_guess, tau_guess/2, amp_guess, tau_guess*2, offset_guess]
    
    try:
        popt, pcov = curve_fit(biexponential, t_offset, y_slice, p0=p0, maxfev=5000)
        return {
            'a1': popt[0], 'tau1': popt[1],
            'a2': popt[2], 'tau2': popt[3],
            'background': popt[4],
            'success': True
        }
    except (RuntimeError, ValueError):
        return {'success': False}

# ==========================================
# g2 FITTING LOGIC (Translated from MATLAB)
# ==========================================

def g2_model(t, amp, tau):
    """
    Model: g2(t) = 1 - amp * exp(-|t|/tau)
    Note: g2(0) = 1 - amp
    """
    return 1 - amp * np.exp(-np.abs(t) / tau)

def fit_g2(delay_axis, coincidences, dip_bins=5):
    """
    Dual-mode analysis of g2 dip (Experimental Average + Curve Fit).
    Generalizes MATLAB logic to work for arbitrary time windows and bin widths.
    """
    if len(delay_axis) < 20:
        return {'fit_success': False, 'g2_0': float('nan'), 'is_single_photon': False}
        
    # 1. Normalization
    # Average the outer 10% edges on both sides to find the baseline (g2=1 level)
    edge_len = max(1, int(len(coincidences) * 0.1))
    bg_edges = np.concatenate((coincidences[:edge_len], coincidences[-edge_len:]))
    baseline = np.mean(bg_edges)
    
    if baseline == 0:
        baseline = 1.0
        
    y_norm = coincidences / baseline
    
    # 2. Find Dip Center 
    # Search in the middle 20% of the data to find the dip (avoids edge artifacts)
    search_width = max(1, len(y_norm) // 10)
    mid_idx = len(y_norm) // 2
    search_start = mid_idx - search_width
    search_end = mid_idx + search_width
    
    local_min_idx = np.argmin(y_norm[search_start:search_end])
    real_center_idx = search_start + local_min_idx
    
    # 3. Experimental g2 (Exp g2) - Average over +/- 5 bins
    # Uses max/min to safely prevent index out-of-bounds errors
    range_start = max(0, real_center_idx - dip_bins)
    range_end = min(len(y_norm), real_center_idx + dip_bins + 1)
    
    g2_exp = np.mean(y_norm[range_start:range_end])
    is_spe_exp = g2_exp < 0.5
    
    # 4. Fit g2
    # Shift time axis so t=0 is exactly at the found dip minimum
    t_axis = delay_axis - delay_axis[real_center_idx]
    
    # Initial guesses and bounds
    # amp: guess 0.8, bounds [0, 1.1]
    # tau: guess 15ns, bounds [0.001, 1000] (expanded from MATLAB to safely allow 300ns/50ns variations)
    p0 = [0.8, 15.0]
    bounds = ([0.0, 0.001], [1.1, 1000.0])
    
    fit_res = {
        'baseline': baseline,
        'center_idx': real_center_idx,
        'g2_exp': g2_exp,
        'is_spe_exp': is_spe_exp,
        't_axis_shifted': t_axis,
        'y_norm': y_norm
    }
    
    try:
        popt, pcov = curve_fit(g2_model, t_axis, y_norm, p0=p0, bounds=bounds)
        amp, tau = popt
        
        g2_fit_0 = 1.0 - amp
        g2_fit_0_err = np.sqrt(pcov[0, 0])
        
        fit_res.update({
            'fit_success': True,
            'g2_fit_0': g2_fit_0,
            'g2_fit_0_err': g2_fit_0_err,
            'tau': tau,
            'is_spe_fit': g2_fit_0 < 0.5,
            
            # Map default keys for Dashboard App compatibility
            'g2_0': g2_fit_0, 
            'is_single_photon': g2_fit_0 < 0.5
        })
        
    except Exception:
        # Fallback to experimental value if the exponential curve fit fails
        fit_res.update({
            'fit_success': False,
            'g2_fit_0': float('nan'),
            'g2_fit_0_err': float('nan'),
            'tau': float('nan'),
            'is_spe_fit': False,
            
            # Map default keys for Dashboard App compatibility
            'g2_0': g2_exp, 
            'is_single_photon': is_spe_exp
        })
        
    return fit_res