"""Same-frame offline detector comparison; no physical success or metric geometry claims."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import cv2
import numpy as np
from .perception import HSVBaseline, SSDLiteDetector, GroundingDinoDetector


def iou(a,b):
    if a is None or b is None: return 0.0
    x=max(0,min(a[2],b[2])-max(a[0],b[0])); y=max(0,min(a[3],b[3])-max(a[1],b[1]))
    inter=x*y
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter
    return inter/union if union>0 else 0.0


def load_case(case, root):
    path=(Path(root)/case['image']).resolve()
    if not path.is_relative_to(Path(root).resolve()): raise ValueError('image escapes dataset root')
    data=path.read_bytes()
    if case.get('sha256') and hashlib.sha256(data).hexdigest()!=case['sha256']: raise ValueError('source image changed')
    image=cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR)
    if image is None: raise ValueError('unreadable image')
    image=cv2.resize(image,tuple(case.get('size_wh',[480,640])))
    variant=case.get('transform','identity')
    if variant=='dark': image=(image.astype(np.float32)*.25).astype(np.uint8)
    elif variant=='gray': image=cv2.cvtColor(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    elif variant=='blank': image[:]=90
    elif variant=='occlude_right':
        x1,y1,x2,y2=map(int,case['original_box']); mid=(x1+x2)//2
        image[y1:y2,mid:x2]=90
    elif variant!='identity': raise ValueError('unknown transform')
    return image


def summarize(rows):
    correct=0
    for row in rows:
        if row['expected_box'] is None:
            correct+=row['observation']['status']=='unknown'
        else: correct+=row['iou']>=.5
    return {'count':len(rows),'correct_at_iou_0_5_or_negative_unknown':correct,
            'positive_count':sum(r['expected_box'] is not None for r in rows),
            'positive_localized_iou_0_5':sum(r['expected_box'] is not None and r['iou']>=.5 for r in rows),
            'negative_false_positives':sum(r['expected_box'] is None and r['observation']['status']=='ok' for r in rows),
            'median_end_to_end_ms':float(np.median([r['end_to_end_ms'] for r in rows])),
            'p95_end_to_end_ms':float(np.percentile([r['end_to_end_ms'] for r in rows],95)),
            'median_detector_ms':float(np.median([r['detector_ms'] for r in rows]))}


def benchmark(dataset,root,*,device='mps',repeats=3,category='orange',cache_dir='outputs/model-cache', model='ssdlite'):
    if type(repeats) is not int or repeats<1: raise ValueError('repeats must be positive')
    cases=dataset['cases']
    if not cases: raise ValueError('empty dataset')
    if len({c['id'] for c in cases})!=len(cases): raise ValueError('duplicate case id')
    detector=(SSDLiteDetector if model=='ssdlite' else GroundingDinoDetector)(device=device,category=category,cache_dir=cache_dir)
    methods=[HSVBaseline(),detector]
    report={'schema_version':1,'backend':'offline_recorded_image_inference','physical_outcome':'not_evaluated',
            'dataset':dataset,'device':device,'gpu_postprocessing':'CPU NMS for MPS; backbone/head on MPS' if device=='mps' and model=='ssdlite' else device,
            'environment':{'python':platform.python_version(),'platform':platform.platform(),'torch':detector.torch.__version__,'opencv':cv2.__version__},
            'model_load_ms_including_download_if_uncached':detector.load_ms,'repeats':repeats,'methods':{},
            'limitations':['Provisional agent-drawn image boxes, not measured metric truth.',
                           'Transforms of four stills are correlated stress tests, not independent trials.',
                           'No training or threshold fitting; fixed HSV bounds and COCO score 0.35.',
                           'Legacy still timestamps/camera IDs not established; no joint alignment claim.',
                           'No cup footage, liquid outcomes, grasp-point accuracy or robot test.']}
    for method in methods:
        rows=[]; cold=None
        for repeat in range(repeats):
            for case in cases:
                start=time.perf_counter(); image=load_case(case,root); loaded=time.perf_counter()
                meta={'object_id':category,'camera_id':'legacy-unidentified','frame_id':case['id'],'timestamp_s':None,'calibration_id':None,
                      'provenance':'recorded' if case.get('transform','identity')=='identity' else 'recorded_transformed'}
                detected=method.detect(image,meta)
                finish=time.perf_counter()
                row={'case_id':case['id'],'repeat':repeat,'expected_box':case['expected_box'],'observation':detected,
                     'iou':iou(case['expected_box'],detected['box_xyxy']),
                     'model_forward_ms':getattr(method,'last_forward_ms',None),
                     'image_load_ms':(loaded-start)*1000,'detector_ms':(finish-loaded)*1000,'end_to_end_ms':(finish-start)*1000}
                if cold is None: cold=row
                rows.append(row)
        warm=[r for r in rows if r['repeat']>0] or rows[1:] or rows
        report['methods'][method.method]={'cold_first_frame_ms':cold['end_to_end_ms'],'summary_all':summarize(rows),'warm_summary':summarize(warm),'rows':rows}
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dataset',type=Path); p.add_argument('--root',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path); p.add_argument('--device',choices=['mps','cuda','cpu'],default='mps')
    p.add_argument('--model',choices=['ssdlite','grounding-dino'],default='ssdlite'); p.add_argument('--repeats',type=int,default=3); p.add_argument('--category',default='orange'); p.add_argument('--cache-dir',default='outputs/model-cache')
    a=p.parse_args()
    report=benchmark(json.loads(a.dataset.read_text()),a.root,device=a.device,repeats=a.repeats,category=a.category,cache_dir=a.cache_dir,model=a.model)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x') as f: json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps({name:r['warm_summary'] for name,r in report['methods'].items()},indent=2))

if __name__=='__main__': main()
