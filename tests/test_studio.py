"""Opt-in desktop smoke test: TCSPC_GUI_TESTS=1 python -m unittest tests.test_studio."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from tests import support


@unittest.skipUnless(os.environ.get('TCSPC_GUI_TESTS') == '1', 'requires a desktop Tk session')
class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.host = tk.Tk()
        cls.host.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.host.destroy()

    def test_load_fit_select_export_and_restore(self):
        import tkinter as tk
        from tcspc.studio import Studio
        from tcspc.publication import MODELS
        root = tk.Toplevel(self.host)
        root.deiconify()
        try:
            app = Studio(root)
            with tempfile.TemporaryDirectory() as folder:
                for writer in (support.write_lifetime, support.write_saturation, support.write_g2,
                               support.write_stability, support.write_spectrum, support.write_pl):
                    app.load(writer(folder))
                    root.update()
                x = np.linspace(-25, 25, 201)
                source = support.write_histogram(Path(folder)/support.g2_name(),
                                                100*MODELS['CW two-level'][0](x, .8, 3))
                app.load(source)
                app.vars['baseline'].set('100')
                app.reset_parameters()
                app.run_fit()
                self.assertAlmostEqual(app.fit['g2_zero'], .2, places=5)
                app.vars['model'].set('CW three-level (free g0)')
                app.reset_parameters()
                app.run_fit()
                self.assertEqual(len(app.comparisons), 2)
                app.vars['origin'].set('1')
                app.refresh()
                self.assertIsNone(app.fit)
                app.vars['mode'].set('Pulsed')
                self.assertEqual(app.get('ylabel'), 'Coincidences')
                app.vars['selection'].set('Central peak')
                app.select(-1, 1)
                app.vars['selection'].set('Add side peak')
                app.select(10, 12)
                app.calculate()
                self.assertIsNotNone(app.ratio)
                for suffix in ('svg', 'pdf', 'png'):
                    target = Path(folder)/f'figure.{suffix}'
                    with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(target)):
                        app.export()
                    self.assertGreater(target.stat().st_size, 1000)
                target = Path(folder)/'values.csv'
                with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(target)):
                    app.export_data()
                self.assertTrue(target.with_suffix('.json').exists())
                target = Path(folder)/'session.json'
                with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(target)):
                    app.save_session()
                app.vars['title'].set('Changed')
                with patch('tcspc.studio.filedialog.askopenfilename', return_value=str(target)):
                    app.load_session()
                self.assertEqual(app.get('title'), r'$g^{(2)}$ correlation')
                self.assertIsNone(app.ratio)
                app.calculate()
                self.assertIsNotNone(app.ratio)
        finally:
            root.update_idletasks()
            for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                root.unbind_all(event)
            root.destroy()

    def test_visible_layout_navigation_and_state(self):
        """Mapped widgets catch geometry bugs that withdrawn-window tests miss."""
        import tkinter as tk
        from types import SimpleNamespace
        from tcspc.studio import Studio
        root = tk.Toplevel(self.host)
        try:
            app = Studio(root)
            root.geometry('1100x760')
            root.update()
            with tempfile.TemporaryDirectory() as folder:
                app.load(support.write_g2(folder, n=201))
                app.notebook.select(1)
                root.update()
                self.assertTrue(app.action_button.winfo_ismapped())
                self.assertTrue(app.fit_group.winfo_ismapped())
                self.assertFalse(app.pulsed_group.winfo_ismapped())
                self.assertFalse(app.advanced.winfo_ismapped())
                self.assertFalse(app.selector.active)
                # All main actions are above the plot and inside the window.
                self.assertLess(app.action_button.winfo_rooty()+app.action_button.winfo_height(),
                                root.winfo_rooty()+root.winfo_height())
                widget = app.canvas.get_tk_widget()
                size = (widget.winfo_width(), widget.winfo_height())
                app.refresh()
                root.update()
                self.assertEqual(size, (widget.winfo_width(), widget.winfo_height()))
                self.assertAlmostEqual(app.figure.bbox.width, widget.winfo_width(), delta=2)
                self.assertAlmostEqual(app.figure.bbox.height, widget.winfo_height(), delta=2)
                app.ax.set_xlim(-5, 5)
                app.refresh()
                np.testing.assert_allclose(app.ax.get_xlim(), [-5, 5])
                app.use_zoom()
                np.testing.assert_allclose(app.style().xlim, [-5, 5])
                app.reset_crop()
                self.assertLess(app.ax.get_xlim()[0], -5)
                self.assertIsNone(app.style().xlim)
                app.vars['mode'].set('Pulsed')
                app.mode_changed()
                root.update()
                self.assertFalse(app.fit_group.winfo_ismapped())
                self.assertTrue(app.pulsed_group.winfo_ismapped())
                self.assertEqual(app.get('selection'), 'Central peak')
                app.select(-1, 1)
                self.assertEqual(app.get('selection'), 'Add side peak')
                app.select(9, 11)
                before = app.get('sides')
                with self.assertRaisesRegex(ValueError, 'overlaps'):
                    app.select(9, 11)
                self.assertEqual(app.get('sides'), before)
                self.assertEqual(app.peak_list.size(), 2)
                app.peak_list.selection_set(1)
                app.remove_peak()
                self.assertEqual(app.get('sides'), '[]')
                app.vars['selection'].set('Central peak')
                with self.assertRaisesRegex(ValueError, 'two histogram bins'):
                    app.select(0, .01)
                app.load(support.write_spectrum(folder))
                app.notebook.select(1)
                root.update()
                self.assertFalse(app.fit_group.winfo_ismapped())
                self.assertTrue(app.action_button.instate(['disabled']))
                self.assertFalse(app.widgets['show_g0'].winfo_ismapped())
                # Scrolling works while the pointer is over an entry, not just the scrollbar.
                app.notebook.select(2)
                root.update()
                app.scroll_canvases[2].yview_moveto(0)
                before = app.scroll_canvases[2].yview()[0]
                app.scroll_controls(SimpleNamespace(widget=app.widgets['font'], delta=-3, num=None))
                self.assertGreater(app.scroll_canvases[2].yview()[0], before)
        finally:
            root.update_idletasks()
            for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                root.unbind_all(event)
            root.destroy()

    def test_background_fit_keeps_ui_responsive_and_discards_stale_result(self):
        import tkinter as tk
        import time
        from threading import Event
        from tcspc.studio import Studio
        from tcspc.publication import fit_curve as real_fit, MODELS
        root = tk.Toplevel(self.host)
        root.deiconify()
        release = Event()
        try:
            app = Studio(root)
            with tempfile.TemporaryDirectory() as folder:
                x = np.linspace(-25, 25, 201)
                path = support.write_histogram(Path(folder)/support.g2_name(),
                                               100*MODELS['CW two-level'][0](x, .8, 3))
                app.load(path)
                app.vars['baseline'].set('100')
                app.reset_parameters()

                def slow_fit(*args):
                    if not release.wait(5):
                        raise RuntimeError('Test worker timed out')
                    return real_fit(*args)

                def wait_for_fit():
                    deadline = time.monotonic()+5
                    while app.fit_busy and time.monotonic() < deadline:
                        root.update()
                        time.sleep(.01)
                    self.assertFalse(app.fit_busy)

                with patch('tcspc.studio.fit_curve', side_effect=slow_fit):
                    app.start_fit()
                    self.assertTrue(app.fit_busy)
                    tick = []
                    root.after(0, lambda: tick.append(True))
                    root.update()
                    self.assertEqual(tick, [True])
                    app.vars['origin'].set('1')
                    release.set()
                    wait_for_fit()
                    self.assertIsNone(app.fit)
                    self.assertIn('changed during fitting', app.status.get())
                app.vars['origin'].set('0')
                app.start_fit()
                wait_for_fit()
                self.assertAlmostEqual(app.fit['g2_zero'], .2, places=5)
                app.vars['model'].set('CW three-level (free g0)')
                self.assertIsNone(app.fit)
                app.model_changed()
                with patch('tcspc.studio.fit_curve', side_effect=ValueError('synthetic fit failure')):
                    app.start_fit()
                    wait_for_fit()
                self.assertIn('synthetic fit failure', app.results.get('1.0', 'end'))
                self.assertFalse(app.action_button.instate(['disabled']))
        finally:
            release.set()
            root.update_idletasks()
            for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                root.unbind_all(event)
            root.destroy()

    def test_offset_preserves_peak_bins_and_export_layout(self):
        import tkinter as tk
        import json
        from PIL import Image
        from tcspc.studio import Studio
        root = tk.Toplevel(self.host)
        try:
            app = Studio(root)
            with tempfile.TemporaryDirectory() as folder:
                app.load(support.write_g2(folder, n=201))
                app.vars['mode'].set('Pulsed')
                app.mode_changed()
                app.select(-1, 1)
                app.select(9, 11)
                app.calculate()
                original = app.ratio.copy()
                for offset in ('-3.2', '1.37', '0'):
                    app.vars['time_offset'].set(offset)
                    app.refresh()
                    app.calculate()
                    self.assertEqual(app.ratio['bins'], original['bins'])
                    self.assertEqual(app.ratio['g2_zero'], original['g2_zero'])
                raw_x = app.data.x.copy()
                central = json.loads(app.get('central'))
                app.vars['time_offset'].set('-3.25')
                app.refresh()
                np.testing.assert_allclose(app.data.x, raw_x-3.25)
                np.testing.assert_allclose(json.loads(app.get('central')), np.array(central)-3.25)
                app.calculate()
                self.assertEqual(app.ratio['g2_zero'], original['g2_zero'])
                self.assertEqual(app.ratio['bins'], original['bins'])
                app.vars['title'].set(r'$g^{(2)}(\tau)$ and $I_0$')
                app.notebook.select(3)
                root.update()
                self.assertTrue(app.export_frame.winfo_ismapped())
                self.assertFalse(app.canvas.get_tk_widget().winfo_ismapped())
                np.testing.assert_allclose(app.export_figure.get_size_inches(), [3.5, 2.8])
                image_shape = app.export_image.size
                axes_before = app.export_figure.axes[0].get_position().bounds
                root.geometry('1300x850')
                root.update()
                self.assertEqual(app.export_image.size, image_shape)
                np.testing.assert_allclose(app.export_figure.axes[0].get_position().bounds, axes_before)
                app.vars['fontsize'].set('11')
                app.vars['labelpad'].set('8')
                app.vars['width'].set('4')
                app.refresh()
                app.vars['dpi'].set('150')
                target = Path(folder)/'exact.png'
                preview_pixels = np.asarray(app.export_image).copy()
                with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(target)):
                    app.export()
                np.testing.assert_array_equal(np.asarray(Image.open(target)), preview_pixels)
                session = Path(folder)/'offset-session.json'
                with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(session)):
                    app.save_session()
                with patch('tcspc.studio.filedialog.askopenfilename', return_value=str(session)):
                    app.load_session()
                np.testing.assert_allclose(app.data.x, raw_x-3.25)
                app.calculate()
                self.assertEqual(app.ratio['g2_zero'], original['g2_zero'])
                app.vars['time_offset'].set('0')
                app.refresh()
                np.testing.assert_allclose(app.data.x, raw_x)
        finally:
            root.update_idletasks()
            for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                root.unbind_all(event)
            root.destroy()

    def test_intensity_controls_exports_and_session(self):
        import tkinter as tk
        from tcspc.studio import Studio
        root = tk.Toplevel(self.host)
        try:
            app = Studio(root)
            with tempfile.TemporaryDirectory() as folder:
                for writer in (support.write_spectrum, support.write_pl):
                    app.load(writer(folder))
                    raw = app.data.y.copy()
                    expected = (raw-raw.min())/(raw.max()-raw.min()) if app.data.kind == 'Spectrum' else raw/raw.max()
                    app.vars['normalize_intensity'].set(True)
                    app.vars['annotation'].set('Peak')
                    app.vars['annotation_color'].set('#cc2244')
                    app.refresh()
                    np.testing.assert_allclose(app.values(), expected)
                    np.testing.assert_array_equal(app.data.y, raw)
                    key = 'colorbar' if app.data.kind == 'PL' else 'ylabel'
                    self.assertEqual(app.get(key), 'Normalized intensity')
                    self.assertEqual(app.ax.texts[0].get_color(), '#cc2244')
                    if app.data.kind == 'Spectrum':
                        np.testing.assert_array_equal(app.ax.get_yticks(), [0, 1])
                        self.assertEqual(app.record()['intensity_normalization_background'], raw.min())
                    target = Path(folder)/'intensity-session.json'
                    with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(target)):
                        app.save_session()
                    with patch('tcspc.studio.filedialog.askopenfilename', return_value=str(target)):
                        app.load_session()
                    self.assertTrue(app.get('normalize_intensity'))
                    self.assertEqual(app.get('annotation_color'), '#cc2244')
                    np.testing.assert_allclose(app.values(), expected)
                    if app.data.kind == 'PL':
                        target = Path(folder)/'map.csv'
                        with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(target)):
                            app.export_data()
                        np.testing.assert_allclose(np.loadtxt(target, delimiter=','), raw/np.max(raw))
                    app.vars['normalize_intensity'].set(False)
                    app.refresh()
                    np.testing.assert_array_equal(app.values(), raw)
                    self.assertEqual(app.get(key), 'Intensity (a.u.)')
        finally:
            root.update_idletasks()
            for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                root.unbind_all(event)
            root.destroy()

    def test_pulsed_and_lifetime_normalization(self):
        import tkinter as tk
        from tcspc.studio import Studio
        root = tk.Toplevel(self.host)
        try:
            app = Studio(root)
            with tempfile.TemporaryDirectory() as folder:
                app.load(support.write_g2(folder, n=201))
                app.vars['mode'].set('Pulsed')
                app.mode_changed()
                app.select(-1, 1)
                app.select(9, 11)
                app.calculate()
                original_ratio = app.ratio.copy()
                raw = app.data.y.copy()
                app.vars['normalize_intensity'].set(True)
                app.refresh()
                np.testing.assert_allclose(app.values(), raw/raw.max())
                self.assertEqual(app.ratio, original_ratio)
                self.assertEqual(app.get('ylabel'), 'Normalized coincidences')
                app.calculate()
                self.assertEqual(app.ratio, original_ratio)
                self.assertEqual(app.record()['intensity_normalization_peak'], raw.max())
                target = Path(folder)/'pulsed.csv'
                with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(target)):
                    app.export_data()
                exported = np.loadtxt(target, delimiter=',', skiprows=1)
                np.testing.assert_array_equal(exported[:, 1], raw)
                np.testing.assert_allclose(exported[:, 2], raw/raw.max())
                app.vars['mode'].set('CW')
                app.mode_changed()
                from tcspc.publication import normalize_cw
                np.testing.assert_allclose(app.values(), normalize_cw(raw)[0])
                app.vars['mode'].set('Pulsed')
                app.mode_changed()
                np.testing.assert_allclose(app.values(), raw/raw.max())

                x = np.linspace(0, 50, 201)
                raw = 900*np.exp(-x/6)+8
                path = support.write_histogram(Path(folder)/support.lifetime_name(), raw)
                app.load(path)
                raw = app.data.y.copy()  # Compare against parsed values after CSV round-tripping.
                app.run_fit()
                original_tau = app.fit['parameters']['tau']
                app.vars['normalize_intensity'].set(True)
                self.assertIsNone(app.fit)
                app.refresh()
                app.run_fit()
                self.assertAlmostEqual(app.fit['parameters']['tau'], original_tau, places=5)
                self.assertAlmostEqual(app.fit['parameters']['B'], 8/raw.max(), places=6)
                np.testing.assert_allclose(app.values(), raw/raw.max())
                self.assertEqual(app.get('yscale'), 'log')
                self.assertEqual(app.get('ylabel'), 'Normalized intensity')
                session = Path(folder)/'lifetime-session.json'
                with patch('tcspc.studio.filedialog.asksaveasfilename', return_value=str(session)):
                    app.save_session()
                with patch('tcspc.studio.filedialog.askopenfilename', return_value=str(session)):
                    app.load_session()
                np.testing.assert_allclose(app.values(), raw/raw.max())
                app.vars['normalize_intensity'].set(False)
                self.assertEqual(app.get('ylabel'), 'Counts')
                np.testing.assert_array_equal(app.values(), raw)
        finally:
            root.update_idletasks()
            for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                root.unbind_all(event)
            root.destroy()
