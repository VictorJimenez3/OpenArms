"""Editable stirred versus still dissolution illustration. Blender 4.5, meters.
Run Blender -b -t 2 --python build.py -- --out OUTPUT [--render]
Robot defaults to ../assets/Robot_STATIC_ART_ONLY.usdc; override with --robot.
No kinetics, dynamics, controller execution, or measured chemistry is claimed.
"""
import bpy, math, random, json, sys, argparse
from pathlib import Path
from mathutils import Vector
ap=argparse.ArgumentParser(); ap.add_argument('--out',default=str(Path(__file__).resolve().parent)); ap.add_argument('--robot');ap.add_argument('--render',action='store_true');ap.add_argument('--render-only',action='store_true');a=ap.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
if a.render_only:
 bpy.ops.wm.open_mainfile(filepath=str(out/'Scene.blend'))
 sc=bpy.context.scene;sc.render.threads_mode='FIXED';sc.render.threads=2
 for n in ['Front','Overhead','Result']:
  sc.camera=bpy.data.objects['Camera_'+n]
  for cam in [bpy.data.objects['Camera_'+k] for k in ['Front','Overhead','Result']]:
   for child in cam.children:child.hide_render=cam!=sc.camera
  sc.render.filepath=str(out/(n+'.png'));bpy.ops.render.render(write_still=True)
 sys.exit(0)
bpy.ops.wm.read_factory_settings(use_empty=True);sc=bpy.context.scene
sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=1
sc.render.engine='CYCLES';sc.cycles.device='CPU';sc.cycles.samples=48;sc.cycles.use_denoising=True;sc.cycles.max_bounces=8;sc.cycles.transparent_max_bounces=24
sc.render.threads_mode='FIXED';sc.render.threads=2
sc.render.resolution_x=1600;sc.render.resolution_y=1000;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='PNG'
sc.view_settings.view_transform='AgX';sc.view_settings.look='AgX - Medium High Contrast';sc.view_settings.exposure=0
sc.world=bpy.data.worlds.new('Neutral_room');sc.world.use_nodes=True;sc.world.node_tree.nodes['Background'].inputs[0].default_value=(.55,.58,.62,1);sc.world.node_tree.nodes['Background'].inputs[1].default_value=.5
groups={}
for n in ['Environment','Stirred_station','Still_station','Dosing','Timing','Cameras','Lighting','Robot_ART_ONLY']:
 ob=bpy.data.objects.new(n,None);sc.collection.objects.link(ob);groups[n]=ob
active='Environment';records=[]
def finish(ob,n,m=None):
 ob.name=n;ob.parent=groups[active]
 if m:ob.data.materials.append(m)
 return ob
def mat(n,c,rough=.5,metal=0,alpha=1):
 m=bpy.data.materials.new(n);m.diffuse_color=(*c,alpha);m.use_nodes=True;p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal;p.inputs['Alpha'].default_value=alpha
 return m
white=mat('Warm_white_housing',(.72,.75,.73));dark=mat('Matte_print',(.025,.033,.04),.85);rubber=mat('Rubber',(.035,.045,.048),.7);steel=mat('Brushed_steel',(.42,.47,.5),.3,.75);bench=mat('Light_bench',(.68,.70,.70),.7);floor=mat('Neutral_floor',(.23,.25,.27),.9);navy=mat('Graphite_observation_bases',(.055,.085,.105),.65);teal=mat('Stir_teal',(.02,.30,.29),.5);amber=mat('Still_amber',(.65,.30,.045),.6);sugar=mat('Sugar_crystals',(.88,.86,.77),.48);glass=mat('Approximate_clear_glass_alpha_009',(.65,.83,.87),.2,alpha=.09);rim=mat('Glass_rim_alpha_035',(.56,.75,.79),.18,alpha=.35);water=mat('Clear_water_alpha_0025',(.65,.83,.87),.22,alpha=.025);green=mat('Power_LED',(.08,.7,.22),.25);screen=mat('LCD_background',(.18,.25,.19),.7)
def cube(n,loc,dim,m,bev=.001):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=finish(bpy.context.object,n,m);o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bev:
  mod=o.modifiers.new('Rounded_edges','BEVEL');mod.width=bev;mod.segments=3;o.modifiers.new('Weighted_normals','WEIGHTED_NORMAL')
 return o
def cyl(n,loc,r,h,m,vertices=64):
 bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=h,location=loc);o=finish(bpy.context.object,n,m)
 for f in o.data.polygons:f.use_smooth=len(f.vertices)==4
 return o
