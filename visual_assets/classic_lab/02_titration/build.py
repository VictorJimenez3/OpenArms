import bpy, math, json, argparse, sys, shutil
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
p=argparse.ArgumentParser();p.add_argument('--render',action='store_true');p.add_argument('--camera',default='all');p.add_argument('--robot',type=Path,default=OUT.parent/'assets'/'Robot_STATIC_ART_ONLY.usdc');a=p.parse_args(args)
ROBOT=a.robot
if not ROBOT.exists():raise FileNotFoundError('Provide the packaged ../assets/Robot_STATIC_ART_ONLY.usdc or --robot PATH')
bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene
s.unit_settings.system='METRIC';s.unit_settings.scale_length=1
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=40;s.cycles.use_denoising=True
s.render.threads_mode='FIXED';s.render.threads=2
s.render.resolution_x=1600;s.render.resolution_y=1000;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=-.30
s.world=bpy.data.worlds.new('Neutral laboratory');s.world.use_nodes=True;s.world.node_tree.nodes['Background'].inputs[0].default_value=(.45,.47,.49,1);s.world.node_tree.nodes['Background'].inputs[1].default_value=.35
G={}
for n in ['Bench','Glassware','Titration','Stand_and_clamps','Reagent_and_catcher','Cameras','Lighting','Robot_ART_ONLY','Overlay_ART_ONLY']:
 o=bpy.data.objects.new(n,None);s.collection.objects.link(o);G[n]=o
active='Bench'
def fin(o,n,m=None):
 o.name=n;o.parent=G[active]
 if m:o.data.materials.append(m)
 return o
def mat(n,c,r=.45,metal=0,trans=0,ior=1.46):
 m=bpy.data.materials.new(n);m.use_nodes=True;b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(*c,1);b.inputs['Roughness'].default_value=r;b.inputs['Metallic'].default_value=metal;b.inputs['Transmission Weight'].default_value=trans;b.inputs['IOR'].default_value=ior;return m
white=mat('Warm white powder coat',(.76,.78,.77));tile=mat('White ceramic tile',(.96,.97,.95),.23);dark=mat('Graphite rubber',(.018,.022,.026),.52);ink=mat('Black enamel graduations',(.015,.022,.025),.42);steel=mat('Brushed stainless steel',(.55,.59,.62),.25,.85);teal=mat('Fixture teal',(.025,.29,.30),.35,.15);glass=mat('Borosilicate clear glass',(.94,.99,1),.065,0,1);water=mat('Clear liquid',(.92,.98,1),.05,0,.94,1.333);pink=mat('Illustrative faint pink endpoint',(.96,.58,.72),.12,0,.78,1.333);plume=mat('Illustrative local pink mixing plume',(.95,.06,.3),.1,0,.7,1.333);amber=mat('Reagent bottle amber glass',(.27,.075,.014),.18,0,.64);paper=mat('Paper label',(.95,.95,.90),.65);ground=mat('Neutral background',(.37,.40,.42),.8)
ink.node_tree.nodes.get('Principled BSDF').inputs['Specular IOR Level'].default_value=0
ink.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=1
hudink=bpy.data.materials.new('Camera annotation dark ink');hudink.use_nodes=True
nt=hudink.node_tree;nt.nodes.clear();em=nt.nodes.new('ShaderNodeEmission');em.inputs[0].default_value=(.012,.016,.019,1);em.inputs[1].default_value=1;outn=nt.nodes.new('ShaderNodeOutputMaterial');nt.links.new(em.outputs[0],outn.inputs['Surface'])
hudpaper=bpy.data.materials.new('Camera annotation white backing');hudpaper.use_nodes=True
nt=hudpaper.node_tree;nt.nodes.clear();em=nt.nodes.new('ShaderNodeEmission');em.inputs[0].default_value=(.85,.87,.86,1);em.inputs[1].default_value=1;outn=nt.nodes.new('ShaderNodeOutputMaterial');nt.links.new(em.outputs[0],outn.inputs['Surface'])
def cube(n,loc,dim,m,bevel=.001):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=fin(bpy.context.object,n,m);o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bevel:b=o.modifiers.new('Rounded manufactured edges','BEVEL');b.width=bevel;b.segments=3;o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
 return o
