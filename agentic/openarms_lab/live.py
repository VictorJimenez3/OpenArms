"""Gemini Live server proxy using google-genai, never public API credentials.

API behavior verified against Google's Live SDK, tools and session-management docs:
https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk
https://ai.google.dev/gemini-api/docs/live-api/tools
https://ai.google.dev/gemini-api/docs/live-api/session-management
Synchronous function calling is portable; do not enable NON_BLOCKING by assumption.
"""
from __future__ import annotations
import asyncio
import base64
import json
import os
from starlette.websockets import WebSocketDisconnect
from google import genai
from google.genai import types
from .voice_controls import VoiceControls

TOOLS=[{'function_declarations':[
    {'name':'request_action','description':'Propose a supported action for explicit student confirmation in the UI. NEVER executes or confirms. Say you are checking the skill catalog first.',
     'parameters':{'type':'OBJECT','properties':{'text':{'type':'STRING'}},'required':['text']}},
    {'name':'select_experiment','description':'Select the student requested experiment by its exact ID. Read available_experiments from get_lab_state first if needed.',
     'parameters':{'type':'OBJECT','properties':{'experiment_id':{'type':'STRING'}},'required':['experiment_id']}},
    {'name':'prepare_next_trial','description':'Prepare/reset the MOCK apparatus for the next trial at the student request. Physical reset belongs to the bench operator.',
     'parameters':{'type':'OBJECT','properties':{}}},
    {'name':'student_confirm','description':'Confirm only after the student explicitly says yes, confirm or execute AFTER the current proposal was presented. If the proposal has a simulation preview, wait until its status is ready. Must use its exact request_id. Server independently checks the input transcript. This is student consent only, never bench operator authorization.',
     'parameters':{'type':'OBJECT','properties':{'request_id':{'type':'STRING'}},'required':['request_id']}},
    {'name':'cancel_request','description':'Cancel the current pending proposal by exact request_id. For active execution use stop_lab.',
     'parameters':{'type':'OBJECT','properties':{'request_id':{'type':'STRING'}},'required':['request_id']}},
    {'name':'record_prediction','description':'Record the student prediction in their own words before a trial.',
     'parameters':{'type':'OBJECT','properties':{'text':{'type':'STRING'}},'required':['text']}},
    {'name':'get_lab_state','description':'Get current experiment, capabilities, requests, observations and notebook. Controller completion is not verified success.',
     'parameters':{'type':'OBJECT','properties':{}}},
    {'name':'answer_question','description':'Record and evaluate the student answer to the CURRENT question.',
     'parameters':{'type':'OBJECT','properties':{'question_id':{'type':'STRING'},'answer':{'type':'STRING'}},'required':['question_id','answer']}},
    {'name':'stop_lab','description':'Request STOP immediately. Never delay STOP for clarification.',
     'parameters':{'type':'OBJECT','properties':{}}},
]}]

def key():return os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
def compact(context):
    c=context()
    return {k:(v[-16:] if k in ('notebook','messages') else v) for k,v in c.items() if k not in ('dedupe',)}
def system_prompt(context):
    return ('You are OpenArms, a concise supportive science learning companion. The student is the scientist: '
      'ask for their question, prediction and controlled-variable decisions. Use the tools to record their prediction, '
      'select experiments, prepare the next trial, propose/correct/cancel actions, read instructions and assess quiz answers. After presenting the exact proposal, ask the student to say confirm or cancel. When the pending proposal has a preview, it is a SIMULATED run shown first: describe its result and notes as SIMULATED and ask the student to say execute to run it for real. Call student_confirm only in a NEW user turn with an explicit yes/confirm/execute; never infer confirmation from a prediction, command, silence or your own speech. '
      'Physical operator authorization is separate. For supported operations quote the known stations and parameters exactly. '
      'Ask clarification for ambiguous requests. Never invent sensors, pictures, real science outcomes or physical success. '
      'Distinguish REAL, SIMULATED, MOCK, MODEL-PREDICTED and UNKNOWN in speech. The buoyancy demo uses MOCK transfer '
      'and analytical MODEL-PREDICTED float/sink, not a physical measurement or Isaac simulation. '
      'Say a short acknowledgement while planning, then use request_action. Speak briefly while execution is running, '
      'and base questions and comparisons on notebook evidence. Do not claim model-predicted values were observed. '
      'An unverified controller completion means outcome UNKNOWN. STOP bypasses reasoning through the UI. '
      'Initial authoritative lab state:\n'+json.dumps(compact(context),ensure_ascii=False))

