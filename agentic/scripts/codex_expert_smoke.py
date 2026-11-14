"""Qualify the real Codex image/tool feedback path using historical bench frames.

This reads committed images only. It never opens a camera or robot connection.
Run with PYTHONPATH=agentic python agentic/scripts/codex_expert_smoke.py --out PATH.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from openarms_lab.codex_expert import CodexExpert


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--executable', default='codex')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    repository = Path(__file__).resolve().parents[2]
    evidence = repository/'research/joseph/mandarin-transfer-2026-11-14/images'

    def image(name):
        path = evidence/name
        return dict(path=str(path), evidence_id=name, captured_at='UNKNOWN_ORIGINAL_FRAME_TIME',
                    episode_window='2026-11-14 06:09–06:13 America/New_York',
                    provenance='RECORDED_REAL', sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    events, invoked = [], []
    async def emit(event):
        events.append(event)
    async def inspect(name, arguments):
        if name != 'inspect_scene' or arguments != {'phase': 'after'}:
            return {'error': 'Only the recorded after views are available; no hardware access.'}
        invoked.append(name)
        return {'source': 'committed historical bench recording', 'current_live_scene': False,
                'images': [image('after-camera-0.jpg'), image('after-camera-1.jpg')]}

    expert = CodexExpert(args.out/'calls', artifact_roots=[evidence], executable=args.executable, max_calls=4)
    context = dict(task_id='codex-provider-image-feedback-qualification', session_id='offline-recorded-replay',
                   request='Check the outcome of the recorded transfer. The initial image is BEFORE the attempt. '
                           'Obtain the after views, inspect them, and decide whether the fruit was placed on the red card. '
                           'Report uncertainty; do not treat a completed controller command as proof.',
                   phase='execution_feedback', images=[image('before-camera-0.jpg')],
                   tools=[dict(name='inspect_scene', description='Read recorded after views; does not operate hardware.',
                               input_schema={'type': 'object', 'properties': {'phase': {'const': 'after'}},
                                             'required': ['phase'], 'additionalProperties': False})],
                   feedback=[{'controller_completed': True, 'observed_outcome': 'UNKNOWN'}],
                   skills=[], capability_limits={'physical_actuation': False, 'recorded_replay_only': True},
                   instructions='After inspecting the requested images, return kind=complete with payload '
                                '{observed_outcome: string, evidence_ids: string[], limitations: string[]}. '
                                'Do not emit motor targets or infer liquid chemistry. This is engineering evidence, '
                                'not a student-facing mandarin demo.')
    result = await expert.run(context, tool_handler=inspect, emit=emit)
    receipt = dict(result=result, events=events, source='recorded bench images',
                   live_hardware=False, actual_provider_call=True,
                   checks={'tool_invoked': bool(invoked), 'fresh_images_returned': len(invoked) > 0,
                           'multiple_model_calls': result['calls'] >= 2})
    (args.out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({'result': result, 'checks': receipt['checks']}, indent=2))
    if not all(receipt['checks'].values()):
        raise SystemExit('Image/tool feedback qualification incomplete')


if __name__ == '__main__':
    asyncio.run(main())