def cyl(n,loc,r,h,m):
 bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=r,depth=h,location=loc);o=fin(bpy.context.object,n,m)
 for f in o.data.polygons:f.use_smooth=len(f.vertices)==4
 return o
def sphere(n,loc,scale,m):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,radius=1,location=loc);o=fin(bpy.context.object,n,m);o.scale=scale
 for f in o.data.polygons:f.use_smooth=True
 return o
def rod(n,p1,p2,r,m):
 d=Vector(p2)-Vector(p1);o=cyl(n,(Vector(p1)+Vector(p2))/2,r,d.length,m);o.rotation_euler=d.to_track_quat('Z','Y').to_euler();return o
def lathe(n,x,y,profile,m):
 vs=[];fs=[];N=96
 for r,z in profile:vs.extend((x+r*math.cos(i*math.tau/N),y+r*math.sin(i*math.tau/N),z) for i in range(N))
 for j in range(len(profile)-1):
  for i in range(N):fs.append((j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i))
 me=bpy.data.meshes.new(n);me.from_pydata(vs,[],fs);me.update();o=bpy.data.objects.new(n,me);s.collection.objects.link(o);fin(o,n,m)
 for f in me.polygons:f.use_smooth=True
 return o
def text(n,t,loc,size=.009,rot=(math.pi/2,0,0),m=ink):
 cu=bpy.data.curves.new(n,'FONT');cu.body=t;cu.size=size;cu.extrude=.000015;cu.space_character=1.05;o=bpy.data.objects.new(n,cu);s.collection.objects.link(o);o.location=loc;o.rotation_euler=rot;return fin(o,n,m)
def ring(n,loc,R,r,m,rot=(0,0,0)):
 bpy.ops.mesh.primitive_torus_add(major_radius=R,minor_radius=r,major_segments=64,minor_segments=12,location=loc,rotation=rot);o=fin(bpy.context.object,n,m)
 for f in o.data.polygons:f.use_smooth=True
 return o
cube('Normal 100 x 75 cm worktop',(.12,0,-.022),(1,.75,.044),white,.006)
for x in [-.31,.55]:
 for y in [-.30,.30]:cube('Bench leg',(x,y,-.38),(.035,.035,.716),steel,.003)
cube('Floor',(.1,0,-.785),(200,200,.05),ground,0)
# Active conical flask and stir plate, modest 250 mL scale.
active='Titration';x=.245;y=-.055
cube('Magnetic stirrer body',(x,y,.014),(.154,.144,.028),white,.009)
cube('White endpoint contrast tile',(x,y,.031),(.132,.124,.006),tile,.002)
for dx in [-.055,.055]:
 for dy in [-.05,.05]:cyl('Stirrer rubber foot',(x+dx,y+dy,.002),.008,.004,dark)
knob=cyl('Stirrer speed knob',(.292,-.130,.016),.009,.007,dark);knob.rotation_euler[0]=math.pi/2
cube('Power indicator',(.199,-.127,.016),(.004,.001,.004),teal,0)
text('Stirrer name','STIR',(.214,-.128,.013),.005)
active='Glassware'
# Continuous closed wall cross-section: real hollow flask with open mouth.
base=.035
profile=[(0,base),(.032,base),(.037,base+.004),(.039,base+.012),(.037,base+.030),(.016,base+.080),(.014,base+.086),(.014,base+.112),(.0155,base+.115),(.0155,base+.118),(.012,base+.118),(.012,base+.086),(.014,base+.080),(.035,base+.030),(.037,base+.012),(.034,base+.004),(.0,base+.004)]
lathe('Open 250 mL conical endpoint flask',x,y,profile,glass)
ring('Rolled flask rim',(x,y,base+.117),.0138,.0016,glass)
# Single staged endpoint volume, pink density muted by transmission against white tile.
lathe('ILLUSTRATIVE faint pink liquid',x,y,[(0,base+.004),(.034,base+.004),(.0364,base+.013),(.034,base+.037),(.032,base+.041),(0,base+.041)],pink)
ring('Pink meniscus',(x,y,base+.041),.0315,.0007,pink)
rod('White PTFE stir bar',(x-.012,y,.043),(x+.012,y,.043),.003,tile)
# Graduations on flask front; short bars follow front surface sufficiently for illustration.
for z,tx in [(base+.018,'50'),(base+.031,'100'),(base+.047,'150')]:
 r=.038-(z-(base+.025))*.35
 cube('Flask graduation '+tx,(x-.011,y-r-.0006,z),(.015,.00025,.0004),ink,0)
 text('Flask volume '+tx,tx,(x+.003,y-r-.0008,z-.002),.0044)
