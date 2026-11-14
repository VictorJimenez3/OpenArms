"""Appearance override on the upstream camera-free articulation, in meters."""
from pxr import Gf, Usd

ROBOT_ASSET = 'SO-ARM101-USD-NO-CAMERA.usd'


def apply_white_plastic(stage, robot_path='/World/Robot'):
    robot = stage.GetPrimAtPath(robot_path)
    cameras = [str(p.GetPath()) for p in Usd.PrimRange(robot, Usd.TraverseInstanceProxies())
               if 'camera' in p.GetName().lower()]
    if cameras:
        raise RuntimeError(f'Unexpected onboard camera geometry: {cameras}')
    shader_path = robot_path + '/Looks/material_a_3d_printed/Shader'
    attribute = stage.GetPrimAtPath(shader_path).GetAttribute('inputs:diffuse_color_constant')
    if not attribute:
        raise RuntimeError('Upstream printed-plastic material was not found')
    attribute.Set(Gf.Vec3f(.95, .95, .95))
    return {'robot_asset': ROBOT_ASSET, 'onboard_camera': False,
            'plastic_color_rgb': [.95, .95, .95], 'material_shader': shader_path,
            'external_evidence_camera': True}
