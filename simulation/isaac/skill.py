"""Bounded, simulation-only file/event interface; never imports hardware code.

The application owns student confirmation. Invoke only after that confirmation,
inside the authorized runtime environment. Each invocation resets a fresh stage.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading


def validate_request(request):
    if not isinstance(request, dict) or set(request) != {
            'request_id', 'session_id', 'skill_id', 'parameters'}:
        raise ValueError('Expected the canonical four-field skill request')
    for key in ('request_id', 'session_id'):
        if not isinstance(request[key], str) or not 1 <= len(request[key]) <= 128:
            raise ValueError(f'{key} must be a nonempty string of at most 128 characters')
    skill = request['skill_id']
    if skill == 'isaac.articulation.v1' and request['parameters'] == {}:
        return 'articulation'
    if skill == 'known_station_transfer.v1' and request['parameters'] == {
            'object': 'sample', 'source': 'A', 'destination': 'B'}:
        return 'cube'
    raise ValueError('Unsupported simulated skill or parameters')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workshop', type=Path, required=True)
    parser.add_argument('--allow-unvalidated-transfer', action='store_true')
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    task = validate_request(request)
    if task == 'cube' and not args.allow_unvalidated_transfer:
        parser.error('Transfer is not yet runtime-qualified; experimental opt-in is required')
    from execution_context import validate_context
    validate_context()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'request.json').write_text(json.dumps(request, indent=2))
    # One simulator per evidence root, including callers in different processes.
    import fcntl
    with (args.output.parent/'.isaac-runtime.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        command = [sys.executable, str(Path(__file__).with_name('run_recording.py')),
                   '--workshop', str(args.workshop), '--output', str(args.output/'recording'),
                   '--request-id', request['request_id'], '--task', task]
        stopped = False
        with (args.output/'startup.log').open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)

            def stop(_signum, _frame):
                nonlocal stopped
                stopped = True
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    def force_stop():
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                    timer = threading.Timer(30, force_stop)
                    timer.daemon = True
                    timer.start()

            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            code = process.wait()
        receipt_file = args.output/'recording/receipt.json'
        receipt = json.loads(receipt_file.read_text()) if receipt_file.exists() else {}
        passed = code == 0 and receipt.get('status') == 'passed'
        if task == 'cube':
            passed = passed and receipt.get('manipulation_success') is True
        result = {'request_id': request['request_id'], 'backend': 'simulated',
                  'status': 'stopped' if stopped else ('completed' if passed else 'failed'),
                  'operator_authorized': False, 'controller_completed': passed and not stopped,
                  'physical_success': None,
                  'observation': {'provenance': 'SIMULATED', 'source': 'Isaac execution receipt',
                                  'text': receipt.get('result', 'No successful execution evidence'),
                                  'value': receipt.get('manipulation_success', False),
                                  'evidence': [str(receipt_file)]},
                  'reason': ('STOP requested' if stopped else
                             (None if passed else receipt.get('error', 'Isaac execution did not pass')))}
        (args.output/'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        return 0 if passed and not stopped else 1


if __name__ == '__main__':
    raise SystemExit(main())