text('Flask capacity','250 mL',(x-.016,y-.021,base+.073),.005)
# Burette: tall passive tube, narrow outlet and single visible hanging drop.
bx=x;by=y;btop=.642;bb=.210
lathe('Graduated burette open glass tube',bx,by,[(.0078,bb),(.0078,btop),(.009,btop+.003),(.007,btop+.003),(.0065,btop),(.0065,bb),(.0078,bb)],glass)
lathe('Clear titrant column',bx,by,[(0,.214),(.00635,.214),(.00635,.572),(0,.572)],water)
for i in range(51):
 z=.620-i*.0075;long=i%5==0
 cube('Burette graduation %02d'%i,(bx-.0025 if long else bx-.003,by-.0079,z),(.008 if long else .004,.00022,.00045),ink,0)
 if long:text('Burette scale %02d'%i,str(i),(bx+.007,by-.0080,z-.0017),.0044)
text('Burette volume','mL',(bx+.007,by-.0080,.632),.0045)
active='Titration'
# Glass stopcock barrel along X and contrasting PTFE plug.
rod('Glass stopcock barrel',(bx-.015,by,.207),(bx+.017,by,.207),.0085,glass)
rod('PTFE stopcock plug',(bx-.018,by,.207),(bx+.023,by,.207),.0055,tile)
cyl('Glass outlet shoulder',(bx,by,.191),.005,.018,glass)
lathe('Burette tapered outlet',bx,by,[(.005,.184),(.002,.168),(.0014,.168),(.0036,.184),(.005,.184)],glass)
sphere('ONE staged hanging titrant drop',(bx,by,.1625),(.0026,.0026,.0042),water)
# Green broad paddle plus shaft extension: conceptual fixture keeps active contact lower.
rod('Stopcock rotary adapter',(bx-.022,by,.207),(bx-.022,by-.035,.207),.004,teal)
rod('Remote dosing lever extension',(bx-.022,by-.035,.207),(bx-.022,by-.035,.127),.0035,steel)
cube('Accessible dosing paddle',(bx-.022,by-.043,.127),(.029,.012,.020),teal,.003)
cube('Paddle tactile stripe',(bx-.022,by-.0495,.127),(.019,.0005,.003),tile,.0002)
# Passive stand aft of flask: stable plate, vertical polished rod, two actual clamp assemblies.
active='Stand_and_clamps'
cube('Heavy retort stand base',(.390,.118,.010),(.175,.185,.020),dark,.008)
rod('Vertical retort stand',(.410,.153,.020),(.410,.153,.681),.006,steel)
cyl('Stand top cap',(.410,.153,.682),.0068,.005,dark)
for z in [.297,.529]:
 cube('Boss head',(.410,.153,z),(.030,.025,.023),steel,.003)
 rod('Boss screw',(.410,.140,z),(.410,.116,z),.003,steel)
 cube('Boss thumb screw',(.410,.112,z),(.024,.007,.008),dark,.002)
 rod('Clamp horizontal arm',(.410,.153,z),(bx+.018,by,z),.004,steel)
 # spring jaws visibly grasp outer tube, rubber pads preserve scale.
 for side in [-1,1]:
  rod('Clamp jaw',(bx+.021,by,z),(bx+.002,by+side*.011,z),.0025,steel)
  rod('Clamp curved finger',(bx+.002,by+side*.011,z),(bx-.006,by+side*.007,z),.0025,steel)
  sphere('Rubber clamp contact',(bx,by+side*.007,z),(.004,.002,.006),dark)
 rod('Clamp adjustment screw',(bx+.020,by-.012,z),(bx+.020,by+.018,z),.002,steel)
 sphere('Clamp screw head',(bx+.020,by-.016,z),(.007,.003,.005),dark)
