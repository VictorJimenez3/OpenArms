"""Export/validate CAD and produce a dimensioned preview and printable fiducials.

Requires OpenSCAD on PATH; pip install numpy trimesh networkx matplotlib opencv-contrib-python-headless reportlab.
Usage: python build.py --out /absolute/output/directory
No robot connections or calibration writes.
"""
from pathlib import Path
import argparse, concurrent.futures, json, re, shutil, subprocess, tempfile
import numpy as np
import trimesh
import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Polygon
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import letter

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--reuse-meshes', action='store_true', help='Only for preview changes: validate existing STLs without re-export; CAD must be unchanged')
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
source = (ROOT/'fixture.scad').read_text()
def scalar(name):
    return float(re.search(r'^'+name+r'\s*=\s*([0-9.]+)',source,re.M)[1])
def pair(name):
    return [float(v) for v in re.search(r'^'+name+r'\s*=\s*\[([^]]+)\]',source,re.M)[1].split(',')]
cup = {kind: [scalar(kind+'_'+key) for key in ['bottom_d','top_d','height']] for kind in ['source','receiver']}
base,gh,clear = [scalar(n) for n in ['base_thickness','guide_height','radial_clearance']]
cc,mc = pair('cup_center'),pair('marker_center')
w,depth = scalar('tile_width'),scalar('tile_depth')
pitch=scalar('layout_pitch')
black,paper=scalar('marker_black_size'),scalar('marker_paper_size')
jobs=[('source-A.stl',['part="source"']),('receiver-C.stl',['part="receiver"'])]
for kind,label in [('source','A'),('receiver','C')]:
    for delta in [-2,0,2]:
        nominal=cup[kind][0]+delta
        jobs.append((f'gauge-{label}-{nominal:g}mm.stl',['part="gauge_single"',f'gauge_cup="{kind}"',f'gauge_delta={delta}']))
def export(job):
    name,definitions=job
    command=['openscad','-o',str(out/name)]
    for definition in definitions: command += ['-D',definition]
    run=subprocess.run(command+[str(ROOT/'fixture.scad')],capture_output=True,text=True)
    if run.returncode or 'WARNING: Object' in run.stderr or 'ERROR:' in run.stderr:
        raise RuntimeError(name+'\n'+run.stderr)
    print('Exported',name,flush=True)
if not args.reuse_meshes:
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(export,jobs))

report={}
meshes={}
for name,_ in jobs:
    mesh=trimesh.load_mesh(out/name,process=True)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0,name
    components=mesh.split(only_watertight=False)
    assert len(components)==1,(name,len(components))
    assert abs(mesh.bounds[0,2])<0.001,name
    expected_z=base+gh if name in ['source-A.stl','receiver-C.stl'] else gh
    assert abs(mesh.extents[2]-expected_z)<0.001,name
    report[name]={'watertight':True,'consistent_winding':True,'connected_solids':len(components),
        'dimensions_mm':np.round(mesh.extents,3).tolist(),'volume_cm3':round(mesh.volume/1000,3),
        'solid_PLA_equivalent_g_not_slicer_estimate':round(mesh.volume/1000*1.24,2)}
    meshes[name]=mesh
report['qualification']={'CAD_mesh':'validated','slicer':'not run','physical_fit':'not tested',
    'robot_reach_and_collision':'not qualified','print_time':'unknown without printer/slicer profile'}
