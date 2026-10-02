"""Stitch PL map tiles onto a common stage grid (used by the explorer)."""

import numpy as np
import pandas as pd


def stitch_pl_maps(pl_measurements):
    """Return ``(x, y, z)`` for a stitched heatmap, or ``(None, None, None)``.

    ``z`` uses NaN for gaps. Pixel size is taken from the first usable tile.
    """
    usable = []
    for meas in pl_measurements:
        if meas.data is None:
            continue
        if meas.meta.scan_size is None or pd.isna(meas.meta.scan_size):
            continue
        if meas.data.size == 0:
            continue
        usable.append(meas)
    if not usable:
        return None, None, None

    ref = usable[0]
    ny, nx = ref.data.shape
    if nx == 0 or ny == 0:
        return None, None, None

    pixel_width = ref.meta.scan_size / nx
    pixel_height = ref.meta.scan_size / ny

    min_x = min(m.meta.x - m.meta.scan_size / 2 for m in usable)
    max_x = max(m.meta.x + m.meta.scan_size / 2 for m in usable)
    min_y = min(m.meta.y - m.meta.scan_size / 2 for m in usable)
    max_y = max(m.meta.y + m.meta.scan_size / 2 for m in usable)

    global_nx = int(np.ceil((max_x - min_x) / pixel_width))
    global_ny = int(np.ceil((max_y - min_y) / pixel_height))
    if global_nx <= 0 or global_ny <= 0:
        return None, None, None

    master_z = np.full((global_ny, global_nx), np.nan)
    for meas in usable:
        data = meas.data.values
        start_x = int(np.round((meas.meta.x - meas.meta.scan_size / 2 - min_x) / pixel_width))
        start_y = int(np.round((meas.meta.y - meas.meta.scan_size / 2 - min_y) / pixel_height))
        end_y = min(start_y + data.shape[0], global_ny)
        end_x = min(start_x + data.shape[1], global_nx)
        if start_x < 0 or start_y < 0:
            continue
        slice_y = end_y - start_y
        slice_x = end_x - start_x
        if slice_y <= 0 or slice_x <= 0:
            continue
        master_z[start_y:end_y, start_x:end_x] = data[0:slice_y, 0:slice_x]

    master_x = np.linspace(min_x, max_x, global_nx)
    master_y = np.linspace(min_y, max_y, global_ny)
    return master_x, master_y, master_z
