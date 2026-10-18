import importlib.util
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('socket_delay_test_module',
    ROOT / 'custom_components/hwhomebridge/socket_delay.py')
delay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = delay
spec.loader.exec_module(delay)


class SocketDelayTests(unittest.TestCase):
    now = datetime(2026, 10, 18, 12, tzinfo=timezone(timedelta(hours=8)))

    def command(self, action=1, **entry):
        return {'delay': {'action': action, 'delay': [entry]}}

    def test_official_card_on_and_off_deadlines_use_utc(self):
        for field, turn_on in [('start', True), ('end', False)]:
            with self.subTest(field=field):
                command = delay.decode(self.command(sid='switch', para='on',
                    **{field: '20261018T043000Z'}), self.now)
                self.assertEqual(command.deadline.astimezone(self.now.tzinfo).hour, 12)
                self.assertEqual(command.deadline.minute, 30)
                self.assertIs(command.turn_on, turn_on)

    def test_update_retains_id_and_delete_has_no_switch_action(self):
        command = delay.decode(self.command(0, id=7, sid='switch', para='on',
            end='20261018T043000Z'), self.now)
        self.assertEqual(command.task_id, 7)
        command = delay.decode(self.command(2, id=7, para='on'), self.now)
        self.assertIsNone(command.turn_on)
        self.assertIsNone(command.deadline)

    def test_expired_invalid_and_ambiguous_commands_are_rejected(self):
        invalid = [
            self.command(sid='switch', para='on', start='20261018T040000Z'),
            self.command(sid='switch', para='on', start='20260230T043000Z'),
            self.command(sid='switch', para='on', start='20261018T043000Z', end='20261018T053000Z'),
            self.command(sid='switch', para='on', start='20261018T043000'),
            self.command(sid='switch', para='brightness', start='20261018T043000Z'),
            self.command(0, sid='switch', para='on', end='20261018T043000Z'),
            self.command(2, id=7, para='on', end='20261018T043000Z'),
            self.command(1, id=7, sid='switch', para='on', start='20261018T043000Z'),
            self.command(True, sid='switch', para='on', start='20261018T043000Z'),
            {'delay': {'action': 1, 'delay': []}},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                delay.decode(payload, self.now)
        with self.assertRaises(ValueError):
            delay.decode(self.command(2, id=7, para='on'), self.now.replace(tzinfo=None))

    def test_persistence_edit_cancel_and_due_action(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            path = Path(folder) / 'countdowns.json'
            store = delay.CountdownStore(path, self.now)
            created = store.apply('socket', self.command(sid='switch', para='on',
                start='20261018T043000Z'), self.now)
            task_id = created['delay']['delay'][0]['id']
            store = delay.CountdownStore(path, self.now)
            self.assertEqual(store.state('socket'), created)
            store.apply('socket', self.command(0, id=task_id, sid='switch', para='on',
                end='20261018T044500Z'), self.now)
            actions = []
            async def execute(sn, turn_on):
                actions.append((sn, turn_on))
            self.assertEqual(asyncio.run(store.tick(self.now, execute)), [])
            asyncio.run(store.tick(self.now + timedelta(minutes=45), execute))
            asyncio.run(store.tick(self.now + timedelta(hours=1), execute))
            self.assertEqual(actions, [('socket', False)])
            store.apply('socket', self.command(sid='switch', para='on',
                start='20261018T050000Z'), self.now)
            task_id = store.state('socket')['delay']['delay'][0]['id']
            store.apply('socket', self.command(2, id=task_id, para='on'), self.now)
            self.assertEqual(store.state('socket')['delay']['num'], 0)
            asyncio.run(store.tick(self.now + timedelta(hours=2), execute))
            self.assertEqual(actions, [('socket', False)])

    def test_restart_does_not_replay_missed_deadline_and_failed_action_is_not_retried(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'temp') as folder:
            path = Path(folder) / 'countdowns.json'
            store = delay.CountdownStore(path, self.now)
            payload = self.command(sid='switch', para='on', end='20261018T043000Z')
            store.apply('socket', payload, self.now)
            restored = delay.CountdownStore(path, self.now + timedelta(hours=1))
            self.assertEqual(restored.state('socket')['delay']['num'], 0)
            store = delay.CountdownStore(path, self.now)
            store.apply('socket', payload, self.now)
            async def fail(sn, turn_on):
                raise OSError('Simulated device unavailable')
            results = asyncio.run(store.tick(self.now + timedelta(hours=1), fail))
            self.assertFalse(results[0]['success'])
            self.assertEqual(asyncio.run(store.tick(self.now + timedelta(hours=2), fail)), [])