class ClientClosed(Exception):pass
class Reconnect(Exception):pass

async def serve_live(websocket,context,tool_call,on_disconnect,*,client_factory=None,reconnect_delay=.5):
    """Accepted same-origin browser websocket; PCM in/out plus explicit app tools."""
    controls=VoiceControls(context,tool_call)
    client=None
    seen={}
    resumable=None
    cancelled=set()
    proposals={}
    pending={}
    send_lock=asyncio.Lock()
    async def emit(data):
        async with send_lock:await websocket.send_json(data)
    async def record(role,text):
        if text:
            await emit({'type':'transcript','role':role,'text':text})
            await tool_call('_record_transcript',{'role':role,'text':text})
    try:
        if not key() and client_factory is None:
            await emit({'type':'error','message':'Gemini API key is unavailable. Text controls and the mock lab remain available.'})
            return
        client=client_factory() if client_factory else genai.Client(api_key=key(),http_options={'api_version':'v1beta'})
        for attempt in range(4):
            config=types.LiveConnectConfig(response_modalities=['AUDIO'],system_instruction=system_prompt(context),
                tools=TOOLS,input_audio_transcription={},output_audio_transcription={},
                session_resumption=types.SessionResumptionConfig(handle=resumable),
                context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()))
            tasks=[]
            try:
                await emit({'type':'status','status':'connecting' if attempt==0 else 'reconnecting'})
                async with client.aio.live.connect(model=os.getenv('GEMINI_LIVE_MODEL','gemini-3.8-live'),config=config) as session:
                    await emit({'type':'status','status':'connected'})
                    await session.send_client_content(turns=types.Content(role='user',parts=[types.Part(text=
                        'Voice has just started. Briefly introduce the available experiments and how to choose one by voice. '
                        'Do not change state or propose any action until the student asks.')]),turn_complete=True)
                    async def upstream():
                        while True:
                            try: msg=await websocket.receive_json()
                            except (WebSocketDisconnect,RuntimeError):raise ClientClosed()
                            kind=msg.get('type')
                            if kind=='close':raise ClientClosed()
                            if kind=='audio':
                                raw=base64.b64decode(msg.get('data',''),validate=True)
                                if not raw or len(raw)>64000 or len(raw)%2:
                                    await emit({'type':'error','message':'Invalid microphone PCM frame.'});continue
                                await session.send_realtime_input(audio=types.Blob(data=raw,mime_type='audio/pcm;rate=16000'))
                            elif kind=='audio_end':await session.send_realtime_input(audio_stream_end=True)
                            elif kind=='text':
                                text=str(msg.get('text','')).strip()
                                if not text or len(text)>4000:continue
                                if text.lower() in ('stop','stop now','emergency stop','cancel'):
                                    await tool_call('stop_lab',{})
                                    await emit({'type':'interrupted'})
                                    continue
                                controls.input(text,finished=True)
                                await record('user',text)
                                await session.send_client_content(turns=types.Content(role='user',parts=[types.Part(text=text)]),turn_complete=True)
                    async def run_tool(call):
                        cid=call.id
                        try:
                            if cid in cancelled:return
                            if cid in seen:result=seen[cid]
                            elif call.name not in {f['name'] for f in TOOLS[0]['function_declarations']}:
                                result={'error':'Tool is not allowed.'}
                            else:
                                try:result=await asyncio.wait_for(controls.dispatch(call.name,{**dict(call.args or {}),**({'_tool_call_id':cid} if call.name=='request_action' else {})}),timeout=35)
                                except Exception as exc:
                                    if call.name=='request_action':await tool_call('_cancel_tool_request',{'tool_call_id':cid})
                                    result={'error':str(exc)[:500]}
                                if call.name=='request_action' and result.get('pending'):
                                    proposals[cid]=result['pending']['request_id']
                                seen[cid]=result
                            if cid not in cancelled:
                                # Live requires explicit responses; SDK auto function calling is not supported.
                                await session.send_tool_response(function_responses=[types.FunctionResponse(id=cid,name=call.name,response={'result':result})])
                        finally:pending.pop(cid,None)
                    async def downstream():
                        nonlocal resumable
                        while True:
                            async for response in session.receive():
                                update=response.session_resumption_update
                                if update and update.resumable and update.new_handle:resumable=update.new_handle
                                if response.go_away:raise Reconnect('Provider requested connection renewal.')
                                if response.tool_call_cancellation:
                                    for cid in response.tool_call_cancellation.ids:
                                        cancelled.add(cid)
                                        task=pending.get(cid)
                                        if task:task.cancel()
                                        await tool_call('_cancel_tool_request',{'tool_call_id':cid,'request_id':proposals.get(cid)})
                                    await emit({'type':'interrupted'})
                                sc=response.server_content
                                if sc and sc.input_transcription:
                                    transcription=sc.input_transcription
                                    fragment=transcription.text or ''
                                    controls.input(fragment,finished=bool(getattr(transcription,'finished',False)))
                                    await record('user',fragment)
                                    if controls.finished.is_set() and controls.text.strip().lower().rstrip('.!') in ('stop','stop now','emergency stop'):
                                        await tool_call('stop_lab',{})
                                        controls.consumed=True
                                        await emit({'type':'interrupted'})
                                if response.tool_call:
                                    for call in response.tool_call.function_calls:
                                        if call.id not in pending and call.id not in cancelled:
                                            pending[call.id]=asyncio.create_task(run_tool(call))
                                sc=response.server_content
                                if sc:
                                    if sc.interrupted:await emit({'type':'interrupted'})
                                    if sc.output_transcription and sc.output_transcription.text:
                                        await record('assistant',sc.output_transcription.text)
                                    if sc.model_turn:
                                        for part in sc.model_turn.parts:
                                            if part.inline_data and part.inline_data.data:
                                                await emit({'type':'audio','data':base64.b64encode(part.inline_data.data).decode()})
                                    if sc.turn_complete:await emit({'type':'status','status':'listening'})
                                if response.usage_metadata:
                                    await tool_call('_record_usage',{'usage':response.usage_metadata.model_dump(mode='json',exclude_none=True)})
                            await asyncio.sleep(0) # receive() ends each turn, not the whole conversation
                    async def updates():
                        last=None
                        while True:
                            await asyncio.sleep(.4)
                            snap=context()
                            requests=snap.get('requests',[])
                            marker=(tuple((r['request_id'],r['status']) for r in requests),snap.get('experiment',{}).get('id'))
                            if last is not None and marker!=last:
                                grounding={'experiment':snap['experiment'],'requests':requests[-2:],
                                  'observations':snap.get('observations',[])[-4:],'quiz':snap.get('quiz')}
                                await session.send_client_content(turns=types.Content(role='user',parts=[types.Part(text='Authoritative lab state update. Briefly explain current status/evidence to the student: '+json.dumps(grounding))]),turn_complete=True)
                            last=marker
                    tasks=[asyncio.create_task(upstream()),asyncio.create_task(downstream()),asyncio.create_task(updates())]
                    done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                    for task in done:task.result()
            except ClientClosed:return
            except (WebSocketDisconnect,RuntimeError) as exc:
                if isinstance(exc,WebSocketDisconnect):return
                if attempt==3:raise
                await on_disconnect()
                await emit({'type':'status','status':'reconnecting','message':'Provider connection interrupted.'})
            except asyncio.CancelledError:raise
            except Exception as exc:
                if attempt==3:raise
                # No stale proposal survives reconnect; never replay commands or tools.
                await on_disconnect()
                await emit({'type':'status','status':'reconnecting','message':type(exc).__name__})
            finally:
                for task in tasks:task.cancel()
                for task in list(pending.values()):task.cancel()
                await asyncio.gather(*tasks,*list(pending.values()),return_exceptions=True)
                pending.clear()
            await asyncio.sleep(reconnect_delay*(attempt+1))
    except (WebSocketDisconnect,ClientClosed):pass
    except Exception as exc:
        # Don't send provider exception strings: they can contain authentication URLs.
        try:await emit({'type':'error','message':f'Gemini Live unavailable ({type(exc).__name__}). Reconnect or use text controls.'})
        except Exception:pass
    finally:
        await on_disconnect()
        if client is not None:
            await client.aio.aclose()
        try:await websocket.close()
        except Exception:pass

