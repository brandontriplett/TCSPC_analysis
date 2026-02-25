import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import glob
import os

# Import your custom modules
from src.parsers import FilenameParser
from src.measurements import LifetimeMeasurement, g2Measurement, SpectrumMeasurement, PLMapMeasurement

# ==========================================
# 1. SETUP: Scan Directory and Build Map Database
# ==========================================
DATA_DIR = "data_raw"
search_pattern = os.path.join(DATA_DIR, "*.csv")
files = glob.glob(search_pattern)

records = []
print(f"Scanning {len(files)} files to build the database...")

for f in files:
    meta = FilenameParser.parse(f)
    if meta:
        records.append({
            'Filename': f,
            'X': meta.x,
            'Y': meta.y,
            'Type': meta.type,
            'Metadata': meta
        })

df_summary = pd.DataFrame(records) if records else pd.DataFrame(columns=['Filename', 'X', 'Y', 'Type', 'Metadata'])

# ==========================================
# 2. STITCHING ENGINE: Build Master PL Scan
# ==========================================
pl_files = df_summary[df_summary['Type'] == 'PL']
point_files = df_summary[df_summary['Type'].isin(['Spectrum', 'Lifetime', 'g2'])]

master_x, master_y, master_z = None, None, None

if not pl_files.empty:
    print("Stitching Master PL Scan...")
    pl_measurements = []
    
    # Load all PL data
    for _, row in pl_files.iterrows():
        try:
            meas = PLMapMeasurement(row['Metadata'])
            meas.load()
            if meas.data is not None and not pd.isna(meas.meta.scan_size):
                pl_measurements.append(meas)
        except Exception as e:
            print(f"Failed to load PL scan {row['Filename']}: {e}")

    if pl_measurements:
        # Determine global pixel size based on the first tile
        ref = pl_measurements[0]
        ny, nx = ref.data.shape
        pixel_width = ref.meta.scan_size / nx
        pixel_height = ref.meta.scan_size / ny
        
        # Find the global spatial bounds
        min_x = min(m.meta.x - m.meta.scan_size/2 for m in pl_measurements)
        max_x = max(m.meta.x + m.meta.scan_size/2 for m in pl_measurements)
        min_y = min(m.meta.y - m.meta.scan_size/2 for m in pl_measurements)
        max_y = max(m.meta.y + m.meta.scan_size/2 for m in pl_measurements)
        
        # Calculate global grid pixel dimensions
        global_nx = int(np.ceil((max_x - min_x) / pixel_width))
        global_ny = int(np.ceil((max_y - min_y) / pixel_height))
        
        # Initialize an empty array with NaNs (Handles missing squares automatically!)
        master_z = np.full((global_ny, global_nx), np.nan)
        
        for m in pl_measurements:
            data = m.data.values
            # Find starting index for this tile in the global array
            start_x_idx = int(np.round((m.meta.x - m.meta.scan_size/2 - min_x) / pixel_width))
            start_y_idx = int(np.round((m.meta.y - m.meta.scan_size/2 - min_y) / pixel_height))
            
            # Prevent boundary overflow
            end_y = min(start_y_idx + data.shape[0], global_ny)
            end_x = min(start_x_idx + data.shape[1], global_nx)
            slice_y = end_y - start_y_idx
            slice_x = end_x - start_x_idx
            
            # Place the tile into the master grid
            master_z[start_y_idx:end_y, start_x_idx:end_x] = data[0:slice_y, 0:slice_x]
            
        master_x = np.linspace(min_x, max_x, global_nx)
        master_y = np.linspace(min_y, max_y, global_ny)

# Group point measurements for the scatter overlay
if not point_files.empty:
    df_map = point_files.groupby(['X', 'Y']).size().reset_index(name='Measurements')
else:
    df_map = pd.DataFrame(columns=['X', 'Y', 'Measurements'])

# ==========================================
# 3. INITIALIZE APP & LAYOUT
# ==========================================
app = dash.Dash(__name__)

# Build the Map Figure
fig_map = go.Figure()

# 1. Add the Stitched PL Heatmap (if it exists)
if master_z is not None:
    fig_map.add_trace(go.Heatmap(
        x=master_x, y=master_y, z=master_z,
        colorscale='inferno',
        colorbar=dict(title="PL Intensity", x=-0.15), # Move colorbar to the left side
        hoverinfo='skip' # Disable hover on the image itself to avoid clutter
    ))

# 2. Overlay the Clickable Scatter Points
if not df_map.empty:
    fig_map.add_trace(go.Scatter(
        x=df_map['X'], y=df_map['Y'],
        mode='markers',
        marker=dict(size=12, color='rgba(0,0,0,0)', line=dict(color='red', width=2)), 
        customdata=np.stack((df_map['X'], df_map['Y'], df_map['Measurements']), axis=-1),
        hovertemplate="<b>Location: (%{customdata[0]}, %{customdata[1]})</b><br>Available Files: %{customdata[2]}<extra></extra>"
    ))

