import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
async function session(page) { return page.evaluate(()=>JSON.parse(sessionStorage.getItem('openarms.ph.session')).session_id); }
async function fixture(page,request,body={}) { return (await request.post(`/fixture/${await session(page)}`,{data:body})).json(); }
async function ready(page) { await page.goto('/'); await expect(page.getByText('Notebook connected',{exact:true})).toBeVisible(); }
async function sendRequest(page, text) {
  await page.getByRole('textbox', {name:'What would you like to do?'}).fill(text);
  await page.getByRole('button',{name:'Send request'}).click();
}
async function openContext(page) {
  await page.getByText('Optional sample and prediction', {exact:true}).click();
}
async function predict(page, prediction='I predict pink because vinegar is acidic.') {
  await page.getByLabel('What do you think will happen?').fill(prediction);
  await page.getByRole('button',{name:/Save prediction/}).click();
  await expect(page.locator('#prediction-saved')).toHaveText('Prediction saved in your notebook.');
}
async function reviewProposal(page) {
  await page.getByRole('link', {name:'Review proposed action'}).click();
  await expect(page.getByRole('button',{name:'Confirm this action'})).toBeEnabled();
}
async function propose(page, request, condition='vinegar') {
  await sendRequest(page, `Check the color of the ${condition} sample.`);
  await expect(page.locator('#task-status')).toHaveText('Request queued');
  await fixture(page,request,{propose:condition});
  await reviewProposal(page);
}

test('a direct request queues without a sample or prediction while typing and voice stay available', async ({page, request}) => {
  await ready(page);
  await expect(page.locator('#trial-context')).not.toHaveAttribute('open');
  const command = 'Check the color of the vinegar sample.';
  await sendRequest(page, command);
  await expect(page.locator('#task-status')).toHaveText('Request queued');
  await expect(page.locator('#messages')).toContainText(command);
  const {state, trace} = await fixture(page, request);
  expect(state.trial.condition_id).toBeNull();
  expect(state.prediction).toBe('');
  expect(state.pending).toBeNull();
  expect(state.tasks).toEqual([expect.objectContaining({status:'queued', request:command})]);
  expect(trace.filter(entry => entry.action === 'request')).toEqual([
    expect.objectContaining({body:{text:command, client_request_id:expect.any(String)}}),
  ]);
  await fixture(page, request, {state:{tasks:[{...state.tasks[0], status:'running', route:'expert'}]}});
  await expect(page.locator('#task-status')).toHaveText('Reviewing your request');
  const draft = page.getByRole('textbox', {name:'What would you like to do?'});
  await draft.fill('Compare with water next.');
  await page.getByRole('button',{name:'Speak a request'}).click();
  await expect(page.locator('#provider-state')).toHaveText('Voice listening');
  await expect(draft).toHaveValue('Compare with water next.');
  await expect(page.locator('#proposal')).toBeHidden();
  await expect(page.locator('#evidence')).toBeHidden();
});

test('an optional prediction saves without a selected sample or a proposal', async ({page, request}) => {
  await ready(page);
  await openContext(page);
  await predict(page);
  const {state, trace} = await fixture(page, request);
  expect(state.trial.condition_id).toBeNull();
  expect(state.prediction).toContain('I predict pink');
  expect(state.pending).toBeNull();
  expect(state.tasks).toEqual([]);
  await expect(page.locator('#proposal')).toBeHidden();
  expect(trace.filter(entry => ['request','present'].includes(entry.action))).toHaveLength(0);
});

