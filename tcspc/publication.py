"""Numerical and rendering support for the single-file publication editor.

Independent of Tk so analysis and exported figures can be tested headlessly.
"""
from __future__ import annotations

from dataclasses import dataclass
import warnings
import numpy as np
from scipy.optimize import curve_fit, OptimizeWarning
from matplotlib.figure import Figure
from matplotlib import rc_context
from .parsers import FilenameParser
from .plotting import measurement_from_meta, TYPE_TITLES
from .measurements import histogram_axis

MODELS = {
    'CW two-level': (lambda x, A, tau1: 1-A*np.exp(-np.abs(x)/tau1), ['A', 'tau1']),
    'CW three-level (ideal)': (lambda x, C, tau1, tau2: 1-(1+C)*np.exp(-np.abs(x)/tau1)+C*np.exp(-np.abs(x)/tau2), ['C', 'tau1', 'tau2']),
    'CW three-level (free g0)': (lambda x, g0, C, tau1, tau2: 1-(1+C-g0)*np.exp(-np.abs(x)/tau1)+C*np.exp(-np.abs(x)/tau2), ['g0', 'C', 'tau1', 'tau2']),
    'Lifetime single': (lambda x, I0, tau, B: I0*np.exp(-x/tau)+B, ['I0', 'tau', 'B']),
    'Lifetime double': (lambda x, I1, tau1, I2, tau2, B: I1*np.exp(-x/tau1)+I2*np.exp(-x/tau2)+B, ['I1', 'tau1', 'I2', 'tau2', 'B']),
    'Saturation': (lambda x, Iinf, Psat: Iinf*x/(x+Psat), ['Iinf', 'Psat']),
    'Saturation + background': (lambda x, Iinf, Psat, B, slope: Iinf*x/(x+Psat)+B+slope*x, ['Iinf', 'Psat', 'B', 'slope']),
}

@dataclass
class Dataset:
    path: str
    kind: str
    x: np.ndarray
    y: np.ndarray
    xlabel: str
    ylabel: str
    title: str
    power: np.ndarray | None = None
    extent: list | None = None


def load_dataset(path):
    meta = FilenameParser.parse(path)
    if meta is None:
        raise ValueError('Filename does not match a supported measurement convention.')
    m = measurement_from_meta(meta)
    m.load()
    if m.data is None:
        raise ValueError('Could not load measurement.')
    power = extent = None
    kind = meta.type
    if kind == 'PL':
        y = np.asarray(m.data, dtype=float)
        if np.isfinite(meta.scan_size):
            extent = m.get_extent()
        return Dataset(str(path), kind, np.array([]), y, 'X (μm)' if extent else 'X (pixels)', 'Y (μm)' if extent else 'Y (pixels)', TYPE_TITLES[kind], extent=extent)
    if kind in ('Lifetime', 'g2'):
        y = np.asarray(m.data.iloc[:, 0], dtype=float)
        x = histogram_axis(meta, len(y), centered=kind == 'g2')
        xlabel, ylabel = ('Time (ns)', 'Counts') if kind == 'Lifetime' else ('Delay (ns)', 'Coincidences')
    elif kind == 'Stability':
        x, y, power = m.series()
        xlabel, ylabel = 'Time (s)', 'Counts'
    elif kind == 'Saturation':
        x, y = m.series()
        xlabel, ylabel = 'Power (instrument units)', 'Counts'
    else:
        x, y = m.data.iloc[:, 0], m.data.iloc[:, 1]
        xlabel, ylabel = 'Wavelength (nm)', 'Intensity (a.u.)'
    x, y = np.asarray(x, float), np.asarray(y, float)
    valid = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(valid) < 2:
        raise ValueError('At least two finite samples are required.')
    order = np.argsort(x[valid], kind='stable')
    if power is not None:
        power = np.asarray(power, float)[valid][order]
    return Dataset(str(path), kind, x[valid][order], y[valid][order], xlabel, ylabel, TYPE_TITLES[kind], power)


