"""Offline image observations. Pixel detections never imply a grasp or metric pose."""
from __future__ import annotations

import math
from pathlib import Path
import time

import cv2
import numpy as np


def observation(metadata, method, *, box=None, confidence=None, reason=None, pixel=None):
    for key in ('object_id', 'camera_id', 'frame_id'):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise ValueError(f'missing {key}')
    timestamp = metadata.get('timestamp_s')
    if timestamp is not None and (type(timestamp) not in (int,float) or not math.isfinite(timestamp)):
        raise ValueError('timestamp_s must be finite or null for legacy unaligned stills')
    if box is not None:
        box = list(map(float,box))
        if len(box)!=4 or not all(math.isfinite(v) for v in box) or box[2]<=box[0] or box[3]<=box[1]:
            raise ValueError('invalid bounding box')
    if confidence is not None and (not math.isfinite(confidence) or not 0<=confidence<=1):
        raise ValueError('invalid confidence')
    return {**{k:metadata.get(k) for k in ('object_id','camera_id','frame_id','timestamp_s','calibration_id')},
            'schema_version':1,'status':'ok' if box is not None else 'unknown','box_xyxy':box,
            'mask':None,'pixel_points':[] if box is None else [pixel or {'name':'box_center','xy':[(box[0]+box[2])/2,(box[1]+box[3])/2]}],
            'confidence':confidence,'unknown_reason':reason,'method':method,
            'geometry_valid':False,'grasp_pose':None,'alignment_known':timestamp is not None,
            'provenance':metadata.get('provenance','recorded')}


def validate_image(image):
    if not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3 or min(image.shape[:2])<2:
        raise ValueError('expected a nonempty uint8 BGR image')


class HSVBaseline:
    """Fixed orange-color heuristic; not an identity detector and not calibrated confidence."""
    method='hsv-orange-v1'
    def __init__(self, minimum_area_fraction=.001, ambiguity_ratio=.65):
        if not 0<minimum_area_fraction<1 or not 0<ambiguity_ratio<=1:
            raise ValueError('invalid HSV thresholds')
        self.minimum_area_fraction=minimum_area_fraction
        self.ambiguity_ratio=ambiguity_ratio
    def detect(self,image,metadata):
        validate_image(image)
        if metadata.get('object_id') not in ('orange','mandarin','orange_marker'):
            return observation(metadata,self.method,reason='HSV baseline supports orange-colored targets only')
        hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
        mask=cv2.inRange(hsv,np.array([5,100,80]),np.array([30,255,255]))
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        candidates=sorted((c for c in contours if cv2.contourArea(c)>=image.shape[0]*image.shape[1]*self.minimum_area_fraction),key=cv2.contourArea,reverse=True)
        if not candidates:
            return observation(metadata,self.method,reason='no orange region')
        if len(candidates)>1 and cv2.contourArea(candidates[1])>=self.ambiguity_ratio*cv2.contourArea(candidates[0]):
            return observation(metadata,self.method,reason='multiple similarly sized orange regions')
        contour=candidates[0]; x,y,w,h=cv2.boundingRect(contour); moments=cv2.moments(contour)
        return observation(metadata,self.method,box=[x,y,x+w,y+h],confidence=None,
                           pixel={'name':'color_region_centroid','xy':[moments['m10']/moments['m00'],moments['m01']/moments['m00']]})


class ManualBox:
    method='manual-box-v1'
    def __init__(self, annotations): self.annotations=annotations
    def detect(self,image,metadata):
        validate_image(image)
        box=self.annotations.get(metadata['frame_id'])
        if box is not None and (box[0]<0 or box[1]<0 or box[2]>image.shape[1] or box[3]>image.shape[0]):
            raise ValueError('manual box outside image')
        return observation(metadata,self.method,box=box,reason=None if box is not None else 'manual annotation absent')