active='Reagent_and_catcher'
# A proper shoulder/neck reagent bottle with recessed base and ribbed closure.
rx=.442;ry=-.125
lathe('Amber reagent bottle',rx,ry,[(0,.002),(.024,.002),(.027,.006),(.027,.076),(.023,.087),(.012,.096),(.012,.115),(.010,.115),(.010,.097),(.021,.085),(.024,.075),(.024,.006),(0,.006)],amber)
cyl('Reagent ribbed screw cap',(rx,ry,.116),.014,.014,dark)
for i in range(32):
 th=i*math.tau/32;rod('Cap grip rib',(rx+.014*math.cos(th),ry+.014*math.sin(th),.110),(rx+.014*math.cos(th),ry+.014*math.sin(th),.122),.00055,dark)
cube('Reagent label',(rx,ry-.0273,.047),(.042,.0007,.047),paper,.001)
text('Reagent bottle legend','TITRANT\nDEMO', (rx-.018,ry-.0278,.055),.007)
text('Reagent provenance','COLORED WATER',(rx-.018,ry-.0278,.031),.0037)
# Spare clear starting sample in small open vial conveys initial transparent state.
sx=.352;sy=-.195
lathe('Clear start sample vial',sx,sy,[(0,.001),(.012,.001),(.012,.040),(.0105,.041),(.0105,.004),(0,.004)],glass)
cyl('Clear starting sample',(sx,sy,.011),.0103,.016,water)
text('Start sample bench label','CLEAR START',(sx-.031,sy-.023,.001),.006,rot=(0,0,0))
# Removable drip catcher, no second experiment.
cx=.433;cy=.013
lathe('Drop catcher dish',cx,cy,[(0,.001),(.029,.001),(.031,.003),(.032,.014),(.029,.014),(.028,.004),(0,.004)],tile)
text('Catcher bench label','DRIP TRAY',(cx-.025,cy-.045,.001),.006,rot=(0,0,0))
# Small endpoint card on work surface only.
cube('Endpoint comparison card',(.238,-.233,.0007),(.151,.040,.0014),paper,.001)
text('Endpoint comparison text','CLEAR  >  FAINT PINK',(.171,-.240,.0016),.007,rot=(0,0,0))
# Lighting and fixed cameras.
active='Cameras'
def cam(n,loc,target,lens):
 d=bpy.data.cameras.new(n);d.lens=lens;d.clip_start=.005;d.clip_end=250;o=bpy.data.objects.new(n,d);s.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();fin(o,n);return o
front=cam('Front',(1.13,-1.58,.82),(.15,.025,.30),46)
over=cam('Overhead',(.14,.035,1.40),(.14,.035,0),44);over.rotation_euler=(0,0,0)
result=cam('Result',(.52,-.62,.32),(.247,-.057,.126),60)
active='Lighting'
def area(n,loc,power,size,target=(.2,0,.2)):
 d=bpy.data.lights.new(n,'AREA');d.energy=power;d.shape='DISK';d.size=size;o=bpy.data.objects.new(n,d);s.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();fin(o,n)
area('Large laboratory ceiling softbox',(-.4,-.3,1.6),45,1.3);area('White wall fill',(.8,.45,1.1),30,.9);area('Glass highlight strip',(.45,.15,.8),8,.36)
s.camera=front
# Export environment before original robot and art-only overlays are added. Text is converted for USD only.
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Environment_editable.blend'),compress=True)
fonts=[o for o in s.objects if o.type=='FONT']
for o in fonts:
 bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o;bpy.ops.object.convert(target='MESH')