def tube(n,pts,rad,m):
 c=bpy.data.curves.new(n,'CURVE');c.dimensions='3D';c.resolution_u=2;c.bevel_depth=rad;c.bevel_resolution=3;s=c.splines.new('POLY');s.points.add(len(pts)-1)
 for p,v in zip(s.points,pts):p.co=(*v,1)
 o=bpy.data.objects.new(n,c);sc.collection.objects.link(o);return finish(o,n,m)
def text(n,body,loc,size,m=dark,rot=(0,0,0),align='LEFT'):
 c=bpy.data.curves.new(n,'FONT');c.body=body;c.size=size;c.extrude=.000015;c.align_x=align;o=bpy.data.objects.new(n,c);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=rot;return finish(o,n,m)
def box_record(n,role,loc,dim,movable=False,grasp=None):
 records.append(dict(object=n,role=role,position_m=loc,dimensions_m=dim,movable=movable,intended_grasp=grasp))
def beaker(n,x,y,z):
 r=.047;h=.116;N=96;verts=[];faces=[]
 # Open vessel with 1.5mm walls, 3mm base, and a shallow outward pouring spout.
 for radius,zz in [(r,0),(r,h),(r-.0015,h),(r-.0015,.003)]:
  for i in range(N):
   t=i*math.tau/N;delta=math.atan2(math.sin(t-math.pi),math.cos(t-math.pi));flare=.008*math.exp(-(delta/.18)**2) if zz==h else 0
   verts.append((x+(radius+flare)*math.cos(t),y+(radius+flare)*math.sin(t),z+zz))
 for j in range(3):
  for i in range(N):faces.append((j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i))
 me=bpy.data.meshes.new(n+'_wall_mesh');me.from_pydata(verts,[],faces);ob=bpy.data.objects.new(n+'_walls',me);sc.collection.objects.link(ob);finish(ob,n+'_walls',glass)
 cyl(n+'_glass_bottom',(x,y,z+.0015),r,.003,glass)
 pts=[]
 for i in range(N+1):
  t=i*math.tau/N;d=math.atan2(math.sin(t-math.pi),math.cos(t-math.pi));rr=r+.008*math.exp(-(d/.18)**2);pts.append((x+rr*math.cos(t),y+rr*math.sin(t),z+h))
 tube(n+'_open_rim',pts,.0008,rim)
 tube(n+'_heel',[(x+r*math.cos(i*math.tau/N),y+r*math.sin(i*math.tau/N),z+.004) for i in range(N+1)],.0006,rim)
 cyl(n+'_clear_water',(x,y,z+.003+.072/2),r-.0017,.072,water)
 tube(n+'_water_meniscus',[(x+.045*math.cos(i*math.tau/N),y+.045*math.sin(i*math.tau/N),z+.075) for i in range(N+1)],.0003,rim)
 # Graduation column kept on one side of the view, away from visible solids.
 for i,zz in enumerate([.0185,.034,.0495,.065,.0805]):
  yy=y-math.sqrt(r*r-.022**2)-.0003;tube(n+'_graduation_'+str(i),[(x+.017,yy,z+zz),(x+.027,yy,z+zz)],.00025,dark)
  if i in [1,3]:text(n+'_volume_'+str(i),str((i+1)*100),(x+.027,yy-.0003,z+zz-.0015),.0045,rot=(math.pi/2,0,0))
 text(n+'_capacity','600 mL',(x-.022,y-.0478,z+.099),.0055,rot=(math.pi/2,0,0))
 box_record(n+'_walls','identical open beaker',[x,y,z],[.102,.094,.116],True,'Upper exterior wall, opposed side contacts; wet-glass grip unqualified.')
 return z+.003
cube('Work_surface',(.12,0,-.022),(1,.75,.044),bench,.005)
for x in [-.31,.55]:
 for y in [-.30,.30]:cube('Table_leg', (x,y,-.4),(.035,.035,.72),rubber,.002)