test('complete a pH trial with text, reflection, history and a new sample',async({page,request})=>{
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await ready(page);
  await openContext(page);
  await page.getByRole('button',{name:/^Vinegar/}).click();
  await predict(page);
  await propose(page, request);
  await expect(page.locator('#proposal-summary')).toContainText('Vinegar');
  await page.getByRole('button',{name:'Confirm this action'}).click();
  await expect(page.locator('#evidence')).toContainText('MODEL-PREDICTED');
  await expect(page.locator('#evidence')).toContainText('expected color');
  await page.getByText('Add a reflection (optional)',{exact:true}).click();
  await page.getByLabel('What did you learn?').fill('The pink reference supports my prediction of an acidic sample.');
  await page.getByRole('button',{name:'Save reflection'}).click();
  await expect(page.getByText('Reflection saved.',{exact:true})).toBeVisible();
  await page.getByRole('textbox', {name:'What would you like to do?'}).fill('Why does cabbage change color?');
  await page.getByRole('button',{name:'Send request'}).click();
  await expect(page.locator('#messages')).toContainText('acid–base conditions');
  await page.getByText('Your lab notebook',{exact:true}).click();
  await expect(page.locator('#history-list')).toContainText('supports my prediction');
  await page.getByRole('button',{name:'Start a new notebook entry'}).click();
  await expect(page.getByRole('textbox', {name:'What would you like to do?'})).toBeFocused();
  await expect(page.getByRole('button',{name:/^Water/})).toHaveAttribute('aria-pressed','false');
  await expect(page.locator('#evidence')).toBeHidden();
  await expect(page.locator('#history-count')).toHaveText('1 trial recorded');
  const result=await fixture(page,request);
  expect(result.trace.filter(t=>t.frame?.type==='hello')).toHaveLength(1);
  expect(result.trace.filter(t=>t.frame?.type==='start_voice')).toHaveLength(0);
  expect(result.trace.filter(t=>t.action==='confirm')).toHaveLength(1);
  expect(errors).toEqual([]);
});

test('exact proposal must be visible before presentation and a newer server proposal replaces it',async({page,request})=>{
  await ready(page);
  await sendRequest(page, 'Check the vinegar sample.');
  await expect(page.locator('#task-status')).toHaveText('Request queued');
  // Place the proposal below the viewport to verify state delivery alone cannot acknowledge it.
  await page.locator('#message-form').evaluate(form => form.style.marginBottom = '110vh');
  const first = await fixture(page,request,{propose:'vinegar'});
  await expect(page.locator('#proposal-summary')).toContainText('Vinegar');
  await page.waitForTimeout(150);
  expect((await fixture(page,request)).trace.filter(t=>t.action==='present')).toHaveLength(0);
  await expect(page.getByRole('button',{name:'Confirm this action'})).toBeDisabled();
  await reviewProposal(page);
  const second = await fixture(page,request,{propose:'water'});
  await expect(page.locator('#proposal-summary')).toContainText('Water');
  await reviewProposal(page);
  expect(second.state.pending.request_id).not.toBe(first.state.pending.request_id);
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await expect(page.locator('#proposal')).toBeHidden();
  const {trace} = await fixture(page,request);
  expect(trace.filter(t=>t.action==='present').map(t=>t.body.request_id)).toEqual([
    first.state.pending.request_id, second.state.pending.request_id,
  ]);
  expect(trace.filter(t=>t.action==='confirm')).toHaveLength(0);
});

test('voice outage preserves the socket, coalesces turns and permits text',async({page,request})=>{
  await ready(page);
  for (const frame of [
    {type:'transcript',role:'assistant',turn_id:'turn-one',text:'Let’s compare',final:false},
    {type:'transcript',role:'assistant',turn_id:'turn-one',text:'Let’s compare the color.',final:true},
    {type:'status',status:'unavailable',message:'Voice provider is offline. Text still works.'},
  ]) await fixture(page,request,{frame});
  await expect(page.locator('.message.assistant')).toHaveCount(1);
  await expect(page.locator('.message.assistant')).toContainText('Let’s compare the color.');
  await expect(page.getByText('Notebook connected',{exact:true})).toBeVisible();
  await expect(page.locator('#provider-state')).toHaveText('Voice unavailable');
  await page.getByRole('textbox', {name:'What would you like to do?'}).fill('Can I compare with water?');
  await page.getByRole('button',{name:'Send request'}).click();
  await expect(page.locator('#messages')).toContainText('Can I compare with water?');
  expect((await fixture(page,request)).trace.filter(t=>t.frame?.type==='hello')).toHaveLength(1);
});

