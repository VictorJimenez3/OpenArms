"""Stand-alone dance page for the simulated arm; it never touches the demo app or its data.

    PYTHONPATH=agentic:simulation:. .venv-lab/bin/python agentic/scripts/dance_server.py [port]   # default 8020

The wave-and-dance video is rendered once at start-up, so the button plays it instantly. The page can also
wait: it reads (read-only) the demo apps' event logs and holds the button, or plays the dance automatically,
once the current task has finished. Simulation only; the real arm is never commanded from here.
"""
import glob
import json
import os
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "dance"
ARM = {"state": "idle", "step": "", "message": "", "stop": False, "lock": threading.Lock()}
HOME_TOLERANCE_DEG = 5.0
BUSY = {"queued", "running", "awaiting_confirmation", "executing", "observing"}
PAGE = """<!doctype html><meta charset=utf-8><title>OpenArms dance</title>
<style>body{font:18px system-ui;margin:2rem;max-width:760px}button{font-size:1.4rem;padding:.7rem 1.4rem}
video{width:100%;margin-top:1rem;background:#000;border-radius:8px}#s{color:#555;margin:.8rem 0}</style>
<h1>Say goodbye</h1>
<button id=b>Dance and wave</button>
<label style="margin-left:1rem"><input type=checkbox id=a> dance automatically when the current task finishes</label>
<div id=s>Simulation only. Press the button, or tick the box to wave after the task.</div>
<video id=v playsinline controls></video>
<h2>Real arm</h2>
<div id=mode style="color:#555">checking...</div>
<label><input type=checkbox id=clear> The area around the arm is clear and I have a hand near Stop.</label><br><br>
<button id=ab>Wave with the real arm</button> <button id=as style="background:#c0392b;color:#fff">STOP arm</button>
<div id=am style="margin:.8rem 0;color:#555"></div>
<script>
const v=document.getElementById('v'),b=document.getElementById('b'),s=document.getElementById('s'),a=document.getElementById('a');
let wasBusy=false,playing=false;
function play(){ if(playing) return; playing=true; v.src='/dance.mp4?'+Date.now(); v.play(); s.textContent='Dancing (simulation)...';
  v.onended=()=>{playing=false;s.textContent='Done. Back at HOME.'}; }
b.onclick=async()=>{ const st=await (await fetch('/status')).json();
  if(st.busy){ s.textContent='A task is still running. Waiting for it to finish...'; a.checked=true; } else play(); };
const ab=document.getElementById('ab'),as=document.getElementById('as'),am=document.getElementById('am'),cl=document.getElementById('clear');
let armWait=false;
ab.onclick=async()=>{ if(!cl.checked){am.textContent='Tick the box first: nobody can be near the arm.';return;}
  const st=await (await fetch('/status')).json();
  if(st.busy){ armWait=true; am.textContent='A task is still running. When it finishes you will be asked to confirm before the arm moves.'; return; }
  await fetch('/arm/dance',{method:'POST',body:JSON.stringify({clear:true})}); };
as.onclick=()=>fetch('/arm/stop',{method:'POST'});
setInterval(async()=>{ const r=await (await fetch('/arm/status')).json();
  document.getElementById('mode').textContent=r.real?'REAL ARM connected through '+r.port:'STAND-IN arm: nothing physical moves (set OPENARMS_FOLLOWER_PORT for the real arm).';
  if(r.state==='running') am.textContent='Arm: '+r.step; else if(r.message && !armWait) am.textContent=r.message; },700);
setInterval(async()=>{ const st=await (await fetch('/status')).json();
  if(wasBusy && !st.busy && a.checked){ a.checked=false; play(); }
  if(wasBusy && !st.busy && armWait){ armWait=false;
    if(confirm('The task has finished. Wave with the arm now? Make sure the area is clear.')) await fetch('/arm/dance',{method:'POST',body:JSON.stringify({clear:true})}); else am.textContent='Cancelled.'; }
  if(st.busy && !playing) b.textContent='Dance after the task'; else b.textContent='Dance and wave';
  wasBusy=st.busy; },1000);
</script>"""


