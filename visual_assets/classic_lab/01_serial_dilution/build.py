"""Editable serial-dilution art. Blender 4.5; CPU-only; no simulated fluids."""
import bpy, math, json, argparse, sys
from pathlib import Path
from mathutils import Vector
P=argparse.ArgumentParser();P.add_argument('--out',default=str(Path(__file__).parent));P.add_argument('--robot');P.add_argument('--render',action='store_true');a=P.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
robot=Path(a.robot) if a.robot else Path(__file__).resolve().parent.parent/'assets'/'Robot_STATIC_ART_ONLY.usdc'
bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene;s.unit_settings.system='METRIC';s.unit_settings.scale_length=1
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=40;s.cycles.use_denoising=True;s.render.threads_mode='FIXED';s.render.threads=2;s.cycles.max_bounces=12;s.cycles.transmission_bounces=8
s.render.resolution_x=1600;s.render.resolution_y=1000;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=-.7
s.world=bpy.data.worlds.new('Neutral laboratory daylight');s.world.use_nodes=True;s.world.node_tree.nodes['Background'].inputs[0].default_value=(.65,.68,.72,1);s.world.node_tree.nodes['Background'].inputs[1].default_value=.35
G={}
for n in ['Bench','Dilution_station','Dosing_fixture','Stock_and_water','Cameras','Lighting','Robot_ART_ONLY','Preview_annotation']:
 o=bpy.data.objects.new(n,None);s.collection.objects.link(o);G[n]=o
active='Bench'
def done(o,n,m=None):
 o.name=n;o.parent=G[active]
 if m:o.data.materials.append(m)
 return o
def mat(n,c,rough=.4,metal=0,trans=0,ior=1.45):
 m=bpy.data.materials.new(n);m.use_nodes=True;b=m.node_tree.nodes['Principled BSDF'];b.inputs['Base Color'].default_value=(*c,1);b.inputs['Roughness'].default_value=rough;b.inputs['Metallic'].default_value=metal;b.inputs['Transmission Weight'].default_value=trans;b.inputs['IOR'].default_value=ior;return m
white=mat('Warm white polypropylene',(.75,.78,.79));bench=mat('Pale laboratory laminate',(.61,.64,.65));dark=mat('Charcoal print',(.002,.004,.007));steel=mat('Brushed steel',(.4,.44,.47),.24,.8);black=mat('Dark rubber',(.028,.037,.043),.65);glass=mat('Clear borosilicate',(.94,.985,1),.075,0,1,1.46);blue=mat('Blue fixture details',(.025,.18,.30));paper=mat('White laboratory label',(.88,.9,.87),.7);floor=mat('Neutral gray floor',(.22,.245,.26),.8)
colors=[(.002,.025,.40),(.005,.13,.70),(.06,.34,.83),(.22,.56,.9),(.48,.73,.94),(.75,.87,.96)]
liquids=[mat('Illustrative concentration '+str(v),c,.13,0,.42,1.333) for v,c in zip([1,.5,.25,.125,.0625,.03125],colors)]
# Alpha transparency is an intentional art readability approximation.
glass.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value=.18
glass.node_tree.nodes['Principled BSDF'].inputs['Transmission Weight'].default_value=.5
water=mat('Clear water',(.90,.965,.99),.08,0,.8,1.333)
def cube(n,l,d,m,bevel=.001):
 bpy.ops.mesh.primitive_cube_add(size=1,location=l);o=done(bpy.context.object,n,m);o.dimensions=d;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bevel:q=o.modifiers.new('Rounded manufactured edges','BEVEL');q.width=bevel;q.segments=3;o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
 return o
def cyl(n,l,r,h,m):
 bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=r,depth=h,location=l);o=done(bpy.context.object,n,m)
 for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
 return o
def cone(n,l,r1,r2,h,m):
 bpy.ops.mesh.primitive_cone_add(vertices=64,radius1=r1,radius2=r2,depth=h,location=l);o=done(bpy.context.object,n,m)
 for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
 return o
def line(n,a,b,r,m):
 a=Vector(a);b=Vector(b);o=cyl(n,(a+b)/2,r,(b-a).length,m);o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();return o
def txt(n,t,l,size=.009,m=None,rot=(math.pi/2,0,0),align='CENTER'):
 c=bpy.data.curves.new(n,'FONT');c.body=t;c.size=size;c.align_x=align;c.extrude=.000015;o=bpy.data.objects.new(n,c);s.collection.objects.link(o);o.location=l;o.rotation_euler=rot;return done(o,n,m or dark)
