"""Download pinned original geometry and licenses. Does not install any simulator."""
import sys,json,hashlib,urllib.request,concurrent.futures
from pathlib import Path
out=Path(sys.argv[1]).resolve()/'assets';out.mkdir(parents=True,exist_ok=True)
workshop='ce807d99724cb65671abec01f908a2fcb4a6eab7';google='370c43965323c0944b433b202aac5058b5f907a9'
items=[]
for file in ['SO-ARM101-USD-NO-CAMERA.usd','Vial.usda','Vial_rack_simple.usda']:
 items.append((f'https://media.githubusercontent.com/media/isaac-sim/Sim-to-Real-SO-101-Workshop/{workshop}/source/sim_to_real_so101/assets/usd/{file}',out/file))
for file,dest in [('LICENSE','WORKSHOP_LICENSE'),('THIRD_PARTY_NOTICES','THIRD_PARTY_NOTICES')]:items.append((f'https://raw.githubusercontent.com/isaac-sim/Sim-to-Real-SO-101-Workshop/{workshop}/{file}',out/dest))
tree=json.load(urllib.request.urlopen(f'https://api.github.com/repos/google-deepmind/mujoco_menagerie/git/trees/{google}?recursive=1'))
for item in tree['tree']:
 path=item['path']
 if item['type']=='blob' and path.startswith('robotstudio_so101/') and not path.endswith('.png'):
  items.append((f'https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/{google}/{path}',out/'google-deepmind-so101'/Path(path).relative_to('robotstudio_so101')))
def fetch(pair):
 url,dest=pair;dest.parent.mkdir(parents=True,exist_ok=True)
 try:urllib.request.urlretrieve(url,dest)
 except Exception:
  if '/media/isaac-sim/' not in url:raise
  urllib.request.urlretrieve(url.replace('media.githubusercontent.com/media/','raw.githubusercontent.com/'),dest)
 data=dest.read_bytes()
 if data.startswith(b'version https://git-lfs.github.com'):raise RuntimeError('Unresolved LFS pointer: '+str(dest))
 return {'file':str(dest.relative_to(out)),'url':url,'sha256':hashlib.sha256(data).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:records=list(pool.map(fetch,items))
(out/'source_receipt.json').write_text(json.dumps(records,indent=2));print('Fetched',len(records),'pinned files')
