"""Import saved environment USDs in fresh Blender sessions; not an Isaac test."""
import bpy,sys,json
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
results=[]
for path in sorted(root.glob('0*/Environment.usdc')):
 bpy.ops.wm.read_factory_settings(use_empty=True)
 bpy.ops.wm.usd_import(filepath=str(path),import_cameras=True,import_lights=True,import_materials=True,create_world_material=False)
 meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
 cams=[o for o in bpy.context.scene.objects if o.type=='CAMERA']
 r={'file':str(path.relative_to(root)),'meshes':len(meshes),'cameras':[o.name for o in cams],'ok':len(meshes)>10 and len(cams)>=2,'scope':'Blender USD roundtrip import; no Isaac execution'}
 results.append(r)
(root/'blender_import_validation.json').write_text(json.dumps(results,indent=2)+'\n')
assert len(results)==6 and all(r['ok'] for r in results),results
print('All six Blender USD imports passed.')
