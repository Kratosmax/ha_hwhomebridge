"""Rebuild the fixed amd64 113D candidate from the working aircon library."""
from pathlib import Path

from build_aircon_library import build


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    build(root / 'custom_components/hwhomebridge/hilink_bridge/aircon/lib/amd64/libhilink_bridge.so',
          root / 'temp/rebuilt-thermohygrometer.so',
          Path(__file__).with_name('thermohygrometer-amd64-patch.json'))
    print('Thermohygrometer candidate rebuilt and checksum verified in temp/')
