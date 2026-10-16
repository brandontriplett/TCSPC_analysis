# TCSPC analysis

Parse, plot, and report Time-Correlated Single Photon Counting lab CSVs.

## Install

```bash
pip install -r requirements.txt
```

Run from anywhere; the scripts add this repo to `sys.path`.

## Commands

All tools live in `scripts/`. No path → a file/folder dialog opens.

**Plot files** (one PNG per CSV, no coordinate grouping):

```bash
python scripts/plot.py
python scripts/plot.py a.csv b.csv
python scripts/plot.py path/to/folder
python scripts/plot.py --out DIR a.csv
```

PNGs go to `data_processed/plots/<timestamp>/`. Mixed types are fine.

**Emitter report** (group by `(X, Y)`, one PDF page per spot):

```bash
python scripts/report.py
python scripts/report.py /path/to/csvs
python scripts/report.py /path/to/csvs --out report.pdf
```

PDF goes to `data_processed/<folder_name>.pdf`.

**Batch fitting** (lifetime + g(2) → summary CSVs):

```bash
python scripts/fit.py /path/to/csvs
python scripts/fit.py /path/to/csvs --out DIR
```

**Map explorer** (click an emitter on a stitched PL map):

```bash
python scripts/explore.py
python scripts/explore.py /path/to/csvs
python scripts/explore.py /path/to/csvs --port 8051
```

Opens http://127.0.0.1:8051. Does not write files.

## Filename convention

Type is the first `_`-separated token:

| Type | Pattern |
|---|---|
| PL | `PL_X{x}_Y{y}_ND{nd}_Pow{power}_Filter{filter}_Size{size}_Mesh{mesh}` |
| Lifetime | `Lifetime_X{x}_Y{y}_ND{nd}_Pow{power}_Filter{filter}_Int{int}_TAC{tac}_Gain{gain}_Bin{bin}` |
| g2 | `g2_X{x}_Y{y}_ND{nd}_Pow{power}_Filter{filter}_Int{int}_TAC{tac}_Gain{gain}_Bin{bin}` |
| Spectrum | `Spectrum_X{x}_Y{y}_ND{nd}_Pow{power}_Int{int}` |
| Stability | `Stability_X{x}_Y{y}_ND{nd}_Pow{power}_Filter{filter}` optional `_Int{int}` |
| Saturation | `Saturation_X{x}_Y{y}_Filter{filter}` |

Unmatched names are listed and skipped. CSVs are tab-separated, no header.
Histograms (lifetime/g2) are a single wide row.

## Layout

```text
scripts/plot.py      # plot selected files → PNGs
scripts/report.py    # folder → per-emitter PDF
scripts/fit.py       # folder → lifetime/g2 summary CSVs
scripts/explore.py   # click-to-plot map
tcspc/               # library (parsers, measurements, plotting, …)
tests/
```

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

## Single-file fitting and publication studio

```bash
python scripts/studio.py
python scripts/studio.py /path/to/measurement.csv
```

Requires Python with Tk support (usually included with python.org installers).
This is a separate desktop editor; existing batch plotting/fitting commands are unchanged.
Select **Open measurement**, edit controls, and press **Apply changes** (or Return). All six
measurement types use the existing filename parser and loaders, including the
existing TAC/gain time-axis convention and stability channel cleaning.

- **Plot / Style:** editable labels, title, legend, fonts, colors, lines/markers,
  linear/log axes, X/Y crop, figure dimensions, and annotation position/size.
  Maps include colormap, intensity limits, and colorbar labels; stability traces
  can include a secondary laser-power axis. Saturation power remains in instrument
  units: relabel only after confirming your acquisition calibration.
- **CW g²:** select CW mode and normalization. The default baseline is the mean
  of the full trace's outer 10% on each side; override it if the edges are not a
  suitable baseline. Set the center explicitly in axis units. Fit two-level,
  ideal three-level, or three-level with free `g0`. The supplied ideal model
  necessarily has g²(0)=0; the free version uses
  `1 - (1+C-g0)*exp(-abs(t)/tau1) + C*exp(-abs(t)/tau2)`.
  Fit each model to compare RMSE/AIC in the result panel; the latest successful
  fit is displayed. Comparison scores are meaningful only for the same data/range.
