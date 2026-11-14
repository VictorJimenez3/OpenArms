"""Six plain single-experiment visual candidates. No physics or simulated success.
Blender 4.5: blender -b -t 8 --python build_candidates.py -- --out PATH --render
"""
import bpy,math,json,sys,argparse
from pathlib import Path
from mathutils import Vector
p=argparse.ArgumentParser(); p.add_argument('--out',required=True); p.add_argument('--render',action='store_true'); p.add_argument('--only',type=int,default=0); a=p.parse_args(sys.argv[sys.argv.index('--')+1:]); out=Path(a.out).resolve(); out.mkdir(parents=True,exist_ok=True)
IDS=['vial_placement','sample_sorting','density','ramp_friction','lever_balance','indicator']
TITLES=['Vial placement','Size-based sample sorting','Density: float or sink','Ramp friction','Lever balance','Indicator response']
base_robot=out/'assets'/'Robot_STATIC_ART_ONLY.usdc'

def build(idx):
 bpy.ops.wm.read_factory_settings(use_empty=True); sc=bpy.context.scene
 sc.unit_settings.system='METRIC'; sc.unit_settings.scale_length=1
 sc.render.engine='CYCLES'; sc.cycles.samples=48; sc.cycles.use_denoising=True
 sc.render.resolution_x=1440; sc.render.resolution_y=900; sc.render.resolution_percentage=100; sc.render.image_settings.file_format='PNG'
 sc.view_settings.view_transform='AgX'; sc.view_settings.look='AgX - Medium High Contrast'; sc.view_settings.exposure=-.4
 sc.world=bpy.data.worlds.new('Neutral studio'); sc.world.use_nodes=True; sc.world.node_tree.nodes['Background'].inputs[0].default_value=(.24,.24,.24,1); sc.world.node_tree.nodes['Background'].inputs[1].default_value=.55
 try:
  pr=bpy.context.preferences.addons['cycles'].preferences; pr.compute_device_type='METAL'; pr.get_devices()
  for d in pr.devices:d.use=d.type=='METAL'
  if any(d.type=='METAL' for d in pr.devices): sc.cycles.device='GPU'
 except Exception: pass
 groups={}
 for name in ['Environment','Experiment','Robot_ART_ONLY','Cameras','Lighting','Guides','ColliderProxies']:
  o=bpy.data.objects.new(name,None); sc.collection.objects.link(o); groups[name]=o
 active='Environment'
 def finish(ob,name,m=None):
  ob.name=name; ob.parent=groups[active]
  if m: ob.data.materials.clear();ob.data.materials.append(m)
  return ob
 def material(n,c,rough=.5,metal=0,trans=0):
  m=bpy.data.materials.new(n);m.use_nodes=True;b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(*c,1);b.inputs['Roughness'].default_value=rough;b.inputs['Metallic'].default_value=metal;b.inputs['Transmission Weight'].default_value=trans;b.inputs['IOR'].default_value=1.33;return m
 white=material('Matte light gray',(.48,.5,.52)); gray=material('Neutral gray',(.2,.22,.24)); dark=material('Dark gray',(.035,.04,.045)); steel=material('Steel',(.45,.47,.50),.3,.65); blue=material('Blue sample',(.015,.15,.58),.35); orange=material('Orange sample',(.65,.16,.025),.4); cream=material('Vial',(.75,.77,.74),.3); glass=material('Clear receiver',(.9,.97,1),.08,trans=.9); water=material('Water representation',(.40,.68,.79),.15,trans=.65)
 def cube(n,loc,dim,m,bev=.002):
  bpy.ops.mesh.primitive_cube_add(size=1,location=loc);ob=finish(bpy.context.object,n,m);ob.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  if bev:
   mod=ob.modifiers.new('Edge radius','BEVEL');mod.width=bev;mod.segments=3;ob.modifiers.new('Normals','WEIGHTED_NORMAL')
  return ob
 def cyl(n,loc,r,h,m):
  bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=r,depth=h,location=loc);ob=finish(bpy.context.object,n,m)
  for f in ob.data.polygons:f.use_smooth=len(f.vertices)==4
  bevel=ob.modifiers.new('Edge radius','BEVEL');bevel.width=.001;bevel.segments=2;ob.modifiers.new('Normals','WEIGHTED_NORMAL');return ob
 def label(n,s,loc,size=.012,rot=(0,0,0),m=dark):
  cu=bpy.data.curves.new(n,'FONT');cu.body=s;cu.size=size;cu.extrude=.00002;ob=bpy.data.objects.new(n,cu);sc.collection.objects.link(ob);ob.location=loc;ob.rotation_euler=rot;return finish(ob,n,m)
 def sample(n,loc,col=blue):return cube(n,loc,(.025,.025,.025),col,.002)
 def tray(n,x,y,col=gray):
  cube(n+'_base',(x,y,.003),(.115,.10,.006),col)
  for dx in (-.055,.055):cube(n+'_side',(x+dx,y,.015),(.005,.10,.024),col,.001)
  for dy in (-.0475,.0475):cube(n+'_end',(x,y+dy,.015),(.11,.005,.024),col,.001)
 def cup(n,x,y,r=.043,h=.105):
  cyl(n+'_base',(x,y,.002),r,.004,glass)
  # Open, thin-walled receiver with clean side normals and no optical fake floor.
  verts=[];faces=[];segments=64
  for radius,z in [(r,0),(r,h),(r-.0015,h),(r-.0015,.004)]:
   verts.extend((x+radius*math.cos(i*math.tau/segments),y+radius*math.sin(i*math.tau/segments),z) for i in range(segments))
  for j in range(3):
   for i in range(segments):faces.append((j*segments+i,j*segments+(i+1)%segments,(j+1)*segments+(i+1)%segments,(j+1)*segments+i))
  me=bpy.data.meshes.new(n);me.from_pydata(verts,[],faces);ob=bpy.data.objects.new(n,me);sc.collection.objects.link(ob);finish(ob,n,glass)
  for f in me.polygons:f.use_smooth=f.index//segments!=1
  return ob
 def import_static(path,name,loc,rotation=0,override=None):
  before=set(sc.objects);bpy.ops.wm.usd_import(filepath=str(path),import_cameras=False,import_lights=False,create_world_material=False,import_materials=True,import_visible_only=True)
  new=set(sc.objects)-before;parent=bpy.data.objects.new(name,None);sc.collection.objects.link(parent);finish(parent,name);parent.location=loc;parent.rotation_euler[2]=rotation
  for ob in new:
   if ob.parent not in new: ob.parent=parent
   if override and ob.type=='MESH':ob.data.materials.clear();ob.data.materials.append(override)
  return parent,new
 cube('Work_surface',(.12,0,-.022),(1.00,.75,.044),white,.006)
 for x in (-.31,.55):
  for y in (-.30,.30):cube('Table_leg',(x,y,-.40),(.035,.035,.72),dark,.003)
 cube('Ground',(.10,0,-.785),(200,200,.05),gray,0)
 # Subtle tabletop ticks, practical 10cm scale without an enclosing room.
 active='Guides'
 for i in range(9):cube('Scale_tick',(-.28+i*.1,-.36,.0002),(.001,.008,.0004),gray,0)
 label('Scale_label','10 cm',(-.27,-.35,.0005),.009)
 active='Experiment'; meta=[{'source_object': 'Sample_vial', 'source_origin_m': [0.23, -0.1, 0.017], 'receiver_object': 'Rack', 'receiver_origin_m': [0.18, 0.08, 0.006], 'target_pocket_center_xy_m': [0.21, 0.11]}, {'source_object': 'Sample', 'source_origin_m': [0.22, -0.12, 0.0075], 'receivers': {'Tray_A_base': [0.16, 0.12, 0.003], 'Tray_B_base': [0.32, 0.12, 0.003]}}, {'source_object': 'Sealed_sample', 'source_origin_m': [0.2, -0.1, 0.013572], 'receiver_object': 'Water_receiver', 'receiver_center_xy_m': [0.25, 0.12], 'rim_z_m': 0.075, 'water_surface_z_m': 0.054}, {'source_object': 'Sliding_block', 'source_origin_m': [0.2, -0.11, 0.013], 'receiver_object': 'Ramp', 'ramp_center_m': [0.25, 0.1, 0.043], 'downhill_axis': '+X', 'ramp_angle_deg': 20}, {'source_object': 'Moveable_mass', 'source_origin_m': [0.23, -0.11, 0.01], 'receiver_object': 'Lever', 'pivot_center_m': [0.25, 0.1, 0.088], 'target_pocket_centers_m': [[0.3, 0.1, 0.094], [0.35, 0.1, 0.094]]}, {'source_object': 'Indicator_tab', 'source_origin_m': [0.22, -0.1, 0.022], 'receiver_object': 'Sample_well', 'well_center_xy_m': [0.25, 0.12], 'liquid_surface_z_m': 0.014606}][idx]
 if idx==0:
  import_static(out/'assets'/'Rack_STATIC_ART_ONLY.usdc','Rack',(.18,.08,.006),override=cream)
  vial,new=import_static(out/'assets'/'Vial_STATIC_ART_ONLY.usdc','Sample_vial',(.23,-.10,.017),override=cream)
  # Distinguishable cap, no invented liquid/result.
  cyl('Vial_cap_color',(.23,-.10,.111),.017,.009,blue)
  label('Source_label','SOURCE',(.19,-.155,.0005),.011);label('Rack_label','RACK',(.195,.225,.0005),.011)
 elif idx==1:
  cyl('Sample',(.22,-.12,.0075),.008,.015,blue);tray('Tray_A',.16,.12,gray);tray('Tray_B',.32,.12,gray)
  label('A_label','A',(.125,.185,.0005),.015);label('B_label','B',(.29,.185,.0005),.015)
  label('Small_bin','SMALL',(.135,.12,.007),.009);label('Large_bin','LARGE',(.295,.12,.007),.009)
 elif idx==2:
  cube('Sealed_sample',(.20,-.10,.013572),(.027144,.027144,.027144),orange);cup('Water_receiver',.25,.12,.060,.075);cyl('Water',(.25,.12,.029),.058,.050,water)
  label('Sample_label','SAMPLE',(.15,-.15,.0005),.011);label('Water_label','WATER',(.205,.195,.0005),.011)
 elif idx==3:
  # A 20-degree rigid ramp, length 0.20m; positive X slopes down.
  ob=cube('Ramp',(.25,.10,.043),(.20,.13,.009),cream,.002);ob.rotation_euler[1]=math.radians(20)
  for y in (.030,.170):
   rail=cube('Ramp_rail',(.25,y,.05),(.20,.004,.018),gray,.001);rail.rotation_euler[1]=math.radians(20)
  cube('Ramp_support',(.16,.10,.036),(.025,.10,.072),gray);tray('Catch_tray',.405,.10,gray)
  sample('Sliding_block',(.20,-.11,.013),blue)
  label('Ramp_label','20 deg',(.29,.195,.0005),.011)
 elif idx==4:
  cube('Fulcrum_base',(.25,.10,.007),(.07,.09,.014),gray)
  cube('Fulcrum',(.25,.10,.045),(.015,.04,.08),steel)
  cube('Lever',(.25,.10,.088),(.28,.055,.012),cream)
  for x in [.13,.19,.25,.31,.37]:cube('Lever_tick',(x,.10,.0945),(.001,.042,.001),dark,0)
  cyl('Fixed_mass',(.20,.10,.114),.016,.04,steel)
  for xx in (.20,.30,.35):
   for yy in (.078,.122):cube('Weight_pocket',(xx,yy,.098),(.042,.003,.008),gray,.0005)
   for dx in (-.021,.021):cube('Weight_pocket',(xx+dx,.10,.098),(.003,.047,.008),gray,.0005)
  cyl('Moveable_mass',(.23,-.11,.010),.016,.020,steel)
  label('Lever_label','BALANCE',(.195,.17,.0005),.011)
 elif idx==5:
  cup('Sample_well',.25,.12,.026,.06);cyl('Prepared_sample',(.25,.12,.009303),.0245,.010606,water)
  cube('Tab_rest',(.19,-.10,.01),(.025,.025,.020),gray);cube('Indicator_tab',(.22,-.10,.022),(.070,.012,.004),cream,.0005);cube('Tab_handle',(.194,-.10,.025),(.018,.014,.006),blue,.001)
  label('Tab_label','INDICATOR',(.16,-.15,.0005),.011);label('Sample_label','SAMPLE',(.215,.17,.0005),.011)
 # Native camera positions are identical across candidate scenes.
 active='Cameras'
 def cam(name,loc,target,lens):
  d=bpy.data.cameras.new(name);d.lens=lens;d.sensor_width=36;d.clip_start=.01;d.clip_end=250;o=bpy.data.objects.new(name,d);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();finish(o,name);return o
 front=cam('Camera_Front',(.70,-1.05,.32),(.12,.035,.12),52)
 overhead=cam('Camera_Overhead',(.14,.035,1.20),(.14,.035,0),44);overhead.rotation_euler=(0,0,0)
 active='Lighting'
 def light(n,loc,power,size):
  d=bpy.data.lights.new(n,'AREA');d.energy=power;d.shape='DISK';d.size=size;o=bpy.data.objects.new(n,d);sc.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((.12,0,0))-o.location).to_track_quat('-Z','Y').to_euler();finish(o,n)
 light('Room_light',(-.5,-.5,1.8),90,1.8);light('Room_fill',(.8,.4,1.5),45,1.5)
 sc.camera=front
 # Simple proxy meshes kept in a separate file. Runtime chooses physics APIs.
 active='ColliderProxies';proxy=cube('Table_proxy',(.12,0,-.022),(1,.75,.044),None,0);proxy.hide_render=True;proxy.display_type='WIRE'
 dirname=out/f'{idx+1:02d}_{IDS[idx]}';dirname.mkdir(exist_ok=True)
 # Editable asset-only version includes no robot. Text converted only for export.
 bpy.ops.wm.save_as_mainfile(filepath=str(dirname/'Environment.blend'),compress=True)
 for ob in list(sc.objects):
  if ob.type=='FONT':bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.object.convert(target='MESH')
 def select_groups(allowed):
  for ob in sc.objects:ob.select_set(ob.name in allowed or (ob.parent and ob.parent.name in allowed))
 # Imported static prop mesh descendants may be below an extra source root.
 def ancestry(ob):
  while ob:
   if ob.name in groups:return ob.name
   ob=ob.parent
  return None
 def export(file,allowed):
  for ob in sc.objects:ob.select_set(ancestry(ob) in allowed)
  bpy.ops.wm.usd_export(filepath=str(file),selected_objects_only=True,visible_objects_only=False,export_materials=True,generate_preview_surface=True,export_textures=False,convert_world_material=False,root_prim_path='/TrainingScene')
 export(dirname/'Experiment.usdc',{'Environment','Experiment','Cameras','Lighting','Guides'})
 proxy.hide_render=False
 export(dirname/'ColliderProxies.usdc',{'ColliderProxies'})
 proxy.hide_render=True
 if idx==0:export(out/'BaseEnvironment.usdc',{'Environment','Cameras','Lighting','Guides'})
 # Add original static robot solely for camera/art review after exports.
 active='Robot_ART_ONLY';robot,meshes=import_static(base_robot,'SO101_original_meshes',(-.05,0,-.03008145),rotation=0)
 robot['evidence']='STATIC ART PREVIEW; runtime articulation and pose are separate'
 bpy.context.view_layer.update()
 manifest={'schema_version':1,'id':IDS[idx],'name':TITLES[idx],'status':'asset_candidate_not_runtime_verified','units':'m','up_axis':'Z','tabletop_z':0,'default_prim':'/TrainingScene','table_size':[1,.75,.044],'robot_in_environment_usd':False,'robot_runtime_initial':{'position':[-.05,0,0],'additional_yaw_deg':None,'note':'Reuse native authored root transform; runtime owns joint/base mapping. Do not duplicate authored yaw.'},'robot_preview_only':{'position':list(robot.location),'yaw_deg':0,'source':'NVIDIA workshop static original meshes'},'cameras':{},'experiment':meta,'physics_attached':False,'required_runtime':'Original articulated robot, collision, mass, reset, controller and measured success. Science models separately labeled.'}
 for c in (front,overhead):
  manifest['cameras'][c.name]={'position_m':list(c.location),'rotation_euler_xyz_rad':list(c.rotation_euler),'focal_length_mm':c.data.lens,'horizontal_aperture_mm':36,'resolution':[1440,900],'fixed':True,'world_matrix_row_major':[list(r) for r in c.matrix_world]}
 manifest['meshes']=[]
 for ob in sc.objects:
  if ob.type=='MESH' and ancestry(ob)!='Robot_ART_ONLY':
   pts=[ob.matrix_world@Vector(v) for v in ob.bound_box];manifest['meshes'].append({'name':ob.name,'group':ancestry(ob),'min':[min(v[i] for v in pts) for i in range(3)],'max':[max(v[i] for v in pts) for i in range(3)]})
 (dirname/'manifest.json').write_text(json.dumps(manifest,indent=2))
 # Annotation is camera-mounted and excluded from USD. Clear evidence provenance.
 def hud(camera):
  active_before=None
  for n,body,x,y,size in [('Title',f'{idx+1:02d}  /  '+TITLES[idx].upper(),-.16,.087,.0065),('Provenance','ART PREVIEW / STATIC ASSETS / NOT ISAAC EXECUTION',-.16,-.092,.0038)]:
   ob=label(camera.name+'_'+n,body,(0,0,0),size,m=dark);ob.parent=camera;ob.location=(x,y,-.50);ob.rotation_euler=(0,0,0)
  # Text dimensions must be relative to focal length so it fits actual viewport.
  for child in camera.children:child.scale*=52/camera.data.lens
 hud(front);hud(overhead)
 sc.camera=front
 for child in overhead.children:child.hide_render=True
 bpy.ops.wm.save_as_mainfile(filepath=str(dirname/'ART_PREVIEW.blend'),compress=True)
 if a.render:
  for camera,filename in [(front,'Front_ART_PREVIEW.png'),(overhead,'Overhead_ART_PREVIEW.png')]:
   for c in (front,overhead):
    for child in c.children:child.hide_render=c!=camera
   sc.camera=camera;sc.render.filepath=str(dirname/filename);bpy.ops.render.render(write_still=True)
 print('CANDIDATE_COMPLETE',idx+1,flush=True)
for idx in range(6):
 if not a.only or a.only==idx+1:build(idx)