bpy.ops.object.select_all(action='DESELECT')
for o in s.objects:o.select_set(o.name not in ['Robot_ART_ONLY','Overlay_ART_ONLY'])
bpy.ops.wm.usd_export(filepath=str(OUT/'Environment.usdc'),selected_objects_only=True,export_materials=True,generate_preview_surface=True,export_textures=False,convert_world_material=False,root_prim_path='/ClassicLab')
# Original licensed SO101 geometry, not reconstructed or rescaled.
active='Robot_ART_ONLY';before=set(s.objects)
bpy.ops.wm.usd_import(filepath=str(ROBOT),import_cameras=False,import_lights=False,create_world_material=False,import_materials=True)
new=set(s.objects)-before
robot=bpy.data.objects.new('Original SO101 static preview',None);s.collection.objects.link(robot);fin(robot,robot.name);robot.location=(-.05,0,-.03008145)
for ob in new:
 if ob.parent not in new:ob.parent=robot
robot['provenance']='Licensed original static geometry; no camera; unqualified preview pose'
# Art annotations locked to camera, excluded from environment USD.
active='Overlay_ART_ONLY'
def hud(c):
 w=.5*36/c.data.lens;h=w*1000/1600
 for suffix,loc,dim in [('Header',(-.345*w,(.415 if c==result else .445)*h,-.501),(.285*w,(.12 if c==result else .065)*h,.0001)),('Footer',(-.32*w,-.452*h,-.501),(.33*w,.036*h,.0001))]:
  o=cube(c.name+' '+suffix+' annotation backing',(0,0,0),dim,hudpaper,0);o.parent=c;o.location=loc;o.rotation_euler=(0,0,0)
 for suffix,body,xx,yy,size in [('Title','02 / ACID-BASE TITRATION',-.47*w,.43*h,.018*w),('Footer','ART PREVIEW | ILLUSTRATIVE ENDPOINT | REACH UNVERIFIED',-.47*w,-.46*h,.0105*w)]:
  o=text(c.name+suffix,body,(0,0,0),size,rot=(0,0,0),m=hudink);o.parent=c;o.location=(xx,yy,-.5)
 if c==result:
  o=text('Result action annotation','ONE DROP  >  FAINT PINK',(0,0,0),.019*w,rot=(0,0,0),m=hudink);o.parent=c;o.location=(-.47*w,.38*h,-.5)
for c in [front,over,result]:hud(c)
def visibility(c):
 for other in [front,over,result]:
  for o in other.children:o.hide_render=other!=c
visibility(front);s.camera=front;bpy.context.view_layer.update()
manifest={'id':'02_titration','name':'Acid-base titration','status':'ART_PREVIEW / ILLUSTRATIVE_SCIENCE','units':'meters','up_axis':'Z','default_prim':'/ClassicLab','table':{'center':[.12,0,-.022],'size':[1,.75,.044],'top_z':0},'robot':{'source':'../assets/Robot_STATIC_ART_ONLY.usdc','preview_translation':[-.05,0,-.03008145],'runtime_reference':[-.05,0,0],'additional_yaw':0,'scaled':False,'camera_mounted':False,'environment_inclusion':False,'pose':'static original; not a qualified reachable pose'},'apparatus':{'burette':{'center_xy':[bx,by],'top_z_m':.645,'outlet_z_m':.168,'outside_diameter_m':.0156,'nominal_markings':'0-50 mL illustrative'},'flask':{'center_xy':[x,y],'height_m':.118,'outer_base_diameter_m':.078,'base_z_m':base,'capacity_label':'250 mL'},'stand':{'rod_xy':[.410,.153],'rod_height_m':.661},'stirrer':{'center':[x,y,.014],'size':[.154,.144,.028]}},'active_source':{'object':'Accessible dosing paddle','contact_center_m':[.223,-.098,.127],'requirement':'gripper contacts widened removable lever adapter; original stopcock axis X; fixture kinematics and collision qualification pending'},'active_target':{'flask_center_m':[x,y,.094],'mouth_center_m':[x,y,.153],'opening_diameter_m':.024},'science':{'source':'Artist-authored illustrative acid-base indicator endpoint; no simulation or chemical model executed','liquid':'non-hazardous colored-water representation','drop':'one suspended mesh, no dynamics','pink':'static illustrative final state; not experimental evidence','clear_start':'separate clear reference vial'},'physics_apis':False,'reach_verified':False,'cameras':{},'groups':list(G)}
for c in [front,over,result]:manifest['cameras'][c.name]={'position_m':list(c.location),'euler_xyz_rad':list(c.rotation_euler),'world_matrix_row_major':[list(r) for r in c.matrix_world],'focal_length_mm':c.data.lens,'resolution':[1600,1000]}

