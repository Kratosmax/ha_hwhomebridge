"""Decode the 124U socket card's countdown commands without executing them.

The card uses start for power-on, end for power-off, and UTC timestamps.
This decoder is not connected to the running bridge until socket registration
and durable scheduling have been verified.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile


@dataclass(frozen=True)
class DelayCommand:
    action: int
    task_id: int | None
    deadline: datetime | None
    turn_on: bool | None


def decode(payload, now):
    """Reject unsupported commands rather than guessing a switch action."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('An aware current time is required')
    if not isinstance(payload, dict) or set(payload) != {'delay'}:
        raise ValueError('Expected a delay service payload')
    service = payload['delay']
    if not isinstance(service, dict) or set(service) != {'action', 'delay'}:
        raise ValueError('Unsupported delay service fields')
    action = service['action']
    if type(action) is not int or action not in (0, 1, 2):
        raise ValueError('Unsupported countdown operation')
    entries = service['delay']
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        raise ValueError('Exactly one countdown is supported')
    entry = entries[0]
    task_id = entry.get('id')
    if task_id is not None and (type(task_id) is not int or task_id < 0):
        raise ValueError('Invalid countdown ID')
    if action in (0, 2) and task_id is None:
        raise ValueError('Update and delete require a countdown ID')
    if entry.get('para') != 'on':
        raise ValueError('Only the switch on characteristic is supported')
    if action == 2:
        if set(entry) != {'id', 'para'}:
            raise ValueError('Delete must not contain a switch action')
        return DelayCommand(action, task_id, None, None)
    if action == 1 and task_id is not None:
        raise ValueError('Create must not replace an existing countdown ID')
    timing = set(entry) & {'start', 'end'}
    if len(timing) != 1 or entry.get('sid') != 'switch':
        raise ValueError('A switch countdown requires either start or end')
    field = next(iter(timing))
    if set(entry) != ({'sid', 'para', field} | ({'id'} if task_id is not None else set())):
        raise ValueError('Unsupported countdown fields')
    value = entry[field]
    if not isinstance(value, str) or not re.fullmatch(r'\d{8}T\d{6}Z', value):
        raise ValueError('Expected a UTC countdown timestamp')
    deadline = datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    if deadline <= now:
        raise ValueError('An expired countdown must not execute immediately')
    return DelayCommand(action, task_id, deadline, field == 'start')


class CountdownStore:
    """One durable countdown per socket, with no HA or SDK dependencies.

    The caller must serialize access and invoke tick on its scheduler. Expired
    tasks loaded after a restart are discarded, never replayed as switch actions.
    """

    def __init__(self, path, now):
        self.path = Path(path)
        self.tasks = {}
        self.next_id = 1
        if self.path.exists():
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if saved.get('version') != 1:
                raise ValueError('Unsupported countdown storage version')
            self.next_id = saved['next_id']
            for sn, task in saved['tasks'].items():
                command = decode({'delay': {'action': 0, 'delay': [task]}},
                                 datetime.min.replace(tzinfo=timezone.utc))
                if command.deadline > now:
                    self.tasks[sn] = task
            self._save(self.tasks, self.next_id)

    def _save(self, tasks, next_id):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, staged = tempfile.mkstemp(prefix=self.path.name + '.', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump({'version': 1, 'next_id': next_id, 'tasks': tasks}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, self.path)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)

    def state(self, sn):
        task = self.tasks.get(sn)
        return {'delay': {'num': int(task is not None), 'delay': [dict(task)] if task else []}}

    def apply(self, sn, payload, now):
        command = decode(payload, now)
        current = self.tasks.get(sn)
        if command.action == 1 and current:
            raise ValueError('Only one countdown per socket is supported')
        if command.action in (0, 2) and (not current or current['id'] != command.task_id):
            raise ValueError('Unknown countdown ID')
        tasks = dict(self.tasks)
        next_id = self.next_id
        if command.action == 2:
            tasks.pop(sn)
        else:
            task = dict(payload['delay']['delay'][0])
            if command.action == 1:
                task['id'] = next_id
                next_id += 1
            tasks[sn] = task
        self._save(tasks, next_id)
        self.tasks, self.next_id = tasks, next_id
        return self.state(sn)

    def take_due(self, now):
        """Persist removal before returning work; call off the HA event loop."""
        due = []
        for sn, task in self.tasks.items():
            command = decode({'delay': {'action': 0, 'delay': [task]}},
                             datetime.min.replace(tzinfo=timezone.utc))
            if command.deadline <= now:
                due.append((sn, command.turn_on))
        if due:
            tasks = dict(self.tasks)
            for sn, _ in due:
                tasks.pop(sn)
            self._save(tasks, self.next_id)
            self.tasks = tasks
        return due

    async def tick(self, now, execute):
        """Attempt each due action once; an execution failure is not retried."""
        due = self.take_due(now)
        results = []
        for sn, turn_on in due:
            try:
                await execute(sn, turn_on)
                results.append({'sn': sn, 'success': True})
            except Exception as exc:
                results.append({'sn': sn, 'success': False, 'error_type': type(exc).__name__})
        return results
