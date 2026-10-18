"""Rebuild the local door/leak candidate from the fixed thermohygrometer DLL."""
from pathlib import Path

from build_aircon_library import build


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    build(root / 'custom_components/hwhomebridge/hilink_bridge/sensors/lib/amd64/libhilink_bridge.so',
          root / 'temp/rebuilt-contact-moisture.so',
          Path(__file__).with_name('contact-moisture-amd64-patch.json'))
    print('Door/leak candidate rebuilt and checksum verified in temp/')