def torus(n,l,r,t,m):
 bpy.ops.mesh.primitive_torus_add(major_segments=64,minor_segments=12,location=l,major_radius=r,minor_radius=t);return done(bpy.context.object,n,m)
def shell(n,x,y,z,profile,m):
 vs=[];fs=[];N=96
 for r,h in profile:
  for i in range(N):
   angle=i*math.tau/N;vs.append((x+r*math.cos(angle),y+r*math.sin(angle),z+h))
 for j in range(len(profile)-1):
  for i in range(N):fs.append((j*N+i,j*N+(i+1)%N,(j+1)*N+(i+1)%N,(j+1)*N+i))
 me=bpy.data.meshes.new(n);me.from_pydata(vs,[],fs);me.update();o=bpy.data.objects.new(n,me);s.collection.objects.link(o);done(o,n,m)
 for p in me.polygons:
  j=p.index//N;p.use_smooth=abs(profile[j+1][1]-profile[j][1])>abs(profile[j+1][0]-profile[j][0])*2
 return o
cube('Laboratory bench',(.12,0,-.022),(1,.75,.044),bench,.006)
for x in [-.31,.55]:
 for y in [-.30,.30]:cube('Bench leg',(x,y,-.40),(.035,.035,.72),steel,.003)
cube('Floor',(.12,0,-.78),(200,200,.04),floor,0)
active='Dilution_station'
xs=[.17,.24,.31,.38,.45];y=-.105;z=.009;r=.0228;ri=.0216;h=.092
cube('Ordered five-position rack base',(.31,y,.004),(.352,.095,.008),white,.004)
# The open low cradle preserves visibility of every colored sample.
for x in xs:
 torus('Rubber anti-slip locating ring',(x,y,.010),.024,.0015,black)
for i,x in enumerate(xs):
 n=f'Beaker_{i+1}'
 shell(n+'_open_glass',x,y,z,[(0,0),(r-.001,0),(r,.002),(r,h-.003),(r+.001,h),(ri,h),(ri,.003),(0,.003)],glass)
 torus(n+'_rolled_rim',(x,y,z+h),r-.0002,.001,glass)
 # A proper pinched pour lip, localized at rear, remains visibly open.
 verts=[(x-.006,y+.021,z+h-.003),(x+.006,y+.021,z+h-.003),(x+.006,y+.029,z+h+.001),(x-.006,y+.029,z+h+.001)]
 me=bpy.data.meshes.new(n+'_spout');me.from_pydata(verts,[],[(0,1,2,3)]);o=bpy.data.objects.new(n+'_pouring_lip',me);s.collection.objects.link(o);done(o,o.name,glass);q=o.modifiers.new('Glass lip thickness','SOLIDIFY');q.thickness=.0009
 fill=50e-6/(math.pi*(ri-.00025)**2)
 cyl(n+'_50_mL_illustrative_solution',(x,y,z+.003+fill/2),ri-.00025,fill,liquids[i+1]);torus(n+'_meniscus',(x,y,z+.003+fill),ri-.0006,.00035,liquids[i+1])
 for ml in [25,50,75,100]:
  hh=z+.003+ml*1e-6/(math.pi*ri**2)
  cube(n+f'_{ml}mL_tick',(x+.009,y-r-.0004,hh),(.009,.0005,.00055),dark,0)
  txt(n+f'_{ml}_print',str(ml),(x+.005,y-r-.00075,hh-.0015),.0038,align='RIGHT')
 txt(n+'_capacity','125 mL',(x,y-r-.0008,z+.081),.0041)
 cube(n+'_position_badge',(x,y-.042,.019),(.058,.001,.027),paper,.0007)
 txt(n+'_number',f'{i+1:02d}',(x,y-.043,.022),.0073,m=blue)
 txt(n+'_ratio',f'1:{2**(i+1)}',(x,y-.043,.011),.0064)
 # Printed rack direction cues indicate ordered handling, not fluid tubes.
 if i<4:
  x2=x+.035
  line('Transfer sequence arrow shaft',(x2-.007,y-.038,.009),(x2+.008,y-.038,.009),.0005,blue)
  line('Arrowhead',(x2+.008,y-.038,.009),(x2+.004,y-.041,.009),.0005,blue);line('Arrowhead',(x2+.008,y-.038,.009),(x2+.004,y-.035,.009),.0005,blue)
