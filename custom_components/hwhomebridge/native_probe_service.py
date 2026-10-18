"""Run a fixed, network-isolated metadata probe outside the active SDK process."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import uuid


def async_register(hass):
    from homeassistant.core import SupportsResponse

    lock = asyncio.Lock()

    async def validate_socket(call):
        if lock.locked():
            return {'success': False, 'error_type': 'ProbeBusy'}
        async with lock:
            folder = Path(hass.config.path('temp', 'hwhomebridge-native-probe'))
            component = Path(__file__).parent
            plan = component / 'hilink_bridge/plans/socket.json'
            script = component / 'native_metadata_probe.py'
            nonce = uuid.uuid4().hex
            result_path = folder / ('result-' + nonce + '.json')
            if not plan.is_file() or not script.is_file():
                return {'success': False, 'error_type': 'ProbeNotStaged'}
            def run():
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                    process = subprocess.run([sys.executable, str(script), '--plan', str(plan),
                        '--result', str(result_path), '--nonce', nonce],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
                    result = json.loads(result_path.read_text(encoding='utf-8'))
                    if result.get('nonce') != nonce or process.returncode != 0:
                        return {'success': False, 'probe_result': result}
                    return result
                except Exception as exc:
                    return {'success': False, 'error_type': type(exc).__name__}
            return await hass.async_add_executor_job(run)

    hass.services.async_register('hwhomebridge', 'socket_validate_metadata', validate_socket,
                                 supports_response=SupportsResponse.ONLY)
