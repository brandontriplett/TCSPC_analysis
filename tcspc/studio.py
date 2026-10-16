"""Tk publication studio. Run with ``python scripts/studio.py [measurement.csv]``."""
from dataclasses import asdict
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.widgets import SpanSelector
from .publication import (MODELS, Style, load_dataset, normalize_cw, normalize_intensity, normalize_spectrum, parameter_defaults,
                          fit_curve, peak_ratio, render, save_figure, publication_figure)


class ParameterEditor(ttk.Frame):
    """Labeled numeric fields; serialize to the existing session representation."""
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = {}

    def delete(self, *args):
        for child in self.winfo_children():
            child.destroy()
        self.rows.clear()

    def insert(self, index, text):
        self.delete()
        values = json.loads(text) if text.strip() else {}
        for col, label in enumerate(('Parameter', 'Initial', 'Minimum', 'Maximum')):
            ttk.Label(self, text=label).grid(row=0, column=col, sticky='w', padx=3)
        for row, (name, bounds) in enumerate(values.items(), start=1):
            ttk.Label(self, text=name).grid(row=row, column=0, sticky='w', padx=3)
            variables = []
            for col, value in enumerate(bounds, start=1):
                var = tk.StringVar(value='' if value is None else str(value))
                ttk.Entry(self, textvariable=var, width=9).grid(row=row, column=col, sticky='ew', padx=3, pady=3)
                variables.append(var)
            self.rows[name] = variables
        for col in range(1, 4):
            self.columnconfigure(col, weight=1)

    def get(self, *args):
        values = {}
        for name, variables in self.rows.items():
            parsed = []
            for i, var in enumerate(variables):
                text = var.get().strip()
                if not text and i:
                    parsed.append(None)
                    continue
                try:
                    value = float(text)
                    if not np.isfinite(value): raise ValueError()
                except ValueError:
                    raise ValueError(f'{name}: enter a finite number. Leave bounds blank for no limit.') from None
                parsed.append(value)
            values[name] = parsed
        return json.dumps(values)


