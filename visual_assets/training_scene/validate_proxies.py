"""Validate opt-in table proxies separately from render materials/cameras."""
import sys,json
from pathlib import Path
from pxr import Usd,UsdGeom
root=Path(sys.argv[1]).resolve();reports=[]
for path in sorted(root.glob('0*/ColliderProxies.usdc')):
 stage=Usd.Stage.Open(str(path));meshes=[p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
 assert len(meshes)==1, str(path)+': expected one complete table mesh'
 assert UsdGeom.Imageable(meshes[0]).ComputePurpose()=='guide'
 assert all(not any('physics' in str(x).lower() or 'physx' in str(x).lower() for x in p.GetAppliedSchemas()) for p in stage.Traverse())
 bound=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['guide'],False,True).ComputeWorldBound(meshes[0]).ComputeAlignedRange()
 assert abs(bound.GetMax()[2])<1e-7 and abs(bound.GetSize()[0]-1)<1e-7 and abs(bound.GetSize()[1]-.75)<1e-7
 mesh=UsdGeom.Mesh(meshes[0]);assert UsdGeom.Mesh.ValidateTopology(mesh.GetFaceVertexIndicesAttr().Get(),mesh.GetFaceVertexCountsAttr().Get(),len(mesh.GetPointsAttr().Get()))[0]
 reports.append({'file':str(path.relative_to(root)),'mesh_count':1,'guide_only':True,'physics_attached':False,'bounds_min':list(bound.GetMin()),'bounds_max':list(bound.GetMax()),'ok':True})
assert len(reports)==6
(root/'proxy_validation.json').write_text(json.dumps(reports,indent=2));print('Six complete table proxies passed')
