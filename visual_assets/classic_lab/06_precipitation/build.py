"""Portable, editable precipitation comparison; Blender 4.5, CPU render only."""
import bpy, math, json, argparse, sys, random
from pathlib import Path
from mathutils import Vector
p=argparse.ArgumentParser();p.add_argument('--out',default=str(Path(__file__).resolve().parent));p.add_argument('--robot',default=str(Path(__file__).resolve().parent.parent/'assets/Robot_STATIC_ART_ONLY.usdc'));p.add_argument('--render',action='store_true');p.add_argument('--view',choices=['Front','Overhead','Result','all'],default='all');a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene
s.unit_settings.system='METRIC';s.unit_settings.scale_length=1;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=48;s.cycles.use_denoising=True;s.render.threads_mode='FIXED';s.render.threads=2
s.render.resolution_x=1600;s.render.resolution_y=1000;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=.1
s.world=bpy.data.worlds.new('Neutral_room');s.world.use_nodes=True;s.world.node_tree.nodes['Background'].inputs[0].default_value=(.42,.45,.49,1);s.world.node_tree.nodes['Background'].inputs[1].default_value=.5
root=bpy.data.objects.new('ClassicLab',None);s.collection.objects.link(root)
groups={}
for n in ['Bench','Fixtures','Reagent_A','Reagent_B','Reactive_condition','Water_control','Cameras','Lighting']:
 ob=bpy.data.objects.new(n,None);s.collection.objects.link(ob);ob.parent=root;groups[n]=ob
active='Bench'
def mat(n,c,rough=.5,metal=0,opacity=1):
 m=bpy.data.materials.new(n);m.use_nodes=True;nt=m.node_tree;b=nt.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(*c,1);b.inputs['Roughness'].default_value=rough;b.inputs['Metallic'].default_value=metal
 if opacity<1:
  tr=nt.nodes.new('ShaderNodeBsdfTransparent');mix=nt.nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=opacity;nt.links.new(tr.outputs[0],mix.inputs[1]);nt.links.new(b.outputs[0],mix.inputs[2]);nt.links.new(mix.outputs[0],nt.nodes.get('Material Output').inputs['Surface'])
 return m
white=mat('Warm_white_bench',(.68,.70,.71));paper=mat('White_reference_panel',(.94,.95,.94));dark=mat('Matte_charcoal_print',(.018,.026,.031),.9);gray=mat('Fixture_gray',(.25,.29,.31));steel=mat('Brushed_stainless',(.48,.53,.56),.3,.75);blue=mat('Reagent_A_blue_identifier',(.04,.25,.42));orange=mat('Reagent_B_ochre_identifier',(.68,.30,.06));glass=mat('Approximate_glass_12percent',(.62,.79,.85),.13,opacity=.12);water=mat('Clear_liquid_5percent',(.54,.75,.79),.16,opacity=.05);cloud=mat('Illustrative_white_suspension',(.78,.84,.83),.7,opacity=.94);sed=mat('Illustrative_settled_solid',(.80,.76,.65),.85);particle=mat('Illustrative_enlarged_particles',(.97,.96,.89),.9);rubber=mat('Silicone_seats',(.08,.12,.13),.85)
def finish(o,n,m=None):
 o.name=n;o.parent=groups[active]
 if m:o.data.materials.append(m)
 return o
def cube(n,loc,dim,m,bev=.001):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=finish(bpy.context.object,n,m);o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bev:md=o.modifiers.new('Soft_edges','BEVEL');md.width=bev;md.segments=3;o.modifiers.new('Weighted_normals','WEIGHTED_NORMAL')
 return o
def cyl(n,loc,r,h,m,verts=64):
 bpy.ops.mesh.primitive_cylinder_add(vertices=verts,radius=r,depth=h,location=loc);o=finish(bpy.context.object,n,m)
 for f in o.data.polygons:f.use_smooth=len(f.vertices)==4
 return o
