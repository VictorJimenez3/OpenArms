"""Set portable transparency and opt-in guide proxies. Never authors physics."""
import sys
from pathlib import Path
from pxr import Usd,UsdGeom,UsdShade,Sdf,Gf
for path in Path(sys.argv[1]).glob('0*/*.usdc'):
 stage=Usd.Stage.Open(str(path))
 if path.name=='ColliderProxies.usdc':
  # Blender may omit render-hidden mesh data even with visible_objects_only=False.
  # Author the exact 1.00 x .75 x .044 m table box on the existing translated prim.
  mesh=UsdGeom.Mesh.Define(stage,'/TrainingScene/ColliderProxies/Table_proxy')
  mesh.CreatePointsAttr([(-.5,-.375,-.022),(.5,-.375,-.022),(.5,.375,-.022),(-.5,.375,-.022),(-.5,-.375,.022),(.5,-.375,.022),(.5,.375,.022),(-.5,.375,.022)])
  mesh.CreateFaceVertexCountsAttr([4]*6)
  mesh.CreateFaceVertexIndicesAttr([0,3,2,1,4,5,6,7,0,1,5,4,1,2,6,5,2,3,7,6,3,0,4,7])
  mesh.CreateSubdivisionSchemeAttr('none')
  mesh.CreateExtentAttr([(-.5,-.375,-.022),(.5,.375,.022)])
  mesh.CreateVisibilityAttr('invisible')
 for prim in stage.Traverse():
  if prim.GetTypeName()=='Shader':
   sh=UsdShade.Shader(prim); name=str(prim.GetPath()).lower()
   if sh.GetIdAttr().Get()=='UsdPreviewSurface' and ('clear_receiver' in name or 'water_representation' in name):
    sh.CreateInput('opacity',Sdf.ValueTypeNames.Float).Set(.18 if 'clear_receiver' in name else .38)
    sh.CreateInput('ior',Sdf.ValueTypeNames.Float).Set(1.333)
  if 'ColliderProxies' in str(prim.GetPath()) and prim.IsA(UsdGeom.Imageable):UsdGeom.Imageable(prim).CreatePurposeAttr().Set('guide')
 stage.GetRootLayer().Save()