- **Pulsed g²:** select Pulsed mode, choose **Central peak** as the drag action,
  and drag across it. Then choose **Add side peak** and drag over each side peak.
  Side windows snap to the central window's bin count. Press **Calculate g²(0)** above the preview. The calculation sums counts per peak, optionally subtracting a constant
  background per bin, then divides the central sum by the mean side sum. Windows
  must be disjoint and contain equal bin counts; no division by window width or
  peak height is substituted. Changing the central selection clears side windows.
  Selected windows appear in a list; remove individual side peaks or clear all.
  Use consistent windows that
  capture the same fraction of each peak, and inspect background sensitivity.
- **Lifetime:** single exponential plus background by default, with a double
  exponential alternative. The origin and range start default to the maximum;
  move the fit start later to exclude the instrument response/rising edge.
  Amplitudes refer to the selected origin. No IRF reconvolution is performed.
- **Saturation:** `Iinf*P/(P+Psat)` or a version with constant background and a
  linear term. Lifetime/saturation model variants and editable parameter guesses
  and bounds allow constrained alternatives without executing arbitrary formulas.
- **Fit controls:** type a range or drag with **Fit range** selected. The plot
  crop and fit range are independent. Disable toolbar pan/zoom before dragging.
  **Advanced** shows a table of initial guesses and minimum/maximum bounds;
  blank bounds mean unbounded. Reset guesses after changing ranges. Fits are unweighted bounded least
  squares; reported errors are local covariance estimates. Inspect residuals,
  bounds, and parameter identifiability, especially for multiple exponentials.
  Analysis-input changes invalidate old results immediately.
  Disable **Show fitted curve** to export data alone; g² annotation is separately
  optional. Spectrum, stability, and map exports need no fitting.

**Export figure** offers SVG/PDF vectors and PNG (600 dpi default). Defaults are
3.5 × 2.8 inches, 9 pt DejaVu Sans, editable SVG text, and embedded TrueType PDF
fonts. These are reasonable single-column starting values, not a guarantee of
compliance with every journal. Export uses the configured physical dimensions;
preview resizing does not change those settings. **Use current zoom** in Plot
copies toolbar zoom into the export crop; **Reset crop** restores automatic limits. Peak-selection shading is omitted.

**Export data + analysis** writes full-trace raw/displayed values, fitted values
and residuals within the fit range, plus a JSON analysis/settings record (maps
export as matrices). **Save session / Load session** restores controls, parameter
settings, and the original file path; rerun fitting/calculation after loading.
Source data must remain accessible. Files are written only on explicit export/save.

### macOS blank window / deprecated system Tk

Apple's command-line-tools Python can use obsolete system Tk 8.5, which may
produce a blank window. `TK_SILENCE_DEPRECATION=1` only hides the warning.
The studio now refuses to launch on macOS with Tk older than 8.6.
Check the **exact interpreter** you use to launch the application:

```bash
.venv/bin/python -c "import sys, tkinter; print(sys.executable, tkinter.TkVersion)"
```

Create a separate environment with a Python that includes Tk 8.6 or newer.
For this machine, the existing Conda Python at `/opt/miniconda3/bin/python`
provides Tk 8.6:

```bash
/opt/miniconda3/bin/python -m venv .venv-studio
.venv-studio/bin/python -m pip install -r requirements.txt
.venv-studio/bin/python scripts/studio.py
```

The original `.venv` stays available for existing workflows. Alternatively,
use a current python.org macOS installer and create the new environment using
that interpreter. Installing Tk with another package manager does not change
which Tk an existing Python interpreter links to.

### Studio navigation

