import json
from pathlib import Path
import tempfile
import unittest
from dialogue import Context
from mandarin import MandarinDialogue
from mcp_server import dispatch

class MandarinTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls=[]
        async def submit(text,directory):
            self.calls.append(text)
            if any(x in text.lower() for x in [' to c','not confirm','maybe confirm']):
                return {'status':'no_plan'}
            result=dispatch('tools/call',{'name':'submit_plan','arguments':{'object':'mandarin','source':'A','destination':'B'}},directory)
            return json.loads(result['content'][0]['text'])
        self.dialogue=MandarinDialogue(submit)
        self.turn=0
    async def asyncTearDown(self): await self.dialogue.close()
    async def say(self,text):
        self.turn+=1
        return await self.dialogue.respond(Context('session',f't-{self.turn}'),text)
    async def test_freeform_intent_reaches_agent(self):
        self.assertEqual((await self.say("Could you take that little orange over to station B from A for me?")).lab_stage,"preview")
        self.assertIn("little orange",self.calls[-1])
    async def test_live_asr_redundant_from(self):
        self.assertEqual((await self.say("Move from the Mandarin from point A to point B.")).lab_stage,"preview")
    async def test_identity_and_exactly_once(self):
        self.assertEqual((await self.say('Move the mandarin from point A to point B.')).lab_stage,'preview')
        plan=self.dialogue.pending['plan_id']
        self.assertIn(plan,(await self.say('I confirm.')).text)
        await self.say('confirm')
        self.assertEqual(self.dialogue.executions,[plan])
        self.assertEqual(self.dialogue.placement,'B')
    async def test_cancel_keeps_a(self):
        await self.say('Move the mandarin from A to B')
        await self.say('Cancel.')
        await self.say('confirm')
        self.assertEqual(self.dialogue.placement,'A')
        self.assertEqual(self.dialogue.executions,[])
        self.assertEqual(len(self.calls),1)
    async def test_changed_destination_and_stale_plan(self):
        await self.say('Move the mandarin from A to B')
        old=self.dialogue.pending['plan_id']
        await self.say('Move the mandarin from A to C')
        await self.say('confirm')
        self.assertEqual(self.dialogue.executions,[])
        await self.say('Move the mandarin from A to B')
        self.assertNotEqual(self.dialogue.pending['plan_id'],old)
        await self.say('confirm '+old)
        self.assertEqual(self.dialogue.executions,[])
    async def test_negative_mixed_confirm(self):
        for text in ['do not confirm','confirm and move to C','maybe confirm','confirm cancel','stop']:
            await self.say('Move the mandarin from A to B')
            await self.say(text)
        self.assertEqual(self.dialogue.executions,[])
    async def test_failed_agent_cannot_preview(self):
        async def failed(text,directory): return {'status':'preview_ready','plan_id':'fake'}
        self.dialogue.submit=failed
        with self.assertRaises(ValueError): await self.say('Move the mandarin from A to B')
        self.assertIsNone(self.dialogue.pending)
    async def test_rejected_tool_no_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            for args in [{'object':'block','source':'A','destination':'B'},{'object':'mandarin','source':'A','destination':'C'}]:
                self.assertTrue(dispatch('tools/call',{'name':'submit_plan','arguments':args},Path(tmp))['isError'])
            self.assertFalse((Path(tmp)/'plan.json').exists())

    async def test_physical_operator_rejection_prevents_execution(self):
        class Runner:
            mode = 'physical'
            calls = 0
            async def authorize(self, plan): return False
            async def execute(self, plan): self.calls += 1
            async def stop(self): pass
        runner = Runner()
        self.dialogue.runner = runner
        await self.say('Move the mandarin from A to B')
        self.assertEqual((await self.say('confirm')).lab_stage,'reflection')
        self.assertEqual(runner.calls,0)
    async def test_wrong_result_plan_is_rejected(self):
        from runner import ExecutionResult
        class Runner:
            mode = 'mock'
            async def execute(self, plan): return ExecutionResult('wrong-id','mock','completed','B')
            async def stop(self): pass
        self.dialogue.runner = Runner()
        await self.say('Move the mandarin from A to B')
        with self.assertRaises(ValueError): await self.say('confirm')
        self.assertIsNone(self.dialogue.pending)
    async def test_physical_runner_contract_preserves_identity_once(self):
        from runner import ExecutionResult
        class Runner:
            mode = 'physical'
            calls = []
            async def authorize(self, plan):
                self.authorized_id = plan['plan_id']
                return True
            async def execute(self, plan):
                assert self.authorized_id == plan['plan_id']
                self.calls.append(plan['plan_id'])
                return ExecutionResult(plan['plan_id'],'physical','completed',None,True)
            async def stop(self): pass
        runner = Runner()
        self.dialogue.runner = runner
        await self.say('Move the mandarin from A to B')
        plan_id = self.dialogue.pending['plan_id']
        reply = await self.say('confirm')
        self.assertIn('Final placement has not been observed',reply.text)
        await self.say('confirm')
        self.assertEqual(runner.calls,[plan_id])