test('network error preserves draft and reconnect never replays a command or approval',async({page,request})=>{
  await ready(page);
  await fixture(page,request,{fail:'request'});
  await page.getByRole('textbox', {name:'What would you like to do?'}).fill('A question that must not replay');
  await page.getByRole('button',{name:'Send request'}).click();
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable');
  await expect(page.getByRole('textbox', {name:'What would you like to do?'})).toHaveValue('A question that must not replay');
  await fixture(page,request,{state:{tasks:[{status:'queued', request:'Check vinegar.'}]}});
  await fixture(page,request,{propose:'vinegar'});
  await reviewProposal(page);
  await fixture(page,request,{close:true});
  await expect(page.locator('#confirm')).toBeDisabled();
  await expect(page.getByText('Notebook connected',{exact:true})).toBeVisible();
  await expect(page.locator('#proposal')).toBeHidden();
  const result=await fixture(page,request);
  expect(result.trace.filter(t=>t.action==='request')).toHaveLength(1);
  expect(result.trace.filter(t=>t.action==='confirm')).toHaveLength(0);
  expect(result.trace.filter(t=>t.frame?.type==='hello')).toHaveLength(2);
});

test('older snapshots cannot replace newer trial state and credentials are private',async({page,request})=>{
  await ready(page);
  const earlier=(await fixture(page,request)).state;
  await openContext(page);
  await page.getByRole('button',{name:/^Water/}).click();
  await fixture(page,request,{frame:{type:'state',state:earlier}});
  await expect(page.getByRole('button',{name:/^Water/})).toHaveAttribute('aria-pressed','true');
  const token=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('openarms.ph.session')).access_token);
  expect(await page.locator('body').innerText()).not.toContain(token);
  expect(page.url()).not.toContain(token);
  await page.reload();
  await expect(page.getByText('Notebook connected',{exact:true})).toBeVisible();
  await openContext(page);
  await expect(page.getByRole('button',{name:/^Water/})).toHaveAttribute('aria-pressed','true');
});

test('layout fits the viewport, touch controls and accessibility at every stage',async({page,request},testInfo)=>{
  await ready(page);
  async function check(name) {
    const violations=(await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze()).violations;
    expect(violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:testInfo.outputPath(`${name}.png`),fullPage:true});
  }
  await check('welcome');
  expect(await page.locator('#voice-request').evaluate(button => {
    const rect = button.getBoundingClientRect();
    return button.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
  })).toBe(true);
  await propose(page, request);
  await check('proposal');
  await page.getByRole('button',{name:'Confirm this action'}).click();
  await check('result');
  const tiny=await page.locator('button:visible').evaluateAll(elements=>elements.filter(el=>{const r=el.getBoundingClientRect();return r.height<44 || r.width<44}).map(el=>el.id));
  expect(tiny).toEqual([]);
});

