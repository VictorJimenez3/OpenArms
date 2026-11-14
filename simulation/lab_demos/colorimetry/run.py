#!/usr/bin/env python3
"""Actuated SO-101 colorimetry lesson."""
import argparse,json,math,os,shutil
from pathlib import Path
os.environ.setdefault("OMP_NUM_THREADS","2");os.environ.setdefault("OPENBLAS_NUM_THREADS","2")
import imageio.v2 as imageio,mujoco,numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.optimize import least_squares
ROOT=Path(__file__).resolve().parents[3];ARM=ROOT/"simulation/models/so101/so101_new_calib.xml"
JN=["shoulder_pan","shoulder_lift","elbow_flex","wrist_flex","wrist_roll"];HOME=np.array([0.,-1.45,1.35,1.,math.pi/2])
S={"reference":{"p":np.array([.28,.08,0.]),"c":.30,"rgb":(.24,.55,.90)},"unknown":{"p":np.array([.31,.18,0.]),"c":.52,"rgb":(.18,.43,.82)}}
R=np.array([.37,.12,0.]);W,H,FPS=1280,720,30
def beer_lambert(c_mol_l,path_cm=1.0,epsilon=math.log(10)):
 return epsilon*c_mol_l*path_cm
def rgb_sensor_proxy(rgb):
 transmission=max(.04,min(.98,sum(rgb)/(3*255)))
 return -math.log(transmission)
def build():
 s=mujoco.MjSpec.from_file(str(ARM));s.modelname="colorimetry"
 s.visual.global_.offwidth=1600;s.visual.global_.offheight=1000
 s.visual.headlight.ambient=[.25]*3;s.visual.headlight.diffuse=[.35]*3
 s.add_texture(name="studio_sky",type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,rgb1=[.97,.98,.98],rgb2=[.82,.87,.9],width=256,height=1536)
 for m in s.materials:
  m.rgba=[.12,.14,.16,1] if "sts3215" in m.name else [.89,.91,.92,1]
 w=s.worldbody;w.add_light(name="key",pos=[.1,-.25,1.2],dir=[0,0,-1],diffuse=[.55,.55,.55],castshadow=False)
 w.add_geom(name="studio_floor",type=mujoco.mjtGeom.mjGEOM_PLANE,size=[2,2,.1],pos=[.25,0,-.075],rgba=[.94,.95,.94,1],contype=0,conaffinity=0)
 w.add_geom(name="bench_pedestal",type=mujoco.mjtGeom.mjGEOM_BOX,size=[.08,.08,.012],pos=[.25,0,-.063],rgba=[.74,.77,.76,1])
 w.add_geom(name="bench",type=mujoco.mjtGeom.mjGEOM_BOX,size=[.38,.31,.025],pos=[.25,0,-.025],rgba=[.88,.88,.85,1])
 b=w.add_body(name="reader",pos=[*R[:2],.055])
 for name,size,pos,col in [("base",[.09,.085,.055],[0,0,0],[.82,.85,.86,1]),("left_top",[.025,.067,.008],[-.047,0,.056],[.94,.95,.94,1]),("right_top",[.025,.067,.008],[.047,0,.056],[.94,.95,.94,1]),("screen",[.032,.022,.002],[-.025,-.085,.022],[.04,.11,.14,1]),("left",[.012,.034,.010],[-.047,0,.07],[.25,.29,.31,1]),("right",[.012,.034,.010],[.047,0,.07],[.25,.29,.31,1])]:
  b.add_geom(name="rd_"+name,type=mujoco.mjtGeom.mjGEOM_BOX,size=size,pos=pos,rgba=col)
 for n,v in S.items():
  x,y,_=v["p"];w.add_geom(name=n+"_stand",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.030,.050,0],pos=[x,y,.050],rgba=[.78,.80,.79,1],contype=0,conaffinity=0);o=w.add_body(name=n,pos=[x,y,.147],mocap=True)
  w.add_geom(name=n+"_station",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.027,.001,0],pos=[x,y,.002],rgba=[.22,.48,.74,1] if n=="reference" else [.62,.38,.72,1],contype=0,conaffinity=0)
  o.add_geom(name=n+"_glass",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.018,.047,0],rgba=[.82,.88,.9,.55],contype=0,conaffinity=0)
  o.add_geom(name=n+"_liquid",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.014,.027,0],pos=[0,0,-.012],rgba=[*v["rgb"],1],contype=0,conaffinity=0)
  o.add_geom(name=n+"_cap",type=mujoco.mjtGeom.mjGEOM_CYLINDER,size=[.019,.007,0],pos=[0,0,.054],rgba=[.22,.28,.3,1],contype=0,conaffinity=0)
  v["mid"]=None
 s.body("gripper").add_site(name="grasp_point",pos=[.022,0,-.079],quat=[.707107,0,.707107,0])
 m=s.compile();d=mujoco.MjData(m);adr=[int(m.joint(j).qposadr[0]) for j in JN];act=[m.actuator(j).id for j in JN]+[m.actuator("gripper").id]
 for n,v in S.items():v["mid"]=int(m.body_mocapid[m.body(n).id])
 for a,q in zip(adr,HOME):d.qpos[a]=q
 d.qpos[m.joint("gripper").qposadr[0]]=0;mujoco.mj_forward(m,d)
 return m,d,adr,act,m.site("grasp_point").id