def tube(n,start,end,r,m):
 mid=(Vector(start)+Vector(end))/2;o=cyl(n,mid,r,(Vector(end)-Vector(start)).length,m,32);o.rotation_euler=(Vector(end)-Vector(start)).to_track_quat('Z','Y').to_euler();return o
def torus(n,loc,major,minor,m):
 bpy.ops.mesh.primitive_torus_add(major_radius=major,minor_radius=minor,major_segments=80,minor_segments=12,location=loc);return finish(bpy.context.object,n,m)
def txt(n,body,loc,size=.010,rot=(math.pi/2,0,0),m=dark,align='CENTER'):
 c=bpy.data.curves.new(n,'FONT');c.body=body;c.size=size;c.align_x=align;c.align_y='CENTER';c.extrude=.000015;o=bpy.data.objects.new(n,c);s.collection.objects.link(o);o.location=loc;o.rotation_euler=rot;return finish(o,n,m)
def vessel(n,x,y,z,r,h):
 # Four rings, open top, distinct flat lip normals, slight outward pouring lip at back.
 verts=[];faces=[];N=96
 for radius,zz in [(r,z),(r,z+h),(r-.0013,z+h),(r-.0013,z+.003)]:
  for i in range(N):
   th=i*math.tau/N;spout=.004*max(0,math.sin(th))**28 if zz>z+h-.001 else 0
   verts.append((x+(radius+spout)*math.cos(th),y+(radius+spout)*math.sin(th),zz))
 for j in range(3):
  for i in range(N):faces.append((j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i))
 me=bpy.data.meshes.new(n);me.from_pydata(verts,[],faces);o=bpy.data.objects.new(n,me);s.collection.objects.link(o);finish(o,n,glass)
 for f in me.polygons:f.use_smooth=f.index//N!=1
 cyl(n+'_bottom',(x,y,z+.0015),r,.003,glass);torus(n+'_rim',(x,y,z+h),r-.0005,.0008,glass)
 for j in range(1,5):
  zz=z+h*.15*j;cube(n+'_graduation_'+str(j),(x+r*.48,y-r*.88-.0008,zz),(.012,.0005,.0007),dark,0)
 return o
def plaque(n,text,x,y,w=.135):
 cube(n+'_card',(x,y,.016),(w,.004,.031),paper,.002);txt(n+'_print',text,(x,y-.0022,.017),.010)
# Workbench
cube('Tabletop',(.12,0,-.022),(1,.75,.044),white,.006)
for x in [-.31,.55]:
 for y in [-.30,.30]:cube('Leg',(x,y,-.398),(.034,.034,.752),gray,.002)
cube('Floor',(.1,0,-.785),(200,200,.05),mat('Floor_gray',(.31,.33,.34)),0)
# Receiving station: two mechanically identical mixers and beakers.
active='Fixtures'
for tag,x in [('Reaction',.235),('Control',.415)]:
 cube(tag+'_drip_tray',(x,-.065,.005),(.154,.158,.010),gray,.008)
 cube(tag+'_mixing_station',(x,-.055,.022),(.127,.125,.025),paper,.006)
 cyl(tag+'_vessel_seat',(x,-.055,.037),.048,.006,rubber)
 for dx in [-.046,.046]:cube(tag+'_locating_stop',(x+dx,-.055,.046),(.007,.020,.012),gray,.002)
 cyl(tag+'_speed_dial',(x+.042,-.118,.025),.009,.006,gray).rotation_euler=(math.pi/2,0,0)
 txt(tag+'_mixer_label','MIX',(x-.027,-.1182,.025),.006)
# White visual reference with black bar patterns shows occlusion.
cube('Reference_backplate',(.325,.012,.112),(.330,.005,.145),paper,.004)
for x in [.235,.415]:
 for dx in [-.023,-.011,0,.011,.023]:cube('Reference_bar',(x+dx,.0088,.102),(.003,.0008,.090),dark,0)
