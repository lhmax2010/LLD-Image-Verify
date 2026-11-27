"""Read-only archive and evidence helpers for the PM review."""
import csv
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parents[1]
BASE = HERE.parent
RELEASE = '6.12.80-arm-rpi4-v7l'
SNAPSHOT = 'tizen-unified-toolchain_20261120.082536'
MODULE_RE = re.compile(r'\.ko(?:\.(?:gz|xz|zst))?$')

def need(condition, message):
    if not condition:
        raise ValueError(message)

def load(root, path):
    return json.loads((root/path).read_text())

def sha(path):
    with path.open('rb') as raw:
        return hashlib.file_digest(raw, 'sha256').hexdigest()

def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')

def csv_rows(root, path):
    with (root/path).open(newline='') as source:
        return list(csv.DictReader(source))

def write_csv(path, rows, fields=None):
    with path.open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=fields or list(rows[0]), extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

def markdown_table(headers, rows):
    values = [headers, ['---']*len(headers), *rows]
    return '\n'.join('| '+' | '.join(str(cell).replace('|', '&#124;').replace('\n',' ') for cell in row)+' | ' for row in values)

def log_ref(evt):
    return f'round1/{evt["evidence"]}#L{evt["line"]}'
