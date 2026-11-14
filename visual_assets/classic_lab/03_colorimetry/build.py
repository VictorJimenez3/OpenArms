"""Editable classic colorimetry art scene. Blender 4.5; meters, Z up.
Run: Blender -b -t 2 --python build.py -- --render [--robot /path/Robot_STATIC_ART_ONLY.usdc]
All procedural assets are original; licensed original static robot is preview-only.
"""
import bpy, math, json, argparse, sys
from pathlib import Path
from mathutils import Vector
P=argparse.ArgumentParser(); P.add_argument('--out',default=str(Path(__file__).parent)); P.add_argument('--robot',default=str(Path(__file__).parent.parent/'assets'/'Robot_STATIC_ART_ONLY.usdc')); P.add_argument('--render',action='store_true'); P.add_argument('--samples',type=int,default=40)
a=P.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
out=Path(a.out).resolve(); out.mkdir(parents=True,exist_ok=True)
robot_path=Path(a.robot)
if not robot_path.exists(): robot_path=Path(__file__).parents[2]/'training_scene'/'assets'/'Robot_STATIC_ART_ONLY.usdc'
bpy.ops.wm.read_factory_settings(use_empty=True); sc=bpy.context.scene
sc.unit_settings.system='METRIC'; sc.unit_settings.scale_length=1
sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=a.samples; sc.cycles.use_denoising=True
sc.render.threads_mode='FIXED'; sc.render.threads=2
sc.render.resolution_x=1600; sc.render.resolution_y=1000; sc.render.resolution_percentage=100
sc.render.image_settings.file_format='PNG'; sc.view_settings.view_transform='AgX'; sc.view_settings.look='AgX - Medium High Contrast'; sc.view_settings.exposure=-.7
sc.world=bpy.data.worlds.new('Neutral daylight'); sc.world.use_nodes=True; sc.world.node_tree.nodes['Background'].inputs[0].default_value=(.55,.57,.60,1); sc.world.node_tree.nodes['Background'].inputs[1].default_value=.4
groups={}
for n in ['Bench','References','Photometer','Preparation','Cameras','Lighting','Robot_ART_ONLY','Overlay_ART_ONLY']:
 o=bpy.data.objects.new(n,None);sc.collection.objects.link(o);groups[n]=o
active='Bench'
def finish(o,n,m=None):
 o.name=n;o.parent=groups[active]
 if m:o.data.materials.append(m)
 return o
def mat(n,c,rough=.45,metal=0,trans=0):
 m=bpy.data.materials.new(n);m.use_nodes=True;b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(*c,1);b.inputs['Roughness'].default_value=rough;b.inputs['Metallic'].default_value=metal;b.inputs['Transmission Weight'].default_value=trans;b.inputs['IOR'].default_value=1.46 if trans>.8 else 1.333;return m
white=mat('Warm white powdercoat',(.76,.79,.77)); bench=mat('Light neutral laminate',(.63,.65,.62)); black=mat('Charcoal rubber',(.025,.034,.044)); steel=mat('Brushed stainless',(.38,.43,.47),.27,.75); navy=mat('Dark instrument blue',(.035,.085,.12)); yellow=mat('Unknown identification amber',(.98,.59,.025)); glass=mat('Clear cuvette walls',(.94,.98,1),.07,0,.96); screen=mat('Display deep teal',(.004,.023,.030),.5); red=mat('Illustrative green lamp filter',(.16,.8,.08),.22); ink=mat('Label ink',(.002,.003,.004),.9); paper=mat('White label',(.92,.93,.90)); lightblue=mat('Optical path illustrative green',(.18,.85,.12),.2,.1)
def cube(n,loc,dim,m,bev=.0015):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=finish(bpy.context.object,n,m);o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bev:b=o.modifiers.new('Rounded manufactured edges','BEVEL');b.width=bev;b.segments=3;o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
 return o
def cyl(n,loc,r,h,m,rot=None,vertices=48):
 bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=h,location=loc);o=finish(bpy.context.object,n,m)
 if rot:o.rotation_euler=rot
 for f in o.data.polygons:f.use_smooth=len(f.vertices)==4
 b=o.modifiers.new('Small edge radius','BEVEL');b.width=.0006;b.segments=2;o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL');return o