# Two clear dosing vessels on sturdy overhead stand, no fictional fluid simulation.
cube('Stand_foot',(.333,.185,.008),(.28,.10,.016),gray,.005)
for x in [.20,.45]:
 cyl('Stand_rod',(x,.18,.148),.006,.28,steel);cyl('Rod_foot',(x,.18,.023),.014,.03,gray)
tube('Upper_crossbar',(.20,.18,.274),(.45,.18,.274),.005,steel)
for tag,x,col,word in [('A',.255,blue,'A  /  CLEAR'),('B',.385,orange,'B  /  CLEAR')]:
 active='Fixtures';tube(tag+'_holder_arm',(x,.18,.211),(x,.103,.211),.004,steel);torus(tag+'_dosing_collar',(x,.103,.210),.029,.003,col)
 active='Reagent_'+tag;vessel(tag+'_dosing_cup',x,.103,.194,.027,.073);cyl(tag+'_clear_reagent',(x,.103,.221),.0255,.047,water)
 cube(tag+'_identity_plate',(x,.073,.239),(.070,.002,.020),paper,.002);txt(tag+'_identity',word,(x,.0718,.239),.0085)
 cyl(tag+'_valve_body',(x,.103,.185),.008,.018,col);tube(tag+'_valve_handle',(x-.014,.103,.187),(x+.014,.103,.187),.003,dark)
 # Two glass angled delivery stems terminate above the reactive receiving beaker.
 end=(.235+(-.018 if tag=='A' else .018),-.040,.164)
 tube(tag+'_delivery_stem',(x,.103,.178),end,.0025,glass);tube(tag+'_spout_tip',end,(end[0],end[1],.149),.0025,glass)
# Matched samples, 36.7mm inner radius, 70mm liquid depth; staged only.
for cond,x,is_cloud in [('Reactive_condition',.235,True),('Water_control',.415,False)]:
 active=cond;vessel(cond+'_beaker',x,-.055,.040,.042,.115)
 cyl(cond+'_liquid',(x,-.055,.0785),.0405,.071,cloud if is_cloud else water)
 cyl(cond+'_meniscus',(x,-.055,.1142),.0403,.0008,cloud if is_cloud else glass)
 # Same magnetic stirring bar in both, visible through the clear control.
 stir=cube(cond+'_stir_bar',(x,-.055,.046),(.035,.008,.006),paper,.003);stir.rotation_euler[2]=.32
 if is_cloud:
  cyl('Illustrative_sediment',(x,-.055,.047),.0404,.007,sed)
  random.seed(62)
  for i in range(100):
   angle=random.uniform(0,math.tau);rr=random.uniform(.024,.040);zz=random.uniform(.052,.110)
   bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=random.uniform(.0006,.0012),location=(x+rr*math.cos(angle),-.055+rr*math.sin(angle),zz));finish(bpy.context.object,'Illustrative_particle_%03d'%i,particle)
 active='Fixtures';plaque(cond,'A + B  |  CLOUDY' if is_cloud else 'A + WATER  |  CLEAR',x,-.158,.165)
 txt(cond+'_overhead_label','A + B' if is_cloud else 'A + WATER',(x,-.134,.040),.011,rot=(0,0,0))
# Spare control water in a practical sealed bottle and handheld stirring tool rack.
active='Fixtures'
cyl('Water_bottle',(.49,.137,.054),.025,.102,glass);cyl('Water_bottle_contents',(.49,.137,.043),.023,.075,water);cyl('Water_bottle_cap',(.49,.137,.110),.016,.012,paper)
cube('Water_bottle_label',(.49,.112,.058),(.042,.002,.027),paper,.001);txt('Water_bottle_text','WATER',(.49,.1108,.058),.008)
cube('Stirrer_rest',(.145,-.19,.012),(.13,.023,.024),gray,.002);tube('Glass_stirring_rod',(.09,-.19,.027),(.245,-.19,.027),.0025,glass)
# Cameras and neutral area lighting.
active='Cameras';cameras={}
def cam(n,loc,target,lens):
 d=bpy.data.cameras.new(n);d.lens=lens;d.clip_start=.005;d.clip_end=250;o=bpy.data.objects.new(n,d);s.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();finish(o,n);cameras[n]=o;return o
