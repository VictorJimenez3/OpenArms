"""Minimal stdio MCP server for one mock planning tool. Never executes motion."""
import json
import os
from pathlib import Path
import sys
import uuid

SCHEMA = {'type':'object','properties':{'object':{'type':'string','enum':['mandarin']},'source':{'type':'string','enum':['A']},'destination':{'type':'string','enum':['B']}},'required':['object','source','destination'],'additionalProperties':False}

def dispatch(method, params, directory):
    if method == 'initialize':
        return {'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'openarms-mandarin','version':'1.0.0'}}
    if method == 'ping': return {}
    if method == 'tools/list':
        return {'tools':[{'name':'submit_plan','description':'Preview a fixed mock mandarin transfer A to B. Returns one plan ID. No physical movement.','inputSchema':SCHEMA}]}
    if method == 'tools/call':
        args = params.get('arguments',{})
        if params.get('name') != 'submit_plan' or args != {'object':'mandarin','source':'A','destination':'B'}:
            return {'content':[{'type':'text','text':'Rejected: only mandarin from A to B is supported.'}],'isError':True}
        path = directory/'plan.json'
        if path.exists():
            plan = json.loads(path.read_text())
        else:
            plan = {'plan_id':'plan-'+uuid.uuid4().hex,'object':'mandarin','source':'A','destination':'B','status':'preview_ready','preview':'placeholder','coordinates':None,'execution':'mock_only'}
            with path.open('x') as out: json.dump(plan,out)
        with (directory/'mcp-calls.jsonl').open('a') as out:
            out.write(json.dumps({'method':method,'tool':'submit_plan','arguments':args,'result':plan})+'\n')
        return {'content':[{'type':'text','text':json.dumps(plan)}],'isError':False}
    raise ValueError('Method not found')

def main():
    os.umask(0o077)
    directory=Path(sys.argv[1]).resolve()
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    for line in sys.stdin:
        try:
            req=json.loads(line)
            if 'id' not in req: continue
            result=dispatch(req['method'],req.get('params',{}),directory)
            response={'jsonrpc':'2.0','id':req['id'],'result':result}
        except Exception as exc:
            response={'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32601,'message':str(exc)}}
        print(json.dumps(response),flush=True)

if __name__ == '__main__': main()
