#!/usr/bin/env python3
"""Interactive map: click an emitter to view its measurements.

Does not write files. Plot/report tools are unchanged.

    python scripts/explore.py
    python scripts/explore.py /path/to/csvs
    python scripts/explore.py /path/to/csvs --port 8051
"""

from __future__ import annotations

import argparse
import _repo
from pathlib import Path

import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from tcspc.dialogs import pick_folder
from tcspc.grouping import (
    POINT_TYPES,
    parse_folder,
    print_unmatched,
    round_coord,
    unique_emitters,
)
from tcspc.maps import stitch_pl_maps
from tcspc.measurements import PLMapMeasurement, histogram_axis
from tcspc.plotting import (
    TYPE_TITLES,
    format_plot_labels,
    measurement_from_meta,
    trace_label,
)

SNAP_UM = 3.0
PLOT_TYPES = ("Spectrum", "Lifetime", "g2", "Stability", "Saturation")


def load_session(folder: Path):
    metas, unmatched = parse_folder(folder)
    print(f"Scanning {folder}... parsed {len(metas)}, skipped {len(unmatched)}")
    print_unmatched(unmatched)

    pl_maps = []
    for meta in metas:
        if meta.type != "PL":
            continue
        meas = PLMapMeasurement(meta)
        try:
            meas.load()
        except Exception as exc:
            print(f"Failed to load PL scan {meta.filepath}: {exc}")
            continue
        pl_maps.append(meas)
    master_x, master_y, master_z = stitch_pl_maps(pl_maps)

    emitters = []
    for ex, ey in unique_emitters(metas):
        here = [
            m
            for m in metas
            if m.type in POINT_TYPES and round_coord(m.x) == ex and round_coord(m.y) == ey
        ]
        types = sorted({m.type for m in here})
        emitters.append({
            "x": ex,
            "y": ey,
            "n": len(here),
            "types": types,
            "types_label": ", ".join(types) if types else "—",
        })
    return metas, unmatched, (master_x, master_y, master_z), emitters


def empty_figure(title, xlabel, ylabel, extra=None):
    layout = dict(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        template="plotly_white",
        margin=dict(t=50, b=30, l=50, r=30),
        legend=dict(font=dict(size=10)),
    )
    if extra:
        layout.update(extra)
    return go.Figure().update_layout(**layout)


def build_map_figure(master, emitters, selected=None):
    master_x, master_y, master_z = master
    fig = go.Figure()
    if master_z is not None:
        fig.add_trace(go.Heatmap(
            x=master_x,
            y=master_y,
            z=master_z,
            colorscale="inferno",
            colorbar=dict(title="PL", thickness=14, len=0.7),
            hoverinfo="skip",
            name="PL",
        ))
    if emitters:
        xs = [e["x"] for e in emitters]
        ys = [e["y"] for e in emitters]
        ns = [e["n"] for e in emitters]
        labels = [e["types_label"] for e in emitters]
        is_sel = [
            selected is not None and e["x"] == selected[0] and e["y"] == selected[1]
            for e in emitters
        ]
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            marker=dict(
                size=[16 if s else 12 for s in is_sel],
                color=["#c1121f" if s else "rgba(0,0,0,0)" for s in is_sel],
                line=dict(color="#c1121f", width=2),
            ),
            customdata=list(zip(xs, ys, ns, labels)),
            hovertemplate=(
                "<b>(%{customdata[0]}, %{customdata[1]})</b><br>"
                "%{customdata[2]} file(s): %{customdata[3]}<extra></extra>"
            ),
            name="Emitters",
        ))
    fig.update_layout(
        xaxis_title="X (µm)",
        yaxis_title="Y (µm)",
        clickmode="event+select",
        height=720,
        template="plotly_white",
        yaxis=dict(scaleanchor="x", scaleratio=1),
        margin=dict(t=20, b=40, l=50, r=20),
        showlegend=False,
    )
    return fig


def resolve_click(click_data, emitters):
    if not click_data or not emitters:
        return None
    try:
        point = click_data["points"][0]
    except (KeyError, IndexError):
        return None
    if "customdata" in point:
        return float(point["customdata"][0]), float(point["customdata"][1])
    click_x = float(point["x"])
    click_y = float(point["y"])
    best = None
    best_d = SNAP_UM
    for e in emitters:
        d = ((e["x"] - click_x) ** 2 + (e["y"] - click_y) ** 2) ** 0.5
        if d < best_d:
            best_d = d
            best = (e["x"], e["y"])
    return best


