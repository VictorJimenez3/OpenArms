import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import { PcmPlayer, SessionClient } from '../live-client.js';

const source = await readFile(new URL('../audio-worklet.js', import.meta.url), 'utf8');

function capture(sampleRate) {
  const messages = [];
  let Processor;
  runInNewContext(source, {
    AudioWorkletProcessor: class { port = { postMessage: message => messages.push(message) }; },
    registerProcessor: (_, implementation) => { Processor = implementation; },
    sampleRate,
  });
  const processor = new Processor();
  return {
    messages,
    gate(enabled, epoch) { processor.port.onmessage({ data: { type: 'gate', enabled, epoch } }); },
    feed(samples, value) { processor.process([[new Float32Array(samples).fill(value)]]); },
  };
}

for (const sampleRate of [16000, 44100, 48000]) {
  test(`capture at ${sampleRate} Hz discards partial samples on generation and mute changes`, () => {
    const mic = capture(sampleRate);
    mic.gate(true, 1);
    mic.feed(sampleRate / 10 - 1, 1);
    assert.equal(mic.messages.length, 0);
    mic.gate(true, 2);
    mic.feed(sampleRate / 20, -1);
    assert.equal(mic.messages.length, 0);
    mic.gate(false, 3);
    mic.feed(sampleRate / 10, 1);
    mic.gate(true, 4);
    mic.feed(sampleRate / 10, -1);
    assert.equal(mic.messages.length, 1);
    const [{ epoch, buffer }] = mic.messages;
    assert.equal(epoch, 4);
    assert.equal(buffer.byteLength, 3200);
    const pcm = new DataView(buffer);
    for (let i = 0; i < 3200; i += 2) assert.equal(pcm.getInt16(i, true), -32768);
  });
}

test('accepted revisions flush old worklet data before allowing the new wire generation', () => {
  const previousDocument = globalThis.document;
  globalThis.document = new EventTarget();
  try {
    const revisions = [];
    const gates = [];
    const client = new SessionClient({ sessionId: 'session' }, { onState: state => revisions.push(state.revision) });
    client.worklet = { port: { postMessage: frame => gates.push(frame) } };
    client.captureEnabled = true;
    const initial = { session_id: 'session', revision: 5, generation: 1 };
    assert.equal(client.acceptState(initial), true);
    assert.equal(client.acceptState({ ...initial, generation: 20 }), false);
    assert.equal(client.acceptState({ ...initial, revision: 4, generation: 20 }), false);
    assert.equal(client.acceptState({ ...initial, session_id: 'different', revision: 6, generation: 20 }), false);
    assert.equal(client.acceptState({ ...initial, revision: 6, generation: 2 }), true);
    assert.equal(client.acceptState({ ...initial, revision: 7, generation: 1 }), false);
    assert.equal(client.acceptState({ ...initial, revision: 7, generation: 2 }), true);
    assert.deepEqual(revisions, [5, 6, 7]);
    assert.deepEqual(gates, [
      { type: 'gate', enabled: true, epoch: 1 },
      { type: 'gate', enabled: true, epoch: 2 },
    ]);
    assert.equal(client.generation, 2);
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

test('playback acknowledgment requires an ended reply and natural completion of every chunk', () => {
  const sources = [];
  const sent = [];
  const context = {
    currentTime: 0,
    state: 'running',
    destination: {},
    createBuffer: (_, samples, hz) => ({ duration: samples / hz, copyToChannel() {} }),
    createBufferSource() {
      const source = { connect() {}, disconnect() {}, start() {}, stop() {} };
      sources.push(source);
      return source;
    },
  };
  const player = new PcmPlayer(context, frame => sent.push(frame));
  const pcm = Buffer.alloc(4800).toString('base64');
  player.start('completed');
  player.chunk('completed', pcm);
  player.chunk('completed', pcm);
  player.end('completed');
  assert.deepEqual(sent, []);
  sources[0].onended();
  assert.deepEqual(sent, []);
  sources[1].onended();
  player.end('completed');
  assert.deepEqual(sent, [{ type: 'played', reply_id: 'completed' }]);

  player.start('interrupted');
  player.chunk('interrupted', pcm);
  player.clear('interrupted', true);
  player.end('interrupted');
  player.chunk('interrupted', pcm);
  assert.equal(sources[2].onended, null);
  assert.equal(sources.length, 3);
  assert.deepEqual(sent.at(-1), { type: 'interrupt', reply_id: 'interrupted' });
  player.clear();
});
