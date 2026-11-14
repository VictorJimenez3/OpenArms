#!/usr/bin/env python3
"""Actuated SO-101 titration demo with an analytical, explicitly simplified chemistry model."""
from __future__ import annotations
import argparse, json, math, os
from pathlib import Path
import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
XML = ROOT / "models/so101/so101_new_calib.xml"
POSES = ROOT / "config/setups/block/poses.json"
FPS = 30
TRIALS = [dict(id="small", pose="GRASP_A", above="ABOVE_A", acid_eq=0.50, sample_ml=5.0, target_drops=6),
          dict(id="large", pose="GRASP_C", above="ABOVE_C", acid_eq=0.80, sample_ml=8.0, target_drops=9)]
DROP_EQ = 0.10
DROP_ML = 0.12


def font(size):
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    return ImageFont.load_default()


def pose_rad(p): return np.deg2rad([p[k] for k in ("shoulder_pan","shoulder_lift","elbow_flex","wrist_flex","wrist_roll")])


def build():
    spec=mujoco.MjSpec.from_file(str(XML)); spec.modelname="titration_so101"
    spec.visual.global_.offwidth=1280; spec.visual.global_.offheight=720
    spec.visual.headlight.ambient=[.32,.32,.32]; spec.visual.headlight.diffuse=[.42,.42,.42]; spec.visual.headlight.specular=[.10,.10,.10]
    w=spec.worldbody
    spec.add_texture(name="lab_sky",type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,rgb1=[.78,.84,.88],rgb2=[.38,.48,.55],width=256,height=1536)
    w.add_light(name="key_light",pos=[.15,-.25,1.2],dir=[0,0,-1],diffuse=[.55,.55,.55],specular=[.12,.12,.12],castshadow=False)
    # Lab bench and trays are fixed primitives; their positions match reachable teaching poses.
    w.add_geom(name="bench", type=mujoco.mjtGeom.mjGEOM_BOX, size=[.29,.31,.018], pos=[.20,-.025,-.020], rgba=[.91,.93,.94,1])
    # small black/white rack under apparatus
    w.add_geom(name="tray", type=mujoco.mjtGeom.mjGEOM_BOX, size=[.175,.245,.006], pos=[.332,-.026,.004], rgba=[.83,.87,.88,1])
    w.add_geom(name="robot_stand",type=mujoco.mjtGeom.mjGEOM_BOX,size=[.036,.036,.027],pos=[0,0,.025],rgba=[.29,.34,.37,1])
    spec.body("base").pos[2]=.055
    trial_sites={}
    for i,t in enumerate(TRIALS):
        # get press points from model transforms so robot goals and fixture are coherent
        pass
    m=spec.compile(); d=mujoco.MjData(m)
    poses=json.loads(POSES.read_text())["poses"]
    for t in TRIALS:
        for j,v in zip(("shoulder_pan","shoulder_lift","elbow_flex","wrist_flex","wrist_roll"),pose_rad(poses[t['pose']])): d.qpos[m.joint(j).qposadr[0]]=v
        mujoco.mj_forward(m,d); xyz=d.site_xpos[m.site("gripperframe").id].copy()
        trial_sites[t["id"]]=xyz
    # Add physically fixed wells, translucent clear cups, colored modeled liquid, pump blocks and visible drops.
    # Each fixture includes a button face geometrically centered at the gripperframe endpoint.
    for t in TRIALS:
        xyz=trial_sites[t['id']]
        x,y,z=xyz
        # small clear sample dish sits forward from paddle; metered nozzle is above well
        dish=np.array([x+0.038,y-0.048,0.018])
        t["dish"]=dish.tolist(); t["press_xyz"]=xyz.tolist()
        base=t["id"]
        w.add_geom(name=f"dishbase_{base}",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.034,.004,0],pos=[dish[0],dish[1],.014],rgba=[.68,.75,.78,1])
        w.add_geom(name=f"dishwall_{base}",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.032,.013,0],pos=[dish[0],dish[1],.027],rgba=[.86,.92,.94,.55],contype=0,conaffinity=0)
        w.add_geom(name=f"liquid_{base}",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.027,.006,0],pos=[dish[0],dish[1],.021],rgba=[.86,.88,.92,1],contype=0,conaffinity=0)
        # vertical dropper and dark press pad in reach
        nozzle=np.array([dish[0],dish[1],.115])
        w.add_geom(name=f"dropper_{base}",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.010,.055,0],pos=[nozzle[0],nozzle[1],.115],rgba=[.94,.96,.96,1],contype=0,conaffinity=0)
        w.add_geom(name=f"dropper_tip_{base}",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.004,.009,0],pos=[nozzle[0],nozzle[1],.052],rgba=[.28,.35,.39,1],contype=0,conaffinity=0)
        # button centered at reachable end site; actuator geometrically engages the top pad
        pump_half=max(.006,(z-.002)/2)
        pump_center=(z+.002)/2
        w.add_geom(name=f"pump_{base}",type=mujoco.mjtGeom.mjGEOM_BOX,size=[.026,.025,pump_half],pos=[x,y,pump_center],rgba=[.18,.26,.31,1],contype=0,conaffinity=0)
        w.add_geom(name=f"pad_{base}",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.012,.004,0],pos=[x,y,z-.004],rgba=[.96,.64,.20,1],contype=0,conaffinity=0)
        # currently dry droplet marker, hidden until a metered action releases it
        drop_body=w.add_body(name=f"dropbody_{base}",pos=[nozzle[0],nozzle[1],.047],mocap=True)
        drop_body.add_geom(name=f"drop_{base}",type=mujoco.mjtGeom.mjGEOM_SPHERE,size=[.006,0,0],rgba=[.2,.58,.82,0],contype=0,conaffinity=0)
    model=spec.compile(); data=mujoco.MjData(model)
    # SO-101 source asset is yellow; recolor structural plastic to white; keep dark motors.
    for i in range(model.nmat):
        name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_MATERIAL,i) or ""
        if "_material" in name and not ("sts3215" in name or "no_horn" in name): model.mat_rgba[i]=[.92,.94,.95,1]
    return model,data,poses,trial_sites


