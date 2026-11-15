"""Probe `devin acp --agent-type summarizer`: record every JSON-RPC message for one text+image prompt."""
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

DEVIN = '/Users/victor/.local/share/local-devin-sessions/runtime/3000.12.57/bin/devin'
OUT = Path(sys.argv[1])
MODEL = sys.argv[2] if len(sys.argv) > 2 else 'gpt-6-1-sol-medium-priority'
IMAGE = Path(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
log = OUT.open('w')
AGENT = ['--agent-type', 'summarizer'] if len(sys.argv) < 5 else []
proc = subprocess.Popen([DEVIN, 'acp', *AGENT, '--model', MODEL],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd='/tmp')


def send(message):
    log.write('>> ' + json.dumps(message)[:20000] + '\n'); log.flush()
    proc.stdin.write(json.dumps(message) + '\n'); proc.stdin.flush()


def until(request_id, limit=180):
    start = time.time()
    while time.time() - start < limit:
        line = proc.stdout.readline()
        if not line:
            break
        log.write(f'<< {time.time()-start:.2f} ' + line.strip()[:20000] + '\n'); log.flush()
        message = json.loads(line)
        if message.get('id') == request_id and ('result' in message or 'error' in message):
            return message
        if 'method' in message and 'id' in message:
            send({'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'denied'}})
    return None


t0 = time.time()
send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
      'params': {'protocolVersion': 1, 'clientCapabilities': {'fs': {'readTextFile': False, 'writeTextFile': False}, 'terminal': False}}})
until(1)
send({'jsonrpc': '2.0', 'id': 2, 'method': 'session/new', 'params': {'cwd': '/tmp', 'mcpServers': []}})
session = until(2)
sid = session['result']['sessionId']
Path(str(OUT) + '.session.json').write_text(json.dumps(session['result'], indent=1))
for option in session['result'].get('configOptions', []):
    if option['id'] == 'model':
        send({'jsonrpc': '2.0', 'id': 9, 'method': 'session/set_config_option', 'params': {'sessionId': sid, 'configId': 'model', 'value': MODEL}})
        until(9)
prompt = [{'type': 'text', 'text': 'Reply with only this JSON object and nothing else: {"ok": true, "colour": "<dominant colour of the image or none>"}'}]
if IMAGE:
    prompt.append({'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(IMAGE.read_bytes()).decode()})
t1 = time.time()
send({'jsonrpc': '2.0', 'id': 3, 'method': 'session/prompt', 'params': {'sessionId': sid, 'prompt': prompt}})
until(3)
log.write(f'## startup {t1-t0:.2f}s prompt {time.time()-t1:.2f}s\n')
proc.terminate()
log.write('## stderr ' + proc.stderr.read()[-2000:] + '\n')
log.close()
