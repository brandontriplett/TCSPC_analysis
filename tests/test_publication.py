"""Scientific recovery, invalid inputs, loading, and publication export checks."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from tcspc.publication import (MODELS, Dataset, Style, fit_curve, normalize_cw,
                               peak_ratio, render, save_figure, load_dataset, publication_figure, normalize_intensity, normalize_spectrum)
from tests import support


class PublicationTests(unittest.TestCase):
    def test_model_recovery(self):
        cases = [
            ('CW two-level', [-50, 50], [.8, 3.]),
            ('CW three-level (ideal)', [-100, 100], [.4, 3., 25.]),
            ('CW three-level (free g0)', [-100, 100], [.2, .4, 3., 25.]),
            ('Lifetime single', [0, 50], [900., 6., 8.]),
            ('Lifetime double', [0, 80], [700., 3., 200., 15., 8.]),
            ('Saturation', [0, 100], [1000., 20.]),
            ('Saturation + background', [0, 100], [1000., 20., 8., 2.]),
        ]
        for model, limits, parameters in cases:
            with self.subTest(model=model):
                x = np.linspace(*limits, 501)
                fn, names = MODELS[model]
                y = fn(x, *parameters)
                result = fit_curve(x, y, model)
                np.testing.assert_allclose(fn(x, *result['parameters'].values()), y, atol=1e-4)
                self.assertLess(result['rmse'], 1e-4)
                if model.startswith('CW'):
                    self.assertAlmostEqual(result['g2_zero'], fn(0., *parameters), places=5)

    def test_origin_and_fit_range(self):
        x = np.linspace(0, 60, 601)
        y = 500*np.exp(-(x-10)/7)+3
        y[x < 10] = 10000
        result = fit_curve(x, y, 'Lifetime single', (10, 60), origin=10)
        self.assertAlmostEqual(result['parameters']['tau'], 7., places=5)
        with self.assertRaises(ValueError):
            fit_curve(x, y, 'Lifetime single', (0, 60), origin=10)
        with self.assertRaises(ValueError):
            fit_curve(x[:2], y[:2], 'Lifetime single')

    def test_normalization(self):
        y, baseline = normalize_cw(np.array([10., 10., 2., 10., 10.]))
        self.assertEqual(baseline, 10)
        self.assertEqual(y[2], .2)
        with self.assertRaises(ValueError): normalize_cw(np.zeros(10))

    def test_peak_counts_and_background(self):
        x = np.arange(-10, 11, dtype=float)
        y = np.ones(len(x))
        y[(x >= -1) & (x <= 1)] += 2
        y[(x >= -7) & (x <= -5)] += 10
        y[(x >= 5) & (x <= 7)] += 6
        r = peak_ratio(x, y, (-1, 1), [(-7, -5), (5, 7)], 1)
        self.assertEqual(r['g2_zero'], .25)
        for sides in ([], [(-1, 1)], [(5, 8)]):
            with self.assertRaises(ValueError): peak_ratio(x, y, (-1, 1), sides)
        with self.assertRaises(ValueError): peak_ratio(x*x, y, (-1, 1), [(5, 7)])
        with self.assertRaises(ValueError): peak_ratio(x, y, (-1, 1), [(5, 7)], 100)

    def test_load_all_types_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            for writer in (support.write_lifetime, support.write_g2, support.write_spectrum,
                           support.write_saturation, support.write_stability, support.write_pl):
                data = load_dataset(writer(folder))
                style = Style(xlabel=data.xlabel, ylabel=data.ylabel, title=data.title)
                fig, ax = render(data, style)
                for suffix in ('svg', 'pdf', 'png'):
                    dest = Path(folder)/f'{data.kind}.{suffix}'
                    save_figure(fig, dest, dpi=100)
                    self.assertGreater(dest.stat().st_size, 1000)
                svg = (Path(folder)/f'{data.kind}.svg').read_text()
                self.assertIn('<text', svg)
                self.assertIn('width="252pt"', svg)

    def test_overlay_is_optional(self):
        x = np.linspace(-20, 20, 101)
        y = MODELS['CW two-level'][0](x, .8, 3)
        data = Dataset('synthetic', 'g2', x, y, 'Delay', 'g²', '')
        fit = fit_curve(x, y, 'CW two-level')
        fig, ax = render(data, Style(show_fit=False, residuals=True), fit=fit)
        self.assertEqual(len(ax.lines), 1)
        self.assertEqual(len(fig.axes), 1)
        fig, ax = render(data, Style(residuals=True), fit=fit)
        self.assertEqual(len(ax.lines), 2)
        self.assertEqual(len(fig.axes), 2)

    def test_publication_layout_is_frozen_across_formats(self):
        x = np.linspace(-20, 20, 101)
        y = MODELS['CW two-level'][0](x, .8, 3)
        data = Dataset('synthetic', 'g2', x, y, 'Delay', 'g²', '')
        style = Style(title=r'$g^{(2)}(\tau)$', xlabel=r'$\tau$ (ns)',
                      ylabel=r'$I_0$', width=4., height=3., labelpad=8., titlepad=10.)
        figure, ax = publication_figure(data, style)
        initial = ax.get_position().bounds
        with tempfile.TemporaryDirectory() as folder:
            for extension in ('pdf', 'svg', 'png'):
                save_figure(figure, Path(folder)/f'plot.{extension}', dpi=300)
                np.testing.assert_allclose(ax.get_position().bounds, initial)
                np.testing.assert_allclose(figure.get_size_inches(), [4., 3.])

    def test_normalized_intensity_and_annotation_color(self):
        raw = np.array([[0., 2.], [4., np.nan]])
        normalized, peak = normalize_intensity(raw)
        self.assertEqual(peak, 4.)
        np.testing.assert_allclose(normalized, [[0., .5], [1., np.nan]])
        np.testing.assert_array_equal(normalize_intensity(np.zeros(3))[0], np.zeros(3))
        for invalid in ([-2., -1.], [np.nan]):
            with self.assertRaises(ValueError): normalize_intensity(invalid)
        data = Dataset('map', 'PL', np.array([]), raw, 'X', 'Y', '')
        style = Style(annotation='g²(0) = 0.2', annotation_color='white', colorbar='Normalized intensity')
        fig, ax = publication_figure(data, style, y=normalized)
        np.testing.assert_allclose(ax.images[0].get_array().filled(np.nan), normalized)
        self.assertEqual(ax.texts[0].get_color(), 'white')
        self.assertEqual(fig.axes[1].get_ylabel(), 'Normalized intensity')

    def test_spectrum_background_and_ticks(self):
        values, background, scale = normalize_spectrum([10., 15., 30.])
        np.testing.assert_allclose(values, [0., .25, 1.])
        self.assertEqual((background, scale), (10., 20.))
        np.testing.assert_array_equal(normalize_spectrum([5., 5.])[0], [0., 0.])
        np.testing.assert_array_equal(normalize_spectrum([-5., -3.])[0], [0., 1.])
        data = Dataset('spectrum', 'Spectrum', np.arange(3), np.array([10., 15., 30.]), 'Wavelength', 'Intensity', '')
        fig, ax = publication_figure(data, Style(normalized_spectrum=True), y=values)
        np.testing.assert_array_equal(ax.get_yticks(), [0., 1.])
        self.assertEqual([tick.get_text() for tick in ax.get_yticklabels()], ['0', '1'])
        self.assertEqual(len(ax.get_yticks(minor=True)), 0)


if __name__ == '__main__':
    unittest.main()
