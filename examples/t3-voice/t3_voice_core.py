"""Local T3 voice prototype: routing, incremental prose, endpointing and adapters."""
from collections import deque
from contextlib import closing
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import threading

from live_reader_core import MessageFeed, Message, clean_prose


@dataclass(frozen=True)
class Ticket:
    thread: str
    revision: int


class Routes:
    def __init__(self, path):
        self.path = Path(path)
        try:
            saved = json.loads(self.path.read_text('utf-8'))
            self.preferences = {key: value for key, value in saved.items() if isinstance(key, str) and type(value) is bool}
        except (OSError, ValueError, AttributeError):
            self.preferences = {}
        self.thread = None
        self.revision = 0
        self.lock = threading.RLock()

    def select(self, thread):
        with self.lock:
            self.thread = thread
            self.revision += 1

    def enable(self, enabled):
        with self.lock:
            if self.thread is None:
                return
            self.preferences[self.thread] = bool(enabled)
            self.revision += 1
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.preferences, indent=2), 'utf-8')
            temporary.replace(self.path)

    def ticket(self):
        with self.lock:
            return Ticket(self.thread, self.revision) if self.preferences.get(self.thread, False) else None

    def current(self, ticket):
        with self.lock:
            return ticket is not None and ticket == self.ticket()


class StreamingFeed(MessageFeed):
    """Only new assistant prose; revisit live rows without replaying consumed text."""
    def __init__(self, path, thread):
        self.prefixes = {}
        self.runs = set()
        super().__init__(path, thread)

    def suppress_current(self):
        self.suppressed.update(self.runs)

    def poll(self):
        with closing(self.connect()) as db:
            rows = db.execute('SELECT rowid,message_id,run_id,role,streaming,payload_json '
                              'FROM orchestration_v2_projection_messages WHERE thread_id=? AND rowid>? '
                              'ORDER BY rowid LIMIT 128', (self.thread, self.cursor)).fetchall()
        result = []
        blocked = False
        for index, (rowid, mid, run, role, streaming, raw) in enumerate(rows):
            run = run or mid
            superseded = any(later[3] == 'user' or (later[3] == 'assistant' and later[2] and later[2] != run)
                             for later in rows[index + 1:])
            active = role == 'assistant' and streaming and run not in self.suppressed and not superseded
            if not blocked and not active:
                self.cursor = rowid
            blocked = blocked or active
            if role != 'assistant' or run in self.suppressed or (streaming and superseded):
                continue
            self.runs.add(run)
            data = json.loads(raw)
            if data.get('creationSource') != 'provider' or data.get('createdBy') != 'agent':
                continue
            source = data.get('text', '')
            # Partial opening fence lines must never become audible code.
            if streaming:
                source = re.sub(r'(?:\A|\n) {0,3}(?:`{1,2}(?!`)|~{1,2}(?!~))[^\n]*\Z', '', source)
            prose = clean_prose(source)
            prefix = self.prefixes.get(mid, '')
            if not prose.startswith(prefix):
                self.suppressed.add(run)  # A rewritten prefix cannot safely be replayed.
                continue
            remaining = prose[len(prefix):].lstrip()
            if streaming:
                boundaries = list(re.finditer(r'[.!?](?=\s)', remaining))
                if boundaries:
                    chunk = remaining[:boundaries[-1].end()]
                elif len(remaining) > 180:
                    cut = remaining.rfind(' ', 0, 180)
                    chunk = remaining[:cut] if cut > 0 else ''
                else:
                    chunk = ''
            else:
                chunk = remaining
            if chunk:
                end = prose.find(chunk, len(prefix)) + len(chunk)
                self.prefixes[mid] = prose[:end]
                result.append(Message(mid, run, chunk))
        # State is bounded by this short-lived feed's window of live messages.
        live = {row[1] for row in rows if row[0] > self.cursor}
        self.prefixes = {key: value for key, value in self.prefixes.items() if key in live}
        return result


class UtteranceGate:
    """20-ms frames: interrupt on sustained speech; finish after a silence gap."""
    def __init__(self, start_frames=3, silence_frames=45, max_frames=1500):
        self.start_frames, self.silence_frames, self.max_frames = start_frames, silence_frames, max_frames
        self.pre = deque(maxlen=10)
        self.frames = None
        self.voiced = self.silent = 0

    def push(self, frame, voiced):
        if self.frames is None:
            self.pre.append(frame)
            self.voiced = self.voiced + 1 if voiced else 0
            if self.voiced >= self.start_frames:
                self.frames = list(self.pre)
                self.silent = 0
                return [('start', None)]
            return []
        self.frames.append(frame)
        self.silent = 0 if voiced else self.silent + 1
        if self.silent >= self.silence_frames or len(self.frames) >= self.max_frames:
            audio = b''.join(self.frames)
            self.frames = None
            self.pre.clear()
            self.voiced = self.silent = 0
            return [('end', audio)]
        return []