fig_map.update_layout(
    xaxis_title="X position (µm)", yaxis_title="Y position (µm)",
    clickmode='event+select', height=750, template="plotly_white", # Slightly taller to match right panel
    yaxis=dict(scaleanchor="x", scaleratio=1),
    margin=dict(t=30, b=30, l=30, r=30)
)

app.layout = html.Div([
    html.H1("Interactive Data Explorer", style={'textAlign': 'center', 'fontFamily': 'Arial'}),
    
    html.Div([
        # LEFT PANEL: Spatial Map (Headers removed)
        html.Div([
            dcc.Graph(id='spatial-map', figure=fig_map)
        ], style={'width': '40%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '10px'}),

        # RIGHT PANEL: Dynamic Plots & Controls
        html.Div([
            # Added a checklist to toggle which plots are visible
            dcc.Checklist(
                id='plot-selector',
                options=[
                    {'label': ' Spectrum \u00A0\u00A0', 'value': 'Spectrum'},
                    {'label': ' Lifetime \u00A0\u00A0', 'value': 'Lifetime'},
                    {'label': ' g(2) Correlation', 'value': 'g2'}
                ],
                value=['Spectrum', 'g2'], # Defaults to showing just Spectrum and g2
                inline=True,
                style={'textAlign': 'center', 'marginBottom': '10px', 'fontFamily': 'Arial', 'fontWeight': 'bold'}
            ),
            dcc.Graph(id='spectrum-plot'),
            dcc.Graph(id='lifetime-plot'),
            dcc.Graph(id='g2-plot')
        ], style={'width': '58%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '10px'})
        
    ], style={'display': 'flex', 'justifyContent': 'space-between'})
])

# ==========================================
# 4. CALLBACKS & DYNAMIC LEGENDS
# ==========================================
def format_plot_labels(metas, base_title, loc_x, loc_y):
    """Helper function to dynamically move static parameters to the title and varying to the legend."""
    attrs_map = {
        'power': 'Pow', 'integration_time': 'Int(s)', 
        'nd': 'ND', 'filter': 'Filter'
    }
    
    unique_vals = {attr: set() for attr in attrs_map}
    for m in metas:
        for attr in attrs_map:
            val = getattr(m, attr, float('nan'))
            if (isinstance(val, float) and pd.isna(val)) or str(val).lower() == "none":
                continue
            unique_vals[attr].add(val)
            
    static_params, varying_params = {}, []
    
    for attr, label in attrs_map.items():
        if len(unique_vals[attr]) == 1:
            static_params[label] = list(unique_vals[attr])[0]
        elif len(unique_vals[attr]) > 1:
            varying_params.append(attr)
            
    # Subtitle for static params
    title = f"{base_title} @ ({loc_x}, {loc_y})"
    if static_params:
        param_str = " | ".join([f"{k}: {v}" for k, v in static_params.items()])
        title += f"<br><sup>{param_str}</sup>"
        
    return title, varying_params, attrs_map

@app.callback(
    [Output('spectrum-plot', 'figure'), Output('spectrum-plot', 'style'),
     Output('lifetime-plot', 'figure'), Output('lifetime-plot', 'style'),
     Output('g2-plot', 'figure'), Output('g2-plot', 'style')],
    [Input('spatial-map', 'clickData'), Input('plot-selector', 'value')]
)
def update_plots(clickData, selected_plots):
    
    # Calculate dynamic heights to fill the vertical space optimally
    num_visible = len(selected_plots) if selected_plots else 1
    dynamic_height = f"{700 // num_visible}px"
    
    # Set display styles based on checklist
    style_spec = {'height': dynamic_height, 'display': 'block' if 'Spectrum' in selected_plots else 'none'}
    style_life = {'height': dynamic_height, 'display': 'block' if 'Lifetime' in selected_plots else 'none'}
    style_g2 = {'height': dynamic_height, 'display': 'block' if 'g2' in selected_plots else 'none'}

    # Base Figures
    fig_spec = go.Figure().update_layout(title="Spectrum", xaxis_title="Wavelength (nm)", yaxis_title="Intensity (a.u.)", template="plotly_white", margin=dict(t=50, b=30))
    fig_life = go.Figure().update_layout(title="Lifetime Decay", xaxis_title="Time (ns)", yaxis_title="Counts", yaxis_type="log", template="plotly_white", margin=dict(t=50, b=30))
    fig_g2 = go.Figure().update_layout(title="g(2) Correlation", xaxis_title="Delay (ns)", yaxis_title="Coincidences", template="plotly_white", margin=dict(t=50, b=30))

    if clickData is None or df_summary.empty: 
        return fig_spec, style_spec, fig_life, style_life, fig_g2, style_g2

    print("\n" + "="*40)
    print("🔘 CLICK EVENT DETECTED")

    try:
        point = clickData['points'][0]
        
        # Scenario A: You perfectly clicked the scatter point
        if 'customdata' in point:
            loc_x = float(point['customdata'][0])
            loc_y = float(point['customdata'][1])
            print(f"📍 Direct hit on scatter point: X={loc_x}, Y={loc_y}")
            
        # Scenario B: You missed the scatter point and clicked the heatmap layer
        else:
            click_x = float(point['x'])
            click_y = float(point['y'])
            print(f"⚠️ Clicked heatmap layer at ({click_x:.2f}, {click_y:.2f}). Initiating magnetic snap...")
            
            distances = np.sqrt((df_summary['X'].astype(float) - click_x)**2 + (df_summary['Y'].astype(float) - click_y)**2)
            min_dist_idx = distances.idxmin()
            
            if distances[min_dist_idx] < 3.0:
                loc_x = float(df_summary.loc[min_dist_idx, 'X'])
                loc_y = float(df_summary.loc[min_dist_idx, 'Y'])
                print(f"🧲 Snapped to nearest measurement at X={loc_x}, Y={loc_y} (Distance: {distances[min_dist_idx]:.2f}µm)")
            else:
                print("❌ Too far from any measurement. Aborting.")
                return fig_spec, style_spec, fig_life, style_life, fig_g2, style_g2

    except Exception as e:
        print(f"🚨 Unexpected click error: {e}")
        return fig_spec, style_spec, fig_life, style_life, fig_g2, style_g2

    mask = np.isclose(df_summary['X'].astype(float), loc_x) & np.isclose(df_summary['Y'].astype(float), loc_y)
    local_files = df_summary[mask]
    
    print(f"📂 Found {len(local_files)} files matching this location.")

    if local_files.empty:
        return fig_spec, style_spec, fig_life, style_life, fig_g2, style_g2

    # Process Spectra (Only process if selected to save computation)
    if 'Spectrum' in selected_plots:
        spec_metas = local_files[local_files['Type'] == 'Spectrum']['Metadata'].tolist()
        if spec_metas:
            title, var_attrs, attr_map = format_plot_labels(spec_metas, "Spectrum", loc_x, loc_y)
            fig_spec.update_layout(title=title)
            
            for meta in spec_metas:
                print(f"  -> Processing Spectrum: {meta.filepath}")
                try:
                    meas = SpectrumMeasurement(meta)
                    meas.load()
                    if meas.data is not None:
                        trace_name = ", ".join([f"{attr_map[a]}: {getattr(meta, a)}" for a in var_attrs])
                        fig_spec.add_trace(go.Scatter(x=meas.data.iloc[:, 0], y=meas.data.iloc[:, 1], name=trace_name or "Spectrum"))
                except Exception as e:
                    print(f"     🚨 ERROR: {e}")

    # Process Lifetime
    if 'Lifetime' in selected_plots:
        life_metas = local_files[local_files['Type'] == 'Lifetime']['Metadata'].tolist()
        if life_metas:
            title, var_attrs, attr_map = format_plot_labels(life_metas, "Lifetime Decay", loc_x, loc_y)
            fig_life.update_layout(title=title)
            
            for meta in life_metas:
                print(f"  -> Processing Lifetime: {meta.filepath}")
                try:
                    meas = LifetimeMeasurement(meta)
                    meas.load()
                    if meas.data is not None:
                        y = meas.data.iloc[:, 0].values
                        tac = meta.tac_range if not pd.isna(meta.tac_range) else 50.0
                        gain = meta.gain if not pd.isna(meta.gain) else 1.0
                        trace_name = ", ".join([f"{attr_map[a]}: {getattr(meta, a)}" for a in var_attrs])
                        fig_life.add_trace(go.Scatter(x=np.linspace(0, tac/gain, len(y)), y=y, name=trace_name or "Lifetime"))
                except Exception as e:
                    print(f"     🚨 ERROR: {e}")

    # Process g2
    if 'g2' in selected_plots:
        g2_metas = local_files[local_files['Type'] == 'g2']['Metadata'].tolist()
        if g2_metas:
            title, var_attrs, attr_map = format_plot_labels(g2_metas, "g(2) Correlation", loc_x, loc_y)
            fig_g2.update_layout(title=title)
            
            for meta in g2_metas:
                print(f"  -> Processing g2: {meta.filepath}")
                try:
                    meas = g2Measurement(meta)
                    meas.load()
                    if meas.data is not None:
                        y = meas.data.iloc[:, 0].values
                        tac = meta.tac_range if not pd.isna(meta.tac_range) else 50.0
                        gain = meta.gain if not pd.isna(meta.gain) else 1.0
                        trace_name = ", ".join([f"{attr_map[a]}: {getattr(meta, a)}" for a in var_attrs])
                        fig_g2.add_trace(go.Scatter(x=np.linspace(-tac/gain/2, tac/gain/2, len(y)), y=y, name=trace_name or "g2"))
                except Exception as e:
                    print(f"     🚨 ERROR: {e}")

    return fig_spec, style_spec, fig_life, style_life, fig_g2, style_g2

if __name__ == '__main__':
    app.run(debug=True, port=8050)