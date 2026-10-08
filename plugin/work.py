"""Bounded outcome journal, not a task runner. Never schedules or replays work."""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)
RETENTION = 7 * 24 * 60 * 60
STAGES = {'running', 'finished', 'failed', 'cancelled', 'unknown'}
# Do not retain credential-shaped replies. No raw requests/audio enter this store.
SENSITIVE = re.compile(r'(?i)(password|secret|token|api.?key|authorization|bearer|BEGIN .*PRIVATE KEY|sk-[a-z0-9]|https?://[^\s]+[?@])')


def _validate(data):
    """Explicit checks (not assert): they must hold under `python -O` too."""
    def need(ok):
        if not ok:
            raise ValueError('invalid work store')
    need(isinstance(data, dict) and data.get('v') == 1)
    need(isinstance(data.get('items'), list) and isinstance(data.get('owners'), dict))
    for r in data['items']:
        need(isinstance(r, dict) and r.get('stage') in STAGES and isinstance(r.get('work_id'), str))
        need(isinstance(r.get('device_id'), str) and isinstance(r.get('origin'), dict))
        need(isinstance(r['origin'].get('turn'), str) and isinstance(r['origin'].get('request'), str))
        res = r.get('result')
        need(isinstance(res, dict) and type(res.get('revision')) is int and res['revision'] >= 0)
        need(isinstance(res.get('glance'), str) and len(res['glance']) <= 240)
        need(all(type(r.get(k)) in (float, int) for k in ('created_at', 'updated_at', 'expires_at')))


class WorkStore:
    def __init__(self, directory):
        self.path = Path(directory) / 'work.json'
        self._lock = threading.RLock()
        self._data = {'v': 1, 'items': [], 'owners': {}}
        try:
            data = json.loads(self.path.read_text())
            _validate(data)
            self._data = data
        except FileNotFoundError:
            pass
        except OSError as e:
            log.error('Work store unreadable, recent work starts empty: %s', e)
        except (ValueError, KeyError, TypeError):
            dest = self.path.with_name('work.json.corrupt-' + uuid.uuid4().hex)
            try:
                os.replace(self.path, dest)
                os.chmod(dest, 0o600)
                log.error('Corrupt work store set aside at %s', dest)
            except OSError as e:
                log.error('Corrupt work store could not be set aside: %s', e)
        changed = self._prune()
        for r in self._data['items']:
            if r['stage'] == 'running':
                r['stage'] = 'unknown'
                r['updated_at'] = time.time()
                changed = True
        if changed:
            self._persist()

    def _persist(self):
        """Best-effort durability: a failed write loses history, never live traffic."""
        try:
            self._save()
        except OSError as e:
            log.error('Work store not saved (recent work kept in memory only): %s', e)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='work-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                os.fchmod(f.fileno(), 0o600)
                json.dump(self._data, f, separators=(',', ':'))
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                try:
                    os.unlink(name)
                except OSError:
                    pass

    def _prune(self):
        old = self._data['items']
        counts = {}
        items = []
        for r in sorted(old, key=lambda r: r['updated_at'], reverse=True):
            d = r['device_id']
            if r['expires_at'] > time.time() and counts.get(d, 0) < 8:
                items.append(r)
                counts[d] = counts.get(d, 0) + 1
        self._data['items'] = items
        return items != old

    def bind(self, device, enrolled):
        """An enrollment generation cannot inherit records from a forgotten device."""
        with self._lock:
            if self._data['owners'].get(device) != enrolled:
                self.clear(device)
                self._data['owners'][device] = enrolled
                self._persist()

    def clear(self, device):
        with self._lock:
            self._data['items'] = [r for r in self._data['items'] if r['device_id'] != device]
            self._persist()

    def items(self, device):
        with self._lock:
            if self._prune():
                self._persist()
            return copy.deepcopy([r for r in self._data['items'] if r['device_id'] == device])

    def interrupt(self, device, turns):
        with self._lock:
            changed = False
            for r in self._data['items']:
                if r['device_id'] == device and r['origin']['turn'] in turns and r['stage'] == 'running':
                    r.update(stage='unknown', updated_at=time.time())
                    changed = True
            if changed:
                self._persist()

    def observe(self, device, msg):
        kind, turn = msg.get('type'), msg.get('turn')
        if kind not in ('turn.start', 'turn.end', 'reply') or not isinstance(turn, str) or not turn:
            return False
        with self._lock:
            self._prune()
            r = next((r for r in self._data['items'] if r['device_id'] == device and r['origin']['turn'] == turn), None)
            now = time.time()
            if kind == 'turn.start' and r is None:
                r = {'work_id': uuid.uuid4().hex, 'device_id': device,
                     'origin': {'turn': turn, 'request': str(msg.get('request') or '')},
                     'stage': 'running', 'result': {'revision': 0, 'glance': ''},
                     'created_at': now, 'updated_at': now, 'expires_at': now + RETENTION}
                self._data['items'].append(r)
            elif r is None or kind == 'turn.start':
                return False
            elif kind == 'turn.end':
                stage = {'success': 'finished', 'failure': 'failed', 'cancelled': 'cancelled'}.get(msg.get('outcome'))
                if not stage or r['stage'] not in ('running', 'unknown'):
                    return False
                r['stage'] = stage
            elif kind == 'reply':
                if msg.get('interim') or not isinstance(msg.get('text'), str):
                    return False
                text = msg['text']
                glance = '[Result omitted: may contain credentials]' if SENSITIVE.search(text) else text[:240]
                if glance == r['result']['glance']:
                    return False
                r['result'] = {'revision': r['result']['revision'] + 1, 'glance': glance}
            r['updated_at'] = now
            self._prune()
            self._persist()
            return True
