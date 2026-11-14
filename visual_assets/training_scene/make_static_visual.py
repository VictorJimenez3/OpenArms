"""Bake original USD mesh transforms to a STATIC visual snapshot; never physics."""
import sys
from pxr import Usd,UsdGeom,UsdShade,Sdf,Gf,Vt
src=Usd.Stage.Open(sys.argv[1]); dst=Usd.Stage.CreateNew(sys.argv[2]); root=UsdGeom.Xform.Define(dst,'/Robot_ART_ONLY'); dst.SetDefaultPrim(root.GetPrim()); UsdGeom.SetStageMetersPerUnit(dst,1); UsdGeom.SetStageUpAxis(dst,'Z')
count=0
for p in Usd.PrimRange.Stage(src,Usd.TraverseInstanceProxies()):
 if not p.IsA(UsdGeom.Mesh): continue
 im=UsdGeom.Imageable(p)
 if im.ComputeVisibility()=='invisible' or im.ComputePurpose() in ('proxy','guide'): continue
 source=UsdGeom.Mesh(p); path='/Robot_ART_ONLY/Mesh_%03d'%count; count+=1; mesh=UsdGeom.Mesh.Define(dst,path)
 xf=UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
 mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(xf.Transform(Gf.Vec3d(v))) for v in source.GetPointsAttr().Get()]))
 mesh.CreateFaceVertexCountsAttr(source.GetFaceVertexCountsAttr().Get()); mesh.CreateFaceVertexIndicesAttr(source.GetFaceVertexIndicesAttr().Get()); mesh.CreateSubdivisionSchemeAttr('none')
 mesh.CreateOrientationAttr(source.GetOrientationAttr().Get()); mesh.GetPrim().SetCustomDataByKey('upstreamPath',str(p.GetPath()))
 normal=source.GetNormalsAttr().Get()
 if normal is not None:
  normxf=xf.GetInverse().GetTranspose(); mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(normxf.TransformDir(Gf.Vec3d(v)).GetNormalized()) for v in normal])); mesh.SetNormalsInterpolation(source.GetNormalsInterpolation())
 bound,_=UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial(); name=bound.GetPrim().GetName() if bound else 'default'
 material=UsdShade.Material.Define(dst,'/Robot_ART_ONLY/Looks/'+name); shader=UsdShade.Shader.Define(dst,material.GetPath().AppendChild('Surface')); shader.CreateIdAttr('UsdPreviewSurface'); n=name.lower()
 col=(.65,.67,.69) if '3d_printed' in n else ((.3,.34,.37) if 'silver' in n else (.025,.033,.038))
 shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(col); shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.3); shader.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(.65 if 'silver' in n or 'aluminum' in n else .05); material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface'); UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
dst.GetRootLayer().Save(); print('baked',count,'original meshes')
