import tempfile
import unittest

from tcspc.maps import stitch_pl_maps
from tcspc.measurements import PLMapMeasurement
from tcspc.parsers import FilenameParser
from tcspc.plotting import format_plot_labels
from tests.support import write_pl, write_spectrum


class StitchTests(unittest.TestCase):
    def test_single_tile_has_expected_extent(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_pl(tmp.name, x="10.0", y="20.0")
        meta = FilenameParser.parse(str(path))
        meas = PLMapMeasurement(meta)
        meas.load()
        x, y, z = stitch_pl_maps([meas])
        self.assertIsNotNone(z)
        self.assertEqual(z.shape, meas.data.shape)
        self.assertAlmostEqual(x[0], 0.0)   # 10 - 20/2
        self.assertAlmostEqual(x[-1], 20.0)
        self.assertAlmostEqual(y[0], 10.0)  # 20 - 20/2
        self.assertAlmostEqual(y[-1], 30.0)

    def test_empty_input(self):
        self.assertEqual(stitch_pl_maps([]), (None, None, None))


class LabelTests(unittest.TestCase):
    def test_html_subtitle_is_opt_in(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = write_spectrum(tmp.name)
        meta = FilenameParser.parse(str(path))
        plain, _ = format_plot_labels([meta], "Spectrum", 10.0, 20.0)
        html, _ = format_plot_labels([meta], "Spectrum", 10.0, 20.0, html=True)
        self.assertIn("\n", plain)
        self.assertNotIn("<br>", plain)
        self.assertIn("<br><sup>", html)
        self.assertNotIn("\n", html)


if __name__ == "__main__":
    unittest.main()