cube('Floor',(.12,0,-.785),(200,200,.05),floor,0)
box_record('Work_surface','static table',[.12,0,-.022],[1,.75,.044])
# Two conditions with matched vessel height, volume, starting sugar dose, and bar geometry.
for name,x,stir in [('Stirred',.145,True),('Still',.325,False)]:
 active='Stirred_station' if stir else 'Still_station';accent=teal if stir else amber;y=.075;z=.038
 cube(name+'_platform',(x,y,.018),(.148,.155,.036),white,.006)
 for dx in [-.052,.052]:
  for dy in [-.055,.055]:cyl(name+'_foot',(x+dx,y+dy,.003),.009,.006,rubber)
 cyl(name+'_observation_plate',(x,y,z-.001),.062,.002,navy)
 cube(name+'_front_band',(x,y-.078,.019),(.139,.001,.026),accent,.001)
 text(name+'_condition','STIR' if stir else 'STILL',(x-.057,y-.079,.019),.014,white,rot=(math.pi/2,0,0))
 text(name+'_subcondition','MIXING ON' if stir else 'NO MIXING',(x-.057,y-.079,.009),.006,white,rot=(math.pi/2,0,0))
 if stir:
  knob=cyl('Stir_speed_knob',(x+.044,y-.083,.018),.010,.010,rubber);knob.rotation_euler=(math.pi/2,0,0)
  cube('Knob_index',(x+.044,y-.089,.024),(.0015,.0007,.005),white,0)
  led=cyl('Power_indicator',(x+.064,y-.0795,.021),.002,.001,green);led.rotation_euler=(math.pi/2,0,0)
  tube('Stir_plate_power_lead',[(x+.072,y+.045,.015),(x+.085,y+.06,.006),(x+.09,y+.15,.005),(x+.06,y+.20,.004)],.002,rubber)
 else:
  text('Passive_platform_label','MATCHED RISER',(x-.048,y+.063,.037),.006,dark)
 bottom=beaker(name,x,y,z)
 bar=cube(name+'_PTFE_bar',(x,y,bottom+.004),(.029,.008,.007),white,.0035);bar.rotation_euler[2]=.32 if stir else 0
 # Individual, deliberately enlarged illustrative solid grains: no cloudy liquid.
 rng=random.Random(42 if stir else 8)
 count=3 if stir else 135
 for i in range(count):
  angle=rng.uniform(0,math.tau);rr=math.sqrt(rng.random())*.037
  xx=x+rr*math.cos(angle);yy=y+rr*math.sin(angle)
  if abs(xx-x)<.019 and abs(yy-y)<.008: yy+=.016 if yy>=y else -.016
  size=rng.uniform(.0022,.0037);height=bottom+size/2+(max(0,.022-rr)*.14 if not stir else 0)
  ob=cube(name+'_sugar_'+str(i).zfill(3),(xx,yy,height),(size,size*.80,size*.75),sugar,.00025);ob.rotation_euler=(rng.uniform(-.25,.25),rng.uniform(-.25,.25),angle)
 text(name+'_result_caption','FEW GRAINS LEFT' if stir else 'SOLID SUGAR LEFT',(x-.068,-.021,.0008),.009,accent)
 box_record(name+'_platform','non-heating stir plate' if stir else 'inert matched-height riser',[x,y,.018],[.148,.155,.036])
 box_record(name+'_PTFE_bar','matched magnetic stir bar',[x,y,bottom+.004],[.029,.008,.007],True,'Not manipulated during run; install before adding water.')
# Matched dosing cups, wide collars for a parallel gripper, empty after the simultaneous dose.
active='Dosing'
for j,x in enumerate([.145,.325]):
 y=-.105;z=.004
 cyl('Dose_cup_'+str(j)+'_base',(x,y,z),.023,.004,white)
 N=64;pts=[(x+.023*math.cos(i*math.tau/N),y+.023*math.sin(i*math.tau/N),z+.017) for i in range(N+1)];tube('Dose_cup_'+str(j)+'_rim',pts,.0016,white)
 verts=[];faces=[]
 for rr,zz in [(.023,z),(.023,z+.017),(.0205,z+.017),(.0205,z+.003)]:verts.extend((x+rr*math.cos(i*math.tau/N),y+rr*math.sin(i*math.tau/N),zz) for i in range(N))
 for k in range(3):
  for i in range(N):faces.append((k*N+i,k*N+(i+1)%N,(k+1)*N+(i+1)%N,(k+1)*N+i))
 me=bpy.data.meshes.new('Dose_cup_mesh');me.from_pydata(verts,[],faces);ob=bpy.data.objects.new('Dose_cup_'+str(j)+'_walls',me);sc.collection.objects.link(ob);finish(ob,ob.name,white)
 cube('Dose_cup_'+str(j)+'_grip',(x+.037,y,.013),(.031,.014,.013),teal if j==0 else amber,.003)
 text('Dose_'+str(j)+'_label','10 g START',(x-.034,y-.043,.0008),.008,dark)
 box_record('Dose_cup_'+str(j)+'_grip','empty dosing cup handle',[x+.037,y,.013],[.031,.014,.013],True,'Flat opposing +/-Y handle faces; proposed 5mm side clearance and 15mm lift, unvalidated.')
