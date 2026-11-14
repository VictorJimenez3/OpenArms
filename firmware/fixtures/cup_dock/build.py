"""Build ONE four-slot platform plus three quick fit gauges.
Requires OpenSCAD and numpy,trimesh,networkx,opencv-contrib-python-headless,reportlab.
Usage: python build.py --out /absolute/export/path
No robot connection or control changes.
"""
from pathlib import Path
import argparse, concurrent.futures, json, shutil, subprocess, tempfile
import numpy as np
import trimesh
import networkx as nx
import cv2
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import letter

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--reuse-meshes',action='store_true',help='Validation/preview only; use only if CAD and parameters are unchanged')
args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
    ep=Path(td)/'config.echo'
    subprocess.run(['openscad','-o',str(ep),'-D','part="config"',str(ROOT/'fixture.scad')],check=True,capture_output=True)
    cfg=json.loads(ep.read_text().strip().removeprefix('ECHO: '))
w,depth,base,gh,wall,clear,opening,black,paper,cups,centres,marker_centres=cfg
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

dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
markers={}
for mid in [10,12]:
    bits=cv2.aruco.generateImageMarker(dictionary,mid,6);markers[mid]=bits
    img=cv2.copyMakeBorder(cv2.resize(bits,(360,360),interpolation=cv2.INTER_NEAREST),40,40,40,40,cv2.BORDER_CONSTANT,value=255)
    _,ids,_=cv2.aruco.ArucoDetector(dictionary).detectMarkers(img)
    assert ids is not None and ids.ravel().tolist()==[mid]
    cv2.imwrite(str(out/f'marker-{mid}.png'),img)
manifest={'design_id':'openarms-ONE-platform-FOUR-cups-v0.4-PROVISIONAL','platform_count':1,'cup_slot_count':4,
    'units':'mm','frame':'whole platform; origin front-left underside; X right, Y rear, Z up',
    'platform_dimensions_mm':[w,depth,base+gh],'base_thickness_mm':base,'guide_height_mm':gh,
    'radial_clearance_mm':clear,'slot_geometry':[{'slot':s,'cup_bottom_top_height_mm':d,'seat_center_mm':p+[base]} for s,d,p in zip('ABCD',cups,centres)],
    'cup_dimensions_status':'ALL provisional; use actual store-bought cups; bottom diameter unmeasured',
    'marker_dictionary':'DICT_4X4_50','marker_black_size_mm':black,'marker_paper_size_mm':paper,
    'markers':[{'id':mid,'center_xy_mm':p,'corners_xy_top_left_clockwise':[[p[0]-black/2,p[1]+black/2],[p[0]+black/2,p[1]+black/2],[p[0]+black/2,p[1]-black/2],[p[0]-black/2,p[1]-black/2]]} for mid,p in zip([10,12],marker_centres)],
    'physical_fixture_id':None,'calibration_id':None,'robot_from_platform_transform':None,
    'mode':'taught_fixture_only','warning':'CAD coordinates are not robot coordinates. Marker height is base + measured paper/adhesive. Front markers alone do not qualify rear-slot planar localization.'}
(out/'fixture-reference.json').write_text(json.dumps(manifest,indent=2)+'\n')

pdf=canvas.Canvas(str(out/'printable-markers.pdf'),pagesize=letter)
pdf.setTitle('OpenArms four-cup platform markers')
pdf.setFont('Helvetica-Bold',19);pdf.drawString(20*mm,258*mm,'OpenArms / one platform, four cups')
pdf.setFont('Helvetica',11);pdf.drawString(20*mm,247*mm,'Print at 100% / Actual Size. Verify the dimensions with a ruler.')
for mid,x in [(10,35),(12,130)]:
    y=177;bits=markers[mid];margin=(paper-black)/2
    pdf.setFont('Helvetica-Bold',13);pdf.drawString(x*mm,(y+53)*mm,f'Platform marker {mid}')
    for row in range(6):
        for col in range(6):
            if bits[row,col]==0:pdf.rect((x+margin+col*black/6)*mm,(y+margin+(5-row)*black/6)*mm,black/6*mm,black/6*mm,fill=1,stroke=0)
    for dx in [0,paper]:
        for dy in [0,paper]:
            pdf.line((x+dx-2)*mm,(y+dy)*mm,(x+dx-.5)*mm,(y+dy)*mm)
            pdf.line((x+dx)*mm,(y+dy-2)*mm,(x+dx)*mm,(y+dy-.5)*mm)
    pdf.setFont('Helvetica',10);pdf.drawString(x*mm,(y-8)*mm,f'{paper:g} mm paper / {black:g} mm black square')
pdf.line(30*mm,147*mm,130*mm,147*mm)
for x in [30,130]:pdf.line(x*mm,144*mm,x*mm,150*mm)
pdf.setFont('Helvetica-Bold',12);pdf.drawString(67*mm,138*mm,'100 mm')
pdf.setFont('Helvetica',10)
for i,line in enumerate(['Use marker 10 at the front-left pad and 12 at the front-right pad.',
    'Keep the white border, mount flat, and avoid glare over the black pattern.',
    'These are platform references, not labels for individual cups.',
    'Four cup slots are labeled A, B, C and D on the single printed platform.',
    'Markers and rulers do not independently measure arbitrary 3D depth.',
    'First demo: secure the platform and teach actual pickup/pour/return positions.']):
    pdf.drawString(20*mm,(118-i*8)*mm,line)
pdf.save()

scene=['$fn=96;',f'color([0.08,0.42,0.48]) import({json.dumps(str(out/"four-cup-platform.stl"))});']
for d,p in zip(cups,centres):
    scene.append(f'translate([{p[0]},{p[1]},{base}]) color([0.75,0.87,0.94,0.25]) difference() {{ cylinder(h={d[2]},d1={d[0]},d2={d[1]}); translate([0,0,0.8]) cylinder(h={d[2]},d1={d[0]-1.2},d2={d[1]-1.2}); }}')
for mid,p in zip([10,12],marker_centres):
    x,y=p;scene.append(f'color("white") translate([{x-paper/2},{y-paper/2},{base}]) cube([{paper},{paper},0.1]);')
    for row in range(6):
        for col in range(6):
            if markers[mid][row,col]==0:scene.append(f'color("black") translate([{x-black/2+col*black/6},{y+black/2-(row+1)*black/6},{base+.1}]) cube([{black/6},{black/6},.02]);')
with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'scene.scad';path.write_text('\n'.join(scene))
    subprocess.run(['openscad','-o',str(out/'four-cup-preview.png'),'--imgsize=1400,1100','--viewall','--autocenter','--projection=o','--colorscheme=Tomorrow',str(path)],check=True,capture_output=True)
for name in ['fixture.scad','build.py','README.md']:
    if (out/name)!=(ROOT/name):shutil.copy2(ROOT/name,out/name)
print(json.dumps(report,indent=2),flush=True)