def normalize_cw(y, baseline=None):
    n = max(1, len(y)//10)
    baseline = float(np.mean(np.r_[y[:n], y[-n:]])) if baseline is None else float(baseline)
    if not np.isfinite(baseline) or baseline <= 0:
        raise ValueError('CW normalization baseline must be positive.')
    return y/baseline, baseline


def normalize_intensity(values):
    """Divide by the full dataset's finite peak; do not subtract background."""
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if not finite.size:
        raise ValueError('Intensity normalization needs finite samples.')
    peak = float(np.max(finite))
    if np.all(finite == 0):
        return values.copy(), 0.
    if peak <= 0:
        raise ValueError('Intensity normalization requires a positive peak.')
    return values / peak, peak


def normalize_spectrum(values):
    """Use the full-spectrum minimum as a constant background estimate."""
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if not finite.size:
        raise ValueError('Spectrum normalization needs finite samples.')
    background = float(np.min(finite))
    scale = float(np.max(finite)-background)
    corrected = values-background
    return (corrected/scale if scale > 0 else corrected), background, scale


def parameter_defaults(model, x, y):
    span = max(float(np.ptp(x)), 1e-6)
    amplitude = max(float(np.ptp(y)), 1e-6)
    guesses = dict(A=.8, g0=.2, C=.2, tau1=span/20, tau2=span/3,
                   I0=amplitude, I1=amplitude*.7, I2=amplitude*.3,
                   tau=span/5, B=max(0., float(np.min(y))), Iinf=max(float(np.max(y)), 1.),
                   Psat=max(float(np.max(x))/3, 1e-6), slope=0.)
    return {name: [guesses[name], 1e-12 if name.startswith('tau') or name == 'Psat' else 0.,
                   1. if name in ('A', 'g0') else None] for name in MODELS[model][1]}


def fit_curve(x, y, model, limits=None, origin=0., parameters=None):
    """Unweighted bounded least squares; errors are local covariance estimates."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    mask = np.isfinite(x) & np.isfinite(y)
    if limits is not None:
        if limits[0] >= limits[1]:
            raise ValueError('Fit minimum must be below maximum.')
        mask &= (x >= limits[0]) & (x <= limits[1])
    xx, yy = x[mask]-origin, y[mask]
    fn, names = MODELS[model]
    if len(xx) <= len(names):
        raise ValueError('Fit range needs more samples than fitted parameters.')
    if model.startswith(('Lifetime', 'Saturation')) and np.any(xx < 0):
        raise ValueError('Lifetime/saturation fit coordinates must be nonnegative; check origin and range.')
    config = parameters or parameter_defaults(model, xx, yy)
    if set(config) != set(names):
        raise ValueError('Parameter names must match the selected model.')
    p0, lower, upper = [], [], []
    for name in names:
        guess, lo, hi = config[name]
        lo, hi = (-np.inf if lo is None else lo), (np.inf if hi is None else hi)
        if name.startswith('tau') or name == 'Psat':
            lo = max(lo, 1e-12)
        if not lo < hi or not lo <= guess <= hi:
            raise ValueError(f'Invalid guess/bounds for {name}.')
        p0.append(guess); lower.append(lo); upper.append(hi)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always', OptimizeWarning)
        p, cov = curve_fit(fn, xx, yy, p0=p0, bounds=(lower, upper), maxfev=30000, x_scale='jac')
    predicted = fn(xx, *p)
    if not np.all(np.isfinite(predicted)):
        raise ValueError('Fit produced nonfinite predictions.')
    residuals = yy-predicted
    rss = float(residuals@residuals)
    n, k = len(xx), len(p)
    result = dict(model=model, parameters=dict(zip(names, p.tolist())),
                  errors=dict(zip(names, np.sqrt(np.maximum(0, np.diag(cov))).tolist())),
                  origin=float(origin), limits=[float(x[mask].min()), float(x[mask].max())],
                  rmse=float(np.sqrt(rss/n)), aic=float(n*np.log(max(rss/n, np.finfo(float).tiny))+2*k),
                  warnings=[str(w.message) for w in caught])
    if model.startswith('CW'):
        result['g2_zero'] = float(fn(np.array([0.]), *p)[0])
    return result


def peak_ratio(x, y, central, sides, background=0.):
    """Sum histogram-bin counts in equal-width, disjoint peak windows."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2 or not np.allclose(np.diff(x), np.diff(x)[0]) or np.diff(x)[0] <= 0:
        raise ValueError('Peak integration requires a uniformly spaced histogram.')
    if not sides:
        raise ValueError('Select at least one side peak.')
    if not np.isfinite(background):
        raise ValueError('Background must be finite.')
    windows = [central, *sides]
    masks = []
    for lo, hi in windows:
        if not np.isfinite([lo, hi]).all() or lo >= hi:
            raise ValueError('Each peak window must have increasing finite bounds.')
        mask = (x >= lo) & (x <= hi)
        if not mask.any():
            raise ValueError('A peak window contains no bins.')
        masks.append(mask)
    if any(np.any(a & b) for i, a in enumerate(masks) for b in masks[i+1:]):
        raise ValueError('Peak windows must not overlap.')
    if len({int(m.sum()) for m in masks}) != 1:
        raise ValueError('Use the same number of bins for every peak window (equal integration widths).')
    areas = [float(np.sum(y[m]-background)) for m in masks]
    if areas[0] < 0 or min(areas[1:]) <= 0:
        raise ValueError('Background-subtracted central area must be nonnegative and side areas positive.')
    return dict(g2_zero=areas[0]/float(np.mean(areas[1:])), central_area=areas[0],
                side_areas=areas[1:], central=list(central), sides=[list(s) for s in sides],
                bins=int(masks[0].sum()), background=float(background))


@dataclass
class Style:
    xlabel: str = ''
    ylabel: str = ''
    title: str = ''
    label: str = 'Data'
    fit_label: str = 'Fit'
    font: str = 'DejaVu Sans'
    fontsize: float = 9.
    width: float = 3.5
    height: float = 2.8
    layout_pad: float = 3.
    labelpad: float = 4.
    titlepad: float = 6.
    subplot_gap: float = .08
    linewidth: float = 1.
    markersize: float = 2.5
    color: str = '#0072B2'
    fit_color: str = '#D55E00'
    marker: str = 'none'
    line: str = '-'
    xscale: str = 'linear'
    yscale: str = 'linear'
    normalized_spectrum: bool = False
    xlim: tuple | None = None
    ylim: tuple | None = None
    legend: str = 'best'
    grid: bool = False
    show_fit: bool = True
    residuals: bool = False
    annotation: str = ''
    annotation_x: float = .97
    annotation_y: float = .95
    annotation_size: float = 9.
    annotation_color: str = '#000000'
    cmap: str = 'inferno'
    vmin: float | None = None
    vmax: float | None = None
    colorbar: str = 'Intensity (a.u.)'
    power: bool = False
    power_label: str = 'Laser power (μW)'


def render(dataset, style, y=None, fit=None, windows=(), figure=None):
    s = style
    if min(s.width, s.height, s.fontsize, s.annotation_size) <= 0:
        raise ValueError('Figure dimensions and font sizes must be positive.')
    if min(s.layout_pad, s.labelpad, s.titlepad, s.subplot_gap) < 0:
        raise ValueError('Spacing values must be nonnegative.')
    for bounds, scale in ((s.xlim, s.xscale), (s.ylim, s.yscale)):
        if bounds and (bounds[0] >= bounds[1] or (scale == 'log' and bounds[0] <= 0)):
            raise ValueError('Axis limits must increase; logarithmic limits must be positive.')
    with rc_context({'font.family': s.font, 'font.size': s.fontsize, 'axes.spines.top': False,
                     'axes.spines.right': False, 'axes.labelpad': s.labelpad, 'axes.titlepad': s.titlepad, 'svg.fonttype': 'none', 'pdf.fonttype': 42}):
        # A live Tk canvas owns its pixel geometry. Resizing it to publication
        # inches on every redraw fights the window manager and causes jumps.
        fig = figure if figure is not None else Figure(figsize=(s.width, s.height))
        fig.clear()
        fig.set_layout_engine('constrained', w_pad=s.layout_pad/72, h_pad=s.layout_pad/72,
                              hspace=s.subplot_gap, wspace=s.subplot_gap)
        residual = fit is not None and s.show_fit and s.residuals
        if residual:
            ax, rax = fig.subplots(2, 1, sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        else:
            ax = fig.subplots()
        if dataset.kind == 'PL':
            im = ax.imshow(dataset.y if y is None else y, origin='lower', extent=dataset.extent, cmap=s.cmap, vmin=s.vmin, vmax=s.vmax)
            fig.colorbar(im, ax=ax, label=s.colorbar)
        else:
            values = dataset.y if y is None else y
            ax.plot(dataset.x, values, label=s.label, color=s.color, linewidth=s.linewidth,
                    marker=s.marker, markersize=s.markersize, linestyle=s.line)
            if fit is not None and s.show_fit:
                lo, hi = fit['limits']
                fx = np.linspace(lo, hi, 1000)
                fn, names = MODELS[fit['model']]
                p = [fit['parameters'][name] for name in names]
                ax.plot(fx, fn(fx-fit['origin'], *p), color=s.fit_color, linewidth=s.linewidth, label=s.fit_label)
                if residual:
                    mask = (dataset.x >= lo) & (dataset.x <= hi)
                    rax.plot(dataset.x[mask], values[mask]-fn(dataset.x[mask]-fit['origin'], *p), color=s.color, lw=.7)
                    rax.axhline(0, color='gray', lw=.5)
                    rax.set_ylabel('Residual')
                    rax.set_xlabel(s.xlabel)
            if s.power and dataset.power is not None:
                twin = ax.twinx()
                twin.plot(dataset.x, dataset.power, color='#009E73', lw=s.linewidth, linestyle='--')
                twin.set_ylabel(s.power_label)
            if s.legend != 'none':
                ax.legend(loc=s.legend, frameon=False)
        for lo, hi in windows:
            ax.axvspan(lo, hi, alpha=.15, color=s.fit_color)
        ax.set(xlabel='' if residual else s.xlabel, ylabel=s.ylabel, title=s.title, xscale=s.xscale, yscale=s.yscale)
        if dataset.kind == 'Spectrum' and s.normalized_spectrum:
            from matplotlib.ticker import NullLocator
            ax.set_yticks([0., 1.], labels=['0', '1'])
            ax.yaxis.set_minor_locator(NullLocator())
        if s.xlim: ax.set_xlim(s.xlim)
        if s.ylim: ax.set_ylim(s.ylim)
        if s.grid:
            ax.grid(True, alpha=.2)
        else:
            ax.grid(False)
        if s.annotation:
            ax.text(s.annotation_x, s.annotation_y, s.annotation, transform=ax.transAxes,
                    ha='right', va='top', fontsize=s.annotation_size, color=s.annotation_color)
        return fig, ax


def publication_figure(dataset, style, y=None, fit=None):
    """Lay out once at export dimensions, then freeze positions across backends.

    The export preview uses this same figure, with no selection guides. Scaling
    its raster preview never changes the underlying figure dimensions or fonts.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig, ax = render(dataset, style, y=y, fit=fit)
    fig.set_dpi(150)
    FigureCanvasAgg(fig)
    fig.canvas.draw()
    fig.set_layout_engine('none')
    return fig, ax


def save_figure(fig, path, dpi=600, transparent=False):
    from pathlib import Path
    if Path(path).suffix.lower() not in ('.png', '.pdf', '.svg'):
        raise ValueError('Choose a .png, .pdf, or .svg filename.')
    if not 72 <= dpi <= 2400:
        raise ValueError('DPI must be between 72 and 2400.')
    with rc_context({'svg.fonttype': 'none', 'pdf.fonttype': 42}):
        fig.savefig(path, dpi=dpi, transparent=transparent)