test('microphone denial is recoverable and cannot block text',async({page,request})=>{
  await page.addInitScript(()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Permission denied','NotAllowedError');};});
  await ready(page);
  await page.getByRole('button',{name:'Start voice',exact:true}).click();
  await expect(page.locator('#mic-state')).toHaveText('Mic blocked');
  await expect(page.getByRole('button',{name:'Retry microphone'})).toBeEnabled();
  await page.getByRole('textbox', {name:'What would you like to do?'}).fill('I prefer typing.');
  await page.getByRole('button',{name:'Send request'}).click();
  await expect(page.locator('#messages')).toContainText('I prefer typing.');
  expect((await fixture(page,request)).trace.filter(t=>t.frame?.type==='start_voice')).toHaveLength(0);
});

test('remote session creation asks for pairing code only after rejection',async({page})=>{
  await page.setExtraHTTPHeaders({'x-fixture-pairing':'required'});
  await page.goto('/');
  await expect(page.getByLabel('Pairing code')).toBeVisible();
  await page.getByLabel('Pairing code').fill('pair-test');
  await page.getByRole('button',{name:'Connect',exact:true}).click();
  await expect(page.getByText('Notebook connected',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Pairing code')).toHaveValue('');
  expect(await page.locator('body').innerText()).not.toContain('pair-test');
});

test('optional task, scene, observation and active skill evidence stays server-owned', async ({page, request}) => {
  await ready(page);
  for (const id of ['task-progress', 'scene', 'active-skills', 'evidence']) await expect(page.locator(`#${id}`)).toBeHidden();
  const { state } = await fixture(page, request);
  const trialId = state.trial.trial_id;
  const evidenceUrl = `/api/sessions/${state.session_id}/evidence/frame-a`;
  const token = await page.evaluate(() => JSON.parse(sessionStorage.getItem('openarms.ph.session')).access_token);
  const evidenceRequests = [];
  page.on('request', req => { if (req.url().includes('/evidence/')) evidenceRequests.push(req.url()); });
  const imageRequest = page.waitForRequest(req => new URL(req.url()).pathname === evidenceUrl);
  const task = { task_id: 'task-1', trial_id: trialId };
  await fixture(page, request, { state: { tasks: [{ ...task, status: 'running', summary: 'Reviewing the prepared samples.' }] } });
  await expect(page.getByText('Reviewing your request')).toBeVisible();
  await expect(page.locator('#evidence')).toBeHidden();

  await fixture(page, request, { state: {
    tasks: [{ ...task, status: 'needs_clarification', summary: 'Which sample is in the left holder?' }],
    scene: { fresh: false },
    scene_images: [
      { evidence_id: 'frame-a', captured_at: '2026-11-14T16:00:00Z', provenance: 'SIMULATED', sha256: 'a'.repeat(64), artifact_url: evidenceUrl, description: 'Prepared sample holders' },
      { evidence_id: 'frame-b', provenance: 'SYNTHETIC', path: '/internal/frame.png', artifact_url: 'https://example.invalid/scene.png' },
      { evidence_id: 'frame-c', artifact_url: `${evidenceUrl.replace('frame-a', 'frame-c')}?token=${token}` },
    ],
    skills: [
      { name: 'Compare sample conditions', version: 'v2', status: 'active' },
      { name: 'Draft technique', version: 'v1', status: 'candidate' },
    ],
  } });
  await expect(page.getByText('Which sample is in the left holder?')).toBeVisible();
  await expect(page.getByText('Stale scene')).toBeVisible();
  await expect(page.locator('#scene')).toContainText('Simulated · Captured');
  await expect(page.getByText('Image unavailable.', {exact:true})).toHaveCount(2);
  expect(await page.locator('#scene').innerText()).not.toContain('frame-a');
  expect(await page.locator('#scene').innerText()).not.toContain('a'.repeat(64));
  const image = page.getByRole('img', { name: 'Prepared sample holders' });
  await image.scrollIntoViewIfNeeded();
  await expect(image).toHaveJSProperty('naturalWidth', 1);
  await expect(image).toHaveAttribute('src', /^blob:/);
  const authenticated = await imageRequest;
  expect(authenticated.url()).toBe(new URL(evidenceUrl, page.url()).href);
  expect(await authenticated.headerValue('authorization')).toBe(`Bearer ${token}`);
  expect(evidenceRequests).toEqual([authenticated.url()]);
  expect((await request.get(evidenceUrl)).status()).toBe(401);
  expect(await page.content()).not.toContain(token);
  await expect(page.locator('#scene img')).toHaveCount(1);
  await expect(page.locator('#scene')).not.toContainText('/internal/frame.png');
  await expect(page.locator('#skill-labels')).toHaveText('Compare sample conditions · v2');
  await page.getByRole('button', { name: 'Reply to the question' }).press('Enter');
  const composer = page.getByRole('textbox', {name:'What would you like to do?'});
  await expect(composer).toBeFocused();
  await composer.fill('The left holder has the water control.');
  await composer.press('Enter');
  await expect(page.locator('#messages')).toContainText('The left holder has the water control.');

  await fixture(page, request, { state: { tasks: [{ ...task, status: 'executing', feedback: [{ type: 'execution_progress', step: 1 }] }] } });
  await expect(page.locator('#task-detail')).toHaveText('Step 2');
  await expect(page.locator('#evidence')).toBeHidden();
  await fixture(page, request, { state: { tasks: [{ ...task, status: 'completed', route: 'active_skill', request: 'Inspect the holder.' }] } });
  await expect(page.locator('#task-status')).toHaveText('Task complete');
  await page.getByText('Task details', {exact:true}).click();
  await expect(page.locator('#task-route')).toHaveText('Reused an active skill');
  await expect(page.locator('#task-request')).toHaveText('Inspect the holder.');
  await expect(page.locator('#evidence')).toBeHidden();
  await fixture(page, request, { state: { observations: [{ trial_id: trialId, provenance: 'SIMULATED', status: 'observed', source: 'Frame observer', features: { indicator_color: 'purple' }, evidence: ['frame-a'], text: 'The indicator is visible in the marked holder.' }] } });
  await expect(page.locator('#evidence-provenance')).toHaveText('OBSERVED · SIMULATED');
  expect(await page.locator('#evidence').innerText()).not.toContain('frame-a');
  await page.getByText('Observation details', {exact:true}).click();
  await expect(page.locator('#observation-fields')).toContainText('indicator color: purple');
  await expect(page.locator('#observation-fields')).toContainText('frame-a');
  await expect(page.locator('#evidence')).toContainText('Frame observer');
  await expect(page.locator('.evidence-swatch')).toBeHidden();
  await fixture(page, request, { state: { observations: [{ trial_id: trialId, provenance: 'UNKNOWN', status: 'unknown', text: 'The receiver was occluded.' }] } });
  await expect(page.locator('#evidence')).toContainText('UNKNOWN');
  await expect(page.locator('#evidence')).toContainText('The receiver was occluded.');
});

test('a replaced frame revokes its blob and a late decode leaves the new scene intact', async ({page, request}) => {
  await page.addInitScript(() => {
    const decode = HTMLImageElement.prototype.decode;
    const revoke = URL.revokeObjectURL.bind(URL);
    window.revokedFrames = [];
    URL.revokeObjectURL = url => { window.revokedFrames.push(url); revoke(url); };
    HTMLImageElement.prototype.decode = function () {
      if (this.alt !== 'Old frame') return decode.call(this);
      const url = this.src;
      return new Promise(resolve => {
        window.oldFrame = { url, finish: resolve };
      });
    };
  });
  await ready(page);
  const sid = await session(page);
  const frame = (evidence_id, description) => ({
    evidence_id, description, provenance:'SYNTHETIC',
    artifact_url:`/api/sessions/${sid}/evidence/${evidence_id}`,
  });
  await fixture(page, request, {state:{scene_images:[frame('old', 'Old frame')]}});
  await page.waitForFunction(() => Boolean(window.oldFrame));
  await page.locator('#scene-frames figure').evaluate(figure => { window.oldFrame.figure = figure; });
  await fixture(page, request, {state:{scene_images:[frame('new', 'New frame')]}});
  const current = page.getByRole('img', {name:'New frame'});
  await expect(current).toHaveJSProperty('naturalWidth', 1);
  expect(await page.evaluate(() => window.revokedFrames)).toContain(await page.evaluate(() => window.oldFrame.url));
  expect(await page.evaluate(async () => {
    window.oldFrame.finish();
    await Promise.resolve();
    return window.oldFrame.figure.querySelector('img') === null;
  })).toBe(true);
  await expect(page.locator('#scene img')).toHaveCount(1);
  await expect(current).toHaveJSProperty('naturalWidth', 1);
  await expect(page.getByText('Image unavailable.', {exact:true})).toBeHidden();
  const currentUrl = await current.getAttribute('src');
  await fixture(page, request, {state:{scene_images:[]}});
  await expect(page.locator('#scene')).toBeHidden();
  expect(await page.evaluate(() => window.revokedFrames)).toContain(currentUrl);
});

test('fresh mic packets follow provider and STOP generations while stale state is ignored', async ({page, request}) => {
  await ready(page);
  await page.getByRole('button', {name:'Start voice', exact:true}).click();
  await expect(page.locator('#provider-state')).toHaveText('Voice listening');
  const audio = async epoch => (await fixture(page, request)).trace.filter(entry => entry.frame?.type === 'audio' && entry.frame.epoch === epoch);
  const { state: initial } = await fixture(page, request);
  await expect.poll(async () => (await audio(initial.generation)).length).toBeGreaterThan(0);

  await fixture(page, request, { frame: {type:'status', status:'reconnecting'}, state: {generation: initial.generation + 1} });
  await expect(page.locator('#provider-state')).toHaveText('Voice reconnecting');
  await fixture(page, request, { frame: {type:'status', status:'listening'} });
  await expect.poll(async () => (await audio(initial.generation + 1)).length).toBeGreaterThan(0);

  await page.getByRole('button', { name:'Stop trial' }).focus();
  await page.keyboard.press('Escape');
  await expect.poll(async () => (await audio(initial.generation + 2)).length).toBeGreaterThan(0);
  const {state: current} = await fixture(page, request);
  for (const state of [
    { ...initial, generation: current.generation + 50 },
    { ...current, generation: current.generation + 50 },
    { ...current, revision: current.revision + 10, generation: initial.generation },
    { ...current, revision: current.revision + 10, generation: current.generation + 50, session_id: 'another-session' },
  ]) await fixture(page, request, { frame: {type:'state', state} });
  await page.getByRole('button', { name:'Mute', exact:true }).click();
  await expect(page.locator('#mic-state')).toHaveText('Mic muted');
  const mutedCount = (await audio(current.generation)).length;
  await page.waitForTimeout(300);
  expect(await audio(current.generation)).toHaveLength(mutedCount);
  await page.getByRole('button', { name:'Unmute', exact:true }).click();
  await expect.poll(async () => (await audio(current.generation)).length).toBeGreaterThan(mutedCount);
  expect((await audio(current.generation)).every(entry => entry.accepted && entry.bytes === 3200)).toBe(true);
  const {trace} = await fixture(page, request);
  expect(trace.filter(entry => entry.frame?.type === 'stop')).toHaveLength(1);
  expect(trace.filter(entry => entry.action === 'stop')).toHaveLength(0);
  expect(trace.filter(entry => entry.frame?.type === 'audio' && entry.frame.epoch > current.generation)).toHaveLength(0);
  await fixture(page, request, {close:true});
  await expect(page.locator('#mic-state')).toHaveText('Mic off');
  await expect(page.getByText('Notebook connected', {exact:true})).toBeVisible();
  expect((await fixture(page, request)).trace.filter(entry => entry.frame?.type === 'start_voice')).toHaveLength(1);
  expect(await audio(current.generation + 1)).toHaveLength(0);
});

test('audio completion acknowledges scheduled playback and interrupt clears queued speech', async ({page, request}) => {
  await ready(page);
  await page.getByRole('button', {name:'Start voice', exact:true}).click();
  await expect(page.locator('#provider-state')).toHaveText('Voice listening');
  const pcm = Buffer.alloc(24000 * 2).toString('base64');
  async function reply(reply_id, chunks) {
    await fixture(page, request, {frame:{type:'reply_start', reply_id}});
    for (let n = 0; n < chunks; n++) await fixture(page, request, {frame:{type:'audio', reply_id, data:pcm}});
    await fixture(page, request, {frame:{type:'reply_end', reply_id}});
  }
  async function frames(type, replyId) {
    return (await fixture(page, request)).trace.filter(entry => entry.frame?.type === type && entry.frame.reply_id === replyId);
  }
  await reply('finished', 2);
  await expect(page.locator('#playback-state')).toHaveText('Speaker playing');
  expect(await frames('played', 'finished')).toHaveLength(0);
  await expect.poll(async () => (await frames('played','finished')).length).toBe(1);
  await expect(page.locator('#playback-state')).toHaveText('Speaker idle');
  await reply('aborted', 2);
  await page.getByRole('button', {name:'Interrupt', exact:true}).click();
  await expect.poll(async () => (await frames('interrupt', 'aborted')).length).toBe(1);
  await fixture(page, request, {frame:{type:'audio', reply_id:'aborted', data:pcm}});
  await expect(page.locator('#playback-state')).toHaveText('Speaker idle');
  expect(await frames('played', 'aborted')).toHaveLength(0);
  await page.getByRole('button', { name:'End voice', exact:true }).click();
  await expect(page.locator('#mic-state')).toHaveText('Mic off');
});
