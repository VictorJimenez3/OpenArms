import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import agy_bridge

class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, cancel):
        original=asyncio.create_subprocess_exec
        children=[]
        async def spawn(*args,**kwargs):
            proc=await original(sys.executable,'-c','import time; time.sleep(60)',**kwargs)
            children.append(proc)
            return proc
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'mcp.json'
            config.write_text(json.dumps({'mcpServers':{'existing':{'command':'keep'}}}))
            state=Path(tmp)/'state'
            with patch.object(agy_bridge,'MCP_CONFIG_PATH',config), patch.object(agy_bridge.asyncio,'create_subprocess_exec',side_effect=spawn):
                task=asyncio.create_task(agy_bridge.submit('Move the mandarin from A to B',state,timeout=.05 if not cancel else 60))
                if cancel:
                    while not children: await asyncio.sleep(.001)
                    task.cancel()
                with self.assertRaises(asyncio.CancelledError if cancel else TimeoutError): await task
            self.assertEqual(json.loads(config.read_text()),{'mcpServers':{'existing':{'command':'keep'}}})
            self.assertTrue(children)
            self.assertIsNotNone(children[0].returncode)
    async def test_timeout_reaps_and_unregisters(self): await self.exercise(False)
    async def test_cancel_reaps_and_unregisters(self): await self.exercise(True)
    async def test_invalid_configuration_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'mcp.json'
            config.write_text('not valid json')
            with patch.object(agy_bridge,'MCP_CONFIG_PATH',config):
                with self.assertRaises(ValueError):
                    with agy_bridge.ScopedMcpServer('test','python',[]): pass
            self.assertEqual(config.read_text(),'not valid json')