def geom(m,name): return m.geom(name).id

class Render:
    def __init__(self,m,path,speed):
        self.r=mujoco.Renderer(m,height=720,width=1280); self.path=path; self.speed=speed
        self.cam=mujoco.MjvCamera(); self.cam.lookat[:]=[.245,-.015,.14]; self.cam.distance=.98; self.cam.azimuth=155; self.cam.elevation=-24
        self.font=font(22); self.small=font(17); self.frames=[]
        self.writer=imageio.get_writer(str(path),fps=FPS,codec="libx264",quality=7,macro_block_size=16,ffmpeg_params=["-crf","22","-preset","veryfast"])
        self.seq=0
    def frame(self,m,d,title,detail,tag,trial=None,drop_count=0,color=None,endpoint=False):
        self.r.update_scene(d,self.cam); im=Image.fromarray(self.r.render()); dr=ImageDraw.Draw(im,"RGBA")
        dr.rectangle((0,0,1280,75), fill=(18,27,35,235)); dr.text((34,14),title,font=self.font,fill="white"); dr.text((35,45),detail,font=self.small,fill=(206,219,224,255))
        dr.rounded_rectangle((1000,17,1245,52),radius=12,fill=(35,57,66,240)); dr.text((1018,25),f"SO-101  •  {self.speed:g}× playback",font=font(14),fill=(255,228,178,255))
        dr.rectangle((0,678,1280,720),fill=(18,27,35,230)); dr.text((34,689),"MuJoCo simulation  |  simplified science model",font=font(16),fill=(221,229,231,255))
        if trial:
            dr.text((970,689),f"{trial.upper()}   {drop_count} drops  •  {drop_count*DROP_ML:.2f} mL",font=font(16),fill=(255,255,255,255))
        self.writer.append_data(np.asarray(im.convert("RGB"))); self.seq+=1
        if self.seq == 1: self.frames.append((self.seq,np.asarray(im.convert("RGB"))))
    def close(self): self.writer.close(); self.r.close()


