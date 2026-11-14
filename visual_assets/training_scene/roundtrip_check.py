"""Blender import checks on six portable USDs, not Isaac runtime verification."""
import bpy,sys,json
from pathlib import Path
out=Path(sys.argv[sys.argv.index('--')+1]).resolve();results=[]
for path in sorted(out.glob('0*/Experiment.usdc')):
 bpy.ops.wm.read_factory_settings(use_empty=True)
 bpy.ops.wm.usd_import(filepath=str(path),import_cameras=True,import_lights=True,import_materials=True,create_world_material=False)
 s=bpy.context.scene; meshes=[o for o in s.objects if o.type=='MESH'];cameras=[o for o in s.objects if o.type=='CAMERA']; materials=[m for m in bpy.data.materials if m.users]
 r={'file':str(path.relative_to(out)),'meshes':len(meshes),'cameras':[c.name for c in cameras],'materials':len(materials),'ok':len(meshes)>5 and len(cameras)==2,'scope':'Blender USD import only'};results.append(r)
(out/'blender_roundtrip_validation.json').write_text(json.dumps(results,indent=2));assert all(r['ok'] for r in results) and len(results)==6
print('SIX_USD_IMPORTS_PASSED')
