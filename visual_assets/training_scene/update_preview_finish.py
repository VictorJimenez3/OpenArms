"""Update static robot's printed parts and save default fixed-camera visibility."""
import bpy,sys
from pathlib import Path
out=Path(sys.argv[sys.argv.index('--')+1]).resolve()
for p in sorted(out.glob('0*/ART_PREVIEW.blend')):
 bpy.ops.wm.open_mainfile(filepath=str(p));sc=bpy.context.scene
 for m in bpy.data.materials:
  if '3d_printed' in m.name.lower() and m.use_nodes:
   b=m.node_tree.nodes.get('Principled BSDF')
   if b:b.inputs['Base Color'].default_value=(.65,.67,.69,1)
 front=bpy.data.objects['Camera_Front'];overhead=bpy.data.objects['Camera_Overhead'];sc.camera=front
 for c in (front,overhead):
  for child in c.children:child.hide_render=c!=front
 sc.cycles.samples=48;bpy.ops.wm.save_as_mainfile(filepath=str(p),compress=True)
 for c,n in [(front,'Front_ART_PREVIEW.png'),(overhead,'Overhead_ART_PREVIEW.png')]:
  for cc in (front,overhead):
   for child in cc.children:child.hide_render=cc!=c
  sc.camera=c;sc.render.filepath=str(p.parent/n);bpy.ops.render.render(write_still=True)
 print('WHITE_PREVIEW_COMPLETE',p.parent.name,flush=True)