# A measured spoon rests outside both result areas.
cube('Spoon_rest',(.425,-.082,.008),(.025,.09,.016),white,.004)
cube('Spoon_handle',(.425,-.094,.019),(.009,.075,.003),steel,.003)
sp=cyl('Spoon_bowl',(.425,-.044,.019),.017,.003,steel);sp.scale=(.76,1,1)
text('Matched_conditions','SAME WATER  /  SAME SUGAR  /  ROOM TEMPERATURE',(.073,-.201,.001),.008,dark)
# A single shared timer makes the same-time endpoint explicit.
active='Timing'
cube('Timer_body',(.242,.218,.045),(.116,.035,.079),rubber,.006)
cube('Timer_display',(.242,.1997,.053),(.097,.0015,.041),screen,.002)
text('Timer_readout','01:00',(.199,.1986,.039),.027,white,rot=(math.pi/2,0,0))
text('Timer_shared','SAME TIME',(.206,.1985,.015),.008,white,rot=(math.pi/2,0,0))
text('Timer_top','ILLUSTRATIVE',(.198,.212,.085),.0065,white)
box_record('Timer_body','shared illustrative endpoint timer',[.242,.218,.045],[.116,.035,.079])
active='Cameras'
def camera(n,loc,target,lens):
 d=bpy.data.cameras.new(n);d.lens=lens;d.clip_start=.005;d.clip_end=250;o=bpy.data.objects.new(n,d);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();return finish(o,n)
front=camera('Camera_Front',(.66,-.98,.53),(.155,.035,.105),52)
overhead=camera('Camera_Overhead',(.14,.035,1.25),(.14,.035,0),44);overhead.rotation_euler=(0,0,0)
result=camera('Camera_Result',(.36,-.49,.43),(.24,.065,.065),57)
active='Lighting'
for n,loc,power,size in [('Key',(-.3,-.5,1.4),80,1.2),('Fill',(.8,.25,1.2),45,1.1),('Rim',(.05,.65,1.0),30,.8)]:
 d=bpy.data.lights.new(n,'AREA');d.energy=power;d.shape='DISK';d.size=size;o=bpy.data.objects.new(n,d);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((.22,.06,.07))-o.location).to_track_quat('-Z','Y').to_euler();finish(o,n)
sc.camera=front;bpy.context.view_layer.update()
# Export from a temporary scene copy: typography remains editable in Scene.blend.
blend_tmp=out/'_source_before_export.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend_tmp),compress=True)
for ob in list(sc.objects):
 if ob.type in {'FONT','CURVE'}:
  bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.object.convert(target='MESH')
bpy.ops.object.select_all(action='SELECT');groups['Robot_ART_ONLY'].select_set(False)
bpy.ops.wm.usd_export(filepath=str(out/'Environment.usdc'),selected_objects_only=True,export_materials=True,generate_preview_surface=True,export_textures=False,convert_world_material=False,root_prim_path='/ClassicLab')
bpy.ops.wm.open_mainfile(filepath=str(blend_tmp));sc=bpy.context.scene;groups={n:bpy.data.objects[n] for n in groups};front=bpy.data.objects['Camera_Front'];overhead=bpy.data.objects['Camera_Overhead'];result=bpy.data.objects['Camera_Result']
# Licensed original robot is preview-only, unchanged geometry, camera free.
dark=bpy.data.materials['Matte_print']
active='Robot_ART_ONLY';robot_path=Path(a.robot).resolve() if a.robot else Path(__file__).resolve().parent.parent/'assets'/'Robot_STATIC_ART_ONLY.usdc'
if not robot_path.exists():raise FileNotFoundError('Provide the packaged ../assets/Robot_STATIC_ART_ONLY.usdc or --robot PATH')
before=set(sc.objects);bpy.ops.wm.usd_import(filepath=str(robot_path),import_cameras=False,import_lights=False,create_world_material=False,import_materials=True);new=set(sc.objects)-before
root=bpy.data.objects.new('Original_SO101_preview',None);sc.collection.objects.link(root);root.parent=groups['Robot_ART_ONLY'];root.location=(-.05,0,-.03008145)
for o in new:
 if o.parent not in new:o.parent=root
root['evidence']='Licensed original static no-camera SO101; not articulation or successful motion.'
sc.camera=front;bpy.context.view_layer.update()
# Per-camera provenance footer, created only after environment export.
for camera_ob in [front,overhead,result]:
 footer=text(camera_ob.name+'_Provenance','ART PREVIEW  /  ILLUSTRATIVE ENDPOINT  /  NO KINETICS MODEL',(0,0,0),.0038,dark)
 footer.parent=camera_ob;footer.location=(-.155*52/camera_ob.data.lens,-.099*52/camera_ob.data.lens,-.5);footer.rotation_euler=(0,0,0);footer.hide_render=camera_ob!=front
