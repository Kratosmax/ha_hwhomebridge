"""Resource regressions without HA, networking, or an actual SDK."""
import ast
import concurrent.futures
import importlib.util
from pathlib import Path
import threading
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/hwhomebridge'


class ResourceAuditTests(unittest.TestCase):
    def test_full_sync_visits_each_entity_once_including_shared_services(self):
        tree = ast.parse((COMPONENT / 'service_router.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ServiceRouter')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'sync_device_state')
        calls = []
        scope = {'VirtualDevice': object}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'sync-audit', 'exec'), scope)
        state = object()
        router = types.SimpleNamespace(_hass=types.SimpleNamespace(states=types.SimpleNamespace(get=lambda e: state)),
            report_state=lambda sn, entity, value: calls.append((sn, entity, value)))
        device = types.SimpleNamespace(sn='test', service_entries={
            name: types.SimpleNamespace(entity_id=entity) for name, entity in
            [('switch', 'climate.test'), ('mode', 'climate.test'),
             ('fan', 'climate.test'), ('temperature', 'climate.test'), ('battery', 'sensor.test')]})
        scope['sync_device_state'](router, device)
        self.assertEqual(calls, [('test', 'climate.test', state), ('test', 'sensor.test', state)])

    def test_queue_count_includes_waiting_cancelled_failed_and_rejected_jobs(self):
        spec = importlib.util.spec_from_file_location('native_resource_audit', COMPONENT / 'native_async.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        started, release = threading.Event(), threading.Event()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        def block():
            started.set()
            release.wait(5)
        try:
            first = module._submit(executor, block, (), {})
            self.assertTrue(started.wait(2))
            second = module._submit(executor, lambda: None, (), {})
            self.assertEqual(module._pending_count, 2)
            self.assertEqual(module.queue_diagnostics()['pending'], 2)
            self.assertTrue(second.cancel())
            self.assertEqual(module._pending_count, 1)
            release.set()
            first.result(2)
            def fail():
                raise ValueError('test')
            with self.assertRaises(ValueError):
                module._submit(executor, fail, (), {}).result(2)
            self.assertEqual(module._pending_count, 0)
            executor.shutdown()
            with self.assertRaises(RuntimeError):
                module._submit(executor, lambda: None, (), {})
            self.assertEqual(module._pending_count, 0)
        finally:
            release.set()
            executor.shutdown(wait=True)
            module._sdk_executor.shutdown(wait=True)
            module._callback_executor.shutdown(wait=True)
