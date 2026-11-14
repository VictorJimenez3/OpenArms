import numpy as np
import pytest
from bench_vision.perception import HSVBaseline, ManualBox, observation
from bench_vision.benchmark import iou, load_case

META={'object_id':'orange','camera_id':'overview','frame_id':'f1','timestamp_s':1.0,'calibration_id':None}

def test_unknown_blank_and_detection_no_geometry():
    image=np.zeros((100,100,3),np.uint8)
    assert HSVBaseline().detect(image,META)['status']=='unknown'
    image[20:50,20:50]=[0,128,255]
    found=HSVBaseline().detect(image,META)
    assert found['status']=='ok' and found['geometry_valid'] is False
    assert found['confidence'] is None and found['grasp_pose'] is None
    assert found['box_xyxy']==[20,20,50,50]

def test_similar_color_distractor_returns_unknown():
    image=np.zeros((100,100,3),np.uint8)
    image[10:30,10:30]=[0,128,255]; image[60:80,60:80]=[0,128,255]
    assert 'multiple' in HSVBaseline().detect(image,META)['unknown_reason']

def test_manual_annotation_and_missing():
    detector=ManualBox({'f1':[1,2,10,20]})
    assert detector.detect(np.zeros((30,30,3),np.uint8),META)['box_xyxy']==[1,2,10,20]
    assert ManualBox({}).detect(np.zeros((30,30,3),np.uint8),META)['status']=='unknown'

@pytest.mark.parametrize('box',[[1,1,1,1],[1,1,float('nan'),5],[1,2,3]])
def test_bad_boxes(box):
    with pytest.raises(ValueError): observation(META,'manual',box=box)

def test_unknown_legacy_timestamp_explicit():
    meta={**META,'timestamp_s':None}
    assert observation(meta,'legacy')['alignment_known'] is False
    with pytest.raises(ValueError): observation({**META,'timestamp_s':float('nan')},'bad')

def test_iou_and_no_target():
    assert iou([0,0,2,2],[0,0,2,2])==1
    assert iou([0,0,2,2],[1,1,3,3])==pytest.approx(1/7)
    assert iou(None,[0,0,1,1])==0

def test_path_escape(tmp_path):
    with pytest.raises(ValueError): load_case({'image':'../secret.jpg'},tmp_path)

def test_hsv_cannot_identify_cup():
    image=np.zeros((100,100,3),np.uint8); image[20:50,20:50]=[0,128,255]
    assert HSVBaseline().detect(image,{**META,"object_id":"cup"})["status"]=="unknown"
