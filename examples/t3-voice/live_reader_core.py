"""Read-only T3 message feed and prose filtering; never logs conversation text."""
from dataclasses import dataclass
from contextlib import closing
import html
import json
from pathlib import Path
import re
import sqlite3


def clean_prose(text: str) -> str:
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if fence is not None or line.startswith(('    ', '\t')):
            continue
        if re.match(r'^\s*(?:[-*_]\s*){3,}$', line):
            continue
        line = re.sub(r'!\[[^\]]*\]\([^\n]*\)', '', line)
        line = re.sub(r'\[([^\]]+)\]\([^\n]*?\)', r'\1', line)
        line = re.sub(r'https?://\S+', '', line)
        line = re.sub(r'<[^>]+>', '', line)
        heading = re.match(r'^\s{0,3}#{1,6}\s+(.+)', line)
        if heading:
            line = heading.group(1).rstrip('# ').rstrip('.!?') + '.'
        line = re.sub(r'^\s*(?:[-+*]|\d+[.)]|>)\s+', '', line)
        line = re.sub(r'(`+)(.*?)\1', r'\2', line)
        line = line.replace('**', '').replace('__', '').replace('~~', '')
        lines.append(line)
    return re.sub(r'\s+', ' ', html.unescape(' '.join(lines))).strip()


@dataclass(frozen=True)
class Message:
    id: str
    run: str
    text: str


class MessageFeed:
    def __init__(self, path: Path, thread: str):
        self.path = Path(path)
        self.thread = thread
        self.suppressed = set()
        self.cursor = 0
        self.discard_pending()

    def connect(self):
        db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.05)
        db.execute('PRAGMA query_only=ON')
        return db

    def discard_pending(self):
        with closing(self.connect()) as db:
            self.cursor = db.execute('SELECT COALESCE(MAX(rowid),0) FROM orchestration_v2_projection_messages WHERE thread_id=?', (self.thread,)).fetchone()[0]

    def suppress(self, run: str):
        if run:
            self.suppressed.add(run)

    def poll(self):
        with closing(self.connect()) as db:
            rows = db.execute('SELECT rowid,message_id,run_id,role,streaming,payload_json FROM orchestration_v2_projection_messages WHERE thread_id=? AND rowid>? ORDER BY rowid LIMIT 128', (self.thread, self.cursor)).fetchall()
        result = []
        for index, (rowid, mid, run, role, streaming, raw) in enumerate(rows):
            if role == 'assistant' and streaming and run not in self.suppressed:
                superseded = any(later[3] == 'user' or
                                 (later[3] == 'assistant' and later[2] and later[2] != run)
                                 for later in rows[index + 1:])
                if not superseded:
                    break  # Retry an active message, but never block a newer reply.
                self.cursor = rowid
                continue
            self.cursor = rowid
            if role != 'assistant' or run in self.suppressed:
                continue
            data = json.loads(raw)
            if data.get('creationSource') != 'provider' or data.get('createdBy') != 'agent':
                continue
            text = clean_prose(data.get('text', ''))
            if text:
                result.append(Message(mid, run or mid, text))
        return result
