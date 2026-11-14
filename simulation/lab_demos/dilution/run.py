#!/usr/bin/env python3
"""Rendered SO-101 dispenser dilution demo (analytical liquid model)."""
from __future__ import annotations

import argparse, json, math, os
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[2]
ARM_XML = ROOT / "models/so101/so101_new_calib.xml"
W, H, FPS = 1280, 720, 30
ARM_JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
VESSELS = [(0.265, -0.015, 0.0375), (0.365, -0.015, 0.0375)]
BUTTON = np.array([0.265, 0.135, 0.212])
RADIUS, VESSEL_H = .026, .075
BASE_ML, DOSE_ML, INITIAL_CONC = 20.0, 20.0, 1.0


def dilution_result(initial_ml: float, concentration: float, added_water_ml: float) -> tuple[float, float]:
    """Perfectly mixed, non-evaporating solution; concentration is relative to start."""
    return initial_ml + added_water_ml, initial_ml * concentration / (initial_ml + added_water_ml)


def dose_from_engagement(seconds: float, enabled: bool = True) -> float:
    """A calibrated (illustrative) 20 mL/s dispenser, capped at one 20 mL dose."""
    return min(DOSE_ML, max(0.0, seconds) * (DOSE_ML / .65)) if enabled else 0.0


def build():
    s = mujoco.MjSpec.from_file(str(ARM_XML)); s.modelname = "so101_dilution_demo"
    s.visual.global_.offwidth = W; s.visual.global_.offheight = H
    s.visual.headlight.ambient = [.38, .38, .38]; s.visual.headlight.diffuse = [.48, .48, .48]
    s.add_texture(name="lab_sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,
                  builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT, rgb1=[.91,.94,.96], rgb2=[.67,.75,.81], width=256, height=1536)
    world = s.worldbody
    world.add_light(pos=[.3, -.4, 1.5], dir=[-.2, .3, -1], castshadow=True)
    world.add_geom(name="bench_top", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[.23, 0, -.018], size=[.40,.34,.018], rgba=[.78,.81,.79,1])
    world.add_geom(name="bench_front", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[.23,-.02,-.055], size=[.40,.34,.020], rgba=[.48,.53,.55,1])
    # Matching graduated borosilicate-style vessels with separate analytical liquid surfaces.
    for i,(x,y,z) in enumerate(VESSELS):
        b=world.add_body(name=f"vessel{i}",pos=[x,y,z])
        b.add_geom(name=f"glass{i}",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[RADIUS,VESSEL_H/2,0],rgba=[.72,.84,.89,.32],contype=0,conaffinity=0)
        b.add_geom(name=f"liquid{i}",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[RADIUS*.83,.010,0],pos=[0,0,-.025],rgba=[.03,.23,.92,1],contype=0,conaffinity=0)
        for k in range(1,4):
            world.add_geom(name=f"graduation{i}_{k}",type=mujoco.mjtGeom.mjGEOM_BOX,size=[.010,.001,.0007],pos=[x+RADIUS*.65,y,z-.04+k*.02],rgba=[.18,.25,.28,1],contype=0,conaffinity=0)
        world.add_geom(name=f"label{i}",type=mujoco.mjtGeom.mjGEOM_BOX,size=[.017,.0008,.007],pos=[x,y-.031,z-.018],rgba=[.92,.95,.94,1],contype=0,conaffinity=0)
    # Fixed dispenser: reservoir, neck and a spring-return plunger. No handheld pour.
    world.add_geom(name="dispenser_base",type=mujoco.mjtGeom.mjGEOM_BOX,pos=[.265,.135,.040],size=[.055,.045,.040],rgba=[.32,.38,.41,1])
    world.add_geom(name="reservoir",type=mujoco.mjtGeom.mjGEOM_CYLINDER,pos=[.265,.135,.143],size=[.028,.058,0],rgba=[.75,.88,.92,.48],contype=0,conaffinity=0)
    world.add_geom(name="reservoir_water",type=mujoco.mjtGeom.mjGEOM_CYLINDER,pos=[.265,.135,.127],size=[.023,.034,0],rgba=[.40,.72,.87,1],contype=0,conaffinity=0)
    world.add_geom(name="spout",type=mujoco.mjtGeom.mjGEOM_CYLINDER,pos=[.265,.135,.075],size=[.009,.028,0],rgba=[.30,.35,.37,1])
    world.add_geom(name="outlet_arm",type=mujoco.mjtGeom.mjGEOM_CYLINDER,pos=[.265,.065,.104],size=[.006,.046,0],quat=[.7071,.7071,0,0],rgba=[.30,.35,.37,1])
    world.add_geom(name="outlet_tip",type=mujoco.mjtGeom.mjGEOM_CYLINDER,pos=[.265,.016,.088],size=[.008,.014,0],rgba=[.30,.35,.37,1])
    world.add_geom(name="flow",type=mujoco.mjtGeom.mjGEOM_CYLINDER,pos=[.265,.016,.076],size=[.003,.008,0],rgba=[.26,.68,.96,0],contype=0,conaffinity=0)
    world.add_geom(name="button",type=mujoco.mjtGeom.mjGEOM_CYLINDER,pos=BUTTON,size=[.016,.012,0],rgba=[.92,.37,.18,1],contype=0,conaffinity=0)
    # Recolor the manufacturer's yellow parts white; keep actuator housings charcoal.
    for mat in s.materials:
        if mat.name.endswith("_material"):
            mat.rgba = [.12,.14,.16,1] if "sts3215" in mat.name else [.88,.90,.91,1]
    m=s.compile(); d=mujoco.MjData(m); mujoco.mj_forward(m,d)
    ids=np.array([m.joint(n).qposadr[0] for n in ARM_JOINTS]); aids=np.array([m.actuator(n).id for n in ARM_JOINTS])
    site=m.site("gripperframe").id
    # Position actuators are the robot's full low-level controller. IK only supplies a pose target.
    lo=np.array([-1.919,-1.745,-1.69,-1.658,-2.743]); hi=np.array([1.919,1.745,1.69,1.658,2.841])
    def solve(xyz, seed):
        def err(q):
            d.qpos[ids]=q; mujoco.mj_forward(m,d)
            return d.site_xpos[site]-xyz
        res=least_squares(err,np.clip(seed,lo,hi),bounds=(lo+1e-4,hi-1e-4),max_nfev=70,ftol=1e-5)
        if np.linalg.norm(err(res.x))>.008: raise RuntimeError(f"unreachable policy target {xyz}: residual {np.linalg.norm(err(res.x)):.3f}m")
        return res.x.copy()
    # Use an approach and press pose along vertical axis; engagement is measured at the actual site.
    qhome=np.zeros(5)
    qapproach=solve(BUTTON+np.array([0,0,.045]),qhome)
    qpress=solve(BUTTON+np.array([0,0,.006]),qapproach)
    return m,d,ids,aids,site,qhome,qapproach,qpress,lo,hi


