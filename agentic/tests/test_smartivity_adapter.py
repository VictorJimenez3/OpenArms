"""Protect the Smartivity adapter's observation and STOP boundaries."""
import asyncio

import numpy as np
import pytest

from agentic.openarms_lab.smartivity import SmartivityRun


class WorldFixture:
    timestep = 0.005

    def __init__(self, seed):
        self.seed = seed
        self.sim_time = 0.0
        self.busy = False
        self.phase = 'ready'
        self.started_actions = []

    def start(self, action):
        self.phase = action
        self.started_actions.append(action)
        self.busy = True

    def tick(self):
        self.sim_time += self.timestep
        self.busy = False

    def halt(self):
        self.busy = False

    def rgb(self, camera):
        shade = 40 if camera == 'overview' else 100
        return np.full((32, 32, 3), shade + len(self.started_actions) * 25, dtype=np.uint8)

    def proprioception(self):
        return {'joints': []}

    def evaluate(self):
        return {'success': False}

    def close(self):
        pass


class PausedExpert:
    def __init__(self):
        self.entered = asyncio.Event()
        self.dispatch = asyncio.Event()
        self.checked = asyncio.Event()
        self.resumed = asyncio.Event()
        self.before = self.after = self.invalid = self.stale_tool = None

    async def run(self, context, *, tool_handler, emit, cancel_event):
        self.stale_tool = tool_handler
        self.before = context
        self.entered.set()
        await self.dispatch.wait()
        self.invalid = await tool_handler('execute_skill', {'action': 'pick', 'evidence_id': 'old'})
        frame = self.invalid['images'][0]
        self.after = await tool_handler('execute_skill', {'action': 'pick', 'evidence_id': frame['evidence_id']})
        self.checked.set()
        await cancel_event.wait()
        with pytest.raises(asyncio.CancelledError):
            await tool_handler('execute_skill', {'action': 'pour', 'evidence_id': self.after['images'][0]['evidence_id']})
        self.resumed.set()
        raise asyncio.CancelledError

    def release(self, task_id):
        pass


@pytest.mark.asyncio
async def test_current_images_drive_action_and_cancelled_policy_cannot_dispatch(tmp_path):
    expert = PausedExpert()
    runner = SmartivityRun(tmp_path, expert, world_factory=WorldFixture)
    await runner.start(seed=7)
    try:
        await asyncio.wait_for(expert.entered.wait(), 1)
        old_world = runner.world
        assert [frame['camera_id'] for frame in expert.before['images']] == ['overview', 'side']
        assert all(frame['provenance'] == 'SIMULATED' for frame in expert.before['images'])
        assert 'evaluation' not in expert.before and 'pose' not in expert.before
        await asyncio.sleep(0.1)
        assert old_world.sim_time > 0.05  # Physics advances while the expert is waiting.
        expert.dispatch.set()
        await asyncio.wait_for(expert.checked.wait(), 1)
        assert 'invalidated' in expert.invalid['error']
        assert expert.after['action_receipt']['overview_mean_rgb_delta'] > 0
        assert expert.before['images'][0]['frame_id'] != expert.after['images'][0]['frame_id']
        await asyncio.wait_for(runner.reset(seed=8), 1)
        assert expert.resumed.is_set()
        assert old_world.started_actions == ['pick']
        assert runner.world.started_actions == []
        new_frame = runner.snapshot()['frames']['overview']
        assert new_frame['generation'] == 2
        with pytest.raises(asyncio.CancelledError):
            await expert.stale_tool('execute_skill', {'action': 'pick', 'evidence_id': new_frame['evidence_id']})
        assert runner.world.started_actions == []
    finally:
        await runner.close()