def ik(m,d,adr,site,t,seed):
 saved=d.qpos.copy()
 lo=np.array([m.jnt_range[m.joint(j).id,0] for j in JN])+.015;hi=np.array([m.jnt_range[m.joint(j).id,1] for j in JN])-.015
 def f(q):
  for a,v in zip(adr,q):d.qpos[a]=v
  mujoco.mj_kinematics(m,d);return np.r_[(d.site_xpos[site]-t)/.008,(q[4]-seed[4])*.05]
 x=least_squares(f,np.clip(seed,lo,hi),bounds=(lo,hi),max_nfev=100).x
 for a,v in zip(adr,x):d.qpos[a]=v
 mujoco.mj_forward(m,d);err=float(np.linalg.norm(d.site_xpos[site]-t))
 d.qpos[:]=saved;mujoco.mj_forward(m,d)
 return x,err
def font(sz,b=False):
 for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if b else "/System/Library/Fonts/Supplemental/Arial.ttf","/System/Library/Fonts/Helvetica.ttc"):
  try:return ImageFont.truetype(p,sz)
  except OSError:pass
 return ImageFont.load_default()
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--output-dir",type=Path,default=Path("evidence"));ap.add_argument("--speed",type=float,default=2);ap.add_argument("--negative-control",action="store_true");a=ap.parse_args()
 out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
 m,d,adr,act,site=build();dt=m.opt.timestep;cam=mujoco.MjvCamera();cam.lookat[:]=[.23,0,.18];cam.distance=.92;cam.azimuth=145;cam.elevation=-30
 rend=mujoco.Renderer(m,H,W);wr=imageio.get_writer(str(out/"colorimetry.mp4"),fps=FPS,codec="libx264",quality=7,macro_block_size=16,pixelformat="yuv420p")
 events=[];trace=[];obs={};sim=0.;frames=0;qtar=HOME.copy();held=None;stride=max(1,round((max(.5,a.speed)/FPS)/dt))
 def ev(k,**kw):events.append({"t_sim_s":round(sim,3),"event":k,**kw})
 def draw(title,cap):
  nonlocal frames
  rend.update_scene(d,cam);im=Image.fromarray(rend.render()).convert("RGB");dr=ImageDraw.Draw(im,"RGBA")
  dr.rectangle([0,0,W,68],fill=(17,31,42,235));dr.text((34,13),title,font=font(29,1),fill="white");dr.text((34,80),cap,font=font(20),fill=(25,42,50,255))
  dr.rounded_rectangle([880,18,1248,54],radius=10,fill=(18,68,72,235));dr.text((899,26),"MuJoCo simulation | simplified science model",font=font(16),fill="white")
  dr.text((1100,80),f"{a.speed:g}× playback",font=font(16),fill=(25,42,50,255))
  if obs:
   y=570;dr.rounded_rectangle([32,y,1248,690],radius=18,fill=(246,248,246,242));dr.text((54,y+12),"PHOTOMETER · modeled optical reading",font=font(18,1),fill=(28,48,53,255));x=55
   for n in ("reference","unknown"):
    if n in obs:dr.text((x,y+48),f"{n.title()}  A*={obs[n]['sensor_A']:.3f}",font=font(23,1),fill=(32,52,58,255));x+=565
  wr.append_data(np.asarray(im));frames+=1
 def step(label,cap,n=1000):
  nonlocal sim
  for _ in range(n):
   d.ctrl[act[:5]]=qtar;d.ctrl[act[5]]=.2 if held else 1.4;mujoco.mj_step(m,d);sim+=dt
   measured=np.array([d.qpos[x] for x in adr])
   if not np.isfinite(measured).all() or not all(m.jnt_range[m.joint(j).id,0]-.01 <= v <= m.jnt_range[m.joint(j).id,1]+.01 for j,v in zip(JN,measured)):raise RuntimeError("nonfinite or out-of-bounds actuator state")
   if held:
    mid=S[held]["mid"];d.mocap_pos[mid]=d.site_xpos[site].copy();d.mocap_quat[mid]=[1,0,0,0]
   if (_+1)%stride==0:draw(label,cap)
  q=np.array([d.qpos[x] for x in adr]);trace.append({"t":round(sim,3),"state":label,"q":q.tolist(),"finite":bool(np.isfinite(q).all()),"within_bounds":bool(all(m.jnt_range[m.joint(j).id,0]-1e-4<=v<=m.jnt_range[m.joint(j).id,1]+1e-4 for j,v in zip(JN,q)))})
  if n%stride:draw(label,cap)
 def move(t,label,cap):
  nonlocal qtar
  q,e=ik(m,d,adr,site,np.array(t,float),qtar)
  if e>.025:raise RuntimeError(f"unreachable {t}: {e:.4f}m")
  qtar=q;step(label,cap,max(750,round(3/dt)))
 def home():move([.27,0,.30],"Return home","Clear reader and return to home pose")
 draw("Color comparison","Two prepared samples · reference and unknown · start")
 move([.27,0,.30],"Approach samples","Move from the starting position toward the prepared samples")
 for n in ("reference","unknown"):
  p=S[n]["p"];above=[p[0],p[1],.25];pick=[p[0],p[1],.147];slot=[R[0],R[1],.25];seat=[R[0],R[1],.166]
  if a.negative_control and n=="reference":ev("negative_control_missed_pick",sample=n);step("Missed-grasp control","Pickup disabled: reference remains on bench; no measurement",120);continue
  move(above,"Align sample",f"Align over the marked {n} station")
  move(pick,"Engage sample",f"Lower to vial; align the gripper around the sample")
  e=float(np.linalg.norm(d.site_xpos[site]-pick));grasp=e<.018;ev("grasp_attempt",sample=n,error_m=round(e,5),engaged=bool(grasp));held=n if grasp else None
  step("Close gripper",f"{n.title()} grasp {'engaged' if grasp else 'missed'}",150)
  move(above,"Lift upright",f"Lift {n} upright for a short transfer")
  move(slot,"Align reader","Center vial over generous open photometer slot")
  move(seat,"Seat sample","Measurement enabled only at correct reader placement")
  pos=d.site_xpos[site].copy();err=float(np.linalg.norm(pos[:2]-R[:2]));placed=grasp and err<.025 and abs(pos[2]-.166)<.035
  placed=bool(placed);ev("measurement_gate",sample=n,reader_error_m=round(err,4),site_z_m=round(float(pos[2]),4),placed=placed)
  if placed:
   prediction=beer_lambert(S[n]["c"]);rgb=tuple(round(255*v) for v in S[n]["rgb"]);sensor=rgb_sensor_proxy(rgb)
   obs[n]={"beer_lambert_prediction_A":round(prediction,4),"sensor_A":round(sensor,4),"rgb":rgb,"measurement_type":"rendered-material RGB sensor proxy"}
   ev("sample_measured",sample=n,prediction_A=round(prediction,4),sensor_proxy_A=round(sensor,4),rgb=rgb)
  step("Read sample","Record the modeled optical reading with the sample seated",150)
  held=None;ev("release",sample=n,location="reader" if placed else "unmeasured")
  move([R[0],R[1],.27],"Clear reader","Open jaws after seating")
  move(seat,"Regrasp sample","Pick up the measured sample from the reader")
  e=float(np.linalg.norm(d.site_xpos[site]-seat));held=n if e<.022 else None;ev("regrasp_attempt",sample=n,error_m=round(e,4),engaged=held==n)
  move(slot,"Lift from reader","Lift vial vertically")
  move(above,"Return sample","Return vial upright above its marked station")
  move(pick,"Set down sample","Lower vial onto its rack stand before releasing")
  held=None;ev("returned_to_station",sample=n);home()
 if set(obs)=={"reference","unknown"}:
  delta=obs["unknown"]["sensor_A"]-obs["reference"]["sensor_A"];ev("comparison",delta_sensor_A=round(delta,4));draw("Comparison complete",f"Unknown modeled optical reading is higher by {delta:.3f} A*")
 else:draw("Control complete","No two-sample comparison: measurement gate correctly withheld")
 wr.close();rend.update_scene(d,cam);imageio.imwrite(out/"final.png",rend.render());rend.close()
 import subprocess
 for i,t in ((0,"first"),(int(frames)//2,"middle"),(int(frames)-1,"last")):subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(out/"colorimetry.mp4"),"-vf",f"select=eq(n\\,{i})","-fps_mode","passthrough",str(out/f"{t}.png")],check=True)
 sheet=Image.new("RGB",(1920,360),"white")
 for i,t in enumerate(("first","middle","last")):sheet.paste(Image.open(out/f"{t}.png").convert("RGB").resize((640,360)),(640*i,0))
 sheet.save(out/"contact-sheet.png")
 summary={"success":bool(not a.negative_control and set(obs)=={"reference","unknown"} and all(r["finite"] and r["within_bounds"] for r in trace)),"mode":"actuated position-controlled MuJoCo SO-101 with mj_step; geometric grasp gate then mocap attachment","simulation_time_s":round(sim,3),"video":{"file":"colorimetry.mp4","fps":FPS,"width":W,"height":H,"frames":int(frames),"playback_speed":a.speed},"model":{"name":"Beer-Lambert teaching model","assumptions":"A=epsilon*c*l; epsilon=ln(10) L mol^-1 cm^-1, c=0.30/0.52 mol L^-1, l=1 cm; illustrative, uncalibrated.","sensor":"rendered vial material RGB proxy converted to optical density; separate from analytical prediction, not physical photometer or camera pixel read."},"observations":obs,"negative_control":{"requested":a.negative_control,"result":"reference pickup disabled; measurement withheld and comparison not claimed" if a.negative_control else "disabled"},"events":events,"joint_trace":{"samples":len(trace),"all_finite":all(r["finite"] for r in trace),"all_within_bounds":all(r["within_bounds"] for r in trace)},"limitations":["Geometric 18 mm grasp gate then mocap attachment; contact forces and slip are not validated.","RGB is a rendered material proxy, not a camera or physical sensor measurement.","Poses and bench coordinates are illustrative, not physically calibrated."]}
 (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n");(out/"trace.json").write_text(json.dumps(trace,indent=2)+"\n")
 if os.environ.get("COLORIMETRY_COPY_OUTPUT"):
  dest=Path(os.environ["COLORIMETRY_COPY_OUTPUT"]);dest.mkdir(parents=True,exist_ok=True)
  for p in out.iterdir():
   if p.is_file():shutil.copy2(p,dest/p.name)
 print(json.dumps({"success":summary["success"],"sim_s":sim,"observations":obs,"frames":int(frames)},indent=2))
if __name__=="__main__":main()