manifest['runtime_contract']={
 'dependencies':{'environment':[],'preview_robot':['../assets/Robot_STATIC_ART_ONLY.usdc'],'textures':[]},
 'conditions':[
  {'name':'Prepared sample A: normalized acid amount 1x','student_variable':'normalized acid amount 1 at fixed starting volume','fixed_assumptions':'same titrant strength, indicator response, starting volume, mixing and endpoint persistence rule','expected_observable':'record dose V_A to the same persistent faint-pink endpoint'},
  {'name':'Prepared sample B: normalized acid amount 2x','student_variable':'normalized acid amount 2 at the same starting volume','fixed_assumptions':'same titrant strength, indicator response, starting volume, mixing and endpoint persistence rule','expected_observable':'ideal declared neutralization model predicts V_B approximately 2 V_A; this package does not execute the model'}],
 'execution_stages':['clear below endpoint','persistent faint pink at endpoint'],
 'controller_missing':True,'reaction_indicator_mixing_model_missing':True,'color_staging_is_runtime_proof':False,
 'entities':{
  'dosing_paddle':{'prim_path':'/ClassicLab/Titration/Accessible_dosing_paddle','mobility':'intended movable fixture; no authored joint','contact_center_m':[.223,-.098,.127],'contact_surface':'front and rear broad faces of teal pad','dimensions_m':[.029,.012,.020],'approach':'from front (-Y), subject to robot-specific collision/reach validation','clearance':'pad extends 22 mm below nearby vertical shaft; all finger envelopes unverified','world_transform_row_major':[list(r) for r in bpy.data.objects['Accessible dosing paddle'].matrix_world]},
  'stopcock':{'prim_path':'/ClassicLab/Titration/PTFE_stopcock_plug','mobility':'intended rotation about world X','center_m':[.2475,-.055,.207],'joint_missing':True},
  'receiving_flask':{'prim_path':'/ClassicLab/Glassware/Open_250_mL_conical_endpoint_flask','mobility':'movable vessel, staged stationary on tile','target_opening_m':[.245,-.055,.153],'opening_diameter_m':.024,'body_height_m':.118,'body_diameter_m':.078,'grasp':'neck outer diameter 28 mm; no current flask-transfer task'},
  'passive_burette':{'prim_path':'/ClassicLab/Glassware/Graduated_burette_open_glass_tube','mobility':'static clamped instrument','outlet_target_m':[.245,-.055,.168]},
  'passive_stand':{'prim_path':'/ClassicLab/Stand_and_clamps','mobility':'static fixture'},
  'staged_drop':{'prim_path':'/ClassicLab/Titration/ONE_staged_hanging_titrant_drop','mobility':'visual-only staged result'},
  'staged_pink':{'prim_path':'/ClassicLab/Glassware/ILLUSTRATIVE_faint_pink_liquid','mobility':'visual-only staged result'}
 }}

(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
for f in ['WORKSHOP_LICENSE','THIRD_PARTY_NOTICES','source_receipt.json']:
 src=ROBOT.parent/f
 if src.exists():shutil.copy2(src,OUT/f)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Scene.blend'),compress=True)
if a.render:
 for c in [front,over,result]:
  if a.camera!='all' and a.camera!=c.name:continue
  visibility(c);s.camera=c;s.render.filepath=str(OUT/(c.name+'.png'));bpy.ops.render.render(write_still=True)
visibility(front);s.camera=front;bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Scene.blend'),compress=True)
print('TITRATION_COMPLETE',flush=True)
