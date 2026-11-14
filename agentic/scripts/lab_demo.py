"""Repeatable complete mock-backed student flow plus cold/warm skill comparison.

No hardware imports or calls. --live-expert opts into one paid Gemini composition call.
"""
import argparse,asyncio,json,os,tempfile,time
from pathlib import Path
from dotenv import load_dotenv
from agentic.openarms_lab.runtime import Lab,LabError
from agentic.openarms_lab.backends import MockBackend

async def run(output,live_expert=False,env_file=None):
    if live_expert:
        if env_file:load_dotenv(env_file)
        if not (os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')):
            raise RuntimeError('--live-expert needs server-side Gemini credentials.')
    else:
        os.environ.pop('GEMINI_API_KEY',None);os.environ.pop('GOOGLE_API_KEY',None)
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='openarms-demo-') as directory:
        lab=Lab(Path(directory),backend_factory=lambda:MockBackend(delay=.002))
        s=await lab.create();sid=s['session_id']
        await lab.prediction(sid,'Sample A will float; Sample C should sink because water density is between them.')
        s=await lab.request(sid,'test sample at A in B','original')
        first=s['pending']['request_id']
        s=await lab.request(sid,'test sample at C in B','correction')
        corrected=s['pending']['request_id']
        try:await lab.confirm(sid,first)
        except LabError:pass
        else:raise AssertionError('Stale confirmation accepted')
        await lab.cancel(sid,corrected)
        s=await lab.request(sid,'test sample at A in B','trial-one')
        pid=s['pending']['request_id']
        await lab.request(sid,'test sample at A in B','trial-one')
        assert len(lab.get(sid)['requests'])==3
        await lab.confirm(sid,pid)
        try:await lab.confirm(sid,pid)
        except LabError:pass
        else:raise AssertionError('Duplicate confirmation accepted')
        await lab.tasks[sid]
        s=lab.snapshot(sid)
        assert s['requests'][-1]['status']=='completed'
        await lab.answer(sid,s['quiz']['id'],'A')
        await lab.prepare(sid)
        await lab.prediction(sid,'Sample C will sink because its density exceeds water.')
        s=await lab.request(sid,'test sample at C in B','trial-two')
        await lab.confirm(sid,s['pending']['request_id']);await lab.tasks[sid]
        s=lab.snapshot(sid)
        models=[o for o in s['observations'] if o['provenance']=='MODEL-PREDICTED']
        assert [o['value'] for o in models]==['floats','sinks']
        await lab.answer(sid,s['quiz']['id'],'Sample A is less dense than water and floats in the model. Sample C is denser and sinks. Buoyant force equals the weight of displaced water; these are model predictions, not physical measurements.')
        start=time.perf_counter()
        candidate=await lab.registry.compose('transfer sample from A to B and observe the destination')
        cold_ms=(time.perf_counter()-start)*1000
        evidence=lab.registry.test_candidate(candidate['skill_id'])
        promoted=lab.registry.promote(candidate['skill_id'],evidence['evidence_id'])
        cases=[
            ('move the sample from station A to station B and inspect','resolved','A'),
            ('transfer orange from C to B and observe','resolved','C'),
            ('test sample at A in B','resolved','A'),
            ('move sample from A to D','unsupported',None),
            ('move sample','clarify',None),
            ('move apple from A to B','unsupported',None),
            ('move sample from A or C to B','clarify',None),
        ]
        results=[]
        for text,status,source in cases:
            start=time.perf_counter();result=lab.registry.resolve(text);elapsed=(time.perf_counter()-start)*1000
            correct=result['status']==status and (source is None or result.get('parameters',{}).get('source')==source)
            results.append({'instruction':text,'expected':status,'actual':result['status'],'correct':correct,'latency_ms':elapsed,'metrics':result['metrics']})
        assert all(r['correct'] for r in results),results
        await lab.prepare(sid);await lab.prediction(sid,'The mock transfer should place A at B; science remains model-predicted.')
        s=await lab.request(sid,'move the sample from station A to station B and inspect','warm')
        assert s['pending']['skill_id']==promoted['skill_id']
        await lab.confirm(sid,s['pending']['request_id']);await lab.tasks[sid]
        snapshot=lab.snapshot(sid)
        assert snapshot['requests'][-1]['status']=='completed'
        assert any(e['kind']=='skill_step' and e['data']['action']=='observe' for e in snapshot['notebook'])
        assert not any(o['provenance']=='REAL' for o in snapshot['observations'])
        report={'scenario':'prediction, proposal, correction, stale rejection, cancellation, duplicate protection, execution, evidence, quiz, second variable, expert compose/test/promote, fast reuse',
            'backend':'MOCK','physical_actuation':False,'completed_trials':3,
            'cold':{'expert_mode':candidate['expert_mode'],'model_calls':candidate['model_calls'],'tokens':candidate['tokens'],'planning_ms':cold_ms,'cost_usd':None,'cost_note':'Dollar cost not measured; provider token usage recorded when supplied.'},
            'warm':{'model_calls':0,'tokens':0,'cases':len(results),'correct':sum(r['correct'] for r in results),'routing_latency_ms_mean':sum(r['latency_ms'] for r in results)/len(results),'results':results},
            'execution_duration_excluded_from_planning':True,'candidate':candidate,'test_evidence':evidence}
        (output/'demo-notebook.json').write_text(json.dumps(snapshot,indent=2))
        (output/'skill-evaluation.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({k:v for k,v in report.items() if k not in ('candidate','test_evidence')},indent=2))
        await lab.shutdown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('outputs/lab-evidence'));p.add_argument('--live-expert',action='store_true');p.add_argument('--env-file',type=Path);a=p.parse_args()
    asyncio.run(run(a.output,a.live_expert,a.env_file))