def run(out:Path,speed=1.0,negative=False,render=True):
    out.mkdir(parents=True,exist_ok=True); m,d,poses,site=build(); dt=m.opt.timestep
    jids=[m.joint(k).id for k in ("shoulder_pan","shoulder_lift","elbow_flex","wrist_flex","wrist_roll")]
    qadr=[int(m.joint(k).qposadr[0]) for k in ("shoulder_pan","shoulder_lift","elbow_flex","wrist_flex","wrist_roll")]
    aid=[m.actuator(k).id for k in ("shoulder_pan","shoulder_lift","elbow_flex","wrist_flex","wrist_roll")]
    siteid=m.site("gripperframe").id
    timeline=[]; events=[]; results=[]; obs=[]; rgb={"small":[.80,.85,.91,1],"large":[.80,.85,.91,1]}
    simtime=0.0; frames=[]
    # Motion uses actuator targets and measured joint state. Control feedback loops until convergence.
    goals={name:pose_rad(p) for name,p in poses.items()}
    current="HOME"
    for j,v in zip(qadr,goals["HOME"]): d.qpos[j]=v
    mujoco.mj_forward(m,d)
    # trajectory event schedule recorded in sim seconds; render speed downsample from 100Hz control ticks
    def policy_move(goal_name,label,trial=None,drop_count=0):
        nonlocal simtime,current
        target=goals[goal_name]
        start=simtime; max_ticks=9000
        command=np.array(d.ctrl[aid],dtype=float)
        for tick in range(max_ticks):
            command += np.clip(target-command,-1.0*dt,1.0*dt)
            for a,v in zip(aid,command): d.ctrl[a]=float(v)
            mujoco.mj_step(m,d); simtime+=dt
            err=float(np.max(np.abs(np.array([d.qpos[q] for q in qadr])-target)))
            if tick % max(1,round(.033*speed/dt))==0 and rec: rec.frame(m,d,label,f"Joint position control  •  max error {err:.3f} rad", "RUNNING", trial or current, drop_count)
            if err < .035 and np.max(np.abs(target-command)) < 1e-5 and tick > 5: break
        current=goal_name
        timeline.append({"t_s":round(simtime,3),"event":"motion_complete","target":goal_name,"joint_error_rad":err,"elapsed_s":round(simtime-start,3)})
        if not np.isfinite(d.qpos).all(): raise RuntimeError("nonfinite joint state")
        for joint_id,q in zip(jids,qadr):
            lo,hi=m.jnt_range[joint_id]
            if d.qpos[q] < lo-1e-6 or d.qpos[q] > hi+1e-6:
                joint_name=mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_JOINT,joint_id)
                raise RuntimeError(f"joint bound exceeded: {joint_name}")
        return err
    rec=None
    if render:
        # target frame budget computed after run; Render frame writer direct and still selection below.
        rec=Render(m,out/"titration.mp4",speed)
    # Start title/setup
    if rec: rec.frame(m,d,"Tiny titration","Two prepared samples • metered drops • persistent endpoint", "READY")
    for t in TRIALS:
        t0=simtime; tdrop=0; tvol=0.; added=0.; consecutive=0; ever_pressed=0
        dropid=geom(m,f"drop_{t['id']}"); dropmocap=int(m.body_mocapid[m.body(f"dropbody_{t['id']}").id]); liquidid=geom(m,f"liquid_{t['id']}")
        dish=np.array(t["dish"]); press_xyz=np.array(t["press_xyz"])
        # only the user-disabled-action control suppresses press triggers; actuators still execute same motions.
        for k in range(13):
            # Positioning and removal of paddle is part of each dispense; no time-based chemical progress.
            policy_move(t["above"],f"{t['id']} sample: approach pump",t["id"],tdrop)
            before=np.array(d.site_xpos[siteid]).copy()
            policy_move(t["pose"],f"{t['id']} sample: press metering paddle",t["id"],tdrop)
            measured=np.array(d.site_xpos[siteid]).copy(); dist=float(np.linalg.norm(measured-press_xyz))
            engage=dist < .014 and not negative
            if engage:
                ever_pressed+=1; tdrop+=1; tvol+=DROP_ML; added+=DROP_EQ
                excess=max(0.,added-t["acid_eq"])
                # Indicator teaching model: faint pink within 0.00..0.10 normalized excess; stronger pink beyond.
                if excess<=0: col=[.72,.77,.83,1]
                elif excess<=.10: col=[.98,.72,.82,1]
                elif excess<=.25: col=[.94,.43,.62,1]
                else: col=[.78,.18,.42,1]
                rgb[t["id"]]=col; m.geom_rgba[liquidid]=col; m.geom_size[liquidid,1]=min(.006+tdrop*.00045,.010); m.geom_rgba[dropid]=[.25,.62,.90,1]; d.mocap_pos[dropmocap]=[dish[0],dish[1],.047]; m.geom_rgba[dropid]=[.25,.62,.90,1]
                mujoco.mj_forward(m,d)
                # Show the action-released, fixed-volume droplet falling into the well.
                for idx,zdrop in enumerate(np.linspace(.047,.032,10)):
                    d.mocap_pos[dropmocap]=[dish[0],dish[1],zdrop]
                    for __ in range(max(1,round(.012/dt))): mujoco.mj_step(m,d); simtime+=dt
                    if rec and idx in (2,5,8): rec.frame(m,d,f"{t['id'].title()} sample • drop {tdrop}","Metered 0.12 mL droplet released by paddle action", "DROPLET",t["id"],tdrop)
                m.geom_rgba[dropid,3]=0.0
                mujoco.mj_forward(m,d)
                events.append({"t_s":round(simtime,3),"event":"dose","trial":t["id"],"dose_index":tdrop,"dose_ml":DROP_ML,"cumulative_ml":round(tvol,3),"normalized_base_added":round(added,3),"sample_ml":t["sample_ml"],"trigger":"geometric_gripper_paddle_engagement","engagement_distance_m":round(dist,5),"indicator_rgb":[round(x,3) for x in col[:3]]})
                # endpoint only inferred from actual cumulative action-driven dose and two repeated modeled readings.
                is_faint=(0 < excess <= .10)
                consecutive=consecutive+1 if is_faint else 0
                obs.append({"t_s":round(simtime,3),"trial":t["id"],"dose":tdrop,"normalized_excess":round(excess,3),"label":"faint pink" if is_faint else ("blue-gray" if excess<=0 else "pink"),"persistent_count":consecutive})
                if is_faint:
                    # Two timed-in-simulation optical reads without further dose establish persistence.
                    for _ in range(2):
                        for __ in range(round(.20/dt)): mujoco.mj_step(m,d); simtime+=dt
                        consecutive+=1
                        obs.append({"t_s":round(simtime,3),"trial":t["id"],"dose":tdrop,"normalized_excess":round(excess,3),"label":"faint pink","persistent_count":consecutive,"dose_added":False})
                if rec: rec.frame(m,d,f"{t['id'].title()} sample • dose {tdrop}",f"{DROP_ML:.2f} mL delivered  |  indicator response updated from delivered dose", "DOSE",t["id"],tdrop)
            else:
                events.append({"t_s":round(simtime,3),"event":"missed_action","trial":t["id"],"engagement_distance_m":round(dist,5),"dose_count_unchanged":tdrop})
            # Geometric pad release requires a return above the paddle before the next permitted trigger.
            policy_move(t["above"],f"{t['id']} sample: release paddle",t["id"],tdrop)
            if consecutive>=2: break
        if abs(tvol-tdrop*DROP_ML)>1e-9: raise RuntimeError("dose volume conservation check failed")
        success=consecutive>=2 and abs(added-t["acid_eq"])<=.10+1e-9
        results.append({"trial":t["id"],"prepared_sample_ml":t["sample_ml"],"normalized_neutralization_equivalent":t["acid_eq"],"drop_ml":DROP_ML,"drops":tdrop,"total_dose_ml":round(tvol,3),"normalized_base_added":round(added,3),"endpoint":"persistent faint pink" if success else None,"persistent_observations":consecutive,"overshoot_drops":max(0,tdrop-t["target_drops"]),"success":success,"mode":"negative_control_actions_disabled" if negative else "actuated_policy"})
        events.append({"t_s":round(simtime,3),"event":"trial_complete","trial":t["id"],"success":success,"drops":tdrop})
        if rec: rec.frame(m,d,f"{t['id'].title()} sample result",f"{tdrop} drops • {tvol:.2f} mL • {'persistent faint pink endpoint' if success else 'endpoint not reached'}","RESULT",t["id"],tdrop)
        # keep pad stable then go home between sample runs, before the next sample starts
        policy_move("HOME","Return to home",t["id"],tdrop)
    if rec: rec.frame(m,d,"Run complete","Both prepared amounts compared • robot returned home","COMPLETE")
    success=all(x["success"] for x in results) and not negative
    summary={"experiment":"tiny titration","policy":"deterministic position-actuator feedback, joint convergence and end-effector geometric paddle engagement","actuator_simulation":True,"physics_validation":"MuJoCo robot dynamics and position actuators; no calibrated contact/friction claim. Dosing trigger is geometric engagement, not force contact.","playback_speed":speed,"initial_state":{"robot_pose":"HOME","samples":[{"trial":t["id"],"sample_ml":t["sample_ml"],"normalized_acid_equivalent":t["acid_eq"],"normalized_base_added":0.0,"metered_drops":0,"initial_indicator":"blue-gray","initial_rgb":[0.80,0.85,0.91]} for t in TRIALS]},"science_model":{"kind":"normalized neutralization and indicator teaching model","dose_ml":DROP_ML,"base_equivalent_per_drop":DROP_EQ,"endpoint_rule":"faint pink when normalized excess base is >0 and <=0.10; require two consecutive post-dose observations","overshoot_rule":"stop on persistent faint pink; darker pink beyond 0.10 excess; finite maximum 13 presses","assumptions":"pre-mixed prepared samples; sample acid equivalent is 0.50 or 0.80 normalized units; drop volume fixed; acid-base reaction is stoichiometric; optical colors illustrative and not calibrated pH"},"success":success,"negative_control":negative,"simulated_seconds":round(simtime,3),"trials":results,"events":events,"policy_timeline":timeline,"observations":obs,"joint_bounds_checked":True,"finite_state_checked":True,"target_engagement_distance_m":0.014}
    (out/"summary.json").write_text(json.dumps(summary,indent=2)); (out/"trace.json").write_text(json.dumps({"events":events,"observations":obs},indent=2))
    if rec:
        rec.close()
        # Representative first/middle/final stills are rendered separately by extraction from video after creation.
    return summary


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output-dir",type=Path,required=True); ap.add_argument("--speed",type=float,default=1.0); ap.add_argument("--negative-control",action="store_true"); ap.add_argument("--no-render",action="store_true")
    a=ap.parse_args(); print(json.dumps(run(a.output_dir,a.speed, a.negative_control,not a.no_render),indent=2))
if __name__=="__main__": main()
