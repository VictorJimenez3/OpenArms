"""Offline policy metadata/normalization preflight. Never loads or executes a robot policy."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path


def _finite(values, size):
    return isinstance(values,list) and len(values)==size and all(type(x) in (int,float) and math.isfinite(x) for x in values)


def check_compatibility(policy, target):
    """Exact convention matching only. Missing metadata is a blocker, never a default."""
    blockers=[]
    for key in ('policy_id','revision','metadata_source'):
        if not isinstance(policy.get(key),str) or not policy[key]: blockers.append('missing '+key)
    names=policy.get('joint_names',[])
    if not isinstance(names,list) or not names or not all(isinstance(name,str) and name for name in names):
        blockers.append('joint names missing/invalid'); names=[]
    elif len(set(names))!=len(names): blockers.append('joint names duplicate')
    n=len(names)
    for key in ('joint_names','joint_units','control_mode','camera_keys'):
        if not policy.get(key) or policy.get(key)!=target.get(key): blockers.append(key+' mismatch or unknown')
    if policy.get('action_dim')!=n or not n: blockers.append('action dimension mismatch')
    if not isinstance(policy.get('joint_units'),list) or len(policy.get('joint_units',[]))!=n: blockers.append('joint units missing')
    if type(policy.get('horizon')) is not int or policy['horizon']<1: blockers.append('invalid horizon')
    norm=policy.get('normalization',{})
    if norm.get('mode')!='q01_q99' or not _finite(norm.get('low'),n) or not _finite(norm.get('high'),n):
        blockers.append('normalization stats missing or invalid')
    elif any(lo>=hi for lo,hi in zip(norm['low'],norm['high'])): blockers.append('normalization range not positive')
    limits=target.get('joint_limits',{})
    if not all(_finite(limits.get(name),2) and limits[name][0]<limits[name][1] for name in names): blockers.append('target joint limits missing')
    if not target.get('mapping_receipt'): blockers.append('no reviewed embodiment/unit/sign/offset mapping receipt')
    if not target.get('embodiment_id'): blockers.append('target embodiment unknown')
    return {'status':'blocked' if blockers else 'offline_compatible','blockers':blockers,
            'physical_execution_allowed':False,'policy_id':policy.get('policy_id'),
            'qualification':'metadata_and_array_checks_only; held-out policy evaluation still required'}


def denormalize_actions(actions, policy, target):
    verdict=check_compatibility(policy,target)
    if verdict['blockers']: raise ValueError('; '.join(verdict['blockers']))
    n=policy['action_dim']
    if not isinstance(actions,list) or len(actions)!=policy['horizon'] or not all(_finite(row,n) for row in actions):
        raise ValueError('action chunk shape or finite-value failure')
    low=policy['normalization']['low']; high=policy['normalization']['high']
    output=[]
    for row in actions:
        if any(abs(x)>1 for x in row): raise ValueError('normalized action outside [-1,1]')
        values=[lo+(x+1)*.5*(hi-lo) for x,lo,hi in zip(row,low,high)]
        for name,value in zip(policy['joint_names'],values):
            lo,hi=target['joint_limits'][name]
            if not lo<=value<=hi: raise ValueError('denormalized '+name+' outside target limits')
        output.append(values)
    return output


def training_preflight(episodes, *, minimum_episodes=2):
    blockers=[]
    if type(minimum_episodes) is not int or minimum_episodes<2: raise ValueError('minimum_episodes must be >=2')
    ids=[e.get('episode_id') for e in episodes]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids): blockers.append('missing/duplicate episode IDs')
    hashes=[e.get('content_hash') for e in episodes]
    if any(not isinstance(h,str) or len(h)!=64 for h in hashes) or len(set(hashes))!=len(hashes): blockers.append('missing/duplicate content hashes')
    if len(episodes)<minimum_episodes: blockers.append('insufficient aligned task episodes')
    for e in episodes:
        if e.get('provenance')!='physical_recording' or e.get('alignment_validated') is not True or not e.get('task_success_observed'):
            blockers.append(str(e.get('episode_id'))+': missing aligned physical task/success evidence')
        if e.get('split') not in ('train','validation'): blockers.append('missing episode-level split')
        if not e.get('position_group'): blockers.append('missing position group')
    train={e.get('position_group') for e in episodes if e.get('split')=='train'}
    validation={e.get('position_group') for e in episodes if e.get('split')=='validation'}
    if not train or not validation or train&validation: blockers.append('need held-out position groups with no split leakage')
    return {'status':'blocked' if blockers else 'ready_for_offline_training_setup','blockers':sorted(set(blockers)),
            'episode_count':len(episodes),'training_started':False,'physical_execution_allowed':False}


def inspect_molmo_metadata(config, norms, *, revision, source):
    tags=norms.get('metadata_by_tag',{})
    tag='so100_so101_molmoact2'
    if tag not in tags: raise ValueError('SO100/101 normalization tag absent')
    info=tags[tag]; stats=info['action_stats']; names=stats['names']
    return {'policy_id':'allenai/MolmoAct2-SO100_101','revision':revision,'metadata_source':source,
            'joint_names':names,'joint_units':None,'control_mode':info.get('control_mode'),
            'camera_keys':info.get('camera_keys'), 'action_dim':len(names),'padded_action_dim':config.get('max_action_dim'),
            'horizon':info.get('action_horizon'), 'normalization':{'mode':norms.get('norm_mode'),'low':stats.get('q01'),'high':stats.get('q99')},
            'metadata_sha256':hashlib.sha256(json.dumps({'config':config,'norms':norms},sort_keys=True).encode()).hexdigest(),
            'missing_semantics':['joint units/signs/offsets for this calibrated Hiwonder arm','camera arrangement and key binding']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='mode',required=True)
    c=sub.add_parser('check'); c.add_argument('policy',type=Path); c.add_argument('target',type=Path)
    t=sub.add_parser('training'); t.add_argument('episodes',type=Path)
    a=p.parse_args()
    result=check_compatibility(json.loads(a.policy.read_text()),json.loads(a.target.read_text())) if a.mode=='check' else training_preflight(json.loads(a.episodes.read_text()))
    print(json.dumps(result,indent=2,allow_nan=False))
    return 2 if result['status']=='blocked' else 0

if __name__=='__main__': raise SystemExit(main())
