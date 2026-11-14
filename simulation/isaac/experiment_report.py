"""Audit recorded Isaac mass/weight trials without importing Isaac or NumPy.

The measured quantity is the signed +Z component of contact_vectors_N[2]
(receiver normal force on the cube), not receiver_force_N's magnitude or m*g.
The final closed one-second interval contains 121 samples at 120 Hz. No samples
in that interval are dropped. Earlier explicit failures and nonfinite values
also invalidate the recording. Hashes check integrity against the local receipt;
they are not an independent signature of the simulator or a physical-robot test.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


DT = 1 / 120
TIME_TOLERANCE_S = 1e-5  # Covers Isaac's accumulated float32 physics-dt roundoff.
STEP_TOLERANCE_S = 1e-6
WINDOW_S = 1.0
MASSES_KG = {'light': .010, 'heavy': .040}


class EvidenceError(ValueError):
    """The supplied local evidence cannot support this report."""


def _require(ok, message):
    if not ok:
        raise EvidenceError(message)


def _finite(value, label):
    if isinstance(value, float):
        _require(math.isfinite(value), f'{label}: nonfinite value')
    elif isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f'{label}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite(item, f'{label}[{index}]')


def _number(value, label, *, positive=False, nonnegative=False):
    _require(type(value) in (int, float), f'{label}: expected a finite number')
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise EvidenceError(f'{label}: invalid number') from exc
    _require(math.isfinite(result), f'{label}: nonfinite value')
    _require(not positive or result > 0, f'{label}: must be positive')
    _require(not nonnegative or result >= 0, f'{label}: must be nonnegative')
    return result


def _vector(value, length, label):
    _require(isinstance(value, list) and len(value) == length,
             f'{label}: expected {length} components')
    return [_number(item, label) for item in value]


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _parse(text, label):
    try:
        result = json.loads(text, object_pairs_hook=_pairs)
    except (ValueError, TypeError) as exc:
        raise EvidenceError(f'{label}: invalid JSON ({exc})') from exc
    _require(isinstance(result, dict), f'{label}: expected a JSON object')
    _finite(result, label)
    return result


def _read(path):
    try:
        return _parse(path.read_text(), str(path))
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f'Missing/unreadable evidence: {path}') from exc


def _sha256(path):
    digest = hashlib.sha256()
    try:
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceError(f'Missing/unreadable artifact: {path}') from exc
    return digest.hexdigest()


def _artifact(root, name):
    _require(isinstance(name, str) and name not in ('', '.', '..', 'receipt.json')
             and Path(name).name == name and '/' not in name and '\\' not in name,
             f'Unsafe artifact name: {name!r}')
    path = root / name
    _require(not path.is_symlink() and path.is_file() and path.stat().st_size > 0,
             f'Missing/empty artifact (copy may be incomplete): {path}')
    return path


def _validate_hashes(root, receipt):
    hashes = receipt.get('sha256')
    _require(isinstance(hashes, dict), 'receipt.sha256 is required')
    video = receipt.get('video')
    _require(isinstance(video, str), 'receipt.video is required')
    required = {'state.jsonl', 'execution.json', 'scene.usda',
                'trial-configuration.json', video}
    _require(required <= hashes.keys(), f'Missing required artifact hashes: {required - hashes.keys()}')
    paths = {}
    for name, expected in hashes.items():
        _require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected),
                 f'Invalid SHA256 for {name}')
        path = _artifact(root, name)
        _require(_sha256(path) == expected, f'SHA256 mismatch: {path} (copy may be incomplete)')
        paths[name] = str(path)
    return paths


def _metadata(receipt, root):
    _require(receipt.get('status') == 'passed' and receipt.get('manipulation_success') is True,
             'Receipt must report passed manipulation')
    _require(type(receipt.get('process_returncode')) is int and receipt['process_returncode'] == 0,
             'Receipt must record process_returncode 0')
    _require(receipt.get('provenance') == 'SIMULATED' and receipt.get('backend') == 'simulated',
             'Expected explicit SIMULATED provenance and simulated backend')
    _require(receipt.get('kind') == 'cube_to_receiver', 'Expected cube_to_receiver evidence')
    _require(receipt.get('git_dirty') is False, 'Source must have recorded clean git state')
    commit = receipt.get('git_commit')
    _require(isinstance(commit, str) and re.fullmatch(r'[0-9a-f]{40}', commit),
             'Missing/invalid source commit')
    asset = receipt.get('robot_asset', {})
    _require(isinstance(asset, dict) and isinstance(asset.get('sha256'), str)
             and re.fullmatch(r'[0-9a-f]{64}', asset['sha256']), 'Missing/invalid robot asset SHA256')
    for key in ('gpu', 'hostname', 'isaac_version', 'workshop_commit'):
        _require(isinstance(receipt.get(key), str) and receipt[key].strip(), f'Missing {key}')
    config, scene = receipt.get('trial_configuration'), receipt.get('scene')
    _require(isinstance(config, dict) and isinstance(scene, dict), 'Missing trial configuration or scene')
    _require(_read(root / 'trial-configuration.json') == config,
             'Receipt and trial-configuration.json disagree')
    experiment = config.get('experiment', {})
    _require(isinstance(experiment, dict) and experiment.get('name') == 'mass_vs_weight',
             'Recording lacks mass_vs_weight experiment metadata; do not relabel a prior run')
    condition = experiment.get('condition')
    _require(isinstance(condition, str) and condition in MASSES_KG,
             'Experiment condition must be light or heavy')
    mass = _number(config.get('cube_mass_kg'), 'cube_mass_kg', positive=True)
    _require(math.isclose(mass, MASSES_KG[condition], rel_tol=0, abs_tol=1e-12),
             'Condition mass must be light .010 kg or heavy .040 kg')
    gravity = _number(experiment.get('gravity_m_s2'), 'experiment.gravity_m_s2', positive=True)
    _require(math.isclose(gravity, 9.81, rel_tol=0, abs_tol=1e-12), 'Expected fixed gravity 9.81 m/s^2')
    _require(scene.get('up_axis') == 'Z' and scene.get('units') == 'meters',
             'Expected meters and Z-up scene')
    _require(_number(scene.get('gravity_m_s2'), 'scene.gravity_m_s2', positive=True) == gravity,
             'Scene and experiment gravity disagree')
    _require(math.isclose(_number(scene.get('physics_dt'), 'physics_dt'), DT,
                         rel_tol=0, abs_tol=1e-12), 'Expected 120 Hz physics_dt')
    for key in ('source_m', 'destination_m'):
        _vector(config.get(key), 3, key)
    _number(config.get('cube_edge_m'), 'cube_edge_m', positive=True)
    _number(config.get('cube_yaw_rad'), 'cube_yaw_rad')
    _require(isinstance(config.get('material'), dict) and
             {'static_friction', 'dynamic_friction', 'restitution'} <= config['material'].keys(),
             'Friction/restitution metadata is required')
    for key in ('static_friction', 'dynamic_friction', 'restitution'):
        _number(config['material'][key], key, nonnegative=True)
    _require(config.get('attachments') is False and config.get('pose_writes_after_reset') is False
             and config.get('receiver_kinematic_fixture') is True,
             'Expected contact-only protocol with fixed receiver')
    phases = config.get('phases')
    _require(isinstance(phases, list) and phases and isinstance(phases[-1], dict)
             and phases[-1].get('name') == 'settle', 'Protocol must end with settle phase')
    settle = phases[-1]
    start = _number(settle.get('start_s'), 'settle.start_s', nonnegative=True)
    end = _number(settle.get('end_s'), 'settle.end_s', positive=True)
    _require(end - start >= WINDOW_S, 'Configured settle phase is shorter than one second')
    return condition, mass, gravity, start, end


def _window(root, receipt, settle_start, settle_end):
    # Keep only a rolling final interval in memory, while validating every row.
    from collections import deque
    tail = deque()
    previous = None
    total = 0
    try:
        with (root / 'state.jsonl').open() as stream:
            for line_number, line in enumerate(stream, 1):
                sample = _parse(line, f'state.jsonl:{line_number}')
                t = _number(sample.get('sim_time_s'), 'sim_time_s', positive=True)
                if previous is None:
                    _require(abs(t - DT) <= TIME_TOLERANCE_S, 'State recording does not start at first physics sample')
                else:
                    _require(abs(t - previous - DT) <= STEP_TOLERANCE_S,
                             f'Noncontiguous 120 Hz samples at state.jsonl:{line_number}')
                _require(sample.get('failure') is None,
                         f'Explicit failed sample at state.jsonl:{line_number}')
                previous = t
                total += 1
                tail.append(sample)
                while tail and tail[0]['sim_time_s'] < t - WINDOW_S - TIME_TOLERANCE_S:
                    tail.popleft()
    except (OSError, UnicodeError) as exc:
        raise EvidenceError('Missing/unreadable state.jsonl') from exc
    _require(total > 0 and abs(previous - settle_end) <= TIME_TOLERANCE_S,
             'Incomplete state recording: final sample must reach configured settle end')
    _require(len(tail) == 121 and
             abs(tail[-1]['sim_time_s'] - tail[0]['sim_time_s'] - WINDOW_S) <= TIME_TOLERANCE_S,
             'Need a contiguous closed one-second window (121 samples at 120 Hz)')
    forces = []
    for sample in tail:
        t = sample['sim_time_s']
        _require(sample.get('phase') == 'settle' and t >= settle_start - TIME_TOLERANCE_S,
                 'Final one-second window must be entirely in settle phase')
        for flag in ('stable', 'released', 'supported', 'upright', 'verified_lift', 'in_receiver', 'success'):
            _require(sample.get(flag) is True, f'Invalid final-window sample at {t}: {flag} must be true')
        _require(_number(sample.get('settled_s'), 'settled_s', nonnegative=True) >= 1 - TIME_TOLERANCE_S,
                 f'Sample at {t} lacks one second of prior settling')
        position = _vector(sample.get('object_position_m'), 3, 'object_position_m')
        destination = receipt['trial_configuration']['destination_m']
        _require(math.dist(position[:2], destination[:2]) <= .020 and abs(position[2] - destination[2]) <= .002,
                 f'Object outside receiver at {t}')
        _require(_number(sample.get('linear_speed_m_s'), 'linear_speed_m_s', nonnegative=True) < .01
                 and _number(sample.get('angular_speed_rad_s'), 'angular_speed_rad_s', nonnegative=True) < .1,
                 f'Unsettled object speed at {t}')
        _require(_number(sample.get('gripper_distance_m'), 'gripper_distance_m', nonnegative=True) > .05,
                 f'Gripper has not retreated at {t}')
        vectors = sample.get('contact_vectors_N')
        _require(isinstance(vectors, list) and len(vectors) == 3, 'Expected three contact vectors')
        vectors = [_vector(v, 3, 'contact_vectors_N') for v in vectors]
        _require(max(math.hypot(*v) for v in vectors[:2]) < .02, f'Finger contact persists at {t}')
        receiver_magnitude = _number(sample.get('receiver_force_N'), 'receiver_force_N', positive=True)
        _require(math.isclose(receiver_magnitude, math.hypot(*vectors[2]), rel_tol=1e-6, abs_tol=1e-8),
                 f'Receiver force magnitude/vector disagree at {t}')
        support = vectors[2][2]  # Signed normal on the cube, along +Z; never abs().
        _require(support > .05, f'No upward receiver support at {t}')
        forces.append(support)
    return forces, {'start_sim_time_s': tail[0]['sim_time_s'], 'end_sim_time_s': previous,
                    'duration_s': previous - tail[0]['sim_time_s'], 'interval': 'closed',
                    'requested_duration_s': WINDOW_S, 'physics_dt_s': DT,
                    'time_tolerance_s': TIME_TOLERANCE_S, 'total_recorded_samples': total}


def summarize(recording_dir) -> dict:
    """Return an audited SIMULATED trial summary, or raise EvidenceError.

    Input is the directory containing receipt.json and state.jsonl (usually the
    run's recording/ subdirectory). It is read only, including during copying.
    """
    root = Path(recording_dir).expanduser().resolve()
    receipt_path = root / 'receipt.json'
    receipt_hash = _sha256(receipt_path)
    receipt = _read(receipt_path)
    paths = _validate_hashes(root, receipt)
    condition, mass, gravity, settle_start, settle_end = _metadata(receipt, root)
    execution = _read(root / 'execution.json')
    _require(execution.get('status') == 'passed' and type(execution.get('returncode')) is int
             and execution['returncode'] == 0, 'execution.json must report passed and returncode 0')
    _require(execution.get('stopped') is False and execution.get('cleanup_failed') is False
             and execution.get('observation_status') == 'passed', 'Execution stopped or observations/cleanup failed')
    _require(receipt.get('observation_status') == 'passed'
             and receipt.get('shutdown_status') in ('completed', 'process_exited_zero'),
             'Receipt has incomplete/failed observations or shutdown')
    forces, window = _window(root, receipt, settle_start, settle_end)
    # Recheck streamed state and receipt to reject a recording changing mid-read.
    _require(_sha256(root / 'state.jsonl') == receipt['sha256']['state.jsonl']
             and _sha256(receipt_path) == receipt_hash, 'Evidence changed while summarizing; retry after copy completes')
    mean = statistics.fmean(forces)
    expected = mass * gravity
    summary = {
        'schema_version': 1, 'provenance': 'SIMULATED', 'experiment': 'mass_vs_weight',
        'condition': condition, 'mass_kg': mass, 'gravity_m_s2': gravity,
        'mean_support_force_N': mean, 'std_support_force_N': statistics.pstdev(forces),
        'min_support_force_N': min(forces), 'max_support_force_N': max(forces),
        'std_definition': 'population standard deviation across raw window samples',
        'measurement': 'contact_vectors_N[2][2]: signed +Z receiver normal force on cube',
        'expected_weight_N': expected, 'expected_weight_provenance': 'ANALYTIC_PREDICTION',
        'expected_weight_formula': 'mass_kg * gravity_m_s2',
        'relative_error': abs(mean - expected) / expected,
        'relative_error_definition': 'abs(measured mean - analytic prediction) / analytic prediction',
        'sample_count': len(forces), 'time_window': window,
        'source': {'git_commit': receipt['git_commit'], 'git_dirty': receipt['git_dirty'],
                   'isaac_version': receipt['isaac_version'], 'workshop_commit': receipt['workshop_commit'],
                   'robot_asset': receipt['robot_asset'], 'gpu': receipt['gpu'],
                   'hostname': receipt['hostname'], 'execution_context': receipt.get('execution_context'),
                   'command': receipt.get('command'), 'request_id': receipt.get('request_id'),
                   'recording_dir': str(root), 'receipt_path': str(receipt_path),
                   'receipt_sha256': receipt_hash, 'artifact_paths': paths,
                   'artifact_sha256': receipt['sha256']},
        'scene': receipt['scene'], 'trial_configuration': receipt['trial_configuration'],
        'recording_configuration': {key: receipt.get(key) for key in (
            'joint_names', 'initial_joint_positions_rad', 'launcher_config', 'cleanup_mode')},
        'limitations': ['Simulated contact-force measurements; no physical robot or laboratory outcome established.',
                        'One trial per condition does not establish repeatability or statistical significance.',
                        'Artifact hashes are checked against the receipt, not independently authenticated.',
                        'Video visual review remains required; this helper audits numeric evidence.'],
    }
    _finite(summary, 'summary')
    return summary


def _controlled_configuration(summary):
    config = copy.deepcopy(summary['trial_configuration'])
    del config['cube_mass_kg']
    del config['experiment']['condition']
    # These are measured initialization diagnostics, not protocol settings.
    config.pop('runtime_fk_errors', None)
    source = summary['source']
    return {'trial_configuration': config, 'scene': summary['scene'],
            'recording_configuration': summary['recording_configuration'],
            **{key: source[key] for key in ('git_commit', 'isaac_version', 'workshop_commit')},
            'robot_asset_sha256': source['robot_asset']['sha256']}


def compare_trials(light_recording, heavy_recording) -> dict:
    """Audit both trials and require identical controls except mass/condition."""
    light, heavy = summarize(light_recording), summarize(heavy_recording)
    _require(light['condition'] == 'light' and heavy['condition'] == 'heavy',
             '--light/--heavy must contain their corresponding conditions')
    _require(_controlled_configuration(light) == _controlled_configuration(heavy),
             'Unmatched controls: source commit, asset SHA256, scene, physics_dt, gravity, geometry, friction or protocol differ')
    measured_ratio = heavy['mean_support_force_N'] / light['mean_support_force_N']
    expected_ratio = heavy['mass_kg'] / light['mass_kg']
    report = {'schema_version': 1, 'provenance': 'SIMULATED', 'experiment': 'mass_vs_weight',
              'light': light, 'heavy': heavy,
              'comparison': {'measured_support_force_ratio_heavy_to_light': measured_ratio,
                             'known_mass_ratio_heavy_to_light': expected_ratio,
                             'analytic_weight_ratio_heavy_to_light': expected_ratio,
                             'analytic_ratio_provenance': 'ANALYTIC_PREDICTION',
                             'relative_ratio_error': abs(measured_ratio - expected_ratio) / expected_ratio,
                             'matched_controls': True,
                             'excluded_observations_from_control_match': ['runtime_fk_errors']},
              'limitations': light['limitations']}
    _finite(report, 'report')
    return report


def _markdown(report):
    lines = ['# Mass versus weight — SIMULATED', '',
             'Measured signed +Z receiver normal force, final closed 1.0 s of settle (121 raw samples at 120 Hz).', '',
             '| Condition | Mass (kg) | Mean force (N) | Population std (N) | Min–max (N) | Analytic m·g (N) | Relative error |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for label in ('light', 'heavy'):
        s = report[label]
        lines.append(f"| {label} | {s['mass_kg']:.3f} | {s['mean_support_force_N']:.8g} | "
                     f"{s['std_support_force_N']:.4g} | {s['min_support_force_N']:.8g}–{s['max_support_force_N']:.8g} | "
                     f"{s['expected_weight_N']:.8g} | {s['relative_error']:.3%} |")
    c = report['comparison']
    lines += ['', f"Measured heavy/light force ratio: **{c['measured_support_force_ratio_heavy_to_light']:.8g}**. "
              f"Known mass ratio and analytic weight prediction: **{c['known_mass_ratio_heavy_to_light']:.8g}×**; "
              f"relative ratio error {c['relative_ratio_error']:.3%}.", '',
              'Source commit, robot asset hash, scene, gravity, geometry, friction and protocol match. '
              'Only mass/condition vary; measured runtime FK diagnostics are excluded from matching.', '']
    for label in ('light', 'heavy'):
        s, source = report[label], report[label]['source']
        w = s['time_window']
        lines += [f"- {label}: `{source['recording_dir']}`; {s['sample_count']} samples from "
                  f"{w['start_sim_time_s']:.8f} to {w['end_sim_time_s']:.8f} sim s; "
                  f"host `{source['hostname']}`; receipt SHA256 `{source['receipt_sha256']}`."]
    lines += ['', f"Source commit: `{report['light']['source']['git_commit']}`.", '',
              'Full artifact paths, SHA256 values, GPU details and control metadata are in report.json.', '',
              'Analytic m·g values are predictions, separate from recorded forces. No failed samples are discarded.', '']
    lines += [f'- {item}' for item in report['limitations']]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--light', type=Path, required=True, metavar='RECORDING')
    parser.add_argument('--heavy', type=Path, required=True, metavar='RECORDING')
    parser.add_argument('--output', type=Path, required=True, metavar='DIR')
    args = parser.parse_args(argv)
    try:
        output = args.output.expanduser().resolve()
        _require(not any(output.is_relative_to(p.expanduser().resolve()) for p in (args.light, args.heavy)),
                 'Output must be outside source recording directories')
        report = compare_trials(args.light, args.heavy)
        serialized = json.dumps(report, indent=2, allow_nan=False) + '\n'
        markdown = _markdown(report)
        output.mkdir(parents=True, exist_ok=True)
        (output / 'report.json').write_text(serialized)
        (output / 'report.md').write_text(markdown)
    except (EvidenceError, OSError) as exc:
        parser.exit(2, f'Report refused: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
