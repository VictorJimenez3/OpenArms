"""Capture process exit independently of Isaac, including native shutdown crashes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args, remaining = parser.parse_known_args()
command = [sys.executable, str(Path(__file__).with_name('smoke.py')),
           '--output', str(args.output), *remaining]
started = time.time()
result = subprocess.run(command)
args.output.mkdir(parents=True, exist_ok=True)
receipt_path = args.output/'receipt.json'
receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
observed = receipt.get('observation_status', receipt.get('status', 'unknown'))
execution = {'command': command, 'returncode': result.returncode,
             'wall_seconds': time.time()-started, 'observation_status': observed,
             'status': 'passed' if result.returncode == 0 and observed == 'passed' else 'failed'}
(args.output/'execution.json').write_text(json.dumps(execution, indent=2))
receipt.update(status=execution['status'], process_returncode=result.returncode,
               shutdown_status='process_exited_zero' if result.returncode == 0 else 'process_failed')
receipt_path.write_text(json.dumps(receipt, indent=2))
sys.exit(0 if execution['status']=='passed' else 1)
