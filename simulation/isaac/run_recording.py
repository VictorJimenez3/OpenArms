"""Capture process exit independently of Isaac, including native shutdown crashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import signal
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args, remaining = parser.parse_known_args()
command = [sys.executable, str(Path(__file__).with_name('smoke.py')),
           '--output', str(args.output), *remaining]
started = time.time()
child = subprocess.Popen(command)
stopped = False

def request_stop(_signum, _frame):
    global stopped
    if not stopped and child.poll() is None:
        stopped = True
        child.send_signal(signal.SIGINT)

signal.signal(signal.SIGTERM, request_stop)
signal.signal(signal.SIGINT, request_stop)
returncode = child.wait()
args.output.mkdir(parents=True, exist_ok=True)
receipt_path = args.output/'receipt.json'
receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
observed = receipt.get('observation_status', receipt.get('status', 'unknown'))
execution = {'command': command, 'returncode': returncode, 'stopped': stopped,
             'wall_seconds': time.time()-started, 'observation_status': observed,
             'status': 'passed' if returncode == 0 and observed == 'passed' and not stopped else 'failed'}
(args.output/'execution.json').write_text(json.dumps(execution, indent=2))
receipt.update(status=execution['status'], process_returncode=returncode,
               shutdown_status='process_exited_zero' if returncode == 0 else 'process_failed')
with (args.output/'events.jsonl').open('a') as events:
    events.write(json.dumps({'request_id': receipt.get('request_id'), 'backend': 'simulated',
                             'provenance': 'SIMULATED', 'event': 'finished',
                             'status': execution['status'], 'returncode': returncode,
                             'stopped': stopped})+'\n')
receipt['sha256'] = {}
for path in args.output.iterdir():
    if path.is_file() and path.name != 'receipt.json':
        with path.open('rb') as stream:
            receipt['sha256'][path.name] = hashlib.file_digest(stream, 'sha256').hexdigest()
receipt_path.write_text(json.dumps(receipt, indent=2))
sys.exit(0 if execution['status']=='passed' else 1)