def metas_for(metas, loc, meas_type):
    ex, ey = loc
    return [
        m
        for m in metas
        if m.type == meas_type and round_coord(m.x) == ex and round_coord(m.y) == ey
    ]


def add_spectrum_traces(fig, metas, loc):
    title, varying = format_plot_labels(metas, TYPE_TITLES["Spectrum"], loc[0], loc[1], html=True)
    fig.update_layout(title=title)
    for meta in metas:
        meas = measurement_from_meta(meta)
        meas.load()
        if meas.data is None:
            continue
        fig.add_trace(go.Scatter(
            x=meas.data.iloc[:, 0],
            y=meas.data.iloc[:, 1],
            name=trace_label(meta, varying) or "Spectrum",
            mode="lines",
        ))


def add_lifetime_traces(fig, metas, loc):
    title, varying = format_plot_labels(metas, TYPE_TITLES["Lifetime"], loc[0], loc[1], html=True)
    fig.update_layout(title=title)
    for meta in metas:
        meas = measurement_from_meta(meta)
        meas.load()
        if meas.data is None:
            continue
        y = meas.data.iloc[:, 0].values
        x = histogram_axis(meta, len(y), centered=False)
        fig.add_trace(go.Scatter(
            x=x, y=y, name=trace_label(meta, varying) or "Lifetime", mode="lines",
        ))


def add_g2_traces(fig, metas, loc):
    title, varying = format_plot_labels(metas, TYPE_TITLES["g2"], loc[0], loc[1], html=True)
    fig.update_layout(title=title)
    for meta in metas:
        meas = measurement_from_meta(meta)
        meas.load()
        if meas.data is None:
            continue
        y = meas.data.iloc[:, 0].values
        x = histogram_axis(meta, len(y), centered=True)
        fig.add_trace(go.Scatter(
            x=x, y=y, name=trace_label(meta, varying) or "g(2)", mode="lines",
        ))


def add_stability_traces(fig, metas, loc):
    title, varying = format_plot_labels(metas, TYPE_TITLES["Stability"], loc[0], loc[1], html=True)
    fig.update_layout(
        title=title,
        yaxis=dict(title="Counts"),
        yaxis2=dict(title="Laser Power (μW)", overlaying="y", side="right", showgrid=False),
    )
    for meta in metas:
        meas = measurement_from_meta(meta)
        time, counts, power = meas.series()
        base = trace_label(meta, varying) or "Stability"
        fig.add_trace(go.Scatter(x=time, y=counts, name=f"{base} counts", yaxis="y1", mode="lines"))
        fig.add_trace(go.Scatter(
            x=time, y=power, name=f"{base} power", yaxis="y2",
            mode="lines", line=dict(dash="dot"),
        ))


def add_saturation_traces(fig, metas, loc):
    title, varying = format_plot_labels(metas, TYPE_TITLES["Saturation"], loc[0], loc[1], html=True)
    fig.update_layout(title=title)
    for meta in metas:
        meas = measurement_from_meta(meta)
        voltage, counts = meas.series()
        fig.add_trace(go.Scatter(
            x=voltage, y=counts, name=trace_label(meta, varying) or "Saturation",
            mode="markers", marker=dict(size=8),
        ))


TRACE_BUILDERS = {
    "Spectrum": add_spectrum_traces,
    "Lifetime": add_lifetime_traces,
    "g2": add_g2_traces,
    "Stability": add_stability_traces,
    "Saturation": add_saturation_traces,
}

AXIS = {
    "Spectrum": ("Wavelength (nm)", "Intensity (a.u.)", None),
    "Lifetime": ("Time (ns)", "Counts", dict(yaxis_type="log")),
    "g2": ("Delay (ns)", "Coincidences", None),
    "Stability": ("Time (s)", "Counts", None),
    "Saturation": ("Power", "Counts", None),
}


