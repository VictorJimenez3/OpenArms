"""Geometry/scale checks only; no physical grasp or pour qualification."""
from collections import Counter
import json
import math

import numpy as np
import pytest

from openarms_sim.vessel_assets import DEFAULT, build, cavity_volume_ml, load_parameters, surface_mesh


def test_frustum_volume_has_explicit_mm_to_ml_conversion():
    v = {'inner_profile': [[2, 10], [32, 20]]}
    expected = math.pi * 30 * (100 + 200 + 400) / 3 / 1000
    assert cavity_volume_ml(v) == pytest.approx(expected)
    assert cavity_volume_ml(v, 2) == 0
    with pytest.raises(ValueError):
        cavity_volume_ml(v, 1)


def test_mesh_closed_oriented_and_matches_declared_metric_extents():
    data = load_parameters(DEFAULT/'parameters.json')
    for name, v in data['vessels'].items():
        vertices, faces = surface_mesh(v)
        edges = Counter(tuple(sorted((a, b))) for f in faces for a,b in zip(f, np.roll(f,-1)))
        assert set(edges.values()) == {2}
        directed = Counter((a,b) for f in faces for a,b in zip(f,np.roll(f,-1)))
        assert all(directed[a,b] == directed[b,a] for a,b in directed)
        tri = vertices[faces]
        signed = np.einsum('ij,ij->i', tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6
        assert signed > 0
        assert vertices[:,2].min() == 0
        assert vertices[:,2].max() == pytest.approx(v['dimensions']['height']['value_mm']/1000)
        diameter = v['dimensions'].get('rim_diameter',v['dimensions'].get('rim_diameter_excluding_spout'))['value_mm']
        assert np.ptp(vertices[:,0]) == pytest.approx(diameter/1000)
        assert np.ptp(vertices[:,1]) == pytest.approx((diameter+v['spout']['extension_mm'])/1000)


def test_generated_mujoco_cavity_is_open_to_floor(tmp_path):
    mujoco = pytest.importorskip('mujoco')
    build(tmp_path, DEFAULT/'parameters.json')
    model = mujoco.MjModel.from_xml_path(str(tmp_path/'vessels.xml'))
    state = mujoco.MjData(model)
    mujoco.mj_forward(model,state)
    parameters = load_parameters(DEFAULT/'parameters.json')
    for index, (name,v) in enumerate(parameters['vessels'].items()):
        origin = np.array([-.055 if index==0 else .055, 0, .10])
        geom_id = np.array([-1],dtype=np.int32)
        distance = mujoco.mj_ray(model,state,origin,np.array([0.,0.,-1.]),np.array([0,0,0,1,0,0],dtype=np.uint8),1,-1,geom_id)
        assert .10-distance == pytest.approx(v['inner_profile'][0][0]/1000,abs=1e-7)
        assert mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,geom_id[0]) == name+'_base'
    assert model.njnt == 0  # Asset scene has no actuation or inferred dynamics.


def test_invalid_interior_cannot_cross_exterior(tmp_path):
    data=json.loads((DEFAULT/'parameters.json').read_text())
    data['vessels']['donor_A']['inner_profile'][1][1]=100
    p=tmp_path/'bad.json';p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Interior'):
        load_parameters(p)