front=cam('Front',(.83,-1.09,.60),(.15,.025,.135),49)
over=cam('Overhead',(.14,.035,1.30),(.14,.035,0),44);over.rotation_euler=(0,0,0)
result=cam('Result',(.64,-.77,.37),(.327,-.030,.117),62)
active='Lighting'
for n,loc,power,size in [('Key',(-.3,-.55,1.5),100,1.25),('Fill',(.85,.25,1.1),65,1.1),('Top',(.25,.5,1.65),65,.9)]:
 d=bpy.data.lights.new(n,'AREA');d.energy=power;d.shape='DISK';d.size=size;o=bpy.data.objects.new(n,d);s.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((.2,0,.1))-o.location).to_track_quat('-Z','Y').to_euler();finish(o,n)
s.camera=front;bpy.context.view_layer.update()
# Keep original editable typography in .blend, temporarily convert for USD export.
font_data=[(o,o.data.copy()) for o in s.objects if o.type=='FONT']
for o,_ in font_data:
 bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o;bpy.ops.object.convert(target='MESH')
bpy.ops.object.select_all(action='SELECT')
# Explicit Preview Surface alpha during export; Blender preview retains the mix shader.
for material, opacity in [(glass,.12),(water,.05),(cloud,.94)]:
 material.node_tree.nodes.get('Principled BSDF').inputs['Alpha'].default_value=opacity
bpy.ops.wm.usd_export(filepath=str(out/'Environment.usdc'),selected_objects_only=True,visible_objects_only=False,export_materials=True,generate_preview_surface=True,export_textures=False,convert_world_material=False,root_prim_path='/ClassicLab')
for material in (glass,water,cloud):material.node_tree.nodes.get('Principled BSDF').inputs['Alpha'].default_value=1
# Restore editable fonts by creating replacements; exported geometry already complete.
for old,data in font_data:
 n=old.name;parent=old.parent;matrix=old.matrix_world.copy();bpy.data.objects.remove(old,do_unlink=True);o=bpy.data.objects.new(n,data);s.collection.objects.link(o);o.parent=parent;o.matrix_world=matrix
# Static original robot for art preview only.
robot_path=Path(a.robot)
if not robot_path.exists():raise FileNotFoundError('Supply --robot original static SO101 USD')
before=set(s.objects);bpy.ops.wm.usd_import(filepath=str(robot_path),import_cameras=False,import_lights=False,create_world_material=False,import_materials=True)
new=set(s.objects)-before;rob=bpy.data.objects.new('SO101_STATIC_ART_ONLY',None);s.collection.objects.link(rob);rob.location=(-.05,0,-.03008145)
for o in new:
 if o.parent not in new:o.parent=rob
# Camera-mounted provenance is not part of environment USD.
active='Cameras'
for n,c in cameras.items():
 o=txt(n+'_provenance','ART PREVIEW  /  ILLUSTRATIVE ENDPOINT  /  STATIC ROBOT',(0,0,0),.00265,rot=(0,0,0),align='LEFT');o.parent=c;o.location=(-.164*49/c.data.lens,-.096*49/c.data.lens,-.5);o.rotation_euler=(0,0,0)
 o.hide_render=n!='Front'
