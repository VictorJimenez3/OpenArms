"""Validate exported USD and enrich manifest with inspected prim paths.
Requires pxr; reads PNG IHDR directly and never claims visual QA.
"""
from pathlib import Path
import json, struct
from pxr import Usd, UsdGeom, Sdf
root=Path(__file__).resolve().parent
s=Usd.Stage.Open(str(root/'Environment.usdc'))
prims=list(s.Traverse())
paths=[str(p.GetPath()) for p in prims]
physics=[str(p.GetPath()) for p in prims if 'Physics' in p.GetTypeName() or any('Physics' in str(v) or 'Physx' in str(v) for v in p.GetAppliedSchemas())]
robot=[x for x in paths if any(n in x.lower() for n in ['so101','so_101','robot_art_only','robot_static'])]
# Empty preview-only group names do not contain robot geometry, but remove them too.
for path in robot:
 p=s.GetPrimAtPath(path)
 if not list(p.GetChildren()) and not p.IsA(UsdGeom.Gprim):s.RemovePrim(path)
s.GetRootLayer().Save(); prims=list(s.Traverse()); paths=[str(p.GetPath()) for p in prims]
robot=[x for x in paths if any(n in x.lower() for n in ['so101','so_101','robot_art_only','robot_static'])]
deps=[]
for layer in s.GetUsedLayers():
 if layer.identifier!=s.GetRootLayer().identifier and not layer.anonymous:deps.append(layer.identifier)
assets=[]
for p in prims:
 for at in p.GetAttributes():
  v=at.Get()
  if isinstance(v,Sdf.AssetPath) and v.path:assets.append(v.path)
manifest=json.loads((root/'manifest.json').read_text())
manifest['actual_exported_prim_paths']=paths
for rec in manifest['apparatus']:
 rec['actual_exported_prim_paths']=[str(p.GetPath()) for p in prims if p.GetName()==rec['object']]
manifest['actual_prim_path_inspection']='Read directly from Environment.usdc using pxr.Usd; no inferred paths.'
(root/'manifest.json').write_text(json.dumps(manifest,indent=2))
renders={}
for n in ['Front.png','Overhead.png','Result.png']:
 f=root/n
 if f.exists():
  data=f.read_bytes(); dims=struct.unpack('>II',data[16:24]); renders[n]={'exists':True,'size_px':dims}
 else:renders[n]={'exists':False}
v={'usd_default_prim':str(s.GetDefaultPrim().GetPath()),'usd_meters_per_unit':UsdGeom.GetStageMetersPerUnit(s),'usd_up_axis':str(UsdGeom.GetStageUpAxis(s)),'external_layer_dependencies':deps,'asset_paths':assets,'robot_prims':robot,'physics_prims':physics,'prim_count':len(prims),'render_outputs':renders,'output_existence':{n:(root/n).exists() for n in ['build.py','Scene.blend','Environment.usdc','manifest.json','EXPERIMENT.md']},'visual_review':'PENDING: parent will inspect actual renders','all_usd_checks_pass':str(s.GetDefaultPrim().GetPath())=='/ClassicLab' and UsdGeom.GetStageMetersPerUnit(s)==1 and str(UsdGeom.GetStageUpAxis(s))=='Z' and not deps and not assets and not robot and not physics}
(root/'validation.json').write_text(json.dumps(v,indent=2)); print(json.dumps(v,indent=2))