(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')

dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
markers={}
for station,identifier in [('A',10),('C',12)]:
    bits=cv2.aruco.generateImageMarker(dictionary,identifier,6)
    image=cv2.copyMakeBorder(cv2.resize(bits,(360,360),interpolation=cv2.INTER_NEAREST),40,40,40,40,cv2.BORDER_CONSTANT,value=255)
    detector=cv2.aruco.ArucoDetector(dictionary)
    _,found,_=detector.detectMarkers(image)
    assert found is not None and found.flatten().tolist()==[identifier]
    cv2.imwrite(str(out/f'marker-{station}-id{identifier}.png'),image)
    markers[station]=bits

manifest={'fixture_design_id':'openarms-cup-v0.3-diamond-2oz-PROVISIONAL',
    'physical_fixture_id':None,'calibration_id':None,'cup_id':None,'camera_mount_id':None,'robot_id':None,
    'mode':'taught_fixture_only','units':'mm','coordinate_frame':'each tile independently; origin front-left underside; X right, Y rear, Z up',
    'base_mm':[w,depth,base],'cup_seat_center_mm':cc+[base],
    'guide_height_mm':gh,'radial_clearance_mm':clear,'source_cup_mm':cup['source'],'receiver_cup_mm':cup['receiver'],
    'source_dimension_provenance':{'top_width_and_height':'Target TCIN94991464 overall48W51H; rim interpretation unmeasured','bottom_d':'38mm engineering placeholder, NOT published'},
    'receiver_dimension_provenance':'all dimensions provisional user brief, base59/top73.7/height63.5',
    'marker_dictionary':'DICT_4X4_50','marker_black_size_mm':black,'marker_paper_size_mm':paper,
    'marker_center_xy_mm':mc,'marker_surface_z_mm':'base thickness + measured paper/adhesive; NOT yet measured',
    'marker_corners_xy_top_left_clockwise':[[mc[0]-black/2,mc[1]+black/2],[mc[0]+black/2,mc[1]+black/2],[mc[0]+black/2,mc[1]-black/2],[mc[0]-black/2,mc[1]-black/2]],
    'marker_ids':{'A':10,'C':12},'robot_from_tile_transform':None,
    'preview_only_A_to_C_offset_mm':[pitch,0,0],
    'warning':'Not a bench_vision calibration or runnable robot pose file. Front marker alone cannot support planar localization at cup center. Moving tiles invalidates taught station assumptions.'}
(out/'fixture-reference.json').write_text(json.dumps(manifest,indent=2)+'\n')

# Vector PDF: exact physical marker scale independent of bitmap metadata.
pdf=canvas.Canvas(str(out/'printable-markers.pdf'),pagesize=letter)
pdf.setTitle('OpenArms A/C camera markers - print at 100 percent')
pdf.setFont('Helvetica-Bold',19);pdf.drawString(22*mm,258*mm,'OpenArms / fixture references')
pdf.setFont('Helvetica',11);pdf.drawString(22*mm,248*mm,'Print at 100% / Actual Size. Disable Fit to Page.')
pdf.drawString(22*mm,241*mm,'Measure the 100 mm line and each 36 mm black square before use.')
for station,x in [('A',35),('C',130)]:
    y=174
    bits=markers[station]
    pdf.setFont('Helvetica-Bold',14);pdf.drawString(x*mm,(y+53)*mm,f'Station {station} / ID {10 if station=="A" else 12}')
    margin=(paper-black)/2
    for row in range(6):
        for col in range(6):
            if bits[row,col]==0:
                pdf.setFillColorRGB(0,0,0)
                pdf.rect((x+margin+col*black/6)*mm,(y+margin+(5-row)*black/6)*mm,black/6*mm,black/6*mm,stroke=0,fill=1)
    # Crop ticks outside white border, not an extra enclosing black square.
    for sx in [0,paper]:
        for sy in [0,paper]:
            pdf.line((x+sx-2)*mm,(y+sy)*mm,(x+sx-0.5)*mm,(y+sy)*mm)
            pdf.line((x+sx)*mm,(y+sy-2)*mm,(x+sx)*mm,(y+sy-0.5)*mm)
    pdf.setFont('Helvetica',10);pdf.drawString(x*mm,(y-8)*mm,'44 mm paper; 36 mm black marker')
pdf.setLineWidth(0.7);pdf.line(30*mm,145*mm,130*mm,145*mm)
for x in [30,130]:pdf.line(x*mm,142*mm,x*mm,148*mm)
pdf.setFont('Helvetica-Bold',12);pdf.drawString(65*mm,137*mm,'100 mm')
pdf.setFont('Helvetica',10)
lines=['Cut at the crop marks; preserve the white margin. Keep both markers upright.',
       'Mount flat between the dock crosses. Avoid glare and tape across the black square.',
       'Dictionary: DICT_4X4_50. Marker size means the entire black square including border.',
       'Markers identify docks; they do not prove cup presence or seating.',
       'For metric pose, measure printed size and calibrate camera intrinsics/distortion.',
       'The front marker alone does not surround the cup or qualify its tabletop position.',
       'First demo: secure docks, teach fixed poses, observe the physical result.']
for i,line in enumerate(lines):pdf.drawString(22*mm,(116-i*7)*mm,line)
pdf.save()

# Depth-correct OpenSCAD preview of the independently validated STL meshes.
scene=['$fn=96;']
colors=['#147c89','#425a76']
for i,(station,kind,name) in enumerate([('A','source','source-A.stl'),('C','receiver','receiver-C.stl')]):
    shift=i*pitch; d=cup[kind]
    scene.append(f'translate([{shift},0,0]) color("{colors[i]}") import({json.dumps(str(out/name))});')
    scene.append(f'translate([{shift+cc[0]},{cc[1]},{base}]) color([0.70,0.85,0.94,0.25]) difference() {{ cylinder(h={d[2]},d1={d[0]},d2={d[1]}); translate([0,0,0.8]) cylinder(h={d[2]},d1={d[0]-1.2},d2={d[1]-1.2}); }}')
    px,py=shift+mc[0],mc[1]
    scene.append(f'color("white") translate([{px-paper/2},{py-paper/2},{base}]) cube([{paper},{paper},0.1]);')
    for row in range(6):
        for col in range(6):
            if markers[station][row,col]==0:
                xx=px-black/2+col*black/6; yy=py+black/2-(row+1)*black/6
                scene.append(f'color("black") translate([{xx},{yy},{base+.1}]) cube([{black/6},{black/6},0.02]);')
with tempfile.TemporaryDirectory() as temp:
    scene_path=Path(temp)/'preview.scad';scene_path.write_text('\n'.join(scene))
    subprocess.run(['openscad','-o',str(out/'assembly.png'),'--imgsize=1400,1000','--viewall','--autocenter','--projection=o','--colorscheme=Tomorrow',str(scene_path)],check=True,capture_output=True)
fig=plt.figure(figsize=(15,8),facecolor='#f6f8fa')
fig.suptitle('OPENARMS   /   A → C cup fixture',x=.055,y=.96,ha='left',fontsize=23,fontweight='bold',color='#173341')
fig.text(.055,.905,'Diamond 2 oz source • independent docks • top-drop / vertical lift • provisional fit',fontsize=12,color='#526573')
ax=fig.add_axes([.015,.19,.63,.68]);ax.imshow(plt.imread(out/'assembly.png'));ax.axis('off')
ax2=fig.add_axes([.66,.25,.31,.57]);ax2.set_facecolor('#f6f8fa')
ax2.add_patch(Rectangle((0,0),w,depth,facecolor='#e1edef',edgecolor='#31616b',lw=1.4))
theta=np.linspace(np.deg2rad(330),np.deg2rad(570),100)
d=cup['source'];r=(d[0]+(d[1]-d[0])*gh/d[2])/2+clear
points=np.vstack([np.column_stack((cc[0]+(r+scalar('guide_wall'))*np.cos(theta),cc[1]+(r+scalar('guide_wall'))*np.sin(theta))),np.column_stack((cc[0]+r*np.cos(theta[::-1]),cc[1]+r*np.sin(theta[::-1])))])
ax2.add_patch(Polygon(points,facecolor=colors[0]));ax2.add_patch(Circle(cc,d[0]/2,fill=False,linestyle='--',edgecolor='#57747d'))
ax2.add_patch(Rectangle((mc[0]-paper/2,mc[1]-paper/2),paper,paper,facecolor='white',edgecolor='none',zorder=2))
ax2.imshow(markers['A'],extent=[mc[0]-black/2,mc[0]+black/2,mc[1]-black/2,mc[1]+black/2],cmap='gray',vmin=0,vmax=255,interpolation='nearest',zorder=3)
ax2.plot(*cc,'+',color='#172c37');ax2.text(cc[0],cc[1]+33,'A cup centre (50, 88)',ha='center',fontsize=10)
ax2.annotate('Open front',xy=(cc[0],cc[1]-r+2),xytext=(cc[0],55),ha='center',fontsize=9,arrowprops={'arrowstyle':'->','color':'#526573'})
ax2.text(50,-13,f'{w:g} mm',ha='center',fontsize=11);ax2.text(-12,depth/2,f'{depth:g} mm',rotation=90,va='center',fontsize=11)
ax2.set_xlim(-20,w+10);ax2.set_ylim(-20,depth+10);ax2.set_aspect('equal');ax2.axis('off')
fig.text(.055,.12,'3 mm base + 6 mm guide    |    0.8 mm radial gap    |    secure each dock to a rigid tray',fontsize=12,color='#173341')
fig.text(.055,.065,'Translucent cups are estimates. Source base Ø38 mm is unmeasured. Layout spacing is illustrative; robot reach is not qualified.',fontsize=10,color='#526573')
fig.savefig(out/'fixture-preview.png',dpi=160,facecolor=fig.get_facecolor());plt.close(fig)
if out != ROOT:
    shutil.copy2(ROOT/'fixture.scad',out/'fixture.scad')
    shutil.copy2(ROOT/'build.py',out/'build.py')
print(json.dumps(report,indent=2),flush=True)