manifest={'schema_version':1,'experiment':'Dissolving: stir versus still','status':'ART PREVIEW / MODEL-PREDICTED ILLUSTRATIVE ENDPOINT','units':'m','up_axis':'Z','default_prim':'/ClassicLab','tabletop_z_m':0,'table_dimensions_m':[1,.75,.044],'table_center_m':[.12,0,-.022],'robot_in_environment_usd':False,'physics_attached':False,'robot_preview':{'source':'../assets/Robot_STATIC_ART_ONLY.usdc','position_m':[-.05,0,-.03008145],'yaw_added_deg':0,'static_only':True},'student_variable':'stirring','conditions':[{'id':'stirred','mixing':'ON; no heating','water_mL_nominal':450,'sugar_g_nominal':10,'visible_illustrative_grains':3},{'id':'still','mixing':'OFF; no heating','water_mL_nominal':450,'sugar_g_nominal':10,'visible_illustrative_grains':135}],'water_note':'Geometry represents equal fill heights, not a calibrated volume. Beaker printed graduations are visual scale cues. Nominal water volume corrected below from geometry.','observation':'Remaining visible solid at a shared illustrative 60-second endpoint; clear liquid in both. Counts and endpoint not measured or simulated.','model_missing':['sucrose dissolution kinetics','temperature and saturation dependence','fluid velocity/mixing','particle surface evolution and transport','mass conservation and grain-to-mass mapping'],'runtime_missing':['articulated robot','collision and rigid-body setup','safe grip and reach qualification','fixture calibration','dose simultaneity/timer synchronization','controller and task reset','vision-based remaining-solid measurement'],'materials':{'glass':'Approximate alpha=.09, rim=.35; no physical refraction.','water':'Clear alpha=.025; no cloudiness or turbidity proxy.','usd_limit':'USD Preview Surface alpha requires transparency-capable renderer; no scientific optics.'},'objects':records,'cameras':{},'clearances':{'beaker_centers_m':[[.145,.075,.038],[.325,.075,.038]],'center_spacing_m':.18,'wall_to_wall_gap_m':.086,'proposed_over_rim_dose_clearance_m':.025,'reach_qualified':False},'staged_result':{'particle_geometry':'Individual enlarged sugar grains, deterministic pseudorandom arrangement, not molecule or mass model.','time_display':'Illustrative 01:00, not a validated dissolution duration.','initial_state':'Equal dose stated; cups shown emptied after dosing. Both beakers contain identical bars; only one driven.'}}
# The chosen inner radius and fill height represent approximately 464mL; visual graduation values are set consistently below.
for condition in manifest['conditions']:condition['water_mL_nominal']=464
manifest['water_note']='Equal geometric fill: inner liquid radius 45.3 mm and water depth 72 mm, approximately 464 mL; nominal volume, not calibration.'
for c in [front,overhead,result]:manifest['cameras'][c.name]={'position_m':list(c.location),'rotation_euler_xyz_rad':list(c.rotation_euler),'focal_length_mm':c.data.lens,'world_matrix_row_major':[list(r) for r in c.matrix_world],'resolution':[1600,1000]}
manifest['object_inventory']=[]
for ob in sc.objects:
 group=ob
 while group.parent:group=group.parent
 if group.name=='Robot_ART_ONLY' or ob.name.endswith('_Provenance') or ob.type not in {'MESH','CURVE','FONT'}:continue
 movable=any(token in ob.name for token in ['Dose_cup','PTFE_bar','Spoon_','sugar_']) or any(ob.name.startswith(prefix) for prefix in ['Stirred_walls','Still_walls','Stirred_glass','Still_glass','Stirred_open_rim','Still_open_rim'])
 manifest['object_inventory'].append({'object':ob.name,'group':group.name,'classification':'movable apparatus or staged solids' if movable else 'static fixture or visual annotation','position_m':list(ob.matrix_world.translation),'dimensions_m':list(ob.dimensions),'world_matrix_row_major':[list(r) for r in ob.matrix_world]})
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'Scene.blend'),compress=True)
blend_tmp.unlink(missing_ok=True)
if a.render:
 for c,n in [(front,'Front'),(overhead,'Overhead'),(result,'Result')]:
  for cam in [front,overhead,result]:
   for child in cam.children:child.hide_render=cam!=c
  sc.camera=c;sc.render.filepath=str(out/(n+'.png'));bpy.ops.render.render(write_still=True)
print('DISSOLUTION_BUILD_COMPLETE',flush=True)
