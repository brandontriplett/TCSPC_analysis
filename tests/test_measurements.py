import tempfile
import unittest
from pathlib import Path

from tcspc.measurements import LifetimeMeasurement, StabilityMeasurement, histogram_axis
from tcspc.parsers import FilenameParser

from tests.support import lifetime_name, write_histogram, write_stability


class HistogramLoadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_single_row_histogram_becomes_a_column(self):
        n = 15
        path = write_histogram(self.folder / lifetime_name(), list(range(n)))
        meta = FilenameParser.parse(str(path))
        meas = LifetimeMeasurement(meta)
        meas.load()
        self.assertIsNotNone(meas.data)
        counts = meas.data.iloc[:, 0].values
        self.assertEqual(len(counts), n)
        # iloc[0] is a single row (one bin) — this is the indexing bug batch used to hit
        self.assertEqual(len(meas.data.iloc[0]), 1)

    def test_histogram_axis_lifetime_and_g2(self):
        path = write_histogram(self.folder / lifetime_name(), [1, 2, 3, 4])
        meta = FilenameParser.parse(str(path))
        x = histogram_axis(meta, 4, centered=False)
        self.assertAlmostEqual(x[0], 0.0)
        self.assertAlmostEqual(x[-1], 50.0)
        xc = histogram_axis(meta, 4, centered=True)
        self.assertAlmostEqual(xc[0], -25.0)
        self.assertAlmostEqual(xc[-1], 25.0)

    def test_stability_series_drops_first_five(self):
        n = 20
        path = write_stability(self.folder, n=n)
        meta = FilenameParser.parse(str(path))
        meas = StabilityMeasurement(meta)
        time, counts, power = meas.series()
        self.assertEqual(len(time), n - 5)
        self.assertEqual(len(counts), n - 5)
        self.assertEqual(len(power), n - 5)


if __name__ == "__main__":
    unittest.main()
