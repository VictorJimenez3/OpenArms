import pytest

from openarms_lab.scene import SceneService


@pytest.mark.asyncio
async def test_observation_depends_on_pixels_not_controller_success(tmp_path):
    service = SceneService(tmp_path)
    before = await service.observe('session-a', {'controller_completed': True, 'condition_id': 'vinegar'})
    assert before['features']['readable'] and before['features']['color'] == 'purple'
    assert before['features']['sample_cup_held'] is False
    service.world('session-a').apply_sample('vinegar')
    after = await service.observe('session-a', {'controller_completed': False})
    assert after['features']['readable'] and after['features']['color'] == 'pink'
    assert before['images'][0]['sha256'] != after['images'][0]['sha256']
    assert after['provenance'] == 'SYNTHETIC'
    assert 'simulation' in after['text']


@pytest.mark.asyncio
async def test_occlusion_secondary_view_staleness_and_missing_receiver(tmp_path):
    service = SceneService(tmp_path)
    world = service.world('s')
    world.occluded_primary = True
    assert (await service.observe('s', {'status': 'completed'}))['status'] == 'unknown'
    assert (await service.observe('s', {'view': 'secondary'}))['status'] == 'observed'
    world.stale = True
    assert (await service.observe('s', {'view': 'secondary'}))['status'] == 'unknown'
    world.stale = False
    world.receiver_missing = True
    assert (await service.observe('s', {'view': 'secondary'}))['status'] == 'unknown'


@pytest.mark.asyncio
async def test_localization_reports_pixel_evidence_without_grasp_coordinates(tmp_path):
    service = SceneService(tmp_path)
    frame = await service.inspect_scene('a')
    located = await service.localize_objects('a', frame['evidence_id'], ['source', 'receiver', 'unknown_object'])
    assert located['verified_labels'] == ['source', 'receiver']
    assert all(item['grasp_pose'] is None and not item['geometry_valid'] for item in located['detections'])
    assert located['detections'][-1]['status'] == 'unknown'
    with pytest.raises(ValueError, match='owned by this session'):
        await service.localize_objects('b', frame['evidence_id'], ['source'])
    from pathlib import Path
    Path(frame['images'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed after capture'):
        await service.localize_objects('a', frame['evidence_id'], ['source'])


@pytest.mark.asyncio
async def test_camera_metadata_binds_localization_to_the_original_vessels_and_docks(tmp_path):
    service = SceneService(tmp_path)
    before = await service.inspect_scene('session', 'secondary')
    frame = before['scene']
    world = service.world('session')
    world.vessels_swapped = True
    after = await service.inspect_scene('session', 'secondary')
    assert frame['captured_at'] == before['images'][0]['captured_at']
    assert frame['frame_id'] == before['images'][0]['evidence_id']
    assert frame['camera_id'] == 'synthetic-secondary'
    assert frame['fixture_registration_valid'] is True
    assert frame['base_registration_id'] is None
    assert (frame['clock'], frame['coordinate_frame'], frame['units']) == ('unix_seconds', 'image_pixels', 'px')
    labels = ['source', 'receiver', 'A', 'C']
    original = await service.localize_objects('session', frame['frame_id'], labels)
    assert original['verified_labels'] == labels
    for d in original['detections']:
        assert d['frame_id'] == frame['frame_id']
        assert d['timestamp_s'] == frame['captured_at']
        for field in ('camera_id', 'camera_config_id', 'calibration_id', 'provenance', 'units', 'coordinate_frame'):
            assert d[field] == frame[field]
    moved = await service.localize_objects('session', after['evidence_id'], labels)
    assert moved['verified_labels'] == ['source', 'receiver']
    assert [(d['vessel_id'], d['dock_id']) for d in moved['detections'][:2]] == [
        ('source', 'C'), ('receiver', 'A')]
    assert (await service.observe('session', {'view': 'secondary'}))['status'] == 'unknown'
