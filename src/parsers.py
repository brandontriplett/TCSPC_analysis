import re
from pathlib import Path
from dataclasses import dataclass

@dataclass
class MeasurementMetadata:
    """Standardized container for all measurement metadata."""
    type: str
    filepath: str
    x: float = 0.0
    y: float = 0.0
    power: float = float('nan')
    nd: float = float('nan')
    filter: str = "None"
    integration_time: float = float('nan')
    tac_range: float = float('nan')
    gain: float = float('nan')
    bin_width: float = float('nan')
    scan_size: float = float('nan')
    mesh_step: float = float('nan')

class FilenameParser:
    """
    Traffic controller for TCSPC filenames.
    Detects the measurement type and extracts parameters using Regex.
    """
    
    PATTERNS = {
        'PL': re.compile(
            r"^PL_X(?P<x>[\d.]*)_Y(?P<y>[\d.]*)_ND(?P<nd>[\d.]*)_Pow(?P<power>[\d.]*)_"
            r"Filter(?P<filter>[^_]+)_Size(?P<size>[\d.]*)_Mesh(?P<mesh>[\d.]*)"
        ),
        
        'Lifetime': re.compile(
            r"^Lifetime_X(?P<x>[\d.]*)_Y(?P<y>[\d.]*)_ND(?P<nd>[\d.]*)_Pow(?P<power>[\d.]*)_"
            r"Filter(?P<filter>[^_]+)_Int(?P<int>[\d.]*)_TAC(?P<tac>[\d.]*)_Gain(?P<gain>[\d.]*)_Bin(?P<bin>[\d.]*)"
        ),
        
        'g2': re.compile(
            r"^g2_X(?P<x>[\d.]*)_Y(?P<y>[\d.]*)_ND(?P<nd>[\d.]*)_Pow(?P<power>[\d.]*)_"
            r"Filter(?P<filter>[^_]+)_Int(?P<int>[\d.]*)_TAC(?P<tac>[\d.]*)_Gain(?P<gain>[\d.]*)_Bin(?P<bin>[\d.]*)"
        ),

        'Spectrum': re.compile(
            r"^Spectrum_X(?P<x>[\d.]*)_Y(?P<y>[\d.]*)_ND(?P<nd>[\d.]*)_"
            r"Pow(?P<power>[\d.]*)_Int(?P<int>[\d.]*)"
        ),

        'Stability': re.compile(
            r"^Stability_X(?P<x>[\d.]*)_Y(?P<y>[\d.]*)_ND(?P<nd>[\d.]*)_"
            r"Pow(?P<power>[\d.]*)_Filter(?P<filter>[^_]+)"
        ),

        'Saturation': re.compile(
            r"^Saturation_X(?P<x>[\d.]*)_Y(?P<y>[\d.]*)_Filter(?P<filter>[^_]+)"
        )
    }

    @staticmethod
    def parse(filepath: str):
        path_obj = Path(filepath)
        filename = path_obj.stem
        parts = filename.split('_')
        
        if not parts: return None
        meas_type = parts[0]

        if meas_type not in FilenameParser.PATTERNS:
            return None

        match = FilenameParser.PATTERNS[meas_type].match(filename)
        if not match: return None

        raw_dict = match.groupdict()

        try:
            return MeasurementMetadata(
                type=meas_type,
                filepath=str(path_obj),
                x=float(raw_dict.get('x', 0)),
                y=float(raw_dict.get('y', 0)),
                power=float(raw_dict.get('power', float('nan'))),
                nd=float(raw_dict.get('nd', float('nan'))),
                filter=raw_dict.get('filter', 'None'),
                integration_time=float(raw_dict.get('int', float('nan'))),
                tac_range=float(raw_dict.get('tac', float('nan'))),
                gain=float(raw_dict.get('gain', float('nan'))),
                bin_width=float(raw_dict.get('bin', float('nan'))),
                scan_size=float(raw_dict.get('size', float('nan'))),
                mesh_step=float(raw_dict.get('mesh', float('nan')))
            )
        except ValueError:
            return None