// Offline deterministic transport fixture. No runtime, model, hardware, or API keys.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { WebSocketServer } from 'ws';
const root = fileURLToPath(new URL('../', import.meta.url));
const sessions = new Map();
const conditions = [{id:'vinegar',title:'Vinegar'},{id:'baking_soda',title:'Baking-soda solution'},{id:'water',title:'Water'}];
const clients = new Map();
const traces = new Map();
const port = Number(process.env.OPENARMS_FIXTURE_PORT || 8766);
const clone = value => JSON.parse(JSON.stringify(value));
const snapshot = session => { const { token, ...state } = session; return clone(state); };
const send = (socket, frame) => socket?.readyState === 1 && socket.send(JSON.stringify(frame));
function publish(session) { session.revision++; send(clients.get(session.session_id), {type:'state',state:snapshot(session)}); return snapshot(session); }
function stop(session) { session.pending = null; session.state = 'STOPPED'; session.generation++; }
function proposal(session) {
  if (session.prediction && session.trial.condition_id) {
    session.pending = {request_id:randomUUID(),proposal_version:1,skill_id:'red_cabbage_ph',skill_version:'1',summary:`Run one mock red-cabbage indicator trial with ${conditions.find(c => c.id === session.trial.condition_id).title}. Use the reference color to discuss whether the sample is acidic, basic, or near neutral.`,condition_id:session.trial.condition_id,status:'pending',expires_at:new Date(Date.now()+300000).toISOString(),presented:false};
  }
}
function message(session, role, text, turnId=randomUUID()) { session.messages.push({id:randomUUID(),role,text,turn_id:turnId}); }
const server = http.createServer(async (request, response) => {
  const path = new URL(request.url,'http://localhost').pathname;
  let body = {};
  if (request.method === 'POST') { let raw=''; for await (const part of request) raw+=part; body = JSON.parse(raw || '{}'); }
  const json = (status, value) => { response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'}); response.end(JSON.stringify(value)); };
  if (path === '/fixture/scene.png') {
    response.writeHead(200,{'Content-Type':'image/png'});
    return response.end(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aNdcAAAAASUVORK5CYII=', 'base64'));
  }
  if (path === '/api/sessions' && request.method === 'POST') {
    if (request.headers['x-fixture-pairing'] && request.headers.authorization !== 'Bearer pair-test') return json(401,{detail:'Pairing required'});
    const sid=randomUUID();
    const session={session_id:sid,token:`secret-${sid}`,backend:'mock',experiment:{id:'red_cabbage_ph',title:'Red-cabbage pH',question:'What does the color tell you?'},revision:1,generation:1,connected:true,trial:{trial_id:randomUUID(),condition_id:null,state:'prepare'},conditions,prediction:'',pending:null,requests:[],observations:[],messages:[],notebook:[],state:'HOME',capabilities:{voice:true}};
    sessions.set(sid,session); traces.set(sid,[]);
    return json(200,{...snapshot(session),access_token:session.token});
  }
  if (path.startsWith('/fixture/')) {
    const sid=path.split('/')[2], session=sessions.get(sid);
    if (!session) return json(404,{});
    if (body.frame) send(clients.get(sid),body.frame);
    if (body.close) clients.get(sid)?.close(1012,'Fixture restart');
    if (body.fail) session.failNext=body.fail;
    if (body.state) { Object.assign(session,body.state); publish(session); }
    return json(200,{trace:traces.get(sid),state:snapshot(session)});
  }
  if (path.startsWith('/api/sessions/')) {
    const [, , , sid, action] = path.split('/');
    const session=sessions.get(sid);
    if (!session) return json(404,{detail:'Session not found'});
    if (request.headers.authorization !== `Bearer ${session.token}`) return json(401,{detail:'Invalid session credential'});
    traces.get(sid).push({channel:'rest',action:action || 'snapshot',body});
    if (!action) return json(200,snapshot(session));
    if (session.failNext===action) { delete session.failNext; return json(503,{detail:'The lab is temporarily unavailable. Your draft has been kept.'}); }
    switch(action) {
      case 'condition': session.trial.condition_id=body.condition_id; session.pending=null; proposal(session); break;
      case 'prediction': session.prediction=body.text; message(session,'user',body.text); session.notebook.push({type:'prediction',trial_id:session.trial.trial_id,text:body.text}); proposal(session); break;
      case 'present':
        if (!session.pending || body.request_id!==session.pending.request_id || body.proposal_version!==session.pending.proposal_version) return json(409,{detail:'Stale proposal'});
        session.pending.presented=true; break;
      case 'confirm': {
        if (!session.pending?.presented || body.request_id!==session.pending.request_id || body.proposal_version!==session.pending.proposal_version) return json(409,{detail:'Stale or unpresented proposal'});
        const outcomes={vinegar:'The expected reference color is pink: consistent with an acidic sample.',baking_soda:'The expected reference color is blue-green: consistent with a basic sample.',water:'The expected reference color is purple: consistent with a near-neutral control.'};
        const observation={trial_id:session.trial.trial_id,request_id:session.pending.request_id,condition_id:session.trial.condition_id,provenance:'MODEL-PREDICTED',text:outcomes[session.trial.condition_id],source:'Prepared cabbage-indicator mock reference',evidence:[]};
        session.observations.push(observation); session.pending=null; session.trial.state='complete'; session.state='HOME'; message(session,'assistant',observation.text); break;
      }
      case 'cancel': session.pending=null; message(session,'assistant','That proposal is canceled. You can change your sample or prediction.'); break;
      case 'request': message(session,'user',body.text); message(session,'assistant','Red-cabbage indicator changes color with acid–base conditions. Compare the mock reference with your prediction.'); break;
      case 'reflection': session.notebook.push({type:'reflection',trial_id:session.trial.trial_id,text:body.text}); message(session,'user',body.text); break;
      case 'prepare': session.trial={trial_id:randomUUID(),condition_id:null,state:'prepare'}; session.prediction=''; session.pending=null; break;
      case 'stop': case 'disconnect': stop(session); break;
      default: return json(404,{detail:'Unknown action'});
    }
    return json(200,publish(session));
  }
  try {
    const file = path==='/' ? 'index.html' : decodeURIComponent(path.slice(1));
    if (file.includes('..') || file.startsWith('tests/')) return json(404,{});
    const content=await readFile(root+file);
    response.writeHead(200,{'Content-Type':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'}); response.end(content);
  } catch { json(404,{}); }
});
const wss = new WebSocketServer({server});
wss.on('connection',(socket,request) => {
  const sid = request.url.split('/')[3];
  const session=sessions.get(sid);
  let authed=false;
  socket.on('message', raw => {
    const frame=JSON.parse(raw);
    if (!authed) {
      if (frame.type!=='hello' || frame.access_token!==session?.token) return socket.close(1008,'Unauthorized');
      clients.get(sid)?.close(4009,'New owner');
      authed=true; clients.set(sid,socket); session.generation++; session.revision++;
      traces.get(sid).push({channel:'ws',frame:{...frame,access_token:'[redacted]'}});
      send(socket,{type:'hello',protocol_version:1,connection_id:frame.connection_id,generation:session.generation});
      send(socket,{type:'state',state:snapshot(session)}); return;
    }
    if (frame.type === 'audio') {
      const { data, ...metadata } = frame;
      traces.get(sid).push({ channel:'ws', frame:metadata, bytes:Buffer.from(data, 'base64').length, accepted:frame.epoch === session.generation });
    } else traces.get(sid).push({channel:'ws',frame});
    if(frame.type==='ping') send(socket,{type:'pong',seq:frame.seq});
    if(frame.type==='start_voice') send(socket,{type:'status',status:'listening'});
    if(frame.type==='mute') send(socket,{type:'status',status:frame.muted?'muted':'listening'});
    if(frame.type==='stop') { stop(session); publish(session); }
  });
  socket.on('close',() => { if(clients.get(sid)===socket) {clients.delete(sid);session.pending=null;session.revision++;} });
});
server.listen(port,'127.0.0.1',()=>process.stdout.write(`Offline lab fixture: http://127.0.0.1:${port}\n`));