# Durable procedure card flat on bench is plausible laboratory apparatus context.
cube('Procedure card',(.305,-.238,.0015),(.292,.083,.002),paper,.001)
txt('Card heading','SERIAL DILUTION',(.305,-.224,.0027),.011,rot=(0,0,0))
txt('Card instruction','50 mL sample  +  50 mL water',(.305,-.244,.0027),.007,rot=(0,0,0))
txt('Card repeat','MIX  /  TRANSFER 50 mL  /  REPEAT',(.305,-.261,.0027),.0064,rot=(0,0,0))
active='Stock_and_water'
# Deep-blue stock in conical open-neck glass flask.
x=.08;y=-.09
shell('Stock flask glass',x,y,.001,[(0,0),(.035,0),(.038,.005),(.038,.018),(.015,.092),(.013,.096),(.013,.126),(.0115,.126),(.0115,.096),(.0135,.092),(.036,.018),(.036,.003),(0,.003)],glass)
cone('Stock blue solution',(x,y,.027),.0355,.023,.046,liquids[0]);torus('Stock rolled neck',(x,y,.127),.0124,.0011,glass)
cube('Stock label',(x,y-.034,.058),(.046,.001,.025),paper,.001)
txt('Stock title','STOCK',(x,y-.035,.062),.007);txt('Stock reference','100%',(x,y-.035,.051),.0055)
# Separate clean-water reservoir with graduated blue screw cap.
x=.44;y=.105
shell('Water reservoir glass',x,y,.002,[(0,0),(.031,0),(.032,.005),(.032,.108),(.018,.13),(.018,.145),(.016,.145),(.016,.131),(.030,.108),(.030,.003),(0,.003)],glass)
cyl('Water in reservoir',(x,y,.042),.0295,.075,water);cyl('Reservoir blue cap',(x,y,.15),.0195,.012,blue)
for i in range(28):
 angle=i*math.tau/28;cube('Cap knurl',(x+.0195*math.cos(angle),y+.0195*math.sin(angle),.15),(.001,.001,.01),blue,.0003)
cube('Water label',(x,y-.032,.075),(.047,.001,.032),paper,.001);txt('Water label title','WATER',(x,y-.033,.081),.007);txt('Water label volume','250 mL',(x,y-.033,.067),.005)
# Tip rack and mix paddle, both in clean supporting roles.
cube('Clean transfer tips tray',(.515,-.083,.01),(.052,.09,.018),white,.004)
for xx in [.503,.524]:
 for yy in [-.112,-.084,-.056]:
  cyl('Tip rack socket',(xx,yy,.020),.006,.002,black);cone('Clean syringe tip',(xx,yy,.032),.002,.005,.025,glass)
active='Dosing_fixture'
# Vertical 50 mL syringe, guided holder. Pose is a staged readiness pose.
cube('Fixture steel foot',(.265,.088,.008),(.11,.075,.016),steel,.005)
cyl('Stand upright',(.265,.105,.157),.005,.298,steel)
line('Stand horizontal arm',(.265,.105,.213),(.24,-.105,.213),.004,steel)
cyl('Clamp boss',(.265,.105,.213),.011,.020,black)
for xx in [.238,.292]:cyl('Fixture foot screw',(xx,.088,.017),.004,.002,steel)
sx=.24;sy=-.105
shell('50mL syringe clear barrel',sx,sy,.120,[(.013,.0),(.013,.092),(.0115,.092),(.0115,.003)],glass)
cone('Syringe tapered outlet',(sx,sy,.113),.0015,.012,.014,white)
cyl('Syringe nozzle',(sx,sy,.099),.0016,.014,white)
cyl('Syringe piston seal',(sx,sy,.194),.0112,.004,black)
cyl('Syringe plunger rod',(sx,sy,.226),.004,.060,white)
cyl('Syringe thumb flange',(sx,sy,.258),.017,.004,blue)
cube('Syringe finger flange',(sx,sy,.212),(.043,.017,.004),white,.002)
for ml in range(10,60,10):
 hh=.122+ml*.00165;cube('Syringe graduation',(sx+.003,sy-.0133,hh),(.009,.0005,.0006),dark,0);txt('Syringe numeral',str(ml),(sx-.004,sy-.0138,hh-.001),.0035,align='RIGHT')
