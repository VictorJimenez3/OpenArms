"""Host-independent boundary checks; these are not Isaac execution evidence."""
import os
import unittest
from unittest.mock import patch
from simulation.isaac.skill import validate_request
from simulation.isaac.execution_context import validate_context


class InterfaceTests(unittest.TestCase):
    def test_bounded_request(self):
        request = {'request_id': 'r1', 'session_id': 's1',
                   'skill_id': 'known_station_transfer.v1',
                   'parameters': {'object': 'sample', 'source': 'A', 'destination': 'B'}}
        self.assertEqual(validate_request(request), 'cube')
        for change in ({'skill_id': 'arbitrary_python'}, {'request_id': ''},
                       {'parameters': {'object': 'sample', 'source': 'C', 'destination': 'B'}},
                       {'extra': 'ignored?'}):
            with self.assertRaises(ValueError):
                validate_request({**request, **change})

    def test_default_requires_slurm(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'Slurm'):
                validate_context()

    def test_science_conditions_keep_canonical_parameters(self):
        for condition in ('light', 'heavy'):
            self.assertEqual(validate_request({
                'request_id': 'r1', 'session_id': 's1',
                'skill_id': f'isaac.mass_weight.{condition}.v1',
                'parameters': {'object': 'sample', 'source': 'A', 'destination': 'B'},
            }), 'cube')

    def test_dedicated_host_must_match_and_not_be_rutgers(self):
        env = {'OPENARMS_EXECUTION_CONTEXT': 'dedicated', 'OPENARMS_DEDICATED_HOST': 'approved-host'}
        with patch.dict(os.environ, env, clear=True), patch('socket.gethostname', return_value='approved-host'):
            with patch('socket.getfqdn', return_value='approved-host'):
                self.assertEqual(validate_context()['mode'], 'dedicated')
            with patch('socket.getfqdn', return_value='rlab7.cs.rutgers.edu'):
                with self.assertRaisesRegex(RuntimeError, 'Slurm'):
                    validate_context()
        with patch.dict(os.environ, env, clear=True), patch('socket.gethostname', return_value='other-host'):
            with self.assertRaisesRegex(RuntimeError, 'exactly match'):
                validate_context()


if __name__ == '__main__':
    unittest.main()