def render(path: Path) -> dict:
    from agentic.openarms_lab.demo_bench_worker import SETUP
    from simulation.openarms_sim.chemistry import load_model
    from simulation.openarms_sim.config import load_bench, load_chemistry_config, load_joint_map, load_pose_file
    from simulation.openarms_sim.dance import build_dance
    from simulation.openarms_sim.joints import JointMap
    from simulation.openarms_sim.player import Player
    from simulation.openarms_sim.render import VideoRecorder
    from simulation.openarms_sim.scene import build_scene

    bench, jm, pose_file = load_bench(SETUP), JointMap(load_joint_map()), load_pose_file(SETUP)
    jm.use_taught_gripper(pose_file.get("gripper"))
    config = load_chemistry_config()
    scene = build_scene(bench)
    trusted = [np.array(jm.pose_to_model(pose_file["poses"][n])) for n in pose_file.get("taught", [])]
    player = Player(scene, jm, config, load_model(config), strict_limits=True, trusted_poses=trusted)
    segments = build_dance(jm, pose_file["poses"]["HOME"])
    recorder = VideoRecorder(scene, path, fps=30, speed=1)
    try:
        player.run(segments, fps=30, on_frame=recorder)
    finally:
        recorder.close()
    blocks = [i.message for i in player.issues if i.severity == "block"]
    return {"seconds": round(player.t, 1), "blocks": blocks}


def arm_config() -> dict:
    port = os.environ.get("OPENARMS_FOLLOWER_PORT") or None
    return {"real": bool(port), "port": port}


def _arm_dance() -> None:
    """Runs on its own thread so the page stays responsive and STOP can interrupt."""
    sys.path.insert(0, str(ROOT))
    from firmware.openarms_executor import dance
    from firmware.openarms_executor.robot import connect

    cfg, robot = arm_config(), None
    try:
        robot = connect(fake=not cfg["real"], port=cfg["port"])
        limits = None
        if cfg["real"]:
            from firmware.openarms_executor.pour_once import bench_limits
            from firmware.openarms_executor.poses import load_poses
            limits = bench_limits()
            home = load_poses(ROOT / os.environ.get("OPENARMS_POSES", "firmware/openarms_executor/poses.json"))["poses"]["HOME"]
            obs = robot.get_observation()
            off = max(abs(float(obs[j]) - home[j]) for j in dance.ARM_JOINTS)
            if off > HOME_TOLERANCE_DEG:
                raise ValueError(f"The arm is {off:.0f} degrees from HOME. Move it to HOME first; nothing was started.")
        ARM.update(state="running", step="starting", message="", stop=False)
        done = dance.run(robot, should_stop=lambda: ARM["stop"], limits=limits,
                         seconds=dance.SECONDS_PER_MOVE if cfg["real"] else 0.02,
                         on_step=lambda label: ARM.update(step=label))
        ARM.update(message="Done. The arm is back where it started." if done else "Stopped. The arm holds where it is.")
    except Exception as error:  # report, never raise into the server
        ARM.update(message=f"Not done: {error}")
    finally:
        ARM.update(state="idle", step="")
        if robot is not None and hasattr(robot, "disconnect"):
            try:
                robot.disconnect()
            except Exception:
                pass
        ARM["lock"].release()


def start_arm_dance(clear: bool) -> tuple[int, str]:
    if not clear:
        return 400, "Confirm that the area is clear first."
    if busy():
        return 409, "A task is still running; try again when it finishes."
    if not ARM["lock"].acquire(blocking=False):
        return 409, "The arm is already moving."
    ARM.update(state="running", step="connecting", message="", stop=False)
    threading.Thread(target=_arm_dance, daemon=True).start()
    return 200, "started"


def busy() -> bool:
    """True while any demo app has a task in flight (read-only look at its event log)."""
    for db in glob.glob(str(ROOT / "outputs" / "demo-app-*" / "lab.sqlite3")) + glob.glob(str(ROOT / "outputs" / "sim-main-demo-app" / "lab.sqlite3")):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
            row = con.execute("select time, data from events where kind='task_status' order by time desc limit 1").fetchone()
            con.close()
        except sqlite3.Error:
            continue
        if row and time.time() - row[0] < 300 and json.loads(row[1]).get("status") in BUSY:
            return True
    return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body, kind, status=200):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        if path == "/arm/dance":
            code, text = start_arm_dance(body.get("clear") is True)
            self._send(json.dumps({"message": text}).encode(), "application/json", code)
        elif path == "/arm/stop":
            ARM["stop"] = True
            self._send(b"{}", "application/json")
        else:
            self._send(b"not found", "text/plain", 404)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(PAGE.encode(), "text/html")
        elif path == "/status":
            self._send(json.dumps({"busy": busy()}).encode(), "application/json")
        elif path == "/arm/status":
            self._send(json.dumps({**arm_config(), "state": ARM["state"], "step": ARM["step"],
                                   "message": ARM["message"]}).encode(), "application/json")
        elif path == "/dance.mp4":
            self._send((OUT / "dance.mp4").read_bytes(), "video/mp4")
        else:
            self._send(b"not found", "text/plain", 404)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    print("Rendering the dance (once)...", flush=True)
    info = render(OUT / "dance.mp4")
    if info["blocks"]:
        raise SystemExit("The dance was refused by the simulator: " + "; ".join(info["blocks"]))
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8020
    print(f"Dance ready ({info['seconds']} s). Open http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