def text(n,body,loc,size=.009,rot=(0,0,0),m=ink,align='LEFT'):
 d=bpy.data.curves.new(n,'FONT');d.body=body;d.size=size;d.align_x=align;d.extrude=.000015;o=bpy.data.objects.new(n,d);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=rot;return finish(o,n,m)
def tube(n,x,y,z,r,h,m,wall=.001):
 N=64;v=[];f=[]
 for rr,zz in [(r,z),(r,z+h),(r-wall,z+h),(r-wall,z+.002)]:v += [(x+rr*math.cos(i*math.tau/N),y+rr*math.sin(i*math.tau/N),zz) for i in range(N)]
 for j in range(3):
  for i in range(N):f.append((j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i))
 f.append(tuple(range(3*N,4*N)));me=bpy.data.meshes.new(n);me.from_pydata(v,[],f);o=bpy.data.objects.new(n,me);sc.collection.objects.link(o);finish(o,n,m)
 for p in me.polygons:p.use_smooth=p.index<N or 2*N<=p.index<3*N
 return o
def cuvette(n,x,y,z,liquid_m,unknown=False):
 # Open, separately editable flat clear walls; custom educational 15 mm optical path.
 before_parts=set(sc.objects)
 w=.018;h=.069;t=.0015
 cube(n+'_bottom',(x,y,z+.0015),(w,w,.003),glass,.0008)
 for dx in (-1,1):cube(n+'_side_'+str(dx),(x+dx*(w-t)/2,y,z+h/2),(t,w,h),glass,.0005)
 for dy in (-1,1):cube(n+'_window_'+str(dy),(x,y+dy*(w-t)/2,z+h/2),(w-2*t,t,h),glass,.0005)
 cube(n+'_solution',(x,y,z+.027),(.0148,.0148,.048),liquid_m,.0007)
 for dz in (.01189,.02078,.02967,.03856,.04744):cube(n+'_graduation',(x+.0055,y-.0092,z+dz),(.004,.00035,.00045),paper,.0001)
 text(n+'_10ml','10',(x+.002,y-.0095,z+.049),.0038,(math.pi/2,0,0),paper)
 # Thin four-sided top rim; no cap blocking access.
 for dx in (-1,1):cube(n+'_rim',(x+dx*.0084,y,z+.068),(.0018,.019,.002),yellow if unknown else glass,.0004)
 for dy in (-1,1):cube(n+'_rim',(x,y+dy*.0084,z+.068),(.018,.0018,.002),yellow if unknown else glass,.0004)
 root=bpy.data.objects.new(n,None);sc.collection.objects.link(root);finish(root,n);root.location=(x,y,z)
 for part in set(sc.objects)-before_parts-{root}:
  part.parent=root;part.location-=Vector((x,y,z))
 return {'prim_path':'/ClassicLab/References/'+n if active=='References' else '/ClassicLab/Photometer/'+n,'base_transform_m':[x,y,z],'center_m':[x,y,z+.0345],'dimensions_m':[.018,.018,.069],'liquid_depth_m':.048,'grasp_height_m':z+.058,'open_top_z_m':z+.069}
# Normal bench; no themed room.
cube('Bench_top',(.12,0,-.022),(1,.75,.044),bench,.007)
for x in (-.31,.55):
 for y in (-.30,.30):cube('Bench_leg',(x,y,-.40),(.035,.035,.72),white,.002)
cube('Neutral_floor',(.10,0,-.785),(200,200,.05),mat('Floor',(.29,.31,.33)),0)
# REFERENCE ARRAY: immediate light-to-dark comparison, separate amber unknown.
active='References'
rackx=.213;racky=-.128
cube('Reference_rack_lower',(rackx,racky,.008),(.225,.062,.016),white,.004)
cube('Reference_rack_back',(rackx,racky+.026,.028),(.225,.008,.042),white,.002)
cube('Rack_front_label_strip',(rackx,racky-.031,.021),(.225,.002,.028),navy,.001)
concs=[0,1,2,3,4]
cols=[(.96,.83,.91),(.65,.03,.22),(.30,.005,.085),(.09,.001,.025),(.02,.0002,.005)]
sol=[]; refs=[]
for i,c in enumerate(cols):sol.append(mat('Magenta reference '+str(i)+' relative units',c,.12,0,.12))
for i in range(5):
 x=.125+i*.043
 # Two short front/rear comb supports hold each cuvette without obscuring the liquid.
 for dy in (-.012,.012):cube('Rack_socket_'+str(i),(x,racky+dy,.020),(.025,.004,.016),navy,.0006)
 refs.append(cuvette('Reference_'+str(i),x,racky,.016,sol[i]))
 text('Concentration_'+str(i),str(i),(x,racky-.0323,.019),.011,(math.pi/2,0,0),paper,'CENTER')
 text('Standard_top_'+str(i),str(i),(x,racky+.012,.0494),.007,m=ink,align='CENTER')