async def _text_generate_reply(text,context,tool_call):
    """Same grounded Gemini tools for text-only clients, with bounded tool rounds."""
    if not key():raise ValueError('Gemini credentials are not configured.')
    controls=VoiceControls(context,tool_call)
    controls.input(text,finished=True)
    c=genai.Client(api_key=key())
    messages=[types.Content(role='user',parts=[types.Part(text=text)])]
    try:
        for _ in range(5):
            response=await c.aio.models.generate_content(model=os.getenv('OPENARMS_TEXT_MODEL','gemini-3.8-flash'),contents=messages,
                config=types.GenerateContentConfig(system_instruction=system_prompt(context),tools=TOOLS,
                  automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
            if response.usage_metadata:await tool_call('_record_usage',{'usage':response.usage_metadata.model_dump(mode='json',exclude_none=True)})
            calls=response.function_calls
            if not calls:return response.text or 'Please review the lab state and proposal.'
            messages.append(response.candidates[0].content)
            responses=[]
            for call in calls:
                if call.name not in {f['name'] for f in TOOLS[0]['function_declarations']}:result={'error':'Tool is not allowed.'}
                else:
                    try:result=await controls.dispatch(call.name,dict(call.args or {}))
                    except Exception as exc:result={'error':str(exc)[:500]}
                responses.append(types.Part.from_function_response(name=call.name,response={'result':result}))
            messages.append(types.Content(role='tool',parts=responses))
        return 'Please review the current proposal or clarify your instruction.'
    finally:await c.aio.aclose()

async def text_reply(text,context,tool_call):
    """Text uses the same supported Live model; ordinary generateContent is opt-in."""
    if os.getenv('OPENARMS_TEXT_TRANSPORT','live')=='generate':
        return await _text_generate_reply(text,context,tool_call)
    if not key():raise ValueError('Gemini credentials are not configured.')
    controls=VoiceControls(context,tool_call)
    controls.input(text,finished=True)
    client=genai.Client(api_key=key(),http_options={'api_version':'v1beta'})
    try:
        config=types.LiveConnectConfig(response_modalities=['AUDIO'],system_instruction=system_prompt(context),
            tools=TOOLS,output_audio_transcription={})
        async with client.aio.live.connect(model=os.getenv('GEMINI_LIVE_MODEL','gemini-3.8-live'),config=config) as session:
            await session.send_client_content(turns=types.Content(role='user',parts=[types.Part(text=text)]),turn_complete=True)
            transcript=[];tool_ids=set();rounds=0
            while rounds<6:
                rounds+=1
                async for response in session.receive():
                    if response.usage_metadata:
                        await tool_call('_record_usage',{'usage':response.usage_metadata.model_dump(mode='json',exclude_none=True)})
                    if response.tool_call:
                        replies=[]
                        for call in response.tool_call.function_calls:
                            if call.id in tool_ids:continue
                            tool_ids.add(call.id)
                            if call.name not in {f['name'] for f in TOOLS[0]['function_declarations']}:
                                result={'error':'Tool is not allowed.'}
                            else:
                                try:result=await controls.dispatch(call.name,dict(call.args or {}))
                                except Exception as exc:result={'error':str(exc)[:500]}
                            replies.append(types.FunctionResponse(id=call.id,name=call.name,response={'result':result}))
                        if replies:await session.send_tool_response(function_responses=replies)
                    sc=response.server_content
                    if sc and sc.output_transcription and sc.output_transcription.text:transcript.append(sc.output_transcription.text)
                    if sc and sc.turn_complete and transcript:return ''.join(transcript)
            return ''.join(transcript) or 'Please review your lab state and try a shorter question.'
    finally:await client.aio.aclose()