class Studio:
    def __init__(self, root, path=None):
        self.root = root
        root.title('TCSPC · Fitting & publication studio')
        root.geometry('1200x820')
        root.minsize(960, 640)
        self.data = self.fit = self.ratio = self.signature = None
        self.comparisons = []
        self.vars = {}
        self.widgets = {}
        self.selector = None
        self.ax = None
        self.applied_offset = 0.
        self.export_image = None
        self.export_photo = None
        self.scroll_canvases = []
        self.refresh_job = None
        self.loading = False
        self.fit_busy = False
        self.analysis_revision = 0
        bar = ttk.Frame(root, padding=(10, 8))
        bar.pack(fill='x')
        ttk.Button(bar, text='Open measurement…', command=lambda: self.guard(self.open_file)).pack(side='left')
        self.file_actions = []
        for title, action in [('Apply changes', self.refresh), ('Export figure…', self.export)]:
            button = ttk.Button(bar, text=title, command=lambda f=action: self.guard(f), state='disabled')
            button.pack(side='left', padx=(8, 0))
            self.file_actions.append(button)
        self.filename = tk.StringVar(value='Open a measurement CSV to begin.')
        ttk.Label(root, textvariable=self.filename, wraplength=1100, padding=(12, 0, 12, 6)).pack(fill='x')
        # Pack the footer before the expanding content so it remains reachable.
        self.status = tk.StringVar(value='1  Open a file     2  Adjust plot or analyze     3  Export')
        ttk.Label(root, textvariable=self.status, wraplength=1100, padding=8).pack(side='bottom', fill='x')
        panes = ttk.Panedwindow(root, orient='horizontal')
        panes.pack(fill='both', expand=True)
        self.notebook = ttk.Notebook(panes, width=390)
        panes.add(self.notebook, weight=0)
        preview = ttk.Frame(panes, padding=(8, 0))
        panes.add(preview, weight=1)
        self.tabs = {}
        for name in ('Plot', 'Analysis', 'Style', 'Export'):
            outer = ttk.Frame(self.notebook)
            self.notebook.add(outer, text=name)
            canvas = tk.Canvas(outer, highlightthickness=0, width=390)
            scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right', fill='y')
            canvas.pack(side='left', fill='both', expand=True)
            frame = ttk.Frame(canvas, padding=10)
            window = canvas.create_window((0, 0), window=frame, anchor='nw')
            frame.bind('<Configure>', lambda e, c=canvas: c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>', lambda e, c=canvas, w=window: c.itemconfigure(w, width=e.width))
            self.tabs[name] = frame
            self.scroll_canvases.append(canvas)
        root.bind_all('<MouseWheel>', self.scroll_controls, add='+')
        root.bind_all('<Button-4>', self.scroll_controls, add='+')
        root.bind_all('<Button-5>', self.scroll_controls, add='+')
        root.bind('<Return>', lambda e: self.guard(self.refresh) if self.data else None)
        a = self.tabs['Plot']
        self.note(a, 'Edit labels and crop here, then Apply changes. Fitting is optional.')
        labels = self.group(a, 'Labels')
        for key, label, value in [('title', 'Title', ''), ('xlabel', 'X label', ''), ('ylabel', 'Y label', ''),
                                  ('label', 'Data legend', 'Data'), ('fit_label', 'Fit legend', 'Fit')]:
            self.field(labels, key, label, value)
        self.note(labels, r'Math labels: use $g^{(2)}(\tau)$, $I_0$, or $10^{-3}$. Text outside dollar signs stays plain. No LaTeX installation is needed.')
        self.offset_group = self.group(a, 'Time calibration')
        self.field(self.offset_group, 'time_offset', 'Time offset (added to X)', 0)
        self.note(self.offset_group, 'Example: enter −3 (as -3) to move a peak at +3 to zero. Counts are unchanged. Peak windows and ranges move with the data.')
        crop = self.group(a, 'Visible range')
        self.note(crop, 'Leave both limits blank for automatic bounds.')
        self.pair(crop, 'xmin', 'xmax', 'X min', 'X max')
        self.pair(crop, 'ymin', 'ymax', 'Y min', 'Y max')
        row = ttk.Frame(crop)
        row.pack(fill='x', pady=4)
        ttk.Button(row, text='Use current zoom', command=lambda: self.guard(self.use_zoom)).pack(side='left')
        ttk.Button(row, text='Reset crop', command=lambda: self.guard(self.reset_crop)).pack(side='left', padx=5)
        for key, label in [('xscale', 'X scale'), ('yscale', 'Y scale')]:
            self.field(crop, key, label, 'linear', ['linear', 'log'])
        overlay = self.group(a, 'Overlays')
        for key, label, value in [('show_fit', 'Show fitted curve', True), ('residuals', 'Show residual panel', False),
                                   ('show_g0', 'Show g²(0) annotation', True)]:
            self.check(overlay, key, label, value)
        self.overlay_group = overlay
        self.field(overlay, 'annotation', 'Additional annotation', '')
        self.stability_group = self.group(a, 'Stability')
        self.check(self.stability_group, 'power', 'Show laser-power axis', False)
        self.field(self.stability_group, 'power_label', 'Power-axis label', 'Laser power (μW)')
        self.intensity_group = self.group(a, 'Intensity normalization')
        self.check(self.intensity_group, 'normalize_intensity', 'Normalize intensity to peak = 1', False)
        self.note(self.intensity_group, 'Spectrum: subtract the minimum and scale to 0–1. Maps, lifetime, and pulsed g²: divide by the full-trace maximum without subtracting background. Pulsed peak areas still use raw counts; peak height is not g²(0).')
        self.map_group = self.group(a, 'Map intensity')
        self.field(self.map_group, 'cmap', 'Color scheme', 'inferno', ['inferno', 'viridis', 'magma', 'cividis', 'gray'])
        self.field(self.map_group, 'colorbar', 'Colorbar label', 'Intensity (a.u.)')
        self.pair(self.map_group, 'vmin', 'vmax', 'Color min', 'Color max')
        b = self.tabs['Analysis']
        self.analysis_hint = tk.StringVar(value='Open a lifetime, saturation, or g² file to analyze it.')
        ttk.Label(b, textvariable=self.analysis_hint, wraplength=350).pack(fill='x', pady=6)
        self.correlation_group = self.group(b, 'Correlation measurement')
        mode = self.field(self.correlation_group, 'mode', 'Acquisition mode', 'CW', ['CW', 'Pulsed'])
        mode.bind('<<ComboboxSelected>>', lambda e: self.guard(self.mode_changed))
        self.cw_group = self.group(b, 'CW normalization')
        self.check(self.cw_group, 'normalize', 'Normalize coincidences', True)
        self.field(self.cw_group, 'baseline', 'Baseline (blank = outer-edge mean)', '')
        self.fit_group = self.group(b, 'Fit setup')
        self.model_widget = self.field(self.fit_group, 'model', 'Model', 'CW two-level', list(MODELS))
        self.model_widget.bind('<<ComboboxSelected>>', lambda e: self.guard(self.model_changed))
        self.origin_widget = self.field(self.fit_group, 'origin', 'Time origin / dip center', 0)
        self.fit_range_row = self.pair(self.fit_group, 'fit_min', 'fit_max', 'Fit from', 'Fit to')
        self.note(self.fit_group, 'Set the range here or choose “Fit range” above the preview and drag. The fit range is independent of the plot crop.')
        self.advanced_open = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.fit_group, text='Advanced: initial guesses and bounds', variable=self.advanced_open,
                        command=self.toggle_advanced).pack(anchor='w', pady=4)
        self.advanced = ttk.Frame(self.fit_group)
        self.params = ParameterEditor(self.advanced)
        self.params.pack(fill='x')
        self.note(self.advanced, 'Blank bounds mean no limit. Lifetime origin defaults to the peak; fit later to exclude the instrument response.')
        ttk.Button(self.advanced, text='Reset guesses for this range', command=lambda: self.guard(self.reset_parameters)).pack(fill='x')
        self.pulsed_group = self.group(b, 'Pulsed peak areas')
        self.note(self.pulsed_group, '1  Drag over the central peak.\n2  Choose “Add side peak” and drag over side peaks.\n3  Calculate g²(0). Side windows use the central bin count.')
        self.vars['central'] = tk.StringVar(value='')
        self.vars['sides'] = tk.StringVar(value='[]')
        self.peak_list = tk.Listbox(self.pulsed_group, height=5, exportselection=False)
        self.peak_list.pack(fill='x', pady=4)
        peak_buttons = ttk.Frame(self.pulsed_group)
        peak_buttons.pack(fill='x')
        ttk.Button(peak_buttons, text='Remove selected', command=lambda: self.guard(self.remove_peak)).pack(side='left')
        ttk.Button(peak_buttons, text='Clear windows', command=self.clear_windows).pack(side='left', padx=4)
        self.field(self.pulsed_group, 'background', 'Background counts per bin', 0)
        self.result_group = self.group(b, 'Results')
        self.results = tk.Text(self.result_group, width=38, height=12, wrap='word', state='disabled', relief='flat')
        self.results.pack(fill='x')
        ttk.Button(self.result_group, text='Clear analysis', command=self.clear_analysis).pack(anchor='w', pady=3)
        s = self.tabs['Style']
        typography = self.group(s, 'Typography')
        for key, label, value in [('font', 'Font family', 'DejaVu Sans'), ('fontsize', 'Font size (pt)', 9),
                                  ('annotation_size', 'Annotation size (pt)', 9),
                                  ('annotation_color', 'Annotation color (name or hex)', '#000000')]:
            self.field(typography, key, label, value)
        self.pair(typography, 'annotation_x', 'annotation_y', 'Annotation X (0–1)', 'Annotation Y (0–1)', '.97', '.95')
        self.trace_group = self.group(s, 'Lines and markers')
        for key, label, value in [('linewidth', 'Line width (pt)', 1), ('markersize', 'Marker size (pt)', 2.5),
                                  ('color', 'Data color', '#0072B2'), ('fit_color', 'Fit color', '#D55E00')]:
            self.field(self.trace_group, key, label, value)
        self.field(self.trace_group, 'marker', 'Marker', 'none', ['none', 'o', '.', 's', '^', '+'])
        self.field(self.trace_group, 'line', 'Line style', '-', ['-', 'none', '--', ':', '-.'])
        self.field(s, 'legend', 'Legend position', 'best', ['best', 'none', 'upper right', 'upper left', 'lower right', 'lower left'])
        self.check(s, 'grid', 'Show grid', False)
        c = self.tabs['Export']
        dimensions = self.group(c, 'Figure size and output')
        self.note(dimensions, 'Default: single-column figure, 9 pt font. SVG/PDF are vector formats; PNG uses the resolution below.')
        self.pair(dimensions, 'width', 'height', 'Width (in)', 'Height (in)', '3.5', '2.8')
        self.field(dimensions, 'dpi', 'PNG resolution (dpi)', 600)
        self.check(dimensions, 'transparent', 'Transparent background', False)
        ttk.Button(dimensions, text='Export figure…', command=lambda: self.guard(self.export)).pack(fill='x', pady=5)
        self.note(dimensions, 'This tab shows the final export layout, scaled to fit the window. Fonts, spacing, and aspect ratio match the saved figure. Peak guides are omitted.')
        spacing = self.group(c, 'Final typography and spacing')
        for key, label in [('fontsize', 'Font size (pt)'), ('annotation_size', 'Annotation size (pt)'), ('annotation_color', 'Annotation color (name or hex)')]:
            row = ttk.Frame(spacing)
            row.pack(fill='x', pady=2)
            ttk.Label(row, text=label).pack(anchor='w')
            ttk.Entry(row, textvariable=self.vars[key]).pack(fill='x')
        for key, label, value in [('layout_pad', 'Outer padding (pt)', 3), ('labelpad', 'Axis-label padding (pt)', 4),
                                  ('titlepad', 'Title padding (pt)', 6), ('subplot_gap', 'Panel gap (fraction)', .08)]:
            self.field(spacing, key, label, value)
        files = self.group(c, 'Data and sessions')
        for title, action in [('Export data + analysis…', self.export_data), ('Save session…', self.save_session), ('Load session…', self.load_session)]:
            ttk.Button(files, text=title, command=lambda f=action: self.guard(f)).pack(fill='x', pady=3)
        self.note(files, 'Data export includes raw values and analysis in CSV/JSON. Sessions restore the source file and controls; rerun analysis after loading.')
        # Keep analysis actions visible, independent of sidebar scrolling.
        self.analysis_bar = ttk.Frame(preview, padding=(0, 5))
        self.analysis_bar.pack(fill='x')
        self.action_button = ttk.Button(self.analysis_bar, text='Fit selected model', command=lambda: self.guard(self.analyze), state='disabled')
        self.action_button.pack(side='left', padx=(0, 8))
        ttk.Label(self.analysis_bar, text='Drag:').pack(side='left')
        self.vars['selection'] = tk.StringVar(value='Off')
        self.selection_widget = ttk.Combobox(self.analysis_bar, textvariable=self.vars['selection'], values=['Off'], state='disabled', width=16)
        self.selection_widget.pack(side='left', padx=5)
        self.selection_widget.bind('<<ComboboxSelected>>', lambda e: self.drag_changed())
        from matplotlib.figure import Figure
        self.figure = Figure(figsize=(6, 4.8))
        self.canvas = FigureCanvasTkAgg(self.figure, master=preview)
        self.toolbar = NavigationToolbar2Tk(self.canvas, preview, pack_toolbar=False)
        # Use our validated export flow instead of Matplotlib's inconsistent save dialog.
        if 'Save' in self.toolbar._buttons:
            self.toolbar._buttons['Save'].pack_forget()
        self.toolbar.pack(side='bottom', fill='x')
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.export_frame = ttk.Frame(preview)
        self.export_caption = tk.StringVar(value='Open a file to preview the export layout.')
        ttk.Label(self.export_frame, textvariable=self.export_caption, padding=8).pack(fill='x')
        self.export_label = ttk.Label(self.export_frame, anchor='center')
        self.export_label.pack(fill='both', expand=True)
        self.export_label.bind('<Configure>', lambda e: self.resize_export_image())
        self.notebook.bind('<<NotebookTabChanged>>', lambda e: self.change_preview_mode())
        self.figure.text(.5, .5, 'Open a measurement to preview it.\n\nPlot → Analysis (optional) → Export', ha='center', va='center', color='#555555')
        self.canvas.draw_idle()
        self.configure_context()
        for key, var in self.vars.items():
            var.trace_add('write', lambda *_, k=key: self.control_changed(k))
        if path:
            self.guard(lambda: self.load(path))

    def group(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.pack(fill='x', pady=(4, 8))
        return frame

    def pair(self, parent, left, right, left_label, right_label, a='', b=''):
        row = ttk.Frame(parent)
        row.pack(fill='x')
        for key, label, value in ((left, left_label, a), (right, right_label, b)):
            column = ttk.Frame(row)
            column.pack(side='left', fill='x', expand=True, padx=2)
            self.field(column, key, label, value)
        return row

    def scroll_controls(self, event):
        widget = event.widget
        if isinstance(widget, (tk.Text, tk.Listbox, ttk.Combobox)):
            return
        for canvas in self.scroll_canvases:
            ancestor = widget
            while ancestor is not None:
                if ancestor == canvas:
                    delta = getattr(event, 'delta', 0)
                    direction = -1 if delta > 0 or getattr(event, 'num', None) == 4 else 1
                    canvas.yview_scroll(direction * max(1, min(5, int(abs(delta)))), 'units')
                    return 'break'
                ancestor = getattr(ancestor, 'master', None)

    def toggle_advanced(self):
        if self.advanced_open.get():
            self.advanced.pack(fill='x', pady=4)
        else:
            self.advanced.pack_forget()

    def configure_context(self):
        kind = self.data.kind if self.data else None
        normalized_spectrum = kind == 'Spectrum' and self.get('normalize_intensity')
        self.widgets['yscale'].configure(state='disabled' if normalized_spectrum else 'readonly')
        if normalized_spectrum: self.vars['yscale'].set('linear')
        pulsed = kind == 'g2' and self.get('mode') == 'Pulsed'
        fitted = kind in ('g2', 'Lifetime', 'Saturation') and not pulsed
        # Repack in a stable order; hidden groups do not consume scrolling space.
        groups = [(self.correlation_group, kind == 'g2'), (self.cw_group, kind == 'g2' and not pulsed),
                  (self.fit_group, fitted), (self.pulsed_group, pulsed), (self.result_group, fitted or pulsed)]
        for group, visible in groups:
            group.pack_forget()
        for group, visible in groups:
            if visible: group.pack(fill='x', pady=(4, 8))
        for group, visible in [(self.offset_group, kind in ('g2', 'Lifetime', 'Stability')), (self.stability_group, kind == 'Stability'), (self.intensity_group, kind in ('Spectrum', 'PL', 'Lifetime') or pulsed), (self.map_group, kind == 'PL'), (self.trace_group, kind != 'PL')]:
            group.pack_forget()
            if visible: group.pack(fill='x', pady=(4, 8))
        self.origin_widget.master.pack_forget()
        if kind in ('g2', 'Lifetime'):
            self.origin_widget.master.pack(fill='x', pady=2, before=self.fit_range_row)
        options = ['Off', 'Central peak', 'Add side peak'] if pulsed else ['Off', 'Fit range'] if fitted else ['Off']
        self.selection_widget.configure(values=options, state='readonly' if fitted or pulsed else 'disabled')
        if self.get('selection') not in options: self.vars['selection'].set('Off')
        self.action_button.configure(text='Calculate g²(0)' if pulsed else 'Fit selected model', state='normal' if (fitted or pulsed) and not self.fit_busy else 'disabled')
        self.analysis_hint.set('Select central and side peaks, then Calculate.' if pulsed else
                               'Choose a model and fit range, then Fit selected model.' if fitted else
                               'No fitting is needed for this data type. Use Plot, Style, and Export.' if kind else
                               'Open a measurement to begin.')
        for key, visible in [('show_fit', fitted), ('residuals', fitted), ('show_g0', kind == 'g2')]:
            widget = self.widgets[key]
            widget.pack_forget()
            if visible: widget.pack(anchor='w', pady=3, before=self.widgets['annotation'].master)
        for key, visible in [('fit_label', fitted), ('label', kind != 'PL')]:
            row = self.widgets[key].master
            row.pack_forget()
            if visible: row.pack(fill='x', pady=2)
        for button in self.file_actions:
            button.configure(state='normal' if kind else 'disabled')

    def control_changed(self, key):
        if self.loading or not self.data:
            return
        if key == 'normalize_intensity':
            self.update_intensity_labels()
            self.configure_context()
            if self.data.kind == 'Lifetime':
                self.invalidate()
                try:
                    self.reset_parameters()
                except ValueError:
                    pass  # Incomplete range edits will be reported when applying/fitting.
        if key in ('mode', 'normalize'):
            self.update_correlation_label()
        if key == 'mode':
            self.configure_context()
        if key == 'selection':
            self.set_selector_active()
            return
        if key in ('mode', 'normalize', 'baseline', 'origin', 'fit_min', 'fit_max', 'central', 'sides', 'background', 'time_offset'):
            self.invalidate()
        if key == 'model':
            self.analysis_revision += 1
            self.fit = None
            self.write_results('Model changed. Fit again to update the curve.')
        self.status.set('Changes pending — Apply changes or press Return to update the preview.')
        # Remove stale overlays promptly and apply toggles without requiring a second click.
        if key in ('mode', 'normalize', 'normalize_intensity', 'annotation_color', 'show_fit', 'show_g0', 'residuals', 'grid', 'power', 'model',
                   'baseline', 'origin', 'fit_min', 'fit_max', 'central', 'sides', 'background', 'time_offset') or self.export_mode():
            if self.refresh_job: self.root.after_cancel(self.refresh_job)
            self.refresh_job = self.root.after(350, self.quiet_refresh)

    def export_mode(self):
        return self.notebook.index(self.notebook.select()) == 3

    def change_preview_mode(self):
        if not hasattr(self, 'export_frame'): return
        if self.export_mode():
            self.canvas.get_tk_widget().pack_forget()
            self.toolbar.pack_forget()
            self.analysis_bar.pack_forget()
            self.export_frame.pack(fill='both', expand=True)
        else:
            self.export_frame.pack_forget()
            self.analysis_bar.pack(fill='x')
            self.toolbar.pack(side='bottom', fill='x')
            self.canvas.get_tk_widget().pack(fill='both', expand=True)
        if self.data: self.quiet_refresh()

    def refresh_export_preview(self):
        from PIL import Image
        self.export_figure, _ = publication_figure(self.data, self.style(), self.values(), self.fit)
        self.export_image = Image.fromarray(np.asarray(self.export_figure.canvas.buffer_rgba()).copy())
        self.export_caption.set(f'Export layout · {self.number("width"):g} × {self.number("height"):g} in · scaled to fit')
        self.resize_export_image()

    def resize_export_image(self):
        if self.export_image is None: return
        from PIL import Image, ImageTk
        image = self.export_image.copy()
        width = max(1, self.export_label.winfo_width()-16)
        height = max(1, self.export_label.winfo_height()-16)
        scale = min(width/image.width, height/image.height)
        image = image.resize((max(1, round(image.width*scale)), max(1, round(image.height*scale))), Image.Resampling.LANCZOS)
        self.export_photo = ImageTk.PhotoImage(image, master=self.root)
        self.export_label.configure(image=self.export_photo)

    def apply_time_offset(self):
        if self.data is None: return
        offset = self.number('time_offset') if self.data.kind in ('g2', 'Lifetime', 'Stability') else 0.
        delta = offset-self.applied_offset
        if delta == 0: return
        updates = {}
        for key in ('fit_min', 'fit_max', 'xmin', 'xmax'):
            value = self.number(key, True)
            if value is not None: updates[key] = str(value+delta)
        # Lifetime amplitudes retain the same reference sample. CW center remains
        # a user-selected coordinate (normally zero after time calibration).
        if self.data.kind == 'Lifetime':
            updates['origin'] = str(self.number('origin')+delta)
        shifted_x = self.raw_x + offset
        def shift_window(pair):
            # Preserve selected bins exactly, even after repeated decimal offsets.
            lo, hi = pair
            indices = np.flatnonzero((self.data.x >= lo) & (self.data.x <= hi))
            if not len(indices):
                raise ValueError('A peak window contains no samples; clear it before changing the offset.')
            return [float(shifted_x[indices[0]]), float(shifted_x[indices[-1]])]
        if self.get('central'):
            updates['central'] = json.dumps(shift_window(json.loads(self.get('central'))))
        updates['sides'] = json.dumps([shift_window(pair) for pair in json.loads(self.get('sides'))])
        was_loading = self.loading
        self.loading = True
        try:
            for key, value in updates.items(): self.vars[key].set(value)
            self.data.x = self.raw_x + offset
            self.applied_offset = offset
        finally:
            self.loading = was_loading
        self.view_config = None

    def quiet_refresh(self):
        self.refresh_job = None
        if not self.data: return
        try:
            self.refresh()
        except (ValueError, TypeError, tk.TclError) as exc:
            self.status.set(f'Check controls: {exc}')

    def mode_changed(self):
        self.configure_context()
        self.vars['selection'].set('Central peak' if self.get('mode') == 'Pulsed' else 'Off')
        self.reset_parameters()
        self.refresh()

    def model_changed(self):
        self.reset_parameters()
        self.refresh()

    def analyze(self):
        self.notebook.select(1)
        if self.data and self.data.kind == 'g2' and self.get('mode') == 'Pulsed':
            self.calculate()
        else:
            self.start_fit()

    def drag_changed(self):
        if self.get('selection') != 'Off':
            if self.toolbar.mode.name == 'PAN': self.toolbar.pan()
            elif self.toolbar.mode.name == 'ZOOM': self.toolbar.zoom()
        self.set_selector_active()
        self.status.set(f'Drag action: {self.get("selection")}. Pan/zoom must be off to select a range.')

    def use_zoom(self):
        self.require_data()
        if self.ax is None: return
        for key, value in zip(('xmin', 'xmax', 'ymin', 'ymax'), (*self.ax.get_xlim(), *self.ax.get_ylim())):
            self.vars[key].set(f'{value:.12g}')
        self.refresh()

    def reset_crop(self):
        self.view_config = None
        for key in ('xmin', 'xmax', 'ymin', 'ymax'):
            self.vars[key].set('')
        self.refresh()

    def update_peak_list(self):
        self.peak_list.delete(0, 'end')
        if self.get('central'):
            a, b = json.loads(self.get('central'))
            self.peak_list.insert('end', f'Central: {a:.5g} to {b:.5g}')
        for i, (a, b) in enumerate(json.loads(self.get('sides')), 1):
            self.peak_list.insert('end', f'Side {i}: {a:.5g} to {b:.5g}')

    def remove_peak(self):
        selected = self.peak_list.curselection()
        if not selected: return
        if selected[0] == 0:
            self.clear_windows()
        else:
            sides = json.loads(self.get('sides'))
            del sides[selected[0]-1]
            self.vars['sides'].set(json.dumps(sides))
            self.refresh()

    def note(self, parent, text):
        ttk.Label(parent, text=text, wraplength=330, justify='left').pack(fill='x', pady=6)

    def field(self, parent, key, label, value, options=None):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=2)
        ttk.Label(row, text=label).pack(anchor='w')
        var = self.vars[key] = tk.StringVar(value=str(value))
        widget = ttk.Combobox(row, textvariable=var, values=options, state='readonly') if options else ttk.Entry(row, textvariable=var)
        widget.pack(fill='x')
        self.widgets[key] = widget
        return widget

    def check(self, parent, key, label, value):
        self.vars[key] = tk.BooleanVar(value=value)
        widget = ttk.Checkbutton(parent, text=label, variable=self.vars[key])
        widget.pack(anchor='w', pady=3)
        self.widgets[key] = widget

    def get(self, key):
        return self.vars[key].get()

    def number(self, key, optional=False):
        val = self.get(key)
        if optional and not val.strip(): return None
        number = float(val)
        if not np.isfinite(number): raise ValueError(f'{key} must be finite.')
        return number

    def guard(self, action):
        try:
            action()
        except Exception as exc:
            self.status.set(str(exc))
            messagebox.showerror('TCSPC studio', str(exc), parent=self.root)

    def require_data(self):
        if self.data is None: raise ValueError('Open a measurement first.')

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[('Measurement CSV', '*.csv'), ('All files', '*')])
        if path: self.load(path)

    def load(self, path):
        self.loading = True
        try:
            self._load(path)
        finally:
            self.loading = False
        self.configure_context()
        self.notebook.select(0)
        for canvas in self.scroll_canvases:
            canvas.yview_moveto(0)

    def _load(self, path):
        data = load_dataset(path)
        self.ax = None
        self.data = data
        self.raw_x = data.x.copy()
        self.applied_offset = 0.
        self.vars['time_offset'].set('0')
        self.filename.set(f'{data.kind}  ·  {Path(path).name}')
        self.clear_analysis(redraw=False)
        for key, value in asdict(Style()).items():
            if key in self.vars:
                self.vars[key].set('' if value is None else value)
        for key in ('xmin', 'xmax', 'ymin', 'ymax', 'central', 'baseline'):
            self.vars[key].set('')
        for key, value in dict(sides='[]', origin='0', background='0', mode='CW', normalize=True, normalize_intensity=False, show_g0=True, selection='Off').items():
            self.vars[key].set(value)
        for key in ('xlabel', 'ylabel', 'title'):
            self.vars[key].set(getattr(data, key))
        models = {'g2': [m for m in MODELS if m.startswith('CW')],
                  'Lifetime': [m for m in MODELS if m.startswith('Lifetime')],
                  'Saturation': [m for m in MODELS if m.startswith('Saturation')]}.get(data.kind, [])
        self.model_widget.configure(values=models)
        self.vars['model'].set(models[0] if models else '')
        self.vars['fit_min'].set(str(data.x.min()) if len(data.x) else '')
        self.vars['fit_max'].set(str(data.x.max()) if len(data.x) else '')
        if data.kind == 'Lifetime':
            peak = float(data.x[np.argmax(data.y)])
            self.vars['origin'].set(str(peak))
            self.vars['fit_min'].set(str(peak))
            self.vars['yscale'].set('log')
        if data.kind == 'Saturation':
            self.vars['marker'].set('o')
            self.vars['line'].set('none')
        if data.kind == 'g2':
            self.vars['ylabel'].set(r'$g^{(2)}(\tau)$')
            self.vars['title'].set(r'$g^{(2)}$ correlation')
        self.reset_parameters()
        self.refresh()

    def update_correlation_label(self):
        defaults = ('g²(τ)', r'$g^{(2)}(\tau)$', 'Coincidences', 'Normalized coincidences')
        if self.data is not None and self.data.kind == 'g2' and self.get('ylabel') in defaults:
            label = 'Coincidences'
            if self.get('mode') == 'CW' and self.get('normalize'):
                label = r'$g^{(2)}(\tau)$'
            elif self.get('mode') == 'Pulsed' and self.get('normalize_intensity'):
                label = 'Normalized coincidences'
            self.vars['ylabel'].set(label)

    def analysis_signature(self):
        signature = tuple(self.get(k) for k in ('mode', 'normalize', 'baseline', 'origin', 'fit_min', 'fit_max', 'central', 'sides', 'background', 'time_offset'))
        # Lifetime fits use displayed units; pulsed area calculations always use raw counts.
        return signature + (self.get('normalize_intensity') if self.data and self.data.kind == 'Lifetime' else None,)

    def invalidate(self):
        signature = self.analysis_signature()
        if signature != self.signature:
            self.clear_analysis(redraw=False)
            self.signature = signature

    def update_intensity_labels(self):
        if self.data.kind not in ('Spectrum', 'PL', 'Lifetime', 'g2'): return
        if self.data.kind == 'g2':
            self.update_correlation_label()
        else:
            key = 'colorbar' if self.data.kind == 'PL' else 'ylabel'
            raw_label = 'Counts' if self.data.kind == 'Lifetime' else 'Intensity (a.u.)'
            if self.get(key) in (raw_label, 'Normalized intensity'):
                self.vars[key].set('Normalized intensity' if self.get('normalize_intensity') else raw_label)
        for bound in (('vmin', 'vmax') if self.data.kind == 'PL' else ('ymin', 'ymax')):
            self.vars[bound].set('')
        self.view_config = None

    def peak_normalization_active(self):
        return self.get('normalize_intensity') and (
            self.data.kind in ('PL', 'Lifetime') or
            (self.data.kind == 'g2' and self.get('mode') == 'Pulsed'))

    def values(self):
        if self.data.kind == 'Spectrum' and self.get('normalize_intensity'):
            return normalize_spectrum(self.data.y)[0]
        if self.peak_normalization_active():
            return normalize_intensity(self.data.y)[0]
        if self.data.kind == 'g2' and self.get('mode') == 'CW' and self.get('normalize'):
            return normalize_cw(self.data.y, self.number('baseline', True))[0]
        return self.data.y

    def bounds(self, low, high):
        a, b = self.number(low, True), self.number(high, True)
        if (a is None) != (b is None): raise ValueError(f'Supply both {low} and {high}, or leave both blank.')
        if a is not None and a >= b: raise ValueError(f'{low} must be below {high}.')
        return None if a is None else (a, b)

    def style(self, include_result=True):
        s = Style()
        numeric = {'fontsize', 'width', 'height', 'linewidth', 'markersize', 'annotation_x', 'annotation_y', 'annotation_size', 'layout_pad', 'labelpad', 'titlepad', 'subplot_gap'}
        for key in asdict(s):
            if key in self.vars:
                setattr(s, key, self.number(key) if key in numeric else self.number(key, True) if key in ('vmin', 'vmax') else self.get(key))
        s.normalized_spectrum = self.data.kind == 'Spectrum' and self.get('normalize_intensity')
        if s.normalized_spectrum: s.yscale = 'linear'
        s.xlim, s.ylim = self.bounds('xmin', 'xmax'), self.bounds('ymin', 'ymax')
        if not 0 <= s.annotation_x <= 1 or not 0 <= s.annotation_y <= 1:
            raise ValueError('Annotation positions must be between 0 and 1.')
        result = self.ratio or self.fit
        if include_result and self.get('show_g0') and result and 'g2_zero' in result:
            s.annotation = f'g²(0) = {result["g2_zero"]:.3f}' + ('\n' + s.annotation if s.annotation else '')
        return s

    def refresh(self):
        self.require_data()
        if self.refresh_job:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        self.apply_time_offset()
        self.invalidate()
        if self.export_mode():
            self.refresh_export_preview()
            self.status.set('Final layout updated. This is the layout used for export.')
            return
        style, values = self.style(), self.values()
        windows = []
        if self.data.kind == 'g2' and self.get('mode') == 'Pulsed':
            if self.get('central'): windows.append(json.loads(self.get('central')))
            windows.extend(json.loads(self.get('sides')))
        view_config = (self.data.path, style.xscale, style.yscale, style.xlim, style.ylim, self.get('mode'), self.get('normalize'), self.get('normalize_intensity'))
        previous = None
        if self.ax is not None and getattr(self, 'view_config', None) == view_config:
            current = (self.ax.get_xlim(), self.ax.get_ylim())
            if current != getattr(self, 'home_limits', None):
                previous = current
        if self.selector: self.selector.disconnect_events()
        _, ax = render(self.data, style, values, self.fit, windows, self.figure)
        self.ax = ax
        self.view_config = view_config
        self.home_limits = (ax.get_xlim(), ax.get_ylim())
        if previous:
            ax.set_xlim(previous[0])
            ax.set_ylim(previous[1])
        self.selector = SpanSelector(ax, lambda lo, hi: self.root.after_idle(
            lambda: self.guard(lambda: self.select(lo, hi))), 'horizontal', useblit=False,
            props=dict(alpha=.2, facecolor='#009E73'))
        self.set_selector_active()
        self.update_peak_list()
        self.canvas.draw_idle()
        self.toolbar.update()
        self.status.set('Preview updated. Use “Use current zoom” in Plot to include a toolbar zoom in the export.')

    def set_selector_active(self):
        if self.selector:
            self.selector.set_active(self.get('selection') != 'Off' and self.data is not None and self.data.kind in ('g2', 'Lifetime', 'Saturation'))

    def select(self, lo, hi):
        if self.toolbar.mode or hi <= lo: return
        action = self.get('selection')
        if action == 'Fit range':
            self.vars['fit_min'].set(f'{lo:.9g}')
            self.vars['fit_max'].set(f'{hi:.9g}')
        elif action in ('Central peak', 'Add side peak'):
            if self.data.kind != 'g2' or self.get('mode') != 'Pulsed':
                raise ValueError('Peak selection requires a g2 file in Pulsed mode.')
            x = self.data.x
            indices = np.flatnonzero((x >= lo) & (x <= hi))
            if len(indices) < 2:
                raise ValueError('Drag across at least two histogram bins.')
            if action == 'Central peak':
                self.vars['central'].set(json.dumps([float(x[indices[0]]), float(x[indices[-1]])]))
                self.vars['sides'].set('[]')
                self.vars['selection'].set('Add side peak')
            else:
                if not self.get('central'): raise ValueError('Select the central peak first.')
                a, b = json.loads(self.get('central'))
                count = int(np.sum((x >= a) & (x <= b)))
                start = int(np.argmin(abs(x-(lo+hi)/2))) - (count-1)//2
                end = start+count-1
                if start < 0 or end >= len(x): raise ValueError('Side window extends beyond the histogram.')
                sides = json.loads(self.get('sides'))
                candidate = [float(x[start]), float(x[end])]
                for left, right in [json.loads(self.get('central')), *sides]:
                    if candidate[0] <= right and candidate[1] >= left:
                        raise ValueError('That window overlaps an existing peak. Choose a different side peak.')
                sides.append(candidate)
                self.vars['sides'].set(json.dumps(sides))
        self.refresh()

    def reset_parameters(self):
        self.require_data()
        self.apply_time_offset()
        self.params.delete('1.0', 'end')
        model = self.get('model')
        if model not in MODELS: return
        x, y = self.data.x, self.values()
        limits = self.bounds('fit_min', 'fit_max')
        mask = np.ones(len(x), dtype=bool) if limits is None else (x >= limits[0]) & (x <= limits[1])
        if not mask.any(): raise ValueError('Fit range contains no samples.')
        defaults = parameter_defaults(model, x[mask]-self.number('origin'), y[mask])
        self.params.insert('1.0', json.dumps(defaults, indent=2))

    def write_results(self, text):
        self.results.configure(state='normal')
        self.results.delete('1.0', 'end')
        self.results.insert('1.0', text)
        self.results.configure(state='disabled')

    def prepare_fit(self):
        self.require_data()
        self.apply_time_offset()
        self.invalidate()
        model = self.get('model')
        if self.data.kind == 'g2' and (self.get('mode') != 'CW' or not self.get('normalize')):
            raise ValueError('CW fits require CW mode and normalized coincidences. Use Calculate for pulsed data.')
        if model not in MODELS: raise ValueError('No fit model for this data type; appearance and export are available.')
        # A failed attempt must not leave an older overlay masquerading as the new fit.
        self.fit = None
        self.ratio = None
        self.write_results('Fitting…')
        self.refresh()
        return (self.data.x.copy(), self.values().copy(), model,
                self.bounds('fit_min', 'fit_max'), self.number('origin'),
                json.loads(self.params.get('1.0', 'end')))

    def finish_fit(self, result):
        model = result['model']
        self.fit = result
        self.comparisons.append(f'{model}: RMSE={result["rmse"]:.5g}, AIC={result["aic"]:.5g}')
        lines = [result['model']]
        if 'g2_zero' in result:
            lines.append(f"g²(0) = {result['g2_zero']:.4g}")
        lines.extend(f"{name} = {value:.5g} ± {result['errors'][name]:.3g}" for name, value in result['parameters'].items())
        lines.extend(['', f"RMSE: {result['rmse']:.4g}", '', 'Model comparisons (same data/range):', *self.comparisons,
                      '', '± values are local covariance estimates. Lower AIC is preferred only for the same data and range.'])
        lines.extend(result['warnings'])
        self.write_results('\n'.join(lines))
        self.refresh()

    def run_fit(self):
        """Synchronous entry point used by regression tests."""
        args = self.prepare_fit()
        try:
            result = fit_curve(*args)
        except Exception as exc:
            self.write_results(f'Fit failed: {exc}\nAdjust the range or advanced guesses and try again.')
            raise
        self.finish_fit(result)

    def start_fit(self):
        """Run only numerical work off the UI thread; apply results on the Tk thread."""
        from queue import Queue, Empty
        from threading import Thread
        if self.fit_busy: return
        args = self.prepare_fit()
        revision = self.analysis_revision
        parameter_snapshot = self.params.get()
        queue = Queue()
        self.fit_busy = True
        self.configure_context()
        self.status.set('Fitting… You can continue editing; changed analysis inputs discard this result.')

        def work():
            try:
                queue.put((fit_curve(*args), None))
            except Exception as exc:
                queue.put((None, str(exc)))

        def poll():
            try:
                result, error = queue.get_nowait()
            except Empty:
                self.root.after(50, poll)
                return
            self.fit_busy = False
            self.configure_context()
            try:
                changed = self.params.get() != parameter_snapshot
            except ValueError:
                changed = True
            if revision != self.analysis_revision or changed:
                self.status.set('Analysis inputs changed during fitting. Fit again with the current settings.')
                return
            if error:
                self.write_results(f'Fit failed: {error}\nAdjust the range or advanced guesses and try again.')
                self.status.set('Fit failed. See Results in Analysis; plotting and export remain available.')
                return
            self.guard(lambda: self.finish_fit(result))

        Thread(target=work, daemon=True).start()
        self.root.after(50, poll)

    def calculate(self):
        self.require_data()
        self.apply_time_offset()
        self.invalidate()
        if self.data.kind != 'g2' or self.get('mode') != 'Pulsed': raise ValueError('Choose a g2 measurement and Pulsed mode.')
        self.fit = None
        if not self.get('central'):
            raise ValueError('Select the central peak first: choose Central peak above the preview, then drag across it.')
        self.ratio = peak_ratio(self.data.x, self.data.y, json.loads(self.get('central')),
                                json.loads(self.get('sides')), self.number('background'))
        self.write_results(f"g²(0) = {self.ratio['g2_zero']:.4g}\n\nCentral area: {self.ratio['central_area']:.6g}\nMean side area: {np.mean(self.ratio['side_areas']):.6g}\nSide peaks: {len(self.ratio['side_areas'])}\nBins per window: {self.ratio['bins']}\nBackground per bin: {self.ratio['background']:.5g}")
        self.refresh()

    def clear_analysis(self, redraw=True):
        self.analysis_revision += 1
        self.fit = self.ratio = None
        self.comparisons = []
        self.write_results('No analysis yet. Choose a model and Fit, or select pulsed peaks and Calculate.')
        if redraw and self.data: self.guard(self.refresh)

    def clear_windows(self):
        self.vars['central'].set('')
        self.vars['sides'].set('[]')
        if self.data and self.data.kind == 'g2' and self.get('mode') == 'Pulsed':
            self.vars['selection'].set('Central peak')
        if self.data: self.guard(self.refresh)

    def export(self):
        self.require_data()
        self.apply_time_offset()
        self.invalidate()
        # A separate figure keeps GUI window resizing and navigation out of output geometry.
        fig, _ = publication_figure(self.data, self.style(), self.values(), self.fit)
        path = filedialog.asksaveasfilename(initialfile=Path(self.data.path).stem+'.pdf', defaultextension='.pdf',
                                          filetypes=[('PDF', '*.pdf'), ('SVG', '*.svg'), ('PNG', '*.png')])
        if path:
            save_figure(fig, path, self.number('dpi'), self.get('transparent'))
            self.status.set(f'Exported {path}')

    def record(self):
        baseline = None
        if self.data.kind == 'g2' and self.get('mode') == 'CW' and self.get('normalize'):
            _, baseline = normalize_cw(self.data.y, self.number('baseline', True))
        intensity_peak = None
        intensity_background = None
        if self.data.kind == 'Spectrum' and self.get('normalize_intensity'):
            _, intensity_background, intensity_peak = normalize_spectrum(self.data.y)
        elif self.peak_normalization_active():
            _, intensity_peak = normalize_intensity(self.data.y)
            intensity_background = 0.
        return dict(intensity_normalization_background=intensity_background, intensity_normalization_peak=intensity_peak, version=1, source=str(Path(self.data.path).resolve()), controls={k: v.get() for k, v in self.vars.items()},
                    parameter_editor=self.params.get('1.0', 'end').strip(), normalization_baseline=baseline,
                    fit=self.fit, peak_ratio=self.ratio)

    def export_data(self):
        self.require_data()
        self.apply_time_offset()
        self.invalidate()
        path = filedialog.asksaveasfilename(initialfile=Path(self.data.path).stem+'_publication.csv', defaultextension='.csv')
        if not path: return
        sidecar = Path(path).with_suffix('.json')
        if sidecar.exists() and not messagebox.askyesno('Replace analysis?', f'Replace existing analysis file {sidecar}?'): return
        if self.data.kind == 'PL':
            np.savetxt(path, self.values(), delimiter=',')
        else:
            x, y = self.data.x, self.values()
            predicted = np.full(len(x), np.nan)
            if self.fit:
                fn, names = MODELS[self.fit['model']]
                lo, hi = self.fit['limits']
                mask = (x >= lo) & (x <= hi)
                predicted[mask] = fn(x[mask]-self.fit['origin'], *[self.fit['parameters'][n] for n in names])
            np.savetxt(path, np.column_stack([x, self.data.y, y, predicted, y-predicted, self.raw_x]), delimiter=',',
                       header='x,raw_y,display_y,fit_y,residual,raw_x', comments='')
        sidecar.write_text(json.dumps(self.record(), indent=2))
        self.status.set(f'Exported {path} and {sidecar.name}')

    def save_session(self):
        self.require_data()
        self.apply_time_offset()
        self.invalidate()
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='publication_session.json')
        if path:
            Path(path).write_text(json.dumps(self.record(), indent=2))
            self.status.set(f'Saved session {path}')

    def load_session(self):
        path = filedialog.askopenfilename(filetypes=[('Session JSON', '*.json')])
        if not path: return
        record = json.loads(Path(path).read_text())
        if record.get('version') != 1: raise ValueError('Unsupported session version.')
        self.load(record['source'])
        self.loading = True
        try:
            for key, value in record['controls'].items():
                if key in self.vars: self.vars[key].set(value)
            self.params.delete('1.0', 'end')
            self.params.insert('1.0', record.get('parameter_editor', ''))
            self.applied_offset = self.number('time_offset')
            self.data.x = self.raw_x + self.applied_offset
        finally:
            self.loading = False
        self.configure_context()
        self.refresh()
        self.status.set('Session restored. Rerun Fit or Calculate to regenerate analysis.')


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='Single-file TCSPC fitting and publication export GUI')
    parser.add_argument('file', nargs='?', help='Optional measurement CSV')
    args = parser.parse_args(argv)
    import sys
    if sys.platform == 'darwin' and tk.TkVersion < 8.6:
        print(
            'The studio requires Tk 8.6 or newer on macOS. This Python uses '
            f'Tk {tk.TkVersion}, which can display a blank window.\n'
            'Use a Python distribution with modern Tk and recreate the virtual '
            'environment; installing packages into this environment cannot upgrade its Tk.\n'
            'If configured, launch: .venv-studio/bin/python scripts/studio.py\n'
            'See README.md: macOS blank window / deprecated system Tk.',
            file=sys.stderr,
        )
        return 1
    root = tk.Tk()
    Studio(root, args.file)
    root.mainloop()
    return 0
