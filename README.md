# TCSPC Data Explorer & Report Generator

A Python toolkit for parsing, visualizing, and analyzing Time-Correlated Single Photon Counting (TCSPC) and spatial scan data. 

This project takes a folder of raw CSV measurements (Photoluminescence maps, Spectra, g(2), Lifetime, Stability, and Saturation), stitches the spatial data together, and correlates all measurements by their physical (X, Y) coordinates.

## Two Main Features

1. **Interactive Dashboard (`app.py`)** A local Plotly Dash web app. It generates a stitched PL map consisting of all taken PL maps. Click on any spatial coordinate to view the Spectrum, Lifetime, g(2), Stability, and Saturation data taken at that spot.
   
2. **Automated PDF Reports (`generate_report.py`)**
   A script that scans your data folder, finds every unique emitter location, and generates a clean, multi-page PDF (`Emitter_Report.pdf`). Each page features a 2x3 grid summarizing all data found for a specific coordinate.

## Project Structure
```text
tcspc_analysis/
├── data_raw/               # Put your raw .csv files here for the autoscan
├── data_processed/         # PDF reports will be saved here
├── app.py                  # Run the interactive dashboard
├── generate_report.py      # Run the PDF report generator
└── src/
    ├── parsers.py          # Regex logic for extracting metadata from filenames
    ├── measurements.py     # Classes for loading/plotting each data type
    └── fitting.py          # Math/fitting logic (biexponential decay, g2 dips)