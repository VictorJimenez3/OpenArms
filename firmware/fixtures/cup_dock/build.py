"""Build ONE single-material four-slot platform plus three quick fit gauges.
Requires OpenSCAD and numpy,trimesh,networkx.
Usage: python build.py --out /absolute/export/path
No robot connection or control changes.
"""
from pathlib import Path
import argparse, concurrent.futures, json, shutil, subprocess, tempfile
import numpy as np
import trimesh
import networkx as nx

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--reuse-meshes',action='store_true',help='Validation/preview only; use only if CAD and parameters are unchanged')
args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
    ep=Path(td)/'config.echo'
    subprocess.run(['openscad','-o',str(ep),'-D','part="config"',str(ROOT/'fixture.scad')],check=True,capture_output=True)
    cfg=json.loads(ep.read_text().strip().removeprefix('ECHO: '))
w,depth,base,gh,wall,clear,opening,cups,centres=cfg
assert len(cups)==len(centres)==4
jobs=[('four-cup-platform.stl',['part="platform"'])]
for delta in [-2,0,2]:jobs.append((f'fit-gauge-{cups[0][0]+delta:g}mm.stl',['part="gauge"',f'gauge_delta={delta}']))
def export(job):
    name,defs=job;cmd=['openscad','-o',str(out/name)]
    for d in defs:cmd+=['-D',d]
    result=subprocess.run(cmd+[str(ROOT/'fixture.scad')],capture_output=True,text=True)
    if result.returncode or 'ERROR:' in result.stderr or 'WARNING: Object' in result.stderr:raise RuntimeError(result.stderr)
    print('Exported',name,flush=True)
if not args.reuse_meshes:
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(export,jobs))
report={}
for name,_ in jobs:
    mesh=trimesh.load_mesh(out/name,process=True)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0,name
    assert len(mesh.split(only_watertight=False))==1,name
    assert abs(mesh.bounds[0,2])<.001,name
    expected=base+gh if name=='four-cup-platform.stl' else gh
    assert abs(mesh.extents[2]-expected)<.001,name
    if name=='four-cup-platform.stl':
        assert np.allclose(mesh.extents,[w,depth,base+gh],atol=.001)
        # Count disconnected guide cross-sections ABOVE the continuous base:
        # each U-shaped slot must yield one separate closed contour here.
        segments=trimesh.intersections.mesh_plane(mesh,[0,0,1],[0,0,base+gh/2])
        graph=nx.Graph()
        for a,b in segments:graph.add_edge(tuple(np.round(a,5)),tuple(np.round(b,5)))
        assert nx.number_connected_components(graph)==4,'Require exactly four raised cup guides'
        assert all(degree==2 for _,degree in graph.degree()),'Guide section contours must be closed'
    report[name]={'watertight':True,'consistent_winding':True,'connected_solids':1,
        'dimensions_mm':np.round(mesh.extents,3).tolist(),'geometric_volume_cm3':round(mesh.volume/1000,3)}
report['platform_raised_guide_count']=4
report['qualification']={'mesh':'passed','physical_cup_fit':'unverified','robot_clearance_and_reach':'unverified','slicer':'not run','print_time_and_filament':'unknown without printer profile'}
(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')

manifest={'design_id':'openarms-one-color-four-cups-v0.5-PROVISIONAL','platform_count':1,'cup_slot_count':4,
    'material_count':1,'applied_graphics':False,
    'units':'mm','frame':'whole platform; origin front-left underside; X right, Y rear, Z up',
    'platform_dimensions_mm':[w,depth,base+gh],'base_thickness_mm':base,'guide_height_mm':gh,
    'radial_clearance_mm':clear,'slot_geometry':[{'slot':s,'cup_bottom_top_height_mm':d,'seat_center_mm':p+[base]} for s,d,p in zip('ABCD',cups,centres)],
    'cup_dimensions_status':'ALL provisional; use actual store-bought cups; bottom diameter unmeasured',
    'references':'Recessed slot letters and 100 mm ruler, same printed material as platform',
    'physical_fixture_id':None,'calibration_id':None,'robot_from_platform_transform':None,
    'mode':'taught_fixture_only','warning':'CAD coordinates are not robot coordinates. Recessed ruler marks do not independently qualify camera localization or depth.'}
(out/'fixture-reference.json').write_text(json.dumps(manifest,indent=2)+'\n')

# Render ONLY the printable STL, using a single uniform material.
scene=[f'color([0.65,0.65,0.65]) import({json.dumps(str(out/"four-cup-platform.stl"))});']
with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'scene.scad';path.write_text('\n'.join(scene))
    subprocess.run(['openscad','-o',str(out/'four-cup-preview.png'),'--imgsize=1400,1100','--viewall','--autocenter','--projection=o','--colorscheme=Tomorrow',str(path)],check=True,capture_output=True)
for name in ['fixture.scad','build.py','README.md']:
    if (out/name)!=(ROOT/name):shutil.copy2(ROOT/name,out/name)
print(json.dumps(report,indent=2),flush=True)