# Split clamp jaws leave the barrel visible.
for dx in [-.017,.017]:cube('Guide clamp jaw',(sx+dx,sy,.208),(.007,.035,.016),blue,.001)
line('Clamp crossbolt',(sx-.026,sy+.012,.208),(sx+.027,sy+.012,.208),.002,steel)
# Two-prong holding cradle for removable stirring rod.
line('Glass stirring rod',(.335,.045,.016),(.395,.045,.016),.002,glass)
for xx in [.345,.385]:cube('Stir rod support',(xx,.045,.008),(.008,.018,.012),white,.001)
active='Cameras'
def cam(n,loc,target,lens):
 d=bpy.data.cameras.new(n);d.lens=lens;d.clip_start=.01;d.clip_end=300;o=bpy.data.objects.new(n,d);s.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();done(o,n);return o
front=cam('Front',(.72,-1.10,.53),(.18,-.025,.105),49)
over=cam('Overhead',(.14,.035,1.25),(.14,.035,0),44);over.rotation_euler=(0,0,0)
result=cam('Result',(.54,-.83,.40),(.29,-.09,.095),66)
active='Lighting'
def light(n,loc,power,size,target):
 d=bpy.data.lights.new(n,'AREA');d.energy=power;d.shape='DISK';d.size=size;o=bpy.data.objects.new(n,d);s.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();done(o,n)
light('Large neutral softbox',(.0,-.55,1.30),90,1.1,(.23,0,0));light('Broad daylight fill',(.70,.25,.9),65,.9,(.25,0,.06));light('Glass rim light',(-.35,.45,.7),45,.7,(.2,0,.08))
s.camera=front
# Semantic assemblies preserve vessel transforms for later runtime ownership.
bpy.context.view_layer.update()
for i,x in enumerate(xs):
 assembly=bpy.data.objects.new(f'Vessel_{i+1:02d}',None);s.collection.objects.link(assembly);assembly.parent=G['Dilution_station'];assembly.location=(x,-.105,.009)
 bpy.context.view_layer.update()
 for ob in list(s.objects):
  if ob.name.startswith(f'Beaker_{i+1}_') and not any(k in ob.name for k in ['position_badge','number','ratio']):
   mw=ob.matrix_world.copy();ob.parent=assembly;ob.matrix_world=mw
# Convert font copies for reliable portable USD while retaining editable originals in .blend.
font_obs=[o for o in s.objects if o.type=='FONT'];copies=[]
for o in font_obs:
 c=o.copy();c.data=o.data.copy();s.collection.objects.link(c);copies.append(c);o.hide_render=True;o.hide_viewport=True
 bpy.ops.object.select_all(action='DESELECT');c.select_set(True);bpy.context.view_layer.objects.active=c;bpy.ops.object.convert(target='MESH')
for o in s.objects:o.select_set(o not in font_obs and o not in [G['Robot_ART_ONLY'],G['Preview_annotation']])
bpy.ops.wm.usd_export(filepath=str(out/'Environment.usdc'),selected_objects_only=True,visible_objects_only=False,export_materials=True,generate_preview_surface=True,export_textures=False,convert_world_material=False,root_prim_path='/ClassicLab')
for o in copies:bpy.data.objects.remove(o,do_unlink=True)
for o in font_obs:o.hide_render=False;o.hide_viewport=False
active='Robot_ART_ONLY'
if not robot.exists():raise FileNotFoundError('Pass --robot PATH to licensed static SO101 USD: '+str(robot))
before=set(s.objects);bpy.ops.wm.usd_import(filepath=str(robot),import_cameras=False,import_lights=False,create_world_material=False,import_materials=True,import_visible_only=True);new=set(s.objects)-before
root=bpy.data.objects.new('Original SO101 static art only',None);s.collection.objects.link(root);done(root,root.name);root.location=(-.05,0,-.03008145)
for o in new:
 if o.parent not in new:o.parent=root
active='Preview_annotation'
# Subtle camera-space provenance, no billboards or false runtime claim.
huds={}
for c in [front,over,result]:
 extent=.50*36/c.data.lens;size=extent*.0105
 o=txt(c.name+' provenance','ART PREVIEW  /  MODEL-PREDICTED COLOURS  /  STATIC ROBOT',(0,0,0),size,m=dark,rot=(0,0,0),align='LEFT');o.parent=c;o.location=(-extent*.475,-extent*.294,-.50);huds[c.name]=o