# Unknown has its own bright holder and same fill as reference 3.
ux=.359
cube('Unknown_separate_holder',(ux,racky,.013),(.036,.056,.026),yellow,.003)
cube('Unknown_holder_front',(ux,racky-.029,.028),(.039,.002,.029),yellow,.001)
unknown=cuvette('Unknown_comparison_aliquot',ux,racky,.026,sol[3],True)
text('Unknown_question','?',(ux,racky-.0304,.020),.020,(math.pi/2,0,0),ink,'CENTER')
# Match bracket connecting standard 3 to unknown on the tabletop, obvious visual result.
cube('Match_line',(.3065,-.196,.0012),(.105,.002,.002),yellow,.0003)
for x in (.254,.359):cube('Match_line_end',(x,-.186,.0012),(.002,.022,.002),yellow,.0003)
text('Reference_caption','KNOWN STANDARDS',(.113,-.180,.0015),.010)
text('Unknown_explicit_label','UNKNOWN',(.359,-.178,.0015),.0085,m=ink,align='CENTER')
text('Match_caption','COMPARE COLOR',(.3065,-.216,.0015),.012,m=ink,align='CENTER')
# Rear label is a low working strip, not a billboard.
text('Reference_units','RELATIVE CONCENTRATION',(.113,-.087,.001),.0075)
# EDUCATIONAL PHOTOMETER: optical rail, enclosed lamp, accessible cuvette holder, detector and controls.
active='Photometer';px=.276;py=.095
cube('Photometer_chassis',(px,py,.020),(.267,.161,.040),white,.008)
cube('Instrument_lower_trim',(px,py,.006),(.267,.161,.011),navy,.004)
for x in (.160,.392):
 for y in (.028,.162):cyl('Rubber_foot',(x,y,.0025),.006,.005,black)
# Optical rail is horizontal across the back of the machine.
cube('Optical_rail',(px,.130,.046),(.226,.030,.012),steel,.0015)
for x in (.180,.355):
 cyl('Rail_fastener',(x,.130,.053),.0024,.002,black)
# Lamp enclosure with cylindrical barrel pointing along +X.
cube('Lamp_housing',(.184,.130,.080),(.052,.055,.061),navy,.004)
cyl('Lamp_output_barrel',(.216,.130,.079),.012,.022,black,(0,math.pi/2,0))
cyl('Lamp_filter_lens',(.228,.130,.079),.0095,.0015,red,(0,math.pi/2,0))
for y in (.112,.121,.130,.139,.148):cube('Lamp_vent',(.182,y,.111),(.030,.002,.001),black,.0003)
text('Lamp_label','LIGHT',(.184,.1022,.076),.007,(math.pi/2,0,0),paper,'CENTER')
# Cuvette receiver: 18 mm socket with slotted optical windows. Lid lifted to rear.
sx=.267;sy=.130
cube('Sample_holder_floor',(sx,sy,.052),(.034,.038,.010),black,.002)
for dy in (-1,1):cube('Sample_holder_front_back',(sx,sy+dy*.015,.065),(.032,.006,.023),black,.001)
for dx in (-1,1):
 for dy in (-1,1):cube('Sample_holder_window_posts',(sx+dx*.014,sy+dy*.010,.078),(.006,.006,.039),black,.001)
 cube('Sample_holder_window_top',(sx+dx*.014,sy,.096),(.006,.026,.005),black,.001)