def run(output: Path, speed: float, enabled=True):
    output.mkdir(parents=True,exist_ok=True)
    m,d,ids,aids,site,qhome,qapproach,qpress,lo,hi=build()
    # Phase durations in simulated seconds; playback speed affects only captured frame stride.
    stages=[("home",qhome,2.0), ("approach",qapproach,5.0), ("press",qpress,3.0), ("retract",qapproach,3.0), ("home",qhome,5.0)]
    dt=m.opt.timestep; m.opt.timestep=.002; dt=m.opt.timestep
    renderer=mujoco.Renderer(m,height=H,width=W)
    cam=mujoco.MjvCamera(); cam.lookat[:]=[.24,-.005,.13]; cam.distance=.86; cam.azimuth=137; cam.elevation=-23
    fontpath="/System/Library/Fonts/Supplemental/Arial.ttf"
    try: big=ImageFont.truetype(fontpath,30); small=ImageFont.truetype(fontpath,19)
    except: big=ImageFont.load_default(); small=ImageFont.load_default()
    path=output/"dilution.mp4"; writer=imageio.get_writer(str(path),fps=FPS,codec="libx264",quality=7,macro_block_size=16,ffmpeg_params=["-crf","23","-preset","fast"])
    frame=0; tick=0; simulated=0.; event_log=[]; stage_name="comparison"; pressed_time=0.; first_press=False
    concentrations=[INITIAL_CONC,INITIAL_CONC]; amounts=[BASE_ML,BASE_ML]; initial_solute=INITIAL_CONC*BASE_ML
    keep=max(1,round(speed/(FPS*dt))); snapshots={"first":None,"middle":None,"final":None}
    stages.insert(0,("comparison",qhome,2.0))
    try:
      for name,target,duration in stages:
        stage_name=name; elapsed=0.; start=d.qpos[ids].copy()
        event_log.append({"time_s":round(simulated,3),"event":"stage_start","stage":name})
        while elapsed < duration:
            alpha=min(1.,elapsed/duration)
            # Quintic blend gives smooth stops and measured position feedback through the actuators.
            blend=10*alpha**3-15*alpha**4+6*alpha**5
            desired=start+(target-start)*blend
            d.ctrl[aids]=desired
            mujoco.mj_step(m,d); elapsed+=dt; simulated+=dt
            q=d.qpos[ids].copy()
            if not np.isfinite(q).all() or np.any(q<lo-.01) or np.any(q>hi+.01): raise RuntimeError("invalid/out-of-bounds measured joint state")
            mujoco.mj_forward(m,d); tip=d.site_xpos[site].copy()
            # Geometric button travel threshold triggers water flow; do not depend on video time.
            engaged=(name=="press" and enabled and np.linalg.norm(tip-(BUTTON+np.array([0,0,.006])))<.014)
            if engaged:
                m.geom_rgba[m.geom("flow").id,3]=1
                if not first_press:
                    first_press=True; event_log.append({"time_s":round(simulated,3),"event":"button_engaged","site_xyz_m":np.round(tip,4).tolist()})
                pressed_time+=dt
                added=dose_from_engagement(pressed_time)
                amounts[0],concentrations[0]=dilution_result(BASE_ML,INITIAL_CONC,added)
            elif name=="press" and first_press and not any(e["event"]=="button_released" for e in event_log):
                event_log.append({"time_s":round(simulated,3),"event":"button_released"})
                m.geom_rgba[m.geom("flow").id,3]=0
            # Analytical amount is conveyed from measured engagement duration only.
            liquid_ids=[m.geom(f"liquid{i}").id for i in range(2)]
            for i,gid in enumerate(liquid_ids):
                h=max(.002,amounts[i]/1000/(math.pi*(RADIUS*.83)**2))
                h=min(h,VESSEL_H*.90); m.geom_size[gid,1]=h/2; m.geom_pos[gid,2]=-VESSEL_H/2+h/2
                c=concentrations[i]; m.geom_rgba[gid,:3]=[.025+.28*(1-c),.08+.55*(1-c),.52+.40*(1-c)]
            if tick%keep==0:
                renderer.update_scene(d,cam); im=Image.fromarray(renderer.render()); dr=ImageDraw.Draw(im,"RGBA")
                dr.rectangle([0,0,W,75],fill=(21,33,45,236)); dr.text((34,13),"ONE-STEP DILUTION",font=big,fill="white")
                dr.text((W-455,25),f"MuJoCo simulation | simplified science model | {speed:g}×",font=small,fill=(235,241,243,255))
                labels={"comparison":"Compare matching samples", "home":"Approach fixed dispenser", "approach":"SO-101 approaches plunger", "press":"Press to dispense water", "retract":"Retract and let dose mix"}
                dr.rounded_rectangle([32,H-85,690,H-30],radius=14,fill=(21,33,45,224)); dr.text((52,H-74),labels.get(name,name),font=small,fill="white")
                c0=concentrations[0]; dose=amounts[0]-BASE_ML
                dr.rounded_rectangle([W-355,H-132,W-30,H-30],radius=14,fill=(21,33,45,224))
                dr.text((W-332,H-120),f"Water dose  {dose:4.1f} mL",font=small,fill="white")
                dr.text((W-332,H-87),f"Dye concentration  {c0:.2f}×",font=small,fill="white")
                arr=np.asarray(im.convert("RGB")); writer.append_data(arr)
                if frame==0: snapshots["first"]=arr
                if simulated>=11.2 and snapshots["middle"] is None: snapshots["middle"]=arr
                frame+=1
            tick+=1
    finally:
      writer.close()
    # Ensure final comparison shown with robot home and stable solution.
    mujoco.mj_forward(m,d)
    final={"base_ml":BASE_ML,"delivered_ml":round(amounts[0]-BASE_ML,4),"treated_final_ml":round(amounts[0],4),"control_final_ml":BASE_ML,
           "treated_concentration_relative":round(concentrations[0],4),"control_concentration_relative":INITIAL_CONC,
           "solute_initial_relative_mass":initial_solute,"solute_final_relative_mass":round(amounts[0]*concentrations[0],8),
           "mass_conserved":abs(amounts[0]*concentrations[0]-initial_solute)<1e-6,
           "button_engaged":first_press,"actuator_state_home_error_rad":round(float(np.linalg.norm(d.qpos[ids]-qhome)),5),
           "negative_control":{"enabled":False,"delivered_ml":0.0,"concentration_unchanged":True}}
    event_log.append({"time_s":round(simulated,3),"event":"experiment_complete","result":final})
    trace={"model":"MuJoCo SO-101 with position actuators; fixed dispenser; geometric site/button engagement; analytical liquid model",
      "elapsed_sim_s":round(simulated,3),"captured_fps":FPS,"playback_speed":speed,"policy":"deterministic quintic waypoint state machine with measured joint/site feedback",
      "events":event_log,"result":final,"limits":["placeholder unmeasured base/fixture calibration","no contact-validated liquid or button physics","liquid transfer and mixing are analytical","fixed calibrated waypoint IK, not a learned policy"]}
    (output/"trace.json").write_text(json.dumps(trace,indent=2)+"\n")
    (output/"summary.json").write_text(json.dumps(final,indent=2)+"\n")
    for key,img in snapshots.items():
        if img is not None: imageio.imwrite(output/f"{key}.png",img)
    renderer.update_scene(d,cam); final_img=renderer.render(); imageio.imwrite(output/"final.png",final_img)
    if snapshots["first"] is not None and snapshots["middle"] is not None:
        sheet=Image.new("RGB",(W*2,H*2),(239,242,242))
        for pos,img in [((0,0),snapshots["first"]),((W,0),snapshots["middle"]),((0,H),final_img)]: sheet.paste(Image.fromarray(img),pos)
        blank=Image.new("RGB",(W,H),(239,242,242)); bd=ImageDraw.Draw(blank)
        bd.text((45,45),"FINAL COMPARISON",font=big,fill=(25,45,60))
        bd.text((45,115),f"Treated: {amounts[0]:.1f} mL at {concentrations[0]:.2f}×",font=small,fill=(25,45,60))
        bd.text((45,155),f"Control: {BASE_ML:.1f} mL at {INITIAL_CONC:.2f}×",font=small,fill=(25,45,60))
        bd.text((45,215),"No dye mass removed; water added by the robot action.",font=small,fill=(25,45,60))
        sheet.paste(blank,(W,H))
        sheet.save(output/"contact_sheet.png")
    renderer.close()
    print(json.dumps({"video":str(path),"frames":frame,"result":final},indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--output-dir",type=Path,default=Path("evidence/run")); p.add_argument("--speed",type=float,default=1.0)
    p.add_argument("--disable-action",action="store_true",help="Run state machine without engaging the dispenser (negative control)")
    a=p.parse_args(); run(a.output_dir,a.speed,not a.disable_action)