s.camera=front
for n,o in huds.items():o.hide_render=n!='Front'
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(out/'Scene.blend'),compress=True)
manifest={'experiment':'serial_dilution','scientific_status':'ILLUSTRATIVE / MODEL-PREDICTED, staged colored-water result. No fluid simulation or measured result.','units':'metres','up_axis':'Z','tabletop_z_m':0,'table_dimensions_m':[1,.75,.044],'table_center_m':[.12,0,-.022],'default_prim':'/ClassicLab','robot_in_environment':False,'physics_apis':False,'robot_preview':{'source':'../assets/Robot_STATIC_ART_ONLY.usdc','translation_m':[-.05,0,-.03008145],'added_yaw_degrees':0,'articulation':'not evaluated','camera_mounted':False},'runtime_base_reference_m':[-.05,0,0],'groups':list(G),'apparatus':{'beakers':{'quantity':5,'outer_radius_m':r,'inner_radius_m':ri,'height_m':h,'nominal_capacity_mL':125,'final_volume_mL':50,'centers_m':[[x,-.105,z] for x in xs],'final_relative_concentrations':[.5,.25,.125,.0625,.03125]},'stock_flask_center_m':[.08,-.09,.001],'water_reservoir_center_m':[.44,.105,.002],'guided_transfer_syringe':{'nominal_mL':50,'tip_m':[.24,-.105,.092],'plunger_top_m':[.24,-.105,.260]}},'active_locations_m':{'initial_source':[.08,-.09,.127],'targets':[[x,-.105,.101] for x in xs],'fixture_plunger':[.24,-.105,.260]},'reach_qualification':'Pending; outer vessels and tall plunger require fixture relocation or qualified controller. No verified robot reach, grasp or motion.','color_model':'Each equal-volume serial dilution halves concentration; material palette is perceptually exaggerated for illustration and is not calibrated absorbance.','result_staging':'Five completed steps shown with equal 50 mL remaining after transfer/discard. Syringe is a static ready pose.','cameras':{}}
manifest['runtime_handoff']={'student_variable':'transfer volume at fixed 50 mL preloaded water', 'conditions':[{'name':'A shown','transfer_mL':50,'water_mL':50,'concentrations':[.5,.25,.125,.0625,.03125]},{'name':'B comparison','transfer_mL':25,'water_mL':50,'concentrations':[1/3,1/9,1/27,1/81,1/243]}],'observable':'relative concentration by dilution count; visible blue is qualitative and uncalibrated','static_prim_paths':['/ClassicLab/Bench','/ClassicLab/Dilution_station/Ordered_five_position_rack_base','/ClassicLab/Dosing_fixture/Fixture_steel_foot','/ClassicLab/Dosing_fixture/Stand_upright'],'movable_vessels':[{'prim_path':f'/ClassicLab/Dilution_station/Vessel_{i+1:02d}','origin_m':[x,-.105,.009],'rotation_xyz_radians':[0,0,0],'grasp_band_world_z_m':[.064,.084],'grasp_outer_diameter_m':.0456,'adjacent_wall_gap_m':.0244,'grasp_qualified':False} for i,x in enumerate(xs)],'dosing_barrel_prim':'/ClassicLab/Dosing_fixture/_50mL_syringe_clear_barrel','plunger_prim':'/ClassicLab/Dosing_fixture/Syringe_plunger_rod','source_prim':'/ClassicLab/Stock_and_water/Stock_flask_glass','source_opening_world_m':[.08,-.09,.127],'source_neck_inner_diameter_m':.023,'target_openings_world_m':[[x,-.105,.101] for x in xs],'target_inner_diameter_m':.0432,'dependencies':{'environment_usd':[],'preview_blend':[],'regeneration_robot':'../assets/Robot_STATIC_ART_ONLY.usdc'},'missing':['articulated robot','collision and mass','dosing fixture constraint','reach and collision qualification','dosing/mixing science state model','controller','calibrated optical model','measured success'],'outcome_meshes':'illustrative visual geometry only, excluded from evidence of runtime success'}
for c in [front,over,result]:manifest['cameras'][c.name]={'position_m':list(c.location),'rotation_xyz_radians':list(c.rotation_euler),'lens_mm':c.data.lens,'world_matrix_row_major':[list(row) for row in c.matrix_world],'resolution_px':[1600,1000]}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
if a.render:
 for c in [front,over,result]:
  for n,o in huds.items():o.hide_render=n!=c.name
  s.camera=c;s.render.filepath=str(out/(c.name+'.png'));bpy.ops.render.render(write_still=True)
print('SERIAL_DILUTION_COMPLETE',flush=True)
