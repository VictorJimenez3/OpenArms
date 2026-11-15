"""Drive the running app as a scripted test student: request, exact present+confirm, wait for the observed result."""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8011'
TEXT = sys.argv[2] if len(sys.argv) > 2 else 'Could you take the beaker at A and pour it into the container at C, then put it back?'


def call(path, body=None, token=None):
    headers = {'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})}
    request = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                     headers=headers, method='GET' if body is None else 'POST')
    return json.load(urllib.request.urlopen(request, timeout=120))


def wait(sid, token, done):
    while True:
        state = call(f'/api/sessions/{sid}', token=token)
        if done(state):
            return state
        time.sleep(.25)


session = call('/api/sessions', {})
sid, token = session['session_id'], session['access_token']
started = time.time()
call(f'/api/sessions/{sid}/request', {'text': TEXT, 'client_request_id': 'live-check'}, token)
state = wait(sid, token, lambda s: s.get('pending') or (s['tasks'] and s['tasks'][-1]['status'] in
                                                           ('failed', 'needs_clarification', 'completed')))
task, pending = state['tasks'][-1], state.get('pending')
result = {'text': TEXT, 'route': task.get('route'), 'request_to_proposal_s': round(time.time() - started, 2),
          'proposal': (pending or {}).get('summary'), 'status_before_consent': task['status']}
if pending:
    exact = {'request_id': pending['request_id'], 'proposal_version': pending['proposal_version']}
    call(f'/api/sessions/{sid}/present', exact, token)
    call(f'/api/sessions/{sid}/confirm', exact, token)
    state = wait(sid, token, lambda s: s['tasks'][-1]['status'] in ('completed', 'failed', 'cancelled'))
    task = state['tasks'][-1]
observation = task['observations'][-1] if task.get('observations') else {}
runs = task.get('expert_runs', [])
result.update(status=task['status'], request_to_result_s=round(time.time() - started, 2),
              executions=len(task.get('execution', [])), observation=observation.get('status'),
              checks=observation.get('checks'), answer=state['messages'][-1]['text'],
              expert_runs=len(runs), model_calls=sum(r.get('calls') or 0 for r in runs),
              requested_model=next((r.get('requested_model') for r in runs), None),
              actual_model=next((r.get('actual_model') for r in runs), None), session_id=sid)
print(json.dumps(result, indent=2))