The sidebar separates **Plot** (labels, crop, overlays), **Analysis** (only the
loaded data type's controls), **Style** (fonts, colors, markers), and **Export**
(physical dimensions, resolution, data, and sessions). Fit/Calculate and drag mode
stay above the preview, outside the scrolling controls. Advanced parameter guesses
are collapsed initially. Scroll the sidebar with the mouse wheel or trackpad.

Pulsed mode guides central → side selection, rejects overlapping windows, and lets
you remove individual windows. Drag selection is off by default for CW/lifetime;
select a drag action explicitly. Choosing a selection action exits toolbar pan/zoom.
Model/input changes clear stale analysis; fits run in the background so controls
remain responsive, and results are discarded if analysis inputs change meanwhile.
Plot toggles update automatically; text/style edits apply with **Apply changes**
or Return. Fit-range edits and peak selections preserve a zoomed preview.

### Time offsets, math labels, and final export layout

- **Plot → Time calibration → Time offset** adds a constant to the time axis
  (ns for g²/lifetime; seconds for stability). For a g² dip at +3 ns, enter `-3`
  and apply. Counts and source files are unchanged. Existing peak windows and
  X ranges move with the data, preserving the selected bins. CW's fit center
  stays at its specified coordinate (normally zero); lifetime's origin moves
  with the trace. Changing the offset clears previous analysis; recalculate/refit.
  Sessions preserve the offset. CSV exports include shifted `x` and original `raw_x`.
- Titles, axis labels, legends, and annotations support Matplotlib math notation
  inside dollar signs: `$g^{(2)}(\tau)$`, `$I_0$`, or `$10^{-3}$`. No external TeX
  installation is needed. G² titles use superscript notation by default.
- **Export** switches the main preview to the actual publication layout, scaled
  proportionally to fit your window. It uses the same fixed-size figure and
  frozen layout as SVG/PDF/PNG export, omitting selection guides. Window resizing
  only scales this preview image; it cannot rearrange the figure. Use the final
  typography controls to adjust font/annotation sizes, outer padding, axis-label
  padding, title padding, and panel spacing. Changes on this tab refresh after
  a short pause; **Apply changes** also refreshes immediately. The other tabs
  keep the larger interactive working preview for fitting and peak selection.

### Intensity normalization and annotation color

For Spectrum and PL files, **Plot → Intensity normalization → Normalize intensity
to peak = 1** normalizes the displayed intensity. Spectra use
`(I - min(I)) / (max(I) - min(I))`, estimating a constant background from the
full-spectrum minimum. Their linear Y-axis shows only **0** and **1** ticks.
Constant spectra become zero. PL maps still divide by the full-map maximum
without background subtraction; the colorbar changes and spatial axes stay
unchanged. Zero-only maps remain zero; other maps require a positive peak. Switching units resets
manual intensity limits, and default intensity labels update automatically.
Custom labels and source data are preserved. Map CSV exports contain displayed
intensities, with the divisor and background recorded in the analysis JSON; spectrum CSV exports
retain both raw and displayed intensities.

**Style → Typography → Annotation color** accepts a color name (`white`, `red`)
or hex value (`#cc2244`). It applies to g²(0) and additional on-plot annotation
text, independently of curve colors. The same control is available under
**Export → Final typography and spacing**. Both new settings persist in sessions
and apply to the working preview, final preview, and exported figures.

### Pulsed g² and lifetime display normalization

**Plot → Intensity normalization** is also available for lifetime files and for
g² files in **Pulsed** mode. It divides by the maximum of the full trace (peak = 1),
without background subtraction. Pulsed plots are labeled **Normalized coincidences**:
this is a display scale, not a direct g²(0) measurement. Peak integration continues
to use raw counts and the raw-count background-per-bin setting, so toggling display
normalization preserves the calculated area ratio.

Lifetime normalization retains the background and the logarithmic display option.
Fits use the displayed units: amplitudes/background are rescaled, while lifetime
time constants remain in ns. Changing normalization clears a lifetime fit and
resets its initial guesses; fit again to update the overlay. CW g² keeps its
separate baseline normalization. Normalization settings persist in sessions and
apply to previews and figure/data exports; CSV retains raw and displayed counts.