measured=cuvette('Unknown_in_optical_holder',sx,sy,.057,sol[3],True)
# Open hinged cap shows where sample enters, cannot be mistaken for solid cube.
lid=cube('Raised_sample_cover',(sx,sy+.031,.105),(.042,.006,.062),navy,.002);lid.rotation_euler[0]=math.radians(-24)
cyl('Cover_hinge',(sx,sy+.023,.073),.004,.040,steel,(0,math.pi/2,0))
text('Holder_label','SAMPLE',(sx,.103,.042),.0065,m=ink,align='CENTER')
# Deliberately visible open gaps around sample illustrate lamp -> sample -> detector.
cyl('Illustrative_light_in',(.240,.130,.079),.0012,.023,lightblue,(0,math.pi/2,0))
cyl('Illustrative_light_out',(.296,.130,.079),.0007,.028,lightblue,(0,math.pi/2,0))
cube('Detector_housing',(.336,.130,.080),(.049,.050,.055),navy,.004)
cyl('Detector_input',(.307,.130,.079),.011,.012,black,(0,math.pi/2,0))
cyl('Detector_lens',(.3005,.130,.079),.008,.001,glass,(0,math.pi/2,0))
text('Detector_label','DETECT',(.336,.1042,.076),.0065,(math.pi/2,0,0),paper,'CENTER')
# Display/control console on top front, broad and readable in result shot.
cube('Display_bezel',(.321,.045,.043),(.113,.048,.008),black,.004)
cube('Display_screen',(.321,.045,.0474),(.101,.036,.0016),screen,.001)
text('Display_absorbance','A  0.600',(.276,.047,.0485),.010,m=paper)
text('Display_concentration','C  3.0 units',(.276,.033,.0485),.0085,m=paper)
text('Display_model_label','MODEL READING',(.273,.072,.041),.0065,m=ink)
for x,body,col in [(.179,'ZERO',white),(.220,'READ',yellow)]:
 cyl('Button_'+body,(x,.047,.047),.009,.010,col)
 text('Button_label_'+body,body,(x,.027,.041),.006,m=ink,align='CENTER')
text('Photometer_name','PHOTOMETER',(.153,.0088,.020),.011,(math.pi/2,0,0),ink)
# REAGENT / PREPARATION: bottle, pipette stand and fixture within same scene.
active='Preparation';bottlecol=mat('Stock magenta',(.46,.018,.18),.12,0,.28)
bx=.453;by=.150
tube('Magenta_food_dye_bottle',bx,by,.002,.024,.111,glass,.0016)
cyl('Stock_solution',(bx,by,.041),.022,.075,bottlecol)
cyl('Bottle_shoulder',(bx,by,.112),.023,.009,glass)
cyl('Bottle_neck',(bx,by,.125),.012,.023,glass)
cyl('Bottle_screw_cap',(bx,by,.140),.014,.014,navy)
for i in range(24):
 t=math.tau*i/24;cyl('Cap_grip',(bx+.014*math.cos(t),by+.014*math.sin(t),.140),.0005,.011,navy)
cube('Bottle_label',(bx,by-.024,.064),(.038,.0006,.033),paper,.001)
text('Bottle_label_text','FOOD DYE',(bx,by-.0246,.069),.006,(math.pi/2,0,0),ink,'CENTER')
text('Bottle_foodsafe','FOOD COLOR',(bx,by-.0246,.058),.0046,(math.pi/2,0,0),ink,'CENTER')
# Passive pipette fixture is behind the active transfer zone.
fx=.453;fy=.035
cube('Pipette_stand_foot',(fx,fy,.006),(.070,.070,.012),white,.006)
cyl('Pipette_stand_post',(fx+.025,fy+.018,.114),.004,.216,steel)
cube('Pipette_holder_arm',(fx+.009,fy+.018,.185),(.037,.014,.012),navy,.003)
# Slot fork holds actual volumetric dosing tool, free tip down.
for dy in (-.009,.009):cube('Pipette_fork',(fx-.011,fy+.018+dy,.185),(.022,.006,.012),navy,.001)
pcx=fx-.013;pcy=fy+.018
cyl('Pipette_body',(pcx,pcy,.180),.008,.065,white)
cyl('Pipette_blue_collar',(pcx,pcy,.149),.0087,.012,navy)
cyl('Pipette_shaft',(pcx,pcy,.119),.0032,.052,white)
bpy.ops.mesh.primitive_cone_add(vertices=48,radius1=.0009,radius2=.0035,depth=.032,location=(pcx,pcy,.077));finish(bpy.context.object,'Transparent_disposable_tip',glass)
cyl('Pipette_plunger',(pcx,pcy,.220),.003,.015,steel)
cyl('Pipette_button',(pcx,pcy,.229),.006,.007,yellow)
cube('Pipette_volume_window',(pcx,pcy-.008,.183),(.009,.001,.017),black,.001)
text('Pipette_volume','1000',(pcx,pcy-.0087,.182),.003,(math.pi/2,0,0),paper,'CENTER')
text('Preparation_label','PREPARE',(.422,-.009,.0125),.008,m=ink)
# Camera/light definitions.
active='Cameras'
def camera(n,loc,target,lens):
 d=bpy.data.cameras.new(n);d.lens=lens;d.sensor_width=36;d.clip_start=.005;d.clip_end=300;o=bpy.data.objects.new(n,d);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();finish(o,n);return o
