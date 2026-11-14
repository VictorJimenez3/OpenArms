"""Synthetic integrity/analysis tests only. These do NOT prove Isaac execution.

Fixture video/USD files are deliberately synthetic stubs. Their integrity, not
their content, is tested here. Actual Isaac run creation belongs to the parent.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from simulation.isaac.experiment_report import (
    EvidenceError, compare_trials, main, summarize,
)


class ExperimentReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.light = self.fixture('light')
        self.heavy = self.fixture('heavy')

    def fixture(self, condition):
        root = self.root / condition
        root.mkdir()
        mass = {'light': .010, 'heavy': .040}[condition]
        config = {
            'kind': 'cube_to_receiver_candidate', 'source_m': [.23, 0., .01],
            'destination_m': [.2, .1, .014], 'cube_edge_m': .02, 'cube_mass_kg': mass,
            'cube_yaw_rad': -1.69,
            'experiment': {'name': 'mass_vs_weight', 'condition': condition, 'gravity_m_s2': 9.81},
            'material': {'static_friction': .9, 'dynamic_friction': .8, 'restitution': 0.},
            'phases': [{'name': 'settle', 'start_s': 1., 'end_s': 3.}],
            'attachments': False, 'pose_writes_after_reset': False,
            'receiver_kinematic_fixture': True,
            'runtime_fk_errors': {'synthetic_body': {'position_error_m': mass / 100}},
        }
        rows = []
        for i in range(1, 361):
            t = i / 120
            # The component to summarize is Z, despite an intentionally nonzero
            # transverse normal component and a greater receiver magnitude.
            force = mass * 9.81 + (i - 300) * 1e-6
            rows.append({'sim_time_s': t, 'phase': 'settle' if t >= 1 else 'retreat',
                         'contact_vectors_N': [[0., 0., 0.], [0., 0., 0.], [.001, 0., force]],
                         'receiver_force_N': (force**2 + .001**2)**.5,
                         'stable': True, 'released': True, 'supported': True, 'upright': True,
                         'verified_lift': True, 'in_receiver': True, 'success': True,
                         'settled_s': t, 'object_position_m': [.2, .1, .014],
                         'linear_speed_m_s': .0003, 'angular_speed_rad_s': .013,
                         'gripper_distance_m': .064, 'failure': None})
        (root / 'state.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        (root / 'trial-configuration.json').write_text(json.dumps(config))
        execution = {'status': 'passed', 'returncode': 0, 'stopped': False,
                     'cleanup_failed': False, 'observation_status': 'passed'}
        (root / 'execution.json').write_text(json.dumps(execution))
        for name in ('camera.mp4', 'scene.usda', 'events.jsonl', 'first-frame.png'):
            (root / name).write_bytes(b'SYNTHETIC TEST STUB: NOT ISAAC EVIDENCE\n')
        receipt = {
            'status': 'passed', 'process_returncode': 0, 'manipulation_success': True,
            'observation_status': 'passed', 'shutdown_status': 'process_exited_zero',
            'provenance': 'SIMULATED', 'backend': 'simulated', 'kind': 'cube_to_receiver',
            'git_commit': 'a' * 40, 'git_dirty': False, 'robot_asset': {'sha256': 'b' * 64, 'path': '/synthetic/robot.usd'},
            'isaac_version': '5.1.0.0', 'workshop_commit': 'c' * 40,
            'gpu': 'SYNTHETIC GPU', 'hostname': 'synthetic-host',
            'command': ['/synthetic/smoke.py', '--output', '/synthetic/recording'],
            'scene': {'physics_dt': 1 / 120, 'up_axis': 'Z', 'units': 'meters', 'gravity_m_s2': 9.81},
            'trial_configuration': config, 'video': 'camera.mp4', 'sha256': {},
        }
        (root / 'receipt.json').write_text(json.dumps(receipt))
        self.rehash(root)
        return root

    def read(self, name='receipt.json', root=None):
        return json.loads(((root or self.light) / name).read_text())

    def write(self, value, name='receipt.json', root=None):
        root = root or self.light
        (root / name).write_text(json.dumps(value))
        self.rehash(root)

    def rehash(self, root):
        path = root / 'receipt.json'
        receipt = json.loads(path.read_text())
        receipt['sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in root.iterdir() if p.name != 'receipt.json' and p.is_file()}
        path.write_text(json.dumps(receipt))

    def rows(self):
        return [json.loads(line) for line in (self.light / 'state.jsonl').read_text().splitlines()]

    def write_rows(self, rows):
        (self.light / 'state.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        self.rehash(self.light)

    def change_config(self, key, value, root=None):
        root = root or self.light
        receipt = self.read(root=root)
        receipt['trial_configuration'][key] = value
        (root / 'trial-configuration.json').write_text(json.dumps(receipt['trial_configuration']))
        self.write(receipt, root=root)

    def test_signed_z_statistics_and_provenance(self):
        result = summarize(self.light)
        self.assertEqual(result['sample_count'], 121)
        self.assertEqual(result['time_window']['start_sim_time_s'], 2.)
        self.assertEqual(result['time_window']['end_sim_time_s'], 3.)
        self.assertAlmostEqual(result['mean_support_force_N'], .0981)
        self.assertAlmostEqual(result['std_support_force_N'], (1220)**.5 * 1e-6)
        self.assertAlmostEqual(result['min_support_force_N'], .0981 - 60e-6)
        self.assertAlmostEqual(result['max_support_force_N'], .0981 + 60e-6)
        self.assertEqual(result['expected_weight_provenance'], 'ANALYTIC_PREDICTION')
        self.assertAlmostEqual(result['expected_weight_N'], .0981)
        self.assertLess(result['relative_error'], 1e-14)
        self.assertEqual(result['source']['hostname'], 'synthetic-host')
        self.assertEqual(result['source']['gpu'], 'SYNTHETIC GPU')
        self.assertEqual(result['source']['artifact_sha256'], self.read()['sha256'])
        self.assertEqual(result['source']['receipt_sha256'], hashlib.sha256((self.light / 'receipt.json').read_bytes()).hexdigest())
        json.dumps(result, allow_nan=False)

    def test_pair_and_cli_report(self):
        result = compare_trials(self.light, self.heavy)
        self.assertAlmostEqual(result['comparison']['measured_support_force_ratio_heavy_to_light'], 4.)
        self.assertEqual(result['comparison']['known_mass_ratio_heavy_to_light'], 4.)
        output = self.root / 'report'
        self.assertEqual(main(['--light', str(self.light), '--heavy', str(self.heavy), '--output', str(output)]), 0)
        self.assertEqual(json.loads((output / 'report.json').read_text()), result)
        text = (output / 'report.md').read_text()
        self.assertIn('SIMULATED', text)
        self.assertIn('Analytic', text)
        self.assertIn('No failed samples are discarded', text)
        self.assertIn('no physical robot', text)

    def test_float_roundoff_is_accepted(self):
        rows = self.rows()
        for i, row in enumerate(rows, 1):
            row['sim_time_s'] += i * 4.346e-10  # Matches observed Isaac dt accumulation.
        self.write_rows(rows)
        self.assertEqual(summarize(self.light)['sample_count'], 121)

    def test_receipt_failure_and_incomplete_receipt_are_refused(self):
        original = self.read()
        for key, value in [('status', 'failed'), ('status', 'awaiting_shutdown'),
                           ('process_returncode', 139), ('process_returncode', False),
                           ('manipulation_success', False), ('observation_status', 'failed'),
                           ('shutdown_status', 'pending'), ('shutdown_status', 'failed')]:
            with self.subTest(key=key, value=value):
                receipt = copy.deepcopy(original)
                receipt[key] = value
                self.write(receipt)
                with self.assertRaises(EvidenceError): summarize(self.light)

    def test_native_execution_failure_is_refused(self):
        original = self.read('execution.json')
        for key, value in [('status', 'failed'), ('returncode', 139), ('returncode', False),
                           ('stopped', True), ('cleanup_failed', True), ('observation_status', 'failed')]:
            with self.subTest(key=key):
                execution = copy.deepcopy(original)
                execution[key] = value
                self.write(execution, 'execution.json')
                with self.assertRaises(EvidenceError): summarize(self.light)

    def test_tampered_artifacts_are_refused(self):
        for filename in self.read()['sha256']:
            with self.subTest(filename=filename):
                path = self.light / filename
                original = path.read_bytes()
                path.write_bytes(original + b'\nTAMPERED')
                with self.assertRaisesRegex(EvidenceError, 'SHA256 mismatch'): summarize(self.light)
                path.write_bytes(original)

    def test_missing_empty_and_unhashed_required_artifacts(self):
        path = self.light / 'camera.mp4'
        original = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(EvidenceError, 'copy may be incomplete'): summarize(self.light)
        path.write_bytes(b'')
        self.rehash(self.light)
        with self.assertRaisesRegex(EvidenceError, 'empty artifact'): summarize(self.light)
        path.write_bytes(original)
        self.rehash(self.light)
        receipt = self.read()
        del receipt['sha256']['scene.usda']
        (self.light / 'receipt.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(EvidenceError, 'Missing required artifact hashes'): summarize(self.light)

    def test_recording_directory_is_read_only(self):
        before = {p.name: p.read_bytes() for p in self.light.iterdir()}
        summarize(self.light)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.light.iterdir()})

    def test_truncated_and_sparse_state_even_with_rehashed_manifest(self):
        original = self.rows()
        for rows in (original[:-1], original[1:], original[:-30], original[:300] + original[301:]):
            self.write_rows(rows)
            with self.assertRaises(EvidenceError): summarize(self.light)

    def test_duplicate_and_reordered_times(self):
        original = self.rows()
        for rows in (original + [original[-1]], original[:300] + list(reversed(original[300:]))):
            self.write_rows(rows)
            with self.assertRaisesRegex(EvidenceError, 'Noncontiguous'): summarize(self.light)

    def test_all_window_predicates_required_without_filtering(self):
        original = self.rows()
        for flag in ('stable', 'released', 'supported', 'upright', 'verified_lift', 'in_receiver', 'success'):
            with self.subTest(flag=flag):
                rows = copy.deepcopy(original)
                rows[-60][flag] = False
                self.write_rows(rows)
                with self.assertRaisesRegex(EvidenceError, flag): summarize(self.light)

    def test_numeric_settle_conditions_override_optimistic_flags(self):
        original = self.rows()
        for key, value in [('linear_speed_m_s', .1), ('angular_speed_rad_s', .2),
                           ('gripper_distance_m', .01), ('settled_s', .9),
                           ('object_position_m', [.2, .1, -.1]), ('receiver_force_N', 1.)]:
            with self.subTest(key=key):
                rows = copy.deepcopy(original)
                rows[-10][key] = value
                self.write_rows(rows)
                with self.assertRaises(EvidenceError): summarize(self.light)

    def test_wrong_force_sign_cannot_be_hidden_by_magnitude(self):
        rows = self.rows()
        rows[-30]['contact_vectors_N'][2][2] *= -1
        self.write_rows(rows)
        with self.assertRaisesRegex(EvidenceError, 'upward'): summarize(self.light)

    def test_persistent_finger_contact_refused(self):
        rows = self.rows()
        rows[-1]['contact_vectors_N'][0] = [.1, 0., 0.]
        self.write_rows(rows)
        with self.assertRaisesRegex(EvidenceError, 'Finger contact'): summarize(self.light)

    def test_nonsettle_sample_not_silently_filtered(self):
        rows = self.rows()
        rows[-60]['phase'] = 'retreat'
        self.write_rows(rows)
        with self.assertRaisesRegex(EvidenceError, 'entirely in settle'): summarize(self.light)

    def test_insufficient_settle_phase(self):
        self.change_config('phases', [{'name': 'settle', 'start_s': 2.5, 'end_s': 3.}])
        with self.assertRaisesRegex(EvidenceError, 'shorter than one second'): summarize(self.light)

    def test_earlier_explicit_failure_is_not_ignored(self):
        rows = self.rows()
        rows[20]['failure'] = 'synthetic contact loss'
        self.write_rows(rows)
        with self.assertRaisesRegex(EvidenceError, 'Explicit failed sample'): summarize(self.light)

    def test_nonfinite_and_malformed_rows_anywhere_are_refused(self):
        original = self.rows()
        for value in (float('nan'), float('inf'), -float('inf')):
            rows = copy.deepcopy(original)
            rows[3]['extra_sensor'] = value
            self.write_rows(rows)
            with self.assertRaisesRegex(EvidenceError, 'nonfinite'): summarize(self.light)
        self.write_rows(original)
        with (self.light / 'state.jsonl').open('a') as stream: stream.write('{')
        self.rehash(self.light)
        with self.assertRaisesRegex(EvidenceError, 'invalid JSON'): summarize(self.light)

    def test_nonfinite_metadata_is_refused(self):
        receipt = self.read()
        receipt['extra_sensor'] = float('nan')
        self.write(receipt)
        with self.assertRaisesRegex(EvidenceError, 'nonfinite'): summarize(self.light)

    def test_duplicate_json_keys_refused(self):
        with (self.light / 'state.jsonl').open('a') as stream:
            stream.write('{"sim_time_s": 3.01, "sim_time_s": 3.02}\n')
        self.rehash(self.light)
        with self.assertRaisesRegex(EvidenceError, 'Duplicate JSON key'): summarize(self.light)

    def test_unlabelled_old_run_cannot_be_repurposed(self):
        self.change_config('experiment', {})
        with self.assertRaisesRegex(EvidenceError, 'do not relabel'): summarize(self.light)

    def test_mismatched_trial_config_refused(self):
        config = self.read('trial-configuration.json')
        config['cube_edge_m'] = .03
        self.write(config, 'trial-configuration.json')
        with self.assertRaisesRegex(EvidenceError, 'disagree'): summarize(self.light)

    def test_provenance_and_clean_source_required(self):
        original = self.read()
        for key, value in [('provenance', 'PHYSICAL'), ('backend', 'robot'), ('git_dirty', True),
                           ('git_commit', ''), ('gpu', ''), ('hostname', '')]:
            receipt = copy.deepcopy(original)
            receipt[key] = value
            self.write(receipt)
            with self.assertRaises(EvidenceError): summarize(self.light)

    def test_gravity_and_sample_rate_required(self):
        original = self.read()
        for key, value in [('physics_dt', 1 / 60), ('up_axis', 'Y'), ('gravity_m_s2', 9.8)]:
            receipt = copy.deepcopy(original)
            receipt['scene'][key] = value
            self.write(receipt)
            with self.assertRaises(EvidenceError): summarize(self.light)

    def test_pair_mismatched_commit_asset_and_scene(self):
        original = self.read(root=self.heavy)
        for key, value in [('git_commit', 'd' * 40), ('robot_asset', {'sha256': 'e' * 64}),
                           ('initial_joint_positions_rad', [1., 2., 3., 4., 5., 6.]),
                           ('launcher_config', {'create_new_stage': False}),
                           ('scene', {**original['scene'], 'solver': 'different'})]:
            with self.subTest(key=key):
                receipt = copy.deepcopy(original)
                receipt[key] = value
                self.write(receipt, root=self.heavy)
                with self.assertRaisesRegex(EvidenceError, 'Unmatched controls'): compare_trials(self.light, self.heavy)

    def test_pair_mismatched_friction_geometry_protocol(self):
        original = copy.deepcopy(self.read(root=self.heavy)['trial_configuration'])
        for key, value in [('material', {'static_friction': .7, 'dynamic_friction': .8, 'restitution': 0.}),
                           ('cube_edge_m', .021), ('closed_jaw_rad', .08), ('source_m', [.24, 0., .01])]:
            with self.subTest(key=key):
                receipt = self.read(root=self.heavy)
                receipt['trial_configuration'] = copy.deepcopy(original)
                self.write(receipt, root=self.heavy)
                self.change_config(key, value, root=self.heavy)
                with self.assertRaisesRegex(EvidenceError, 'Unmatched controls'): compare_trials(self.light, self.heavy)

    def test_wrong_label_mass_and_gravity(self):
        original = copy.deepcopy(self.read()['trial_configuration'])
        for key, value in [('cube_mass_kg', .02), ('experiment', {**original['experiment'], 'gravity_m_s2': 1.62}),
                           ('experiment', {**original['experiment'], 'condition': 'medium'})]:
            receipt = self.read()
            receipt['trial_configuration'] = copy.deepcopy(original)
            self.write(receipt)
            self.change_config(key, value)
            with self.assertRaises(EvidenceError): summarize(self.light)

    def test_pair_arguments_cannot_be_swapped(self):
        with self.assertRaisesRegex(EvidenceError, 'corresponding conditions'): compare_trials(self.heavy, self.light)

    def test_path_traversal_and_symlink_artifacts_refused(self):
        original = self.read()
        receipt = copy.deepcopy(original)
        receipt['sha256']['../outside'] = 'a' * 64
        (self.light / 'receipt.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(EvidenceError, 'Unsafe artifact'): summarize(self.light)
        (self.light / 'receipt.json').write_text(json.dumps(original))
        (self.root / 'outside').write_bytes((self.light / 'camera.mp4').read_bytes())
        (self.light / 'camera.mp4').unlink()
        (self.light / 'camera.mp4').symlink_to(self.root / 'outside')
        with self.assertRaisesRegex(EvidenceError, 'Missing/empty artifact'): summarize(self.light)

    def test_changing_receipt_during_read_refused(self):
        from simulation.isaac import experiment_report
        original = experiment_report._window
        def change(*args):
            result = original(*args)
            receipt = self.read()
            receipt['changed_during_read'] = True
            self.write(receipt)
            return result
        with patch.object(experiment_report, '_window', side_effect=change):
            with self.assertRaisesRegex(EvidenceError, 'Evidence changed'): summarize(self.light)

    def test_cli_refusal_creates_no_report(self):
        receipt = self.read()
        receipt['status'] = 'failed'
        self.write(receipt)
        output = self.root / 'refused'
        command = [sys.executable, '-m', 'simulation.isaac.experiment_report', '--light', str(self.light),
                   '--heavy', str(self.heavy), '--output', str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Report refused', result.stderr)
        self.assertFalse(output.exists())

    def test_cli_cannot_write_inside_recording(self):
        with self.assertRaises(SystemExit) as caught:
            main(['--light', str(self.light), '--heavy', str(self.heavy), '--output', str(self.light / 'report')])
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse((self.light / 'report').exists())


if __name__ == '__main__':
    unittest.main()
