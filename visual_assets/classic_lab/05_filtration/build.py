"""Portable classic filtration art preview; Blender 4.5+, CPU only.
blender -b -t 2 --python build.py -- --render [--robot path]
No simulated fluid, physics, or controller success is claimed.
"""
import bpy, math, random, json, argparse, sys
from pathlib import Path
from mathutils import Vector

P=argparse.ArgumentParser(); P.add_argument('--out',default=str(Path(__file__).resolve().parent)); P.add_argument('--robot',default=str(Path(__file__).resolve().parent.parent/'assets'/'Robot_STATIC_ART_ONLY.usdc')); P.add_argument('--render',action='store_true'); P.add_argument('--render-only',action='store_true'); A=P.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
OUT=Path(A.out); OUT.mkdir(parents=True,exist_ok=True)
if A.render_only:
 bpy.ops.wm.open_mainfile(filepath=str(OUT/'Scene.blend'))
 sc=bpy.context.scene
else:
 bpy.ops.wm.read_factory_settings(use_empty=True); sc=bpy.context.scene
sc.unit_settings.system='METRIC'; sc.unit_settings.scale_length=1
sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=40; sc.cycles.use_denoising=True
sc.render.threads_mode='FIXED'; sc.render.threads=2
sc.render.resolution_x=1600; sc.render.resolution_y=1000; sc.render.resolution_percentage=100; sc.render.image_settings.file_format='PNG'
sc.view_settings.view_transform='AgX'; sc.view_settings.look='AgX - Medium High Contrast'; sc.view_settings.exposure=-1.15