def list_threads(path):
    with closing(MessageFeed.connect(type('Source', (), {'path': Path(path)})())) as db:
        return [{'id': row[0], 'title': row[1]} for row in db.execute(
            'SELECT thread_id,title FROM orchestration_v2_projection_threads '
            'WHERE deleted_at IS NULL AND archived_at IS NULL ORDER BY updated_at DESC LIMIT 150')]


class McpSender:
    """One warm session against the local T3 MCP endpoint; the CLI boots Electron per call."""
    PROTOCOL = '2025-06-18'

    def __init__(self, token_path, runtime_path=Path.home() / '.t3/userdata/server-runtime.json'):
        self.token_path = Path(token_path)
        self.runtime_path = Path(runtime_path)
        self.session = None
        self.lock = threading.Lock()

    def available(self):
        return self.token_path.exists() and self.runtime_path.exists()

    def _post(self, body, session=None):
        import urllib.request
        token = self.token_path.read_text('utf-8').strip()
        origin = json.loads(self.runtime_path.read_text('utf-8'))['origin']
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': self.PROTOCOL}
        if session:
            headers['Mcp-Session-Id'] = session
        request = urllib.request.Request(origin + '/mcp', json.dumps(body).encode(), headers)
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read().decode('utf-8')
            if 'text/event-stream' in (response.headers.get('Content-Type') or ''):
                raw = chr(10).join(line[5:].strip() for line in raw.splitlines() if line.startswith('data:'))
            return response.headers.get('Mcp-Session-Id'), (json.loads(raw) if raw.strip() else None)

    def _open(self):
        session, reply = self._post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': self.PROTOCOL, 'capabilities': {},
            'clientInfo': {'name': 'maeve-voice', 'version': '0.1'}}})
        if not session or 'result' not in (reply or {}):
            raise RuntimeError('T3 MCP initialize failed.')
        self._post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, session)
        return session

    def send(self, thread, text):
        import urllib.error
        with self.lock:
            for attempt in range(2):
                try:
                    if self.session is None:
                        self.session = self._open()
                    _, reply = self._post({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                        'name': 't3_thread_send',
                        'arguments': {'threadId': thread, 'message': text, 'mode': 'queue'}}}, self.session)
                    break
                except urllib.error.HTTPError as error:
                    self.session = None
                    if error.code == 404 and attempt == 0:
                        continue  # Server restarted or expired the session; one fresh handshake.
                    raise
        if reply is None or 'error' in reply or reply.get('result', {}).get('isError'):
            detail = ''
            try:
                detail = json.loads(reply['result']['content'][0]['text']).get('code', '')
            except (KeyError, IndexError, TypeError, ValueError):
                pass
            raise RuntimeError('T3 rejected this message' + (' (' + detail + ')' if detail else '') + '. Not retried.')
        return reply['result'].get('structuredContent') or {'delivery': 'accepted'}


MCP = McpSender(Path(__file__).resolve().parent / 't3-voice-token.txt')


def send_message(thread, text):
    """Direct local MCP when a token exists; otherwise the supported CLI. Never a guessed editor."""
    if not thread or not text.strip():
        raise ValueError('A target thread and nonempty transcript are required.')
    if MCP.available():
        return MCP.send(thread, text)
    return send_message_cli(thread, text)


def send_message_cli(thread, text):
    program = Path.home() / 'AppData/Local/Programs/t3code'
    executable = program / 'T3 Code (Beta).exe'
    script = program / 'resources/server.asar/apps/server/dist/bin.mjs'
    environment = dict(os.environ, ELECTRON_RUN_AS_NODE='1', T3CODE_DESKTOP_CLI_LAUNCHER='1')
    result = subprocess.run([str(executable), str(script), 'thread', 'send', '--json', thread, '-'],
                            input=text, capture_output=True, text=True, encoding='utf-8',
                            timeout=20, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('T3 did not acknowledge this send. It will not be retried automatically.')
    return json.loads(result.stdout)


def transcribe(pcm, sample_rate=16000):
    """Existing sherpa offline WebSocket protocol; all audio remains on loopback."""
    import numpy as np
    import websocket
    samples = (np.frombuffer(pcm, dtype='<i2').astype('<f4') / 32768).tobytes()
    payload = struct.pack('<II', sample_rate, len(samples)) + samples
    socket = websocket.create_connection('ws://127.0.0.1:6006', timeout=25,
                                         http_no_proxy=['127.0.0.1', 'localhost'])
    try:
        for offset in range(0, len(payload), 10240):
            socket.send_binary(payload[offset:offset + 10240])
        result = json.loads(socket.recv())
        socket.send('Done')
        text = result.get('text', '')
        if not isinstance(text, str):
            raise ValueError('Unexpected local transcription result.')
        return text.strip()
    finally:
        socket.close()
