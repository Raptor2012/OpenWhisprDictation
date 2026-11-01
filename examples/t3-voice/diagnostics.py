"""Best-effort diagnostics must never interrupt the interactive event loop."""
import json
from pathlib import Path


def write_status(path: Path, data: dict) -> bool:
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
        temporary.replace(path)
        return True
    except OSError:
        return False