front=camera('Camera_Front',(.80,-1.15,.48),(.17,.02,.115),52)
over=camera('Camera_Overhead',(.14,.035,1.25),(.14,.035,0),44);over.rotation_euler=(0,0,0)
result=camera('Camera_Result',(.56,-.64,.47),(.283,-.025,.066),62)
active='Lighting'
def light(n,loc,power,size):
 d=bpy.data.lights.new(n,'AREA');d.energy=power;d.shape='DISK';d.size=size;o=bpy.data.objects.new(n,d);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((.20,0,.04))-o.location).to_track_quat('-Z','Y').to_euler();finish(o,n)
light('Large_front_softbox',(.1,-.5,1.4),110,1.25);light('Rear_softbox',(.5,.5,1.1),80,1);light('Left_fill',(-.6,-.1,.7),35,.8)
bpy.context.view_layer.update()
manifest={'schema_version':1,'experiment':'Color comparison: find the unknown concentration','status':'ART PREVIEW; MODEL-PREDICTED readings; no runtime evidence','units':'meters','up_axis':'Z','default_prim':'/ClassicLab','tabletop_z_m':0,'table_center_m':[.12,0,-.022],'table_dimensions_m':[1,.75,.044],'robot_in_environment_usd':False,'physics_attached':False,'robot_runtime_base_reference_m':[-.05,0,0],'robot_preview_translation_m':[-.05,0,-.03008145],'robot_added_yaw_rad':0,'robot_source':str(robot_path),'references':refs,'unknown_comparison_aliquot':unknown,'unknown_measurement_aliquot':measured,'source_bottle_center_m':[bx,by,.06],'pipette_fixture_m':[pcx,pcy,.185],'photometer_dimensions_m':[.267,.161,.126],'optical_path_direction':'+X','cuvette_internal_path_m':.015,'model':{'kind':'Illustrative linear absorbance calibration','concentration_unit':'relative units, not mg/L','standards':[0,1,2,3,4],'assumed_absorbance_per_relative_unit':.2,'unknown_relative_concentration':3,'displayed_absorbance':.6,'transmittance_equation':'T=10^(-A)','unknown_predicted_transmittance':10**(-.6),'solution_colors':'Artist-authored illustrative magenta ramp, not spectral rendering','measured_data':False,'light_ray_geometry':'Explanatory visible glyph, not physically visible laboratory beam'},'robot_requirements':'Controller, reach, grasp, force, insertion and optical measurements unqualified; no motion executed. Two staged equal aliquots represent comparison and measuring views.','cameras':{}}
for c in (front,over,result):manifest['cameras'][c.name]={'position_m':list(c.location),'rotation_euler_xyz_rad':list(c.rotation_euler),'lens_mm':c.data.lens,'world_matrix_row_major':[list(r) for r in c.matrix_world],'resolution_px':[1600,1000]}
manifest['groups']=list(groups)
manifest['runtime_handoff']={
 'static_prim_roots':['/ClassicLab/Bench','/ClassicLab/Photometer','/ClassicLab/Preparation'],
 'movable_cuvette_roots':[r['prim_path'] for r in refs]+[unknown['prim_path'],measured['prim_path']],
 'static_exception':'Photometer group contains a removable Unknown_in_optical_holder cuvette; split this child from static assembly before assigning rigid bodies.',
 'grasp':'Cuvette side flats at local Z=.054-.063 m; fingers parallel to X, avoiding front/back optical windows and rim. 18 mm outer width. Reference center spacing 43 mm leaves 25 mm nominal gap before finger thickness.',
 'approach':'Vertical +Z clearance above open socket required. Lift cuvette at least 40 mm before lateral transfer. No reach, swept-volume or collision test performed.',
 'source_base_transform_m':[.359,-.128,.026],
 'target_base_transform_m':[.267,.130,.057],
 'source_and_target_rotation_euler_rad':[0,0,0],
 'holder_nominal_clear_width_m':.022,
 'clearance_note':'Nominal 2 mm each side for 18 mm cuvette; not manufacturing tolerance or proven robotic insertion margin.',
 'student_variable':'Unknown relative dye concentration, keeping path length and fill height fixed.',
 'conditions':[{'unknown_concentration':1,'predicted_absorbance':.2,'predicted_transmittance':10**(-.2),'visual':'pale magenta matches standard 1'},{'unknown_concentration':3,'predicted_absorbance':.6,'predicted_transmittance':10**(-.6),'visual':'dark magenta matches standard 3; staged scene'}],
 'observable':'Change in transmitted light / absorbance and matched reference index.',
 'missing':['articulated robot','collision and rigid-body assignments','grasp and insertion controller','button actuation','liquid transfer model','spectral optical model','real calibration','measured camera/sensor observations'],
 'dependencies':{'Environment.usdc':[],'Scene.blend':[],'build.py':['Blender 4.5 or compatible','../assets/Robot_STATIC_ART_ONLY.usdc for preview only']}}

