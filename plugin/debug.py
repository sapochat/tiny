"""Linux same-user diagnostic IPC; never a device/admin network endpoint.

Bound to the adapter's own store, not the process-local default-profile fallback.
Only metadata, a short display card, and a fixed quiet speaker test are exposed.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
import socket
import stat
import struct
import time

from . import protocol, textfmt

LIMIT = 8192
TIMEOUT = 3.0


def _private(path: Path, kind: str) -> None:
    info = path.lstat()
    matches = stat.S_ISDIR(info.st_mode) if kind == 'directory' else stat.S_ISSOCK(info.st_mode)
    if not matches or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError(f'diagnostic {kind} must be owned by this user and private')


def _address(path: Path) -> tuple[str, int | None]:
    """A bindable address for ``path``. Unix socket paths are capped near 107 bytes, so a deep
    HERMES_HOME is reached through ``/proc/self/fd/<dir>/``: the same private directory, a short
    name. Returns the open directory fd as well; the caller closes it."""
    if len(os.fsencode(str(path))) < 100:
        return str(path), None
    fd = os.open(path.parent, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    return f'/proc/self/fd/{fd}/{path.name}', fd


def _peer(sock) -> None:
    _, uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != os.getuid():
        raise PermissionError('diagnostics requires the same OS user')


class DebugServer:
    def __init__(self, adapter):
        self.adapter = adapter
        self.directory = adapter._store.path.parent / 'debug'
        self.path = self.directory / 'control.sock'
        self.server = None
        self.lock_fd = None
        self.dir_fd = None  # held while bound through /proc/self/fd (a long path)
        self.busy = False
        self.connections = set()

    async def start(self) -> None:
        import fcntl
        self.directory.mkdir(mode=0o700, exist_ok=True)
        _private(self.directory, 'directory')
        # A live owner cannot be displaced; the lock is released on process death.
        self.lock_fd = os.open(self.directory / 'owner.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists() or self.path.is_symlink():
                _private(self.path, 'socket')
                self.path.unlink()
            address, self.dir_fd = _address(self.path)
            self.server = await asyncio.start_unix_server(self.handle, path=address, limit=LIMIT)
            self.path.chmod(0o600)
        except BaseException:
            if self.dir_fd is not None:
                os.close(self.dir_fd)
                self.dir_fd = None
            os.close(self.lock_fd)
            self.lock_fd = None
            raise

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            for task in list(self.connections):
                task.cancel()
            await asyncio.gather(*list(self.connections), return_exceptions=True)
            self.path.unlink(missing_ok=True)
            self.server = None
        if self.dir_fd is not None:
            os.close(self.dir_fd)
            self.dir_fd = None
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    async def handle(self, reader, writer) -> None:
        task = asyncio.current_task()
        self.connections.add(task)
        try:
            _peer(writer.get_extra_info('socket'))
            async with asyncio.timeout(TIMEOUT):
                raw = await reader.readline()
                if not raw.endswith(b'\n') or len(raw) > LIMIT:
                    raise ValueError('invalid or oversized request')
                request = json.loads(raw)
                if not isinstance(request, dict):
                    raise ValueError('request must be an object')
                result = await self.dispatch(request)
            response = {'success': True, **result}
        except asyncio.CancelledError:
            writer.close()
            self.connections.discard(task)
            raise
        except Exception as exc:
            response = {'success': False, 'error': str(exc) or type(exc).__name__}
        try:
            encoded = json.dumps(response).encode() + b'\n'
            if len(encoded) > 65536:
                encoded = b'{"success":false,"error":"diagnostic response too large"}\n'
            writer.write(encoded)
            await asyncio.wait_for(writer.drain(), TIMEOUT)
        except (ConnectionError, OSError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()
            self.connections.discard(task)

    async def dispatch(self, request: dict) -> dict:
        op = request.get('op')
        if op not in ('status', 'display', 'tone'):
            raise ValueError('supported operations: status, display, tone')
        hub = self.adapter.hub
        if not hub:
            raise RuntimeError('gadget hub is not connected')
        if op == 'status':
            return {'pid': os.getpid(), 'profile': self.adapter._registry_key,
                    'connected': [dict(s.describe(), last_rx_age_s=round(time.monotonic() - s.last_rx, 2))
                                  for s in hub.sessions.values()],
                    'operations': ['status', 'display', 'tone'], 'device_ack_supported': False}
        if request.get('confirm') is not True:
            raise ValueError('display/tone requires --confirm (explicit user-authorized test)')
        device = request.get('device')
        if not isinstance(device, str) or not protocol.DEVICE_ID_RE.fullmatch(device):
            raise ValueError('an exact device id is required')
        session = hub.get(device)
        if session is None or session.closed:
            raise ValueError('device is not connected')
        # Do not trust the asynchronously refreshed paired flag alone.
        if not session.paired or self.adapter._authorized(device) is not True:
            raise PermissionError('device is not currently approved')
        if (self.busy or device in self.adapter._turns or self.adapter._prompts.get(device)
                or device in self.adapter._installing or session._upload is not None
                or (session._audio_out and not session._audio_out.done.is_set())):
            raise RuntimeError('device is busy; retry after its conversation or approval ends')
        self.busy = True
        try:
            if op == 'display':
                text = request.get('text')
                if not isinstance(text, str) or not text.strip() or len(text) > 500:
                    raise ValueError('text must contain 1-500 characters')
                if not session.display:
                    raise ValueError('device has no display')
                await session.show_card('Hermes debug', textfmt.for_device(text, session.charset), 10)
            else:
                if not session.has_speaker or not 4000 <= session.speaker_rate <= 48000:
                    raise ValueError('device has no supported speaker')
                # Fixed 250 ms, 440 Hz, low-amplitude PCM; never read a mic or a file.
                pcm = b''.join(struct.pack('<h', round(1000 * math.sin(2 * math.pi * 440 * i / 16000)))
                               for i in range(4000))
                out = await session.open_audio(16000)
                try:
                    out.write(pcm)
                    out.finish()
                    await out.done.wait()
                    if out.aborted or session.closed or out.sent_seconds < .249:
                        raise RuntimeError('audio transport interrupted')
                except BaseException:
                    await out.abort()
                    raise
            return {'device_id': device, 'operation': op, 'delivery': 'transport_sent',
                    'device_acknowledged': False,
                    'note': 'Protocol v1 has no display/audio completion acknowledgement; confirm on hardware.'}
        finally:
            self.busy = False


def query(directory: Path, request: dict) -> dict:
    path = directory / 'debug/control.sock'
    try:
        _private(path.parent, 'directory')
        _private(path, 'socket')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(TIMEOUT + 1)
            address, fd = _address(path)
            try:
                sock.connect(address)
            finally:
                if fd is not None:
                    os.close(fd)
            _peer(sock)
            payload = json.dumps(request).encode() + b'\n'
            if len(payload) > LIMIT:
                raise ValueError('request too large')
            sock.sendall(payload)
            with sock.makefile('rb') as stream:
                raw = stream.readline(65537)
            if not raw.endswith(b'\n') or len(raw) > 65536:
                raise ValueError('invalid diagnostic response')
            result = json.loads(raw)
            if not isinstance(result, dict) or not isinstance(result.get('success'), bool):
                raise ValueError('invalid diagnostic response')
            return result
    except (OSError, ValueError) as exc:
        return {'success': False, 'error': f'Local gadget diagnostics unavailable: {exc}',
                'activation': 'Requires the updated gadget adapter in the gateway. Ask before restarting it.'}


def setup_argparse(parser) -> None:
    sub = parser.add_subparsers(dest='debug_operation', required=True)
    sub.add_parser('status', help='Read live connections, capabilities and latest telemetry (JSON)')
    display = sub.add_parser('display', help='Show a 10-second test card')
    display.add_argument('device', help='Exact hg- device id')
    display.add_argument('text', help='1-500 characters')
    display.add_argument('--confirm', action='store_true', help='Confirm user-authorized visible test')
    tone = sub.add_parser('tone', help='Play a quiet 250-ms 440-Hz speaker test')
    tone.add_argument('device', help='Exact hg- device id')
    tone.add_argument('--confirm', action='store_true', help='Confirm user-authorized audible test')


def handle(args) -> None:
    from plugins.plugin_storage import plugin_data_dir
    request = {'op': args.debug_operation}
    for key in ('device', 'text', 'confirm'):
        if hasattr(args, key):
            request[key] = getattr(args, key)
    result = query(plugin_data_dir('gadget'), request)
    print(json.dumps(result))
    if not result['success']:
        raise SystemExit(1)