if not A.render_only:
 sc.world=bpy.data.worlds.new('Neutral studio'); sc.world.use_nodes=True; sc.world.node_tree.nodes['Background'].inputs[0].default_value=(.3,.33,.36,1); sc.world.node_tree.nodes['Background'].inputs[1].default_value=.55
 groups={}
 for n in ['Environment','Apparatus','Samples','Annotations','Cameras','Lighting','Robot_ART_ONLY','PreviewFooter']:
  o=bpy.data.objects.new(n,None); sc.collection.objects.link(o); groups[n]=o
 active='Apparatus'; records=[]
 def finish(o,n,m=None):
  o.name=n; o.parent=groups[active]
  if m:o.data.materials.append(m)
  return o
 def mat(n,c,rough=.5,metal=0,opacity=1):
  m=bpy.data.materials.new(n); m.use_nodes=True; nt=m.node_tree; bs=nt.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(*c,1); bs.inputs['Roughness'].default_value=rough; bs.inputs['Metallic'].default_value=metal
  if opacity<1:
   out=nt.nodes.get('Material Output'); tr=nt.nodes.new('ShaderNodeBsdfTransparent'); mix=nt.nodes.new('ShaderNodeMixShader'); mix.inputs[0].default_value=opacity; nt.links.new(tr.outputs[0],mix.inputs[1]); nt.links.new(bs.outputs[0],mix.inputs[2]); nt.links.new(mix.outputs[0],out.inputs[0]); m.diffuse_color=(*c,opacity)
  return m
 white=mat('Warm white bench',(.66,.69,.7)); ink=mat('Matte charcoal print',(.003,.006,.009),.95); slate=mat('Fixture graphite',(.08,.11,.13),.7); steel=mat('Brushed steel',(.42,.48,.52),.35,.75); paper=mat('White folded cellulose paper',(.91,.87,.75),.95); glass=mat('Illustrative clear glass opacity 0.13',(.58,.77,.83),.22,opacity=.13); edge=mat('Glass rim edge',(.42,.67,.73),.28,opacity=.58); muddy=mat('Brown suspended solids',(.09,.029,.006),.72); grit=mat('Retained insoluble grains',(.10,.038,.009),1); clear=mat('Much clearer filtrate illustrative',(.38,.76,.80),.22,opacity=.42); cyan=mat('Paper condition teal',(.015,.29,.34)); ochre=mat('No paper condition ochre',(.59,.26,.035)); rubber=mat('Soft grip collar',(.13,.17,.19),.95)
 def cube(n,loc,dim,m,bevel=.001):
  bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=finish(bpy.context.object,n,m); o.dimensions=dim; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  if bevel: mod=o.modifiers.new('Soft edges','BEVEL'); mod.width=bevel; mod.segments=3; o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
  return o
 def cyl(n,loc,r,h,m,verts=64):
  bpy.ops.mesh.primitive_cylinder_add(vertices=verts,radius=r,depth=h,location=loc); o=finish(bpy.context.object,n,m)
  for f in o.data.polygons:f.use_smooth=len(f.vertices)==4
  return o
 def lathe(n,xy,profile,m,N=96,fold=0):
  vs=[]; fs=[]
  for r,z in profile:
   for i in range(N):
    ang=math.tau*i/N; rr=r*(1+fold*math.cos(8*ang)); vs.append((xy[0]+rr*math.cos(ang),xy[1]+rr*math.sin(ang),z))
  for k in range(len(profile)-1):
   for i in range(N):fs.append((k*N+i,k*N+(i+1)%N,(k+1)*N+(i+1)%N,(k+1)*N+i))
  me=bpy.data.meshes.new(n); me.from_pydata(vs,[],fs); me.update(); o=bpy.data.objects.new(n,me); sc.collection.objects.link(o); finish(o,n,m)
  # Flat ring-to-ring faces intentionally avoid sharp rim normal smearing.
  return o
 def torus(n,loc,major,minor,m):
  bpy.ops.mesh.primitive_torus_add(major_radius=major,minor_radius=minor,major_segments=96,minor_segments=10,location=loc); return finish(bpy.context.object,n,m)
 def line(n,pts,r,m):
  cu=bpy.data.curves.new(n,'CURVE'); cu.dimensions='3D'; cu.bevel_depth=r; cu.bevel_resolution=3; sp=cu.splines.new('POLY'); sp.points.add(len(pts)-1)
  for p,v in zip(sp.points,pts):p.co=(*v,1)
  o=bpy.data.objects.new(n,cu); sc.collection.objects.link(o); return finish(o,n,m)
 def text(n,s,loc,size=.012,rot=(math.pi/2,0,0),m=ink):
  cu=bpy.data.curves.new(n,'FONT'); cu.body=s; cu.size=size; cu.extrude=.000025; cu.align_x='CENTER'; o=bpy.data.objects.new(n,cu); sc.collection.objects.link(o); o.location=loc; o.rotation_euler=rot; return finish(o,n,m)
 def plaque(n,s,x,y,z,width=.11,col=None):
  cube(n+'_plate',(x,y,z),(width,.003,.025),white,.0015); text(n+'_text',s,(x,y-.0018,z-.004),.011,m=col or ink)
 def sphere(n,loc,scale,m):
  bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=1,location=loc); o=finish(bpy.context.object,n,m); o.scale=scale; return o
 def item(n,kind,origin,dims,handling=None):records.append({'object':n,'classification':kind,'origin_m':origin,'nominal_dimensions_m':dims,'proposed_handling':handling})
 active='Environment'; cube('Work_surface',(.12,0,-.022),(1,.75,.044),white,.006); cube('Ground',(.12,0,-.785),(200,200,.05),mat('Neutral floor',(.25,.27,.29)),0)
 for x in [-.31,.55]:
  for y in [-.30,.30]:cube('Table_leg',(x,y,-.40),(.035,.035,.72),slate,.003)
 active='Apparatus'
 rig_start=set(sc.objects)
 # One spill-contained comparison station.
 cube('Catch_tray_base',(.30,.065,.006),(.365,.275,.012),slate,.004)
 for x in [.1225,.4775]:cube('Catch_tray_side',(x,.065,.016),(.010,.275,.026),slate,.003)
 for y in [-.0675,.1975]:cube('Catch_tray_end',(.30,y,.016),(.355,.010,.026),slate,.003)
 item('Catch_tray_base','static_fixture',[.30,.065,.006],[.365,.275,.012])
 # Single stand supports the matched funnels with distinct arm collars.
 cube('Stand_foot',(.322,.165,.030),(.22,.055,.018),steel,.004); cyl('Stand_post',(.322,.165,.197),.006,.32,steel)
 sphere('Stand_post_cap',(.322,.165,.359),(.0065,.0065,.0065),slate)
 for cond,x,col in [('Paper',.235,cyan),('NoPaper',.405,ochre)]:
  y=.055
  cube(cond+'_flask_nest',(x,y,.020),(.105,.105,.012),col,.004)
  for dx,dy in [(-.049,0),(.049,0),(0,.049)]:cube(cond+'_locating_tab',(x+dx,y+dy,.033),(.009,.009,.026),rubber,.002)
  # Open conical receiving flask: exterior, neck lip, internal wall, bottom.
  lathe(cond+'_Flask',(x,y),[(0,.027),(.043,.027),(.048,.033),(.048,.053),(.022,.106),(.016,.111),(.016,.143),(.018,.145),(.018,.148),(.0135,.148),(.0135,.113),(.020,.108),(.0455,.052),(.0455,.032),(0,.032)],glass)
  torus(cond+'_flask_lip',(x,y,.147),.016,.0016,edge)
  torus(cond+'_flask_base',(x,y,.031),.046,.0012,edge)
  # Liquid uses its own closed frustum so contrast remains visible in all views.
  active='Samples'; liquid=clear if cond=='Paper' else muddy
  lathe(cond+'_Filtrate',(x,y),[(0,.034),(.044,.034),(.044,.052),(.033,.075),(0,.075)],liquid)
  if cond=='NoPaper':
   random.seed(67)
   for i in range(20):
    xx=random.uniform(-.029,.029); yy=random.uniform(-.019,.019); sphere('Control_suspended_grain_%02d'%i,(x+xx,y+yy,.0755),(random.uniform(.001,.002),.0015,.0014),grit)
  active='Apparatus'
  # Glass funnel bowl and genuine hollow stem; 110 mm top diameter.
  lathe(cond+'_Funnel',(x,y),[(.006,.158),(.006,.201),(.055,.269),(.057,.270),(.057,.273),(.053,.273),(.0043,.202),(.0043,.158)],glass)
  torus(cond+'_funnel_rim',(x,y,.272),.055,.0016,edge)
  torus(cond+'_funnel_stem_end',(x,y,.159),.0052,.001,edge)
  # Ring bracket behind the cone, connected to a shared upright.
  torus(cond+'_support_ring',(x,y,.229),.029,.0024,steel)
  line(cond+'_support_arm',[(x,y+.029,.229),(x,.165,.229),(.322,.165,.229)],.0036,steel)
  cube(cond+'_clamp_boss',(.322,.165,.229 if cond=='Paper' else .245),(.025,.024,.023),slate,.003)
  knob=cyl(cond+'_clamp_screw',(.322,.185,.229 if cond=='Paper' else .245),.010,.011,slate); knob.rotation_euler[0]=math.pi/2
  if cond=='Paper':
   lathe('Folded_filter_paper',(x,y),[(.004,.205),(.050,.267),(.0515,.267),(.0055,.205)],paper,fold=.035)
   # Visible retained particles occupy an actual shallow bed on the cone.
   active='Samples'; lathe('Retained_brown_grit_bed',(x,y),[(0,.210),(.009,.215),(.034,.249),(0,.249)],muddy,fold=.035)
   random.seed(42)
   for i in range(80):
    r=.0325*math.sqrt(random.random()); theta=random.random()*math.tau; z=.249+random.uniform(.0003,.0012); q=random.uniform(.001,.0023)
    sphere('Retained_grain_%03d'%i,(x+r*math.cos(theta),y+r*math.sin(theta),z),(q,q*.78,q*.6),grit)
  active='Samples'
  # Frozen falling droplets communicate active filtration, not a fluid simulation.
  for i,z in enumerate([.153,.136,.118]):sphere(cond+'_illustrative_drop_'+str(i),(x,y,z),(.0021,.0021,.0032),clear if cond=='Paper' else muddy)
  active='Annotations'; plaque(cond+'_condition','PAPER' if cond=='Paper' else 'NO PAPER',x,-.074,.038,.135,col)
  plaque(cond+'_outcome','CLEARER' if cond=='Paper' else 'STILL BROWN',x,-.073,.073,.132,ink)
  # Graduation marks directly on front of flask.
  for iz,z in enumerate([.045,.055,.065]):
   rr=.047 if z<.053 else .047-(z-.053)*.49
   line(cond+'_graduation_'+str(iz),[(x-.010,y-rr-.0005,z),(x+.010,y-rr-.0005,z)],.00045,ink)
  active='Apparatus'; item(cond+'_Flask','movable_vessel',[x,y,.027],[.096,.096,.121],{'surface':'neck exterior','neck_radius_m':.016,'z_range_m':[.115,.138],'warning':'lifting only empty and without funnel; filled neck must remain beneath stem'})
  item(cond+'_Funnel','passive_clamped_vessel',[x,y,.158],[.114,.114,.115],{'surface':'ring support; do not robot-grasp glass cone','pour_target_m':[x,y,.278],'clear_opening_radius_m':.047})
 # Offset the complete passive rig away from the original static robot envelope.
 # The source cup stays in the front handling area. Preserve all relative rig geometry.
 for rig_ob in set(sc.objects)-rig_start:rig_ob.location.y+=.10
 for record in records:
  record['origin_m'][1]+=.10
  handling=record.get('proposed_handling') or {}
  if 'pour_target_m' in handling:handling['pour_target_m'][1]+=.10
 # Source at reachable front-left; real open lip with integral pouring spout.
 x=.115; y=-.155; active='Apparatus'
 cube('Source_cradle',(x,y,.006),(.105,.105,.012),cyan,.004)
 for dx in [-.047,.047]:cube('Source_locator',(x+dx,y,.019),(.008,.070,.026),rubber,.002)
 lathe('Dirty_input_beaker',(x,y),[(0,.013),(.039,.013),(.042,.017),(.042,.116),(.043,.118),(.039,.118),(.039,.019),(0,.019)],glass)
 torus('Input_beaker_rim',(x,y,.117),.041,.0014,edge)
 # Open V-shaped extended pouring spout.
 line('Beaker_spout_left',[(x+.032,y-.026,.116),(x+.054,y-.010,.118),(x+.041,y+.003,.116)],.0015,edge)
 lathe('Input_grip_collar',(x,y),[(.0425,.057),(.044,.057),(.044,.077),(.0425,.077)],rubber)
 cube('Grip_flat_left',(x-.047,y,.067),(.008,.027,.022),rubber,.002); cube('Grip_flat_right',(x+.047,y,.067),(.008,.027,.022),rubber,.002)
 cube('Robot_grip_lug',(x-.067,y,.067),(.043,.018,.022),slate,.002)
 for dy in [-.010,.010]:cube('Robot_grip_contact_pad',(x-.072,y+dy,.067),(.024,.002,.019),rubber,.0007)
 # A rear handle gives a human a distinct separate handling surface.
 line('Beaker_handle',[(x,y+.042,.094),(x,y+.068,.094),(x,y+.068,.038),(x,y+.042,.038)],.004,slate)
 active='Samples'; cyl('Dirty_input_water',(x,y,.052),.038,.064,muddy)
 random.seed(9)
 for i in range(65):
  r=.035*math.sqrt(random.random()); t=random.random()*math.tau; q=random.uniform(.001,.003)
  sphere('Input_insoluble_grain_%03d'%i,(x+r*math.cos(t),y+r*math.sin(t),.084+random.uniform(.0001,.001)),(q,q*.8,q*.5),grit)
 active='Annotations'; plaque('Input_label','DIRTY WATER',x,-.214,.044,.130)
 text('Bench_comparison_caption','SAME WATER  /  SAME FUNNEL',(.318,-.13,.001),.010,(0,0,0),ink)
 # Small glass stirring rod in an anti-roll holder: useful preparation apparatus.
 active='Apparatus'; cube('Stirrer_rest',(.255,-.17,.009),(.12,.025,.018),white,.003); line('Glass_stirring_rod',[(.201,-.17,.021),(.309,-.17,.021)],.0025,edge)
 item('Dirty_input_beaker','movable_source',[x,y,.013],[.132,.11,.105],{'surface':'narrow rigid collar-attached lug with opposing rubber pads','contact_a_m':[x-.072,y-.011,.067],'contact_b_m':[x-.072,y+.011,.067],'contact_face_m':[.024,.019],'required_gripper_opening_m':.022,'proposed_side_approach_clearance_m':.02,'qualification':'requires validated adaptor fabrication, gripping force, payload and reachable pour poses; unverified'})
 item('Stand_post','static_fixture',[.322,.265,.197],[.012,.012,.32]); item('Source_cradle','static_fixture',[x,y,.006],[.105,.105,.012])
 active='Cameras'
 def camera(n,loc,target,lens):
  d=bpy.data.cameras.new(n); d.lens=lens; d.clip_start=.008; d.clip_end=250; o=bpy.data.objects.new(n,d); sc.collection.objects.link(o); o.location=loc; o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler(); finish(o,n); return o
 front=camera('Camera_Front',(1.10,-.75,.82),(.19,.075,.12),50)
 overhead=camera('Camera_Overhead',(.17,.015,1.35),(.17,.015,0),44)
 result=camera('Camera_Result',(.78,-.48,.72),(.28,.135,.15),57)
 active='Lighting'
 for n,loc,power,size in [('Key',(-.3,-.5,1.5),110,1.0),('Fill',(.7,.35,1.0),65,.8)]:
  d=bpy.data.lights.new(n,'AREA'); d.energy=power; d.shape='DISK'; d.size=size; o=bpy.data.objects.new(n,d); sc.collection.objects.link(o); o.location=loc; o.rotation_euler=(Vector((.2,0,.1))-o.location).to_track_quat('-Z','Y').to_euler(); finish(o,n)
 # Convert labels and rods to portable geometry. Export before original robot import.
 for o in list(sc.objects):
  if o.type in {'FONT','CURVE'}:
   bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active=o; bpy.ops.object.convert(target='MESH')
 bpy.ops.object.select_all(action='SELECT'); groups['Robot_ART_ONLY'].select_set(False); groups['PreviewFooter'].select_set(False); bpy.ops.wm.usd_export(filepath=str(OUT/'Environment.usdc'),selected_objects_only=True,export_materials=True,generate_preview_surface=True,export_textures=False,convert_world_material=False,root_prim_path='/ClassicLab')
 robot_path=Path(A.robot)
 if not robot_path.exists():raise FileNotFoundError('Provide the packaged ../assets/Robot_STATIC_ART_ONLY.usdc or --robot PATH')
 before=set(sc.objects); bpy.ops.wm.usd_import(filepath=str(robot_path),import_cameras=False,import_lights=False,create_world_material=False,import_materials=True); added=set(sc.objects)-before
 for o in added:
  if o.parent not in added:o.parent=groups['Robot_ART_ONLY']
 groups['Robot_ART_ONLY'].location=(-.05,0,-.03008145)
 # Camera-relative provenance text is preview-only.
 active='PreviewFooter'
 for c in [front,overhead,result]:
  o=text(c.name+'_footer','ART PREVIEW  /  MODEL-PREDICTED FILTRATION  /  NOT POTABLE',(0,0,0),.004,(0,0,0),ink); o.parent=c; o.location=(-.001,-.091,-.50); o.scale*=50/c.data.lens
 sc.camera=front; bpy.context.view_layer.update()
 manifest={'schema_version':1,'experiment':'Dirty-water filtration / matched paper versus no-paper control','status':'ILLUSTRATIVE ART PREVIEW; no physics or executed manipulation','units':'m','up_axis':'Z','default_prim':'/ClassicLab','tabletop_z_m':0,'table_center_m':[.12,0,-.022],'table_dimensions_m':[1,.75,.044],'robot_in_environment_usd':False,'physics_attached':False,'robot_preview':{'source':str(robot_path),'translation_m':[-.05,0,-.03008145],'extra_yaw_rad':0,'camera_attached':False,'runtime_base_reference_m':[-.05,0,0]},'apparatus':records,'conditions':[{'name':'Paper','changed_variable':'folded paper fitted','source':'same prepared suspended-particle water','predicted_observation':'visible brown residue retained; much clearer collected liquid'},{'name':'NoPaper','changed_variable':'paper absent','source':'matched aliquot of same water','predicted_observation':'particles pass through funnel; collected liquid stays brown'}],'controlled_variables':['same mixed feed batch','equal aliquot volume','same funnel geometry','matched observation interval','same receiving flask geometry'],'measurable_observation':['relative transmitted light or calibrated turbidity of collected aliquots','visible residue mass after drying under supervised protocol'],'illustrative_staging':['brown water mesh','retained particulate mesh','clearer filtrate mesh','frozen droplets'],'science_limits':['No claim of potability, disinfection, or removal of dissolved substances.','Particles smaller than effective paper pores may pass; adsorption and sedimentation are not modeled.','No particle transport, fluid volume conservation, filtration rate or turbidity calibration is implemented.'],'glass_approximation':{'shader':'Transparent/Principled mix','glass_opacity':.13,'rim_opacity':.58,'clear_filtrate_opacity':.42,'USD_limit':'USD Preview Surface may not reproduce Blender mix transparency; geometry is fully self-contained.'},'cameras':{},'objects':[]}
 for c in [front,overhead,result]:manifest['cameras'][c.name]={'position_m':list(c.location),'rotation_euler_xyz_rad':list(c.rotation_euler),'matrix_world_row_major':[list(r) for r in c.matrix_world],'focal_length_mm':c.data.lens,'resolution_px':[1600,1000]}
 for o in sc.objects:
  if o.type!='MESH':continue
  q=o
  while q.parent:q=q.parent
  if q.name=='Robot_ART_ONLY':continue
  manifest['objects'].append({'name':o.name,'world_matrix_row_major':[list(r) for r in o.matrix_world],'dimensions_m':list(o.dimensions),'parent':o.parent.name if o.parent else None})
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
 for c in [front,overhead,result]:
  for o in c.children:o.hide_render=c!=front
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Scene.blend'),compress=True)
 print('BUILD_READY',flush=True)

if A.render or A.render_only:
 for name,file in [('Camera_Front','Front.png'),('Camera_Overhead','Overhead.png'),('Camera_Result','Result.png')]:
  cam=bpy.data.objects[name]
  for cname in ['Camera_Front','Camera_Overhead','Camera_Result']:
   for o in bpy.data.objects[cname].children:o.hide_render=cname!=name
  sc.camera=cam; sc.render.filepath=str(OUT/file); bpy.ops.render.render(write_still=True)
 print('RENDERS_COMPLETE',flush=True)