def make_app(folder: Path, metas, master, emitters):
    n_pl = sum(1 for m in metas if m.type == "PL")
    n_pt = sum(1 for m in metas if m.type in POINT_TYPES)
    app = Dash(__name__)
    app.title = "TCSPC explorer"

    app.layout = html.Div(
        style={"fontFamily": "system-ui, sans-serif", "padding": "12px 20px", "maxWidth": "1400px", "margin": "0 auto"},
        children=[
            html.H2("TCSPC explorer", style={"margin": "0 0 4px 0"}),
            html.Div(
                f"{folder}  ·  {n_pt} point file(s), {n_pl} PL map(s), {len(emitters)} emitter(s)",
                style={"color": "#555", "marginBottom": "8px"},
            ),
            html.Div(
                id="status",
                children="Click a red marker on the map (or near one on the PL image).",
                style={"marginBottom": "10px", "fontWeight": "600"},
            ),
            html.Div(
                style={"display": "flex", "gap": "16px", "alignItems": "flex-start"},
                children=[
                    html.Div(
                        style={"flex": "0 0 42%"},
                        children=[dcc.Graph(id="spatial-map", figure=build_map_figure(master, emitters))],
                    ),
                    html.Div(
                        style={"flex": "1", "minWidth": 0},
                        children=[
                            dcc.Checklist(
                                id="plot-selector",
                                options=[{"label": f"  {TYPE_TITLES[t]}", "value": t} for t in PLOT_TYPES],
                                value=["Spectrum", "g2"],
                                inline=True,
                                style={"marginBottom": "8px"},
                            ),
                            dcc.Graph(id="spectrum-plot"),
                            dcc.Graph(id="lifetime-plot"),
                            dcc.Graph(id="g2-plot"),
                            dcc.Graph(id="stability-plot"),
                            dcc.Graph(id="saturation-plot"),
                        ],
                    ),
                ],
            ),
        ],
    )

    graph_ids = {
        "Spectrum": "spectrum-plot",
        "Lifetime": "lifetime-plot",
        "g2": "g2-plot",
        "Stability": "stability-plot",
        "Saturation": "saturation-plot",
    }

    @app.callback(
        [Output("spatial-map", "figure"), Output("status", "children")]
        + [Output(gid, "figure") for gid in graph_ids.values()]
        + [Output(gid, "style") for gid in graph_ids.values()],
        [Input("spatial-map", "clickData"), Input("plot-selector", "value")],
    )
    def update(click_data, selected_plots):
        selected_plots = selected_plots or []
        loc = resolve_click(click_data, emitters)
        map_fig = build_map_figure(master, emitters, selected=loc)

        n_vis = max(len(selected_plots), 1)
        height = f"{max(220, min(360, 720 // n_vis))}px"
        styles = {
            t: {"height": height, "display": "block" if t in selected_plots else "none"}
            for t in PLOT_TYPES
        }

        figs = {}
        for t in PLOT_TYPES:
            xlabel, ylabel, extra = AXIS[t]
            figs[t] = empty_figure(TYPE_TITLES[t], xlabel, ylabel, extra)

        if loc is None:
            status = "Click a red marker on the map (or near one on the PL image)."
            return (map_fig, status, *[figs[t] for t in PLOT_TYPES], *[styles[t] for t in PLOT_TYPES])

        counts = {t: len(metas_for(metas, loc, t)) for t in PLOT_TYPES}
        present = [f"{TYPE_TITLES[t]}×{counts[t]}" for t in PLOT_TYPES if counts[t]]
        status = f"Emitter ({loc[0]}, {loc[1]})"
        if present:
            status += "  ·  " + ", ".join(present)
        else:
            status += "  ·  no point measurements here"

        for t in PLOT_TYPES:
            if t not in selected_plots:
                continue
            here = metas_for(metas, loc, t)
            if not here:
                figs[t].update_layout(title=f"{TYPE_TITLES[t]} — none at ({loc[0]}, {loc[1]})")
                continue
            try:
                TRACE_BUILDERS[t](figs[t], here, loc)
            except Exception as exc:
                figs[t].update_layout(title=f"{TYPE_TITLES[t]} — failed to load")
                print(f"explore plot error ({t} @ {loc}): {exc}")

        return (map_fig, status, *[figs[t] for t in PLOT_TYPES], *[styles[t] for t in PLOT_TYPES])

    return app


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Interactive TCSPC map explorer (click an emitter to plot its files)."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Folder of CSV files. If omitted, a folder dialog opens.",
    )
    parser.add_argument("--port", type=int, default=8051)
    parser.add_argument("--debug", action="store_true", help="Dash debug reloader")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    folder = args.folder
    if not folder:
        try:
            folder = pick_folder()
        except Exception as exc:
            print(f"❌ Folder dialog failed ({exc}). Pass a folder on the command line instead.")
            return 1
    if not folder:
        print("❌ No folder selected. Exiting.")
        return 1

    folder = Path(folder)
    metas, unmatched, master, emitters = load_session(folder)
    if not metas:
        print(f"❌ No valid TCSPC files found in {folder}")
        return 1
    if not emitters and master[2] is None:
        print("❌ Nothing to show (no PL maps and no point measurements).")
        return 1

    app = make_app(folder, metas, master, emitters)
    print(f"Open http://127.0.0.1:{args.port}")
    app.run(debug=args.debug, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