s.camera=front;bpy.context.view_layer.update()
manifest={'schema_version':1,'experiment':'Precipitation: clear + clear produces cloudy solid','status':'illustrative_asset_not_runtime_verified','units':'m','up_axis':'Z','default_prim':'/ClassicLab','tabletop_z_m':0,'table_dimensions_m':[1,.75,.044],'robot_in_environment_usd':False,'robot_preview_transform_m':[-.05,0,-.03008145],'robot_runtime_base_m':[-.05,0,0],'robot_added_yaw_deg':0,'robot_scale':1,'physics_apis':False,'student_variable':'Replace dose B with the same volume of water','conditions':[{'id':'reactive','doses':'clear A + clear B','vessel_center_m':[.235,-.055,.040],'illustrative_result':'milky suspension, enlarged flecks, settled solid layer'},{'id':'control','doses':'clear A + equal-volume water','vessel_center_m':[.415,-.055,.040],'illustrative_result':'clear liquid; reference stripes visible'}],'matched_geometry':{'beaker_outer_radius_m':.042,'beaker_height_m':.115,'liquid_radius_m':.0405,'liquid_depth_m':.071,'nominal_final_liquid_volume_ml':365.85,'note':'Visual geometry only; no calibrated dose or physical reaction recipe'},'sources':[{'group':'Reagent_A','location_m':[.255,.103,.194],'radius_m':.027,'height_m':.073},{'group':'Reagent_B','location_m':[.385,.103,.194],'radius_m':.027,'height_m':.073}],'active_target':{'position_m':[.235,-.055,.040],'rim_z_m':.155,'stem_endpoints_m':[[.217,-.04,.149],[.253,-.04,.149]]},'fixtures':{'mixers':{'centers_m':[[.235,-.055,.022],[.415,-.055,.022]],'dimensions_m':[.127,.125,.025]},'reference_panel':{'center_m':[.325,.012,.112],'dimensions_m':[.330,.005,.145]},'stand':{'center_m':[.333,.185,.008],'base_dimensions_m':[.28,.10,.016],'rod_height_m':.28}},'interaction':{'movable':['dosing valve handles after articulation','water bottle after separating liquid','stirring rod'],'static':['bench','stand','mixing stations','reference panel'],'intended_grasp_surfaces':'28mm valve lever or 5mm stirring rod; intended fixture use only, not reach-qualified','proposed_clearance_m':.015,'reach_status':'pending; high dosing fixtures and control station require controller/fixture qualification','required_work':'jointed metering, grasp geometry, collision, fluid containment, equal-dose control and measured success'},'science':{'model':'No reaction or transport solver present','observable':'calibrated turbidity/reference-pattern contrast plus separately modeled solid fraction','solid_fraction':'not derived; geometric sediment and enlarged particles are illustrative','chemistry':'Chosen classroom reference: A is aqueous calcium chloride, B is aqueous sodium carbonate; calcium carbonate precipitates. The water control replaces B. No reaction/transport model is implemented.'},'material_limits':'Approximate glass uses 12% opaque / 88% transparent shader mix; clear liquid 5%; USD Preview Surface explicitly authors opacity .12/.05/.94 for glass/water/suspension; renderer appearance may vary. No refractive calibration.','cameras':{},'objects':[]}
for n,c in cameras.items():manifest['cameras'][n]={'position_m':list(c.location),'rotation_euler_rad':list(c.rotation_euler),'world_matrix':[list(row) for row in c.matrix_world],'lens_mm':c.data.lens,'resolution':[1600,1000]}
for o in s.objects:
 if o.parent in groups.values() and o.type=='MESH':manifest['objects'].append({'name':o.name,'group':o.parent.name,'position_m':list(o.location),'dimensions_m':list(o.dimensions),'rotation_euler_rad':list(o.rotation_euler)})
(out/'manifest.json').write_text(json.dumps(manifest,indent=2));bpy.ops.wm.save_as_mainfile(filepath=str(out/'Scene.blend'),compress=True)
if a.render:
 for n,c in cameras.items():
  if a.view!='all' and a.view!=n:continue
  for cc in cameras.values():
   for o in cc.children:o.hide_render=cc!=c
  s.camera=c;s.render.filepath=str(out/(n+'.png'));bpy.ops.render.render(write_still=True)
print('PRECIPITATION_READY',flush=True)
