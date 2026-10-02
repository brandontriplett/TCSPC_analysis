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
