"""Rebuild evidence-bound vessel assets. No robot, poses, docks or hardware access.

Input profiles are millimetres; OBJ, STL and MuJoCo exports are metres.
The datum is the centre of the exterior support plane; +Z points to the opening.
The donor spout points along +Y. Interior assumptions remain explicit in JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

DEFAULT = Path(__file__).resolve().parents[1] / 'models/vessels/measured_2026_11_14'


def load_parameters(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data['units'] != 'mm':
        raise ValueError('Profile input must use mm.')
    for vessel in data['vessels'].values():
        for field in ('outer_profile', 'inner_profile'):
            p = np.asarray(vessel[field], dtype=float)
            if p.ndim != 2 or p.shape[1] != 2 or len(p) < 2:
                raise ValueError('Profiles require [height, radius] pairs.')
            if not np.isfinite(p).all() or (p < 0).any() or (np.diff(p[:, 0]) <= 0).any():
                raise ValueError('Profiles must be finite, nonnegative and strictly ascending.')
        outer, inner = np.asarray(vessel['outer_profile']), np.asarray(vessel['inner_profile'])
        if outer[0, 0] != 0 or not 0 < inner[0, 0] < outer[-1, 0] or inner[-1, 0] != outer[-1, 0]:
            raise ValueError('Support plane, interior floor and rim datum are inconsistent.')
        heights = np.unique(np.r_[inner[:, 0], outer[outer[:, 0] >= inner[0, 0], 0]])
        if np.any(np.interp(heights, inner[:, 0], inner[:, 1]) >= np.interp(heights, outer[:, 0], outer[:, 1])):
            raise ValueError('Interior must remain inside exterior.')
        spout = vessel['spout']
        if (not all(math.isfinite(spout[k]) for k in ('extension_mm', 'half_angle_deg', 'start_height_mm'))
                or spout['extension_mm'] < 0 or not 0 < spout['half_angle_deg'] < 90
                or not 0 <= spout['start_height_mm'] < outer[-1, 0]):
            raise ValueError('Invalid spout.')
    return data


def radius(profile, height):
    p = np.asarray(profile)
    return float(np.interp(height, p[:, 0], p[:, 1]))


def cavity_volume_ml(vessel, height_mm=None):
    """Exact frustum integration of the axial interior; excludes spout expansion."""
    p = vessel['inner_profile']
    stop = p[-1][0] if height_mm is None else height_mm
    if not p[0][0] <= stop <= p[-1][0]:
        raise ValueError('Requested liquid level lies outside the cavity.')
    volume = 0.0
    for (z0, r0), (z1, r1) in zip(p, p[1:]):
        end = min(z1, stop)
        if end <= z0:
            break
        rend = r0 + (r1 - r0) * (end - z0) / (z1 - z0)
        volume += math.pi * (end - z0) * (r0*r0 + r0*rend + rend*rend) / 3
    return volume / 1000


def _spout_offset(vessel, z, angle):
    spout = vessel['spout']
    height = vessel['outer_profile'][-1][0]
    dz = max(0.0, min(1.0, (z - spout['start_height_mm']) / (height - spout['start_height_mm'])))
    delta = math.atan2(math.sin(angle - math.pi/2), math.cos(angle - math.pi/2))
    angular = max(0.0, 1 - abs(delta) / math.radians(spout['half_angle_deg']))
    return spout['extension_mm'] * dz * angular


def surface_mesh(vessel, segments=128):
    """Closed material surface, including cavity, floor, underside, lip and spout."""
    if segments < 16 or segments % 4:
        raise ValueError('Use at least 16 angular segments, divisible by four.')
    outer, inner = vessel['outer_profile'], vessel['inner_profile']
    profile = [(0.0, 0.0)] + [tuple(p) for p in outer] + [tuple(p) for p in reversed(inner)] + [(inner[0][0], 0.0)]
    verts, rings = [], []
    for z, r in profile:
        if r == 0:
            rings.append([len(verts)])
            verts.append([0.0, 0.0, z/1000])
        else:
            ring = []
            for i in range(segments):
                a = math.tau*i/segments
                rr = r + _spout_offset(vessel, z, a)
                ring.append(len(verts))
                verts.append([rr*math.cos(a)/1000, rr*math.sin(a)/1000, z/1000])
            rings.append(ring)
    faces = []
    for a, b in zip(rings, rings[1:]):
        for j in range(segments):
            k = (j+1) % segments
            if len(a) == 1:
                faces.append([a[0], b[k], b[j]])
            elif len(b) == 1:
                faces.append([a[j], a[k], b[0]])
            else:
                faces.extend([[a[j], a[k], b[k]], [a[j], b[k], b[j]]])
    return np.asarray(verts), np.asarray(faces, dtype=int)


def write_obj(path, vertices, faces):
    lines = ['# Metres; origin support-plane centre; +Z up; donor spout +Y']
    lines += ['v '+ ' '.join(f'{v:.9g}' for v in p) for p in vertices]
    lines += ['f '+' '.join(str(i+1) for i in face) for face in faces]
    path.write_text('\n'.join(lines)+'\n')


def write_stl(path, vertices, faces):
    with path.open('wb') as stream:
        stream.write(b'OpenArms vessel; coordinates in METRES'.ljust(80, b'\0'))
        stream.write(struct.pack('<I', len(faces)))
        for face in faces:
            triangle = vertices[face]
            normal = np.cross(triangle[1]-triangle[0], triangle[2]-triangle[0])
            normal /= np.linalg.norm(normal)
            stream.write(struct.pack('<12fH', *normal, *triangle.ravel(), 0))


def _wedge(vessel, z0, z1, i, n):
    """One convex wall segment; chords approximate the circular boundary."""
    vertices = []
    for z in (z0, z1):
        for field in ('inner_profile', 'outer_profile'):
            r = radius(vessel[field], z)
            for a in (math.tau*i/n, math.tau*(i+1)/n):
                rr = r + _spout_offset(vessel, z, a)
                vertices.append([rr*math.cos(a)/1000, rr*math.sin(a)/1000, z/1000])
    return vertices


def build(output=DEFAULT, parameters=None):
    output = Path(output)
    parameters = Path(parameters or output/'parameters.json')
    data = load_parameters(parameters)
    output.mkdir(parents=True, exist_ok=True)
    root = ET.Element('mujoco', model='photo_derived_vessels')
    ET.SubElement(root, 'compiler', angle='radian')
    ET.SubElement(root, 'option', gravity='0 0 -9.81')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='1400', offheight='1000')
    assets = ET.SubElement(root, 'asset')
    world = ET.SubElement(root, 'worldbody')
    ET.SubElement(world, 'light', pos='0 -0.3 0.5', dir='0 0 -1', diffuse='.8 .8 .8')
    ET.SubElement(world, 'geom', name='table', type='plane', size='.25 .2 .005', rgba='.13 .16 .18 1')
    summary = {}
    for index, (name, vessel) in enumerate(data['vessels'].items()):
        vertices, faces = surface_mesh(vessel)
        write_obj(output/f'{name}.obj', vertices, faces)
        write_stl(output/f'{name}.stl', vertices, faces)
        ET.SubElement(assets, 'mesh', name=name+'_visual', file=name+'.obj')
        body = ET.SubElement(world, 'body', name=name, pos=f'{-.055 if index == 0 else .055} 0 0')
        ET.SubElement(body, 'geom', name=name+'_surface', type='mesh', mesh=name+'_visual', contype='0', conaffinity='0', group='1', rgba='.72 .84 .91 1')
        floor = vessel['inner_profile'][0][0]
        # Base and separate convex wall segments preserve an open collision cavity.
        # These are geometry proxies, not validated friction/mass/contact properties.
        ET.SubElement(body, 'geom', name=name+'_base', type='cylinder',
                      pos=f'0 0 {floor/2000}', size=f'{radius(vessel["outer_profile"], 0)/1000} {floor/2000}',
                      group='3', rgba='.8 .4 .2 1')
        z_values = sorted(set([p[0] for p in vessel['inner_profile']] + [p[0] for p in vessel['outer_profile'] if p[0] >= floor] + [vessel['spout']['start_height_mm']]))
        z_values = [z for z in z_values if floor <= z <= vessel['outer_profile'][-1][0]]
        for level, (z0, z1) in enumerate(zip(z_values, z_values[1:])):
            for i in range(48):
                mesh_name = f'{name}_wall_{level}_{i}'
                verts = _wedge(vessel, z0, z1, i, 48)
                ET.SubElement(assets, 'mesh', name=mesh_name, vertex=' '.join(f'{v:.9g}' for p in verts for v in p))
                ET.SubElement(body, 'geom', type='mesh', mesh=mesh_name, group='3', rgba='.8 .4 .2 1')
        summary[name] = {'axisymmetric_cavity_to_rim_ml': cavity_volume_ml(vessel),
                         'dimensions_m': (vertices.max(axis=0)-vertices.min(axis=0)).tolist(),
                         'visual_triangles': len(faces), 'nominal_identity': 'unconfirmed',
                         'interior_status': vessel['interior_status']}
        if vessel.get('graduation'):
            g = vessel['graduation']
            volume = cavity_volume_ml(vessel, g['height_from_exterior_base_mm'])
            summary[name]['graduation_check'] = {'marked_ml':g['marked_ml'], 'model_ml':volume,
                'difference_ml':volume-g['marked_ml'],
                'height_above_interior_floor_mm':g['height_from_exterior_base_mm']-floor}
    ET.indent(root)
    ET.ElementTree(root).write(output/'vessels.xml', encoding='unicode', xml_declaration=True)
    summary['parameters_sha256'] = hashlib.sha256(parameters.read_bytes()).hexdigest()
    (output/'geometry_summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary



def render_views(output=DEFAULT, parameters=None):
    """Render uncalibrated comparison views; collision group 3 stays hidden."""
    import mujoco
    from PIL import Image, ImageDraw, ImageFont
    output = Path(output)
    source = load_parameters(Path(parameters or output/'parameters.json'))
    model = mujoco.MjModel.from_xml_path(str(output/'vessels.xml'))
    model.vis.global_.fovy = .16  # Orthographic vertical span in metres.
    state = mujoco.MjData(model)
    mujoco.mj_forward(model, state)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0, 0, .025]
    camera.distance = .29
    camera.orthographic = 1
    options = mujoco.MjvOption()
    options.geomgroup[3] = 0
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 23)
    except OSError:
        font = ImageFont.load_default()
    with mujoco.Renderer(model, 800, 1200) as renderer:
        for name, azimuth, elevation in [('oblique',90,-28),('side',90,0),('top',90,-90)]:
            camera.azimuth, camera.elevation = azimuth, elevation
            renderer.update_scene(state, camera, scene_option=options)
            image = Image.fromarray(renderer.render())
            draw = ImageDraw.Draw(image)
            draw.rectangle((0,0,1200,76),fill='#14212a')
            draw.text((25,14),f'Photo-derived vessels | {name} view | dimensions in mm',font=font,fill='white')
            draw.text((25,45),'Geometry only. Interior assumptions remain unmeasured.',font=font,fill='#e8c58b')
            for x, (vessel_name, vessel) in zip((145, 670), source['vessels'].items()):
                height = vessel['outer_profile'][-1][0]
                diameter = 2 * vessel['outer_profile'][-1][1]
                draw.text((x,745), f'{vessel_name} | H {height:g} | circular rim {diameter:g}',font=font,fill='white')
            image.save(output/f'{name}.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--parameters', type=Path)
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.parameters), indent=2))
    if args.render:
        render_views(args.output, args.parameters)


if __name__ == '__main__':
    main()
