"""Tiny synthetic CSVs whose names match src.parsers patterns."""

from pathlib import Path


def spectrum_name(x="10.0", y="20.0") -> str:
    return f"Spectrum_X{x}_Y{y}_ND0.5_Pow10_Int5.csv"


def lifetime_name(x="10.0", y="20.0") -> str:
    return f"Lifetime_X{x}_Y{y}_ND0.5_Pow10_FilterNone_Int30_TAC50_Gain1_Bin0.1.csv"


def g2_name(x="10.0", y="20.0") -> str:
    return f"g2_X{x}_Y{y}_ND0.5_Pow10_FilterNone_Int30_TAC50_Gain1_Bin0.1.csv"


def stability_name(x="10.0", y="20.0") -> str:
    return f"Stability_X{x}_Y{y}_ND0.5_Pow10_FilterNone_Int30.csv"


def saturation_name(x="10.0", y="20.0") -> str:
    return f"Saturation_X{x}_Y{y}_FilterNone.csv"


def pl_name(x="10.0", y="20.0") -> str:
    return f"PL_X{x}_Y{y}_ND0.5_Pow10_FilterNone_Size20_Mesh0.5.csv"


def write_tsv(path, rows):
    path = Path(path)
    lines = ["\t".join(str(c) for c in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


def write_histogram(path, values):
    path = Path(path)
    path.write_text("\t".join(str(v) for v in values) + "\n")
    return path


def write_spectrum(folder, x="10.0", y="20.0"):
    path = Path(folder) / spectrum_name(x, y)
    return write_tsv(path, [(500.0, 1.0), (510.0, 2.0), (520.0, 1.5)])


def write_lifetime(folder, x="10.0", y="20.0", n=20):
    path = Path(folder) / lifetime_name(x, y)
    # decaying-ish counts so a fit has something to chew on
    values = [max(1, int(1000 * (0.8 ** i))) for i in range(n)]
    return write_histogram(path, values)


def write_g2(folder, x="10.0", y="20.0", n=40):
    path = Path(folder) / g2_name(x, y)
    mid = n // 2
    values = [10 if abs(i - mid) > 2 else 2 for i in range(n)]
    return write_histogram(path, values)


def write_stability(folder, x="10.0", y="20.0", n=20):
    path = Path(folder) / stability_name(x, y)
    rows = [(5.0 + 0.01 * i, 100 + i) for i in range(n)]
    return write_tsv(path, rows)


def write_saturation(folder, x="10.0", y="20.0"):
    path = Path(folder) / saturation_name(x, y)
    return write_tsv(path, [(0.1, 0, 10), (0.2, 0, 20), (0.3, 0, 25)])


def write_pl(folder, x="10.0", y="20.0"):
    path = Path(folder) / pl_name(x, y)
    return write_tsv(path, [(1, 2, 3), (4, 5, 6), (7, 8, 9)])
