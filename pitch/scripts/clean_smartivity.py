"""Re-render a recorded Smartivity episode with no burned-in captions, for the film.
The film adds its own small 'Simulation' label in the brand type."""
import sys, json, gzip
from contextlib import closing
from pathlib import Path
import openarms_sim.smartivity_video as sv
from openarms_sim.smartivity_world import VisualState, World

sv._caption = lambda rgb, *a, **k: rgb
episode, out = Path(sys.argv[1]), Path(sys.argv[2])
receipt = json.loads((episode / 'receipt.json').read_text())
with gzip.open(episode / 'motion.json.gz', 'rt') as f:
    frames = [(t, a, VisualState(**s)) for t, a, s in json.load(f)]
prep = []
if (episode / 'preparation.json.gz').is_file():
    with gzip.open(episode / 'preparation.json.gz', 'rt') as f:
        prep = [(st, VisualState(**s)) for st, s in json.load(f)]
with closing(World(seed=receipt['seed'], scenario=receipt['scenario'], position_variation_m=receipt.get('position_variation_m'))) as w:
    r = sv.render_movie(w, frames, out, title=receipt['scenario'], mode=receipt['mode'], episode_id=receipt['episode_id'], preparation=prep)
out.with_suffix('.video.json').write_text(json.dumps({k: v for k, v in r.items() if k != 'timeline'}, indent=2))
print(out)