class SSDLiteDetector:
    """TorchVision COCO_V1 detector; optional GPU backbone with explicit CPU NMS.

    TorchVision's NMS kernel is not available on MPS in the pinned build. Run the
    official model's postprocess_detections on CPU; no implicit backend fallback.
    """
    method='torchvision-ssdlite320-mobilenet-v3-large-coco-v1'
    def __init__(self, *, device='mps', category='orange', threshold=.35, cache_dir='outputs/model-cache'):
        import torch
        from torchvision.models.detection import ssdlite320_mobilenet_v3_large, SSDLite320_MobileNet_V3_Large_Weights
        if not 0<threshold<=1: raise ValueError('threshold must be in (0,1]')
        if device not in ('cpu','mps','cuda'): raise ValueError('unsupported device')
        if device=='mps' and not torch.backends.mps.is_available(): raise RuntimeError('MPS unavailable')
        if device=='cuda' and not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
        self.torch=torch; self.device=device; self.threshold=threshold
        weights=SSDLite320_MobileNet_V3_Large_Weights.COCO_V1
        if category not in weights.meta['categories']: raise ValueError('unsupported COCO category')
        self.category=category; self.label=weights.meta['categories'].index(category)
        torch.hub.set_dir(str(Path(cache_dir).resolve()))
        started=time.perf_counter()
        self.model=ssdlite320_mobilenet_v3_large(weights=weights,progress=False).eval().to(device)
        if device=='mps':
            original=self.model.postprocess_detections
            def cpu_postprocess(head_outputs, anchors, image_shapes):
                return original({k:v.cpu() for k,v in head_outputs.items()},[a.cpu() for a in anchors],image_shapes)
            self.model.postprocess_detections=cpu_postprocess
        self.sync()
        self.load_ms=(time.perf_counter()-started)*1000
    def sync(self):
        if self.device=='mps': self.torch.mps.synchronize()
        elif self.device=='cuda': self.torch.cuda.synchronize()
    def detect(self,image,metadata):
        validate_image(image)
        rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
        tensor=self.torch.from_numpy(rgb).permute(2,0,1).float().div(255).to(self.device)
        self.sync(); started=time.perf_counter()
        with self.torch.inference_mode(): result=self.model([tensor])[0]
        self.sync(); self.last_forward_ms=(time.perf_counter()-started)*1000
        labels=result['labels'].cpu().tolist(); scores=result['scores'].cpu().tolist(); boxes=result['boxes'].cpu().tolist()
        found=[(s,b) for l,s,b in zip(labels,scores,boxes) if l==self.label and s>=self.threshold]
        if not found: return observation(metadata,self.method,reason='no target above threshold')
        # Multiple plausible objects require an identity/ROI decision, never largest-score selection.
        if len(found)>1: return observation(metadata,self.method,reason='multiple target instances; identity unresolved')
        score,box=found[0]
        return observation(metadata,self.method,box=box,confidence=score)


class GroundingDinoDetector:
    """Public Apache-2.0 pretrained text detector, pinned revision, no remote code."""
    method='grounding-dino-tiny-a2bb814'
    revision='a2bb814dd30d776dcf7e30523b00659f4f141c71'
    def __init__(self, *, device='mps', category='orange', threshold=.35, cache_dir='outputs/model-cache'):
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        if not 0<threshold<=1: raise ValueError('threshold must be in (0,1]')
        if not isinstance(category,str) or not category.strip(): raise ValueError('category required')
        if device not in ('cpu','mps','cuda'): raise ValueError('unsupported device')
        if device=='mps' and not torch.backends.mps.is_available(): raise RuntimeError('MPS unavailable')
        if device=='cuda' and not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
        self.torch=torch; self.device=device; self.threshold=threshold; self.category=category
        started=time.perf_counter()
        kwargs={'revision':self.revision,'cache_dir':str(Path(cache_dir).resolve()),'token':False,'trust_remote_code':False}
        self.processor=AutoProcessor.from_pretrained('IDEA-Research/grounding-dino-tiny',**kwargs)
        self.model=AutoModelForZeroShotObjectDetection.from_pretrained('IDEA-Research/grounding-dino-tiny',**kwargs).eval().to(device)
        self.sync(); self.load_ms=(time.perf_counter()-started)*1000
    def sync(self):
        if self.device=='mps': self.torch.mps.synchronize()
        elif self.device=='cuda': self.torch.cuda.synchronize()
    def detect(self,image,metadata):
        validate_image(image)
        inputs=self.processor(images=cv2.cvtColor(image,cv2.COLOR_BGR2RGB),text=self.category.strip()+'.',return_tensors='pt').to(self.device)
        self.sync(); started=time.perf_counter()
        with self.torch.inference_mode(): outputs=self.model(**inputs)
        self.sync(); self.last_forward_ms=(time.perf_counter()-started)*1000
        results=self.processor.post_process_grounded_object_detection(outputs,inputs.input_ids,threshold=self.threshold,text_threshold=.25,target_sizes=[image.shape[:2]])[0]
        boxes=results['boxes'].cpu().tolist(); scores=results['scores'].cpu().tolist()
        # Merge duplicate predictions of the same instance only; distinct objects stay ambiguous.
        retained=[]
        for score,box in sorted(zip(scores,boxes),reverse=True):
            duplicate=False
            for _,other in retained:
                inter=max(0,min(box[2],other[2])-max(box[0],other[0]))*max(0,min(box[3],other[3])-max(box[1],other[1]))
                union=(box[2]-box[0])*(box[3]-box[1])+(other[2]-other[0])*(other[3]-other[1])-inter
                if union>0 and inter/union>.8: duplicate=True
            if not duplicate: retained.append((score,box))
        if not retained: return observation(metadata,self.method,reason='no target above threshold')
        if len(retained)>1: return observation(metadata,self.method,reason='multiple target instances; identity unresolved')
        score,box=retained[0]
        return observation(metadata,self.method,box=box,confidence=score)
