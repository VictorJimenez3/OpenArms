"""One student lifecycle across text, Gemini tools and every execution adapter."""
from __future__ import annotations
import asyncio
import copy
import os
import time
import uuid
from pathlib import Path
from .backends import MockBackend, TransferRunnerAdapter
from .contracts import Parameters, SkillRequest
from .store import Store
from .voice_controls import MUTATING_TOOLS
from agentic.openarms_agent.validator import validate as validate_legacy

TERMINAL={'completed','failed','stopped','unknown','cancelled','rejected','expired'}

class LabError(ValueError):
    pass

class Lab:
    def __init__(self, data_dir:Path, *, backend_factory=None, registry=None, execution_timeout=60, confirmation_ttl=120):
        from .skills import SkillRegistry
        self.store=Store(data_dir/'lab.sqlite3')
        self.registry=registry or SkillRegistry(data_dir/'skills.json')
        from .recipes import install_recipes
        install_recipes(self.registry)
        self.sessions={}
        self.backends={}
        self.tasks={}
        self.subscribers={}
        self.execution_timeout,self.confirmation_ttl=execution_timeout,confirmation_ttl
        self.backend_factory=backend_factory
        self.physical=None
        self.motion_lock=asyncio.Lock()
        self.physical_owner=None
        self.physical_unavailable=False
        self.model_tasks={}
        self.locks={}
    def _backend(self,sid):
        if sid not in self.backends:
            if self.backend_factory:
                backend=self.backend_factory()
            elif os.getenv('OPENARMS_BACKEND','mock')=='physical':
                if self.physical is None:
                    checkout=os.environ.get('OPENARMS_HARDWARE_CHECKOUT')
                    if not checkout:
                        raise LabError('Physical mode needs OPENARMS_HARDWARE_CHECKOUT and an explicitly configured runner.')
                    self.physical=TransferRunnerAdapter.load(checkout,os.getenv('OPENARMS_RUNNER','firmware.openarms_executor.transfer_runner:create_runner'))
                backend=self.physical
            elif os.getenv('OPENARMS_BACKEND','mock')=='mock':
                backend=MockBackend()
            else:
                raise LabError('Unsupported backend. Attach a simulation adapter through backend_factory; mock never imports hardware.')
            self.backends[sid]=backend
        return self.backends[sid]
    def _event(self,s,kind,**data):
        s['notebook'].append(self.store.event(s['session_id'],kind,**data))
    def _message(self,s,role,text):
        s['messages'].append({'role':role,'text':text})
        self._event(s,'message',role=role,text=text)
    def get(self,sid):
        if sid not in self.sessions:
            s=self.store.load(sid)
            if s is None: raise KeyError('Session not found.')
            # History is recoverable, confirmation and motion are not replayable after process restart.
            s['pending']=None
            s['connected']=False
            for r in s['requests']:
                if r['status'] not in TERMINAL:
                    r['status']='unknown'
                    r['reason']='Server restarted; motion is never resumed automatically.'
            self.sessions[sid]=s
            self._event(s,'recovery',text='History restored. Establish a new session before another trial.')
            self._backend(sid)._state['armed']=False
        return self.sessions[sid]
    def snapshot(self,sid):
        s=self.get(sid)
        s['state']=self._backend(sid).state()
        s['capabilities']=self._backend(sid).capabilities()
        s['skills']=self.registry.list()
        snap=copy.deepcopy(s)
        from .learning import EXPERIMENTS
        snap['available_experiments']=copy.deepcopy(EXPERIMENTS)
        return snap
    async def publish(self,s):
        snap=self.snapshot(s['session_id'])
        self.store.save(snap)
        for q in tuple(self.subscribers.get(s['session_id'],())):
            if q.full():
                try: q.get_nowait()
                except asyncio.QueueEmpty: pass
            q.put_nowait({'type':'state','state':snap})
        return snap
    async def create(self,experiment_id='buoyancy'):
        from .learning import EXPERIMENTS,get_experiment
        # Accept the lesson module's canonical buoyancy identifier.
        try: exp=get_experiment(experiment_id)
        except ValueError: exp=next(x for x in EXPERIMENTS if 'buoy' in x['id'])
        sid=str(uuid.uuid4())
        b=self._backend(sid)
        if b.mode=='physical':
            exp=next(x for x in EXPERIMENTS if 'transfer' in x['id'])
        obj='mandarin' if 'transfer' in exp['id'] else 'sample'
        if isinstance(b,MockBackend): b.prepare(obj,exp['id'])
        s={'session_id':sid,'experiment':exp,'prediction':'','backend':b.mode,'state':b.state(),
           'pending':None,'requests':[],'observations':[],'quiz':None,'notebook':[],
           'messages':[],'skills':self.registry.list(),'connected':True,'dedupe':{},'generation':0}
        self.sessions[sid]=s
        self._event(s,'session_created',backend=b.mode,experiment=exp['id'])
        self._message(s,'assistant',f"Welcome. {exp['question']} Choose your prediction before requesting a trial. Backend: {b.mode.upper()}.")
        return await self.publish(s)
    def _busy(self,s):
        return any(r['status'] in ('approved','awaiting_operator','executing','stopping') for r in s['requests'])
    def _invalidate(self,s,reason):
        if s['pending']:
            r=s['pending']
            if r['status']=='requested':
                r['status']='cancelled'
                r['reason']=reason
                self._event(s,'request_cancelled',request_id=r['request_id'],reason=reason)
            s['pending']=None
    async def select_experiment(self,sid,experiment_id):
        from .learning import get_experiment
        s=self.get(sid)
        if self._busy(s): raise LabError('Stop the current execution before changing experiment.')
        e=get_experiment(experiment_id)
        if s['backend']=='physical' and 'transfer' not in e['id']:
            raise LabError('The physical adapter currently supports mandarin transfer only; this lesson has no validated apparatus.')
        self._invalidate(s,'Experiment changed.')
        s.update(experiment=e,prediction='',quiz=None)
        if isinstance(self._backend(sid),MockBackend): self._backend(sid).prepare('mandarin' if 'transfer' in e['id'] else 'sample',e['id'])
        self._event(s,'experiment_selected',experiment=e)
        return await self.publish(s)
    async def prediction(self,sid,text):
        s=self.get(sid)
        if self._busy(s): raise LabError('Record a prediction before the next trial, not during an active trial.')
        if not text.strip(): raise LabError('Enter your prediction first.')
        self._invalidate(s,'Prediction changed.')
        s['prediction']=text.strip()
        self._event(s,'prediction',text=text.strip(),experiment_id=s['experiment']['id'])
        return await self.publish(s)
    def _validate(self,s,skill_id,params):
        try: p=Parameters.model_validate(params)
        except Exception as exc: raise LabError(f'Unsupported parameters: {exc}') from exc
        skill=self.registry.get(skill_id)
        if skill.get('status') not in ('active','approved'):
            raise LabError('Skill has not been tested and promoted.')
        # Only these high-level bindings are executable. Generated trajectories never enter this runtime.
        transfer={'action':'transfer','args':{'source':'$source','destination':'$destination','object':'$object'}}
        observe={'action':'observe','args':{'station':'$destination'}}
        dilution=s['experiment']['id']=='color_dilution' and skill_id=='premeasured_dilution.v1'
        dose=[{'action':'add_sample','args':{'source':'$source','into':'$destination','portions':1}}]
        if skill.get('steps') not in ([transfer],[transfer,observe]) and not (dilution and skill.get('steps')==dose):
            raise LabError('Skill definition has unsupported steps or parameter bindings.')
        b=self._backend(s['session_id'])
        if b.mode=='physical' and skill.get('approval_scopes',{}).get('physical') not in ('approved','team_reported_baseline_only'):
            raise LabError('This skill has mock approval only; physical skill validation is pending.')
        caps=b.capabilities()
        if [p.source,p.destination] not in caps['routes'] or p.object not in caps['objects']:
            raise LabError('This controller has no validated capability for that object or station route.')
        expected='mandarin' if 'transfer' in s['experiment']['id'] else 'sample'
        if p.object!=expected:
            raise LabError(f'This experiment uses {expected}. Choose the corresponding experiment or correct your request.')
        legacy={'plan_id':'validation','student_instruction':'Validated skill invocation',
                'steps':[{'action':'move_block','args':{'from':p.source,'to':p.destination}}]}
        state=b.state()
        if dilution:
            legacy['steps']=[{'action':'add_sample','args':{'source':p.source,'into':p.destination,'portions':1}}]
        # The existing independent validator owns station occupancy and empty-gripper invariants.
        stations={name:{'kind':'point','holds':value} for name,value in state['point_holds'].items()}
        if dilution:stations={'A':{'kind':'source','portions':1},'C':{'kind':'source','portions':1},'B':{'kind':'receiver','capacity':1}}
        v=validate_legacy(legacy,state,stations)
        if not v['ok']: raise LabError(v['reason'])
        return p,v
    async def request(self,sid,text,client_request_id=None):
        s=self.get(sid)
        if len(text)>4000: raise LabError('Please shorten that instruction.')
        # Exact STOP/cancel is handled before routing or any provider call.
        if text.strip().lower() in ('stop','emergency stop','stop now','cancel'):
            return await self.stop(sid)
        cid=client_request_id or str(uuid.uuid4())
        if cid in s['dedupe']:
            if s['dedupe'][cid]['text']!=text: raise LabError('Idempotency key was reused for different input.')
            return await self.publish(s)
        if self._busy(s): raise LabError('An action is active. Stop or wait before requesting another.')
        self._invalidate(s,'New instruction superseded the proposal.')
        self._message(s,'user',text)
        s['dedupe'][cid]={'text':text}
        if not s['connected']: s['connected']=True
        if not s['prediction']:
            self._message(s,'assistant','What do you predict will happen, and why? Record your prediction before a trial.')
            return await self.publish(s)
        route_text=text
        if s['experiment']['id']=='color_dilution':
            # Lesson-specific nouns map to the same bounded parameter resolver.
            import re
            route_text=re.sub(r'\b(?:one premeasured water portion|water portion|water|a portion)\b','sample',text,flags=re.I)
            route_text=re.sub(r'\b(?:add|pour|dilute)\b','transfer',route_text,flags=re.I)
        routed=self.registry.resolve(route_text)
        if s['experiment']['id']=='color_dilution' and routed['status']=='resolved':
            # Only a single transfer maps to this dose-only recipe. A composite
            # request must not lose its observation or any other requested step.
            if routed['skill_id']=='known_station_transfer.v1':
                routed['skill_id']='premeasured_dilution.v1'
                # Keep the recognized object: an orange request cannot silently become a water dose.
            else:
                routed={**routed,'status':'unsupported','message':(
                    'This dilution recipe can add one premeasured water portion only. '
                    'It cannot carry out the additional steps in your request. '
                    'Please revise your request; nothing has started.')}
        self._event(s,'routing',instruction=text,result=routed)
        if routed['status']!='resolved':
            self._message(s,'assistant',routed.get('message','Please name the source A or C and destination B.'))
            return await self.publish(s)
        try:
            params,v=self._validate(s,routed['skill_id'],routed['parameters'])
        except LabError as exc:
            self._event(s,'validation_rejected',reason=str(exc))
            self._message(s,'assistant',str(exc))
            return await self.publish(s)
        request=SkillRequest(request_id=str(uuid.uuid4()),session_id=sid,skill_id=routed['skill_id'],parameters=params)
        r={**request.model_dump(),'client_request_id':cid,'status':'requested','expires_at':time.time()+self.confirmation_ttl,
           'summary':(f'Add the premeasured water cup at {params.source} into dye receiver {params.destination} (MOCK)' if s['experiment']['id']=='color_dilution' else f'Transfer {params.object} from {params.source} to {params.destination}'),
           'student_confirmed':False,'operator_authorized':False,'validation':v,'metrics':routed.get('metrics',{})}
        s['requests'].append(r)
        s['pending']=r
        self._event(s,'request_proposed',request_id=r['request_id'],request=r)
        self._message(s,'assistant',f"I understood: {r['summary']}. Review it, then confirm or correct it. No motion has started.")
        return await self.publish(s)
    async def converse(self,sid,text,client_request_id=None):
        import re
        if not re.search(r"^\s*(?:what|why|how|explain|help me understand|tell me about|compare)\b",text,re.I):
            return await self.request(sid,text,client_request_id)
        s=self.get(sid)
        self._message(s,'user',text)
        await self.publish(s)
        from .live import text_reply,key
        if key():
            try:
                generation=s.get('generation',0)
                async def guarded(name,args):
                    if name in MUTATING_TOOLS and s.get('generation',0)!=args.pop('_voice_generation',generation):
                        raise LabError('This model turn was cancelled. Start a fresh instruction.')
                    return await self.tool(sid,name,args)
                task=asyncio.create_task(text_reply(text,lambda:self.snapshot(sid),guarded))
                self.model_tasks.setdefault(sid,set()).add(task)
                try:reply=await asyncio.wait_for(task,timeout=40)
                finally:self.model_tasks[sid].discard(task)
                if s.get('generation',0)!=generation:return await self.publish(s)
            except asyncio.CancelledError:
                return await self.publish(s)
            except Exception as exc:
                reply=f"The Gemini text service is unavailable ({type(exc).__name__}). You can still select a sample, record a prediction and run the mock trial."
        else:
            reply=("Offline lesson guidance: density is mass divided by volume. An ideal rigid sample less dense than water floats; "
                   "a denser sample sinks. These are analytical MODEL-PREDICTED expectations. Our mock controller only reports transfer state. "
                   "Choose A (0.8 g/mL) or C (1.2 g/mL), then record your prediction. What evidence would test it?") if 'buoy' in s['experiment']['id'] else (
                   "Offline guidance: transfer means moving the mandarin between known stations. Controller completion does not prove placement. "
                   "Independent observation is needed. Predict the outcome, then request A to B.")
        self._message(s,'assistant',reply)
        return await self.publish(s)
    async def confirm(self,sid,request_id):
        # Serialize confirmations; the first consumes the proposal before yielding.
        lock=self.locks.setdefault(sid,asyncio.Lock())
        async with lock:
            s=self.get(sid)
            r=s['pending']
            if r is None or r['request_id']!=request_id or r['status']!='requested':
                raise LabError('Stale or already consumed confirmation. Review the current proposal.')
            if r['expires_at']<=time.time() or not s['connected']:
                r['status']='expired';s['pending']=None
                self._event(s,'confirmation_rejected',request_id=request_id,reason='expired or disconnected')
                await self.publish(s)
                raise LabError('Confirmation expired. Please request a fresh action.')
            self._validate(s,r['skill_id'],r['parameters'])
            r.update(status='approved',student_confirmed=True)
            s['pending']=None
            self._event(s,'student_confirmed',request_id=request_id)
            self.tasks[sid]=asyncio.create_task(self._execute(s,r))
            return await self.publish(s)
    async def _safe_stop_backend(self,s,backend):
        if backend.mode=='physical' and self.physical_owner!=s['session_id']:
            return
        try:
            await backend.stop()
        except Exception as exc:
            if backend.mode=='physical':self.physical_unavailable=True
            self._event(s,'stop_failed',reason=type(exc).__name__,outcome='UNKNOWN',operator_recovery_required=True)
            raise LabError('Controller STOP failed; outcome UNKNOWN. Operator recovery is required.') from exc

    async def _execute(self,s,r):
        sid=s['session_id'];b=self._backend(sid)
        request=SkillRequest.model_validate({k:r[k] for k in ('request_id','session_id','skill_id','parameters')})
        async def progress(phase):
            r['phase']=phase
            self._event(s,'execution_progress',request_id=r['request_id'],phase=phase)
            await self.publish(s)
        acquired=False
        try:
            # Never queue physical commands behind another session's motion.
            if b.mode=='physical':
                if self.motion_lock.locked() or self.physical_unavailable:
                    r.update(status='rejected',reason='Another physical session owns the arm, or operator recovery is required.')
                    self._event(s,'execution_rejected',request_id=r['request_id'],reason=r['reason'])
                    return
                await self.motion_lock.acquire();acquired=True
                self.physical_owner=sid
            if r['status']!='approved': return
            if b.mode=='physical':
                r['status']='awaiting_operator'
                self._message(s,'assistant','Your request is confirmed. Waiting for the bench operator to authorize this exact action.')
                await self.publish(s)
                authorized=await asyncio.wait_for(b.authorize(request),timeout=self.execution_timeout)
                if not authorized:
                    r.update(status='rejected',reason='Physical operator declined authorization.')
                    self._event(s,'operator_rejected',request_id=r['request_id'])
                    return
                r['operator_authorized']=True
                self._event(s,'operator_authorized',request_id=r['request_id'])
            self._validate(s,r['skill_id'],r['parameters'])
            r['status']='executing'
            self._message(s,'assistant','The action is running. You can use STOP at any time.')
            await self.publish(s)
            result=await asyncio.wait_for(b.execute(request,progress),timeout=self.execution_timeout)
            if result.request_id!=r['request_id'] or result.backend!=b.mode:
                raise LabError('Execution result does not match this request/backend.')
            r.update(status=result.status,result=result.model_dump())
            self._event(s,'execution_result',request_id=r['request_id'],result=result.model_dump())
            if len(self.registry.get(r['skill_id']).get('steps',[]))>1:
                await progress('observing_destination')
                self._event(s,'skill_step',request_id=r['request_id'],action='observe',station=request.parameters.destination,
                    provenance=result.observation.provenance if result.observation else 'UNKNOWN')
            if result.observation:
                obs={**result.observation.model_dump(),'request_id':r['request_id'],'experiment_id':s['experiment']['id']}
                s['observations'].append(obs)
                self._event(s,'observation',**obs)
            if result.status=='completed':
                from .learning import model_observation,make_quiz
                if b.mode=='mock' and result.observation and result.observation.provenance=='MOCK':
                    modeled=model_observation(s['experiment']['id'],r['parameters'])
                    if modeled:
                        modeled={**modeled,'request_id':r['request_id'],'experiment_id':s['experiment']['id']}
                        s['observations'].append(modeled);self._event(s,'observation',**modeled)
                obs=[o for o in s['observations'] if o.get('experiment_id')==s['experiment']['id']]
                s['quiz']=make_quiz(s['experiment']['id'],obs,len([x for x in s['notebook'] if x['kind']=='observation' and x['data'].get('experiment_id')==s['experiment']['id'] and x['data'].get('provenance') in ('MOCK','REAL','SIMULATED','UNKNOWN')]))
                s['quiz']['template_id']=s['quiz']['id']
                s['quiz']['id']=s['quiz']['id']+'-'+r['request_id']
                self._event(s,'question',question=s['quiz'])
                self._message(s,'assistant',f"Controller completed ({b.mode.upper()}). "+(result.observation.text if result.observation else 'The experimental outcome is UNKNOWN.')+' '+s['quiz']['prompt'])
            else:
                await b.stop()
                self._message(s,'assistant',f"The action ended: {result.status}. {result.reason or 'Check the apparatus before another trial.'}")
        except asyncio.CancelledError:
            try:await self._safe_stop_backend(s,b)
            except LabError:pass
            r.update(status='unknown' if b.mode=='physical' and self.physical_unavailable else 'stopped',reason='Controller STOP failed; operator recovery required.' if b.mode=='physical' and self.physical_unavailable else 'Cancelled, disconnected or STOP requested; physical outcome may be unknown.')
            self._event(s,'execution_stopped',request_id=r['request_id'],reason=r['reason'])
        except Exception as exc:
            try:await self._safe_stop_backend(s,b)
            except LabError:pass
            r.update(status='unknown',reason=f'{type(exc).__name__}: {exc}')
            self._event(s,'execution_error',request_id=r['request_id'],reason=r['reason'])
            self._message(s,'assistant','Execution did not produce a verified outcome. '+r['reason'])
        finally:
            if acquired:
                self.physical_owner=None
                self.motion_lock.release()
            await self.publish(s)
    async def cancel(self,sid,request_id=None):
        s=self.get(sid)
        if request_id and (s['pending'] is None or s['pending']['request_id']!=request_id):
            raise LabError('That proposal is stale. Use STOP to cancel active execution.')
        self._invalidate(s,'Student cancelled.')
        return await self.publish(s)
    async def stop(self,sid,*,disconnect=False):
        s=self.get(sid)
        self._invalidate(s,'Session disconnected.' if disconnect else 'STOP requested.')
        t=self.tasks.get(sid)
        active=t is not None and not t.done()
        if active:
            for r in s['requests']:
                if r['status'] in ('approved','awaiting_operator','executing'): r['status']='stopping'
        s['generation']=s.get('generation',0)+1
        for model_task in tuple(self.model_tasks.get(sid,())):
            if model_task is not asyncio.current_task():model_task.cancel()
        self._event(s,'stop_requested',disconnect=disconnect)
        if disconnect: s['connected']=False
        await self.publish(s)  # acknowledge STOP without waiting for motion thread shutdown
        # The stop hook is called BEFORE cancellation. Legacy threaded motion remains tracked.
        # Never stop another student's physical execution when this session does not own it.
        if active or self._backend(sid).mode!='physical':
            try:await self._safe_stop_backend(s,self._backend(sid))
            except LabError:
                for request in s['requests']:
                    if request['status']=='stopping':request.update(status='unknown',reason='Controller STOP failed. Operator recovery required.')
        if active:
            t.cancel()
            try: await t
            except asyncio.CancelledError: pass
            for r in s['requests']:
                if r['status']=='stopping':
                    r.update(status='stopped',reason='STOP requested before execution started.')
                    self._event(s,'execution_stopped',request_id=r['request_id'],reason=r['reason'])
        return await self.publish(s)
    async def prepare(self,sid):
        s=self.get(sid)
        if self._busy(s): raise LabError('Wait for the current trial before preparing the apparatus.')
        b=self._backend(sid)
        if not isinstance(b,MockBackend): raise LabError('Physical apparatus reset belongs to the bench operator.')
        self._invalidate(s,'Mock apparatus reset.')
        b.prepare('mandarin' if 'transfer' in s['experiment']['id'] else 'sample',s['experiment']['id'])
        s.update(prediction='',quiz=None)
        self._event(s,'mock_apparatus_prepared',text='Samples reset to A and C; receiver B cleared. This is a MOCK reset.')
        return await self.publish(s)
    async def answer(self,sid,question_id,answer):
        from .learning import evaluate_answer
        s=self.get(sid)
        q=s['quiz']
        if not q or q['id']!=question_id: raise LabError('That question is stale.')
        if not answer.strip(): raise LabError('Enter your answer.')
        if q.get('answered'): raise LabError('This question has already been answered.')
        obs=[o for o in s['observations'] if o.get('experiment_id')==s['experiment']['id']]
        feedback=evaluate_answer(s['experiment']['id'],q,answer,obs)
        q.update(answered=True,answer=answer,feedback=feedback)
        self._event(s,'quiz_answer',question_id=question_id,answer=answer,evaluation=feedback)
        self._message(s,'assistant',feedback['feedback']+' '+feedback.get('follow_up',''))
        return await self.publish(s)
    async def tool(self,sid,name,args):
        if name=='get_lab_state': return self.snapshot(sid)
        if name=='select_experiment': return await self.select_experiment(sid,args['experiment_id'])
        if name=='prepare_next_trial': return await self.prepare(sid)
        if name=='cancel_request': return await self.cancel(sid,args['request_id'])
        if name=='student_confirm':
            consent=args.get('_voice_consent') or {}
            if consent.get('request_id')!=args.get('request_id') or not consent.get('text'):
                raise LabError('Student confirmation needs trusted explicit input for this proposal.')
            s=self.get(sid)
            # confirm() independently checks pending ID, expiry, connection and validation.
            result=await self.confirm(sid,args['request_id'])
            self._event(s,'voice_student_consent',request_id=args['request_id'],text=consent['text'],operator_authorized=False)
            return await self.publish(s)
        if name=='request_action': return await self.request(sid,args['text'],('live:'+args['_tool_call_id']) if args.get('_tool_call_id') else None)
        if name=='record_prediction': return await self.prediction(sid,args['text'])
        if name=='answer_question': return await self.answer(sid,args['question_id'],args['answer'])
        if name=='stop_lab': return await self.stop(sid)
        if name=='_cancel_tool_request':
            s=self.get(sid)
            if s['pending'] and ((args.get('request_id') and s['pending']['request_id']==args['request_id']) or (args.get('tool_call_id') and s['pending'].get('client_request_id')=='live:'+args['tool_call_id'])):
                self._invalidate(s,'Gemini tool call cancelled/interrupted.')
            return await self.publish(s)
        if name=='_record_transcript':
            s=self.get(sid)
            role=args['role'];text=args['text']
            # Transcripts are visible and durable, clearly distinguished from controller observations.
            self._message(s,role,text)
            return await self.publish(s)
        if name=='_record_usage':
            s=self.get(sid)
            self._event(s,'model_usage',**args)
            self.store.save(self.snapshot(sid))
            return {'recorded':True}
        raise LabError('Unknown lab tool.')
    async def shutdown(self):
        for sid in list(self.sessions): await self.stop(sid,disconnect=True)
        self.store.db.close()
