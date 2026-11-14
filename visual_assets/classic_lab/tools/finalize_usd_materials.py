"""Author explicit, portable PreviewSurface opacity approximations after Blender export.
Usage: python tools/finalize_usd_materials.py /absolute/classic_lab
This does not alter Blender optics, geometry, physics, or scientific state.
"""
from pathlib import Path
import sys,json
from pxr import Usd,UsdShade,Sdf
root=Path(sys.argv[1]).resolve()
overrides={
 '01_serial_dilution':{'Clear_borosilicate':.18,'Clear_water':.08},
 '02_titration':{'Borosilicate_clear_glass':.16,'Reagent_bottle_amber_glass':.65,'Clear_liquid':.06,'Illustrative_faint_pink_endpoint':.55},
 '03_colorimetry':{'Clear_cuvette_walls':.16,'Magenta_reference_0_relative_units':.04},
 '05_filtration':{'Illustrative_clear_glass_opacity_0_13':.13,'Glass_rim_edge':.35,'Much_clearer_filtrate_illustrative':.05},
}
results=[]
for folder,values in overrides.items():
 p=root/folder/'Environment.usdc'
 if not p.exists(): continue
 stage=Usd.Stage.Open(str(p)); matches={}
 for prim in stage.Traverse():
  if not prim.IsA(UsdShade.Material) or prim.GetName() not in values: continue
  material=UsdShade.Material(prim); shader,_src,_typ=material.GetSurfaceOutput().GetConnectedSource()
  shader=UsdShade.Shader(shader.GetPrim())
  assert shader.GetIdAttr().Get()=='UsdPreviewSurface',prim.GetPath()
  value=values[prim.GetName()];shader.CreateInput('opacity',Sdf.ValueTypeNames.Float).Set(value)
  matches[prim.GetName()]=value
 assert set(matches)==set(values),(folder,'Missing materials',set(values)-set(matches))
 stage.GetRootLayer().Save()
 results.append({'scene':folder,'opacity_overrides':matches,'scope':'Illustrative opacity fallback; not physical transmission or verified Isaac appearance'})
(root/'usd_opacity_fallbacks.json').write_text(json.dumps(results,indent=2)+'\n')
print('Authored opacity fallbacks for',len(results),'environments')