(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
# Export environment before importing robot. Text converted only temporarily, keeping editable text in blend.
texts=[o for o in sc.objects if o.type=='FONT']; original=[]
for o in texts:
 clone=o.copy();clone.data=o.data.copy();sc.collection.objects.link(clone);original.append(o);o.hide_viewport=True;o.hide_render=True
 bpy.ops.object.select_all(action='DESELECT');clone.select_set(True);bpy.context.view_layer.objects.active=clone;bpy.ops.object.convert(target='MESH')
bpy.ops.object.select_all(action='DESELECT')
for o in sc.objects:
 if o not in original and o.name not in ('Robot_ART_ONLY','Overlay_ART_ONLY'):o.select_set(True)
bpy.ops.wm.usd_export(filepath=str(out/'Environment.usdc'),selected_objects_only=True,visible_objects_only=False,export_materials=True,generate_preview_surface=True,export_textures=False,convert_world_material=False,root_prim_path='/ClassicLab')
for o in list(sc.objects):
 if o.type=='MESH' and any(o.name.startswith(t.name+'.') for t in original):bpy.data.objects.remove(o,do_unlink=True)
for o in original:o.hide_viewport=False;o.hide_render=False
# Original static white SO101, camera-free, retained with source transforms.
active='Robot_ART_ONLY';before=set(sc.objects)
bpy.ops.wm.usd_import(filepath=str(robot_path),import_cameras=False,import_lights=False,import_materials=True,create_world_material=False)
new=set(sc.objects)-before
root=bpy.data.objects.new('SO101_ORIGINAL_STATIC_PREVIEW',None);sc.collection.objects.link(root);finish(root,root.name);root.location=(-.05,0,-.03008145)
for o in new:
 if o.parent not in new:o.parent=root
root['evidence']='Original licensed static art only; no camera; no runtime robot behavior.'
# Small camera-mounted footer is excluded from USD.
active='Overlay_ART_ONLY'
for c in (front,over,result):
 footer=text(c.name+'_footer','ART PREVIEW  /  MODEL-PREDICTED OPTICAL READING',(0,0,0),.0033,m=ink)
 footer.parent=c; footer.location=(-.164*52/c.data.lens,-.103*52/c.data.lens,-.5);footer.rotation_euler=(0,0,0);footer.scale=(52/c.data.lens,)*3
sc.camera=front
for c in (over,result):
 for child in c.children:child.hide_render=True
bpy.ops.wm.save_as_mainfile(filepath=str(out/'Scene.blend'),compress=True)
if a.render:
 for c,name in [(front,'Front.png'),(over,'Overhead.png'),(result,'Result.png')]:
  for cc in (front,over,result):
   for child in cc.children:child.hide_render=cc!=c
  sc.camera=c;sc.render.filepath=str(out/name);bpy.ops.render.render(write_still=True)
print('COLORIMETRY_COMPLETE',flush=True)
