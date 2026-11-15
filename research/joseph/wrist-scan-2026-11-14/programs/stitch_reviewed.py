"""Build a ruler-overlap mosaic using only this sweep's newly acquired files."""
from pathlib import Path
import json
import cv2
import numpy as np

root = Path(__file__).resolve().parent
captures = json.loads((root / "capture-finished.json").read_text())
if captures["status"] != "complete":
    raise SystemExit("Sweep did not reach a reviewed completion.")
latest_views = {int(name.split("-")[3]): name for name in sorted(captures["frames"])}
frames = {n: cv2.imread(str(root / name)) for n, name in latest_views.items()}
if 716 not in frames or any(im is None for im in frames.values()):
    raise SystemExit("Fresh center view is missing or an image could not be read.")
anchor = 716
cv2.setNumThreads(4)
sift = cv2.SIFT_create(nfeatures=4000, contrastThreshold=.013)
local = cv2.createCLAHE(clipLimit=2.5,tileGridSize=(10,10))
features = {n:sift.detectAndCompute(local.apply(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)),None)
            for n,im in frames.items()}
matcher = cv2.BFMatcher(cv2.NORM_L2)
height,width = frames[anchor].shape[:2]

def match(a,b):
    left, ld = features[a]
    right, rd = features[b]
    if ld is None or rd is None:
        return None
    def neighbors(x,y):
        return {m.queryIdx:m.trainIdx for pair in matcher.knnMatch(x,y,k=2) if len(pair)==2
                for m,n in [pair] if m.distance < .75*n.distance}
    ab, ba = neighbors(ld,rd), neighbors(rd,ld)
    pairs = [(a,b) for a,b in ab.items() if ba.get(b)==a]
    if len(pairs) < 25:
        return None
    x = np.float32([left[a].pt for a,b in pairs])
    y = np.float32([right[b].pt for a,b in pairs])
    h,m = cv2.findHomography(x,y,cv2.USAC_MAGSAC,2.5,maxIters=6000,confidence=.999)
    if h is None:
        return None
    inlier = m.ravel().astype(bool)
    count = int(inlier.sum())
    spread = cv2.contourArea(cv2.convexHull(y[inlier]))/(width*height) if count > 2 else 0
    if count < 25 or spread < .07 or count/len(pairs) < .45:
        return None
    median = float(np.median(np.linalg.norm(cv2.perspectiveTransform(x[None],h)[0][inlier]-y[inlier],axis=1)))
    return h,{"inliers":count,"coverage":spread,"median_error_px":median,"matches":len(pairs)}

transforms = {anchor:np.eye(3)}
receipts = {anchor:{"reference":True}}
for _ in range(len(frames)):
    carry = []
    for n in frames:
        if n in transforms:
            continue
        for dest in transforms:
            result=match(n,dest)
            if result:
                transform,quality=result
                carry.append((dest==anchor,quality["inliers"],n,dest,transform,quality))
    if not carry:
        break
    _,_,n,dest,h,quality=max(carry,key=lambda row:row[:2])
    transforms[n]=transforms[dest]@h
    receipts[n]={"target":dest,**quality}

corners=np.float32([[[0,0],[width-1,0],[width-1,height-1],[0,height-1]]])
boxes=np.vstack([cv2.perspectiveTransform(corners,h)[0] for h in transforms.values()])
lo=np.floor(boxes.min(axis=0)).astype(int)
hi=np.ceil(boxes.max(axis=0)).astype(int)
size=tuple(map(int,hi-lo+1))
if min(size) <= 0 or size[0]>3*width or size[1]>3*height:
    raise SystemExit("Fresh image registration projects outside reasonable mosaic dimensions.")
shift=np.float64([[1,0,-lo[0]],[0,1,-lo[1]],[0,0,1]])
canvas=np.zeros((*size[::-1],4),np.uint8)
for n in [n for n in sorted(transforms) if n != anchor] + [anchor]:
    h=shift@transforms[n]
    rgb=cv2.warpPerspective(frames[n],h,size)
    valid=cv2.warpPerspective(np.full((height,width),255,np.uint8),h,size,flags=cv2.INTER_NEAREST)>0
    canvas[valid,:3]=rgb[valid]
    canvas[valid,3]=255

file = root/"fresh-overhead.png"
cv2.imwrite(str(file),canvas)
resize = min(1,1400/canvas.shape[1],1000/canvas.shape[0])
cv2.imwrite(str(root/"fresh-overhead-review.png"),cv2.resize(canvas,None,fx=resize,fy=resize,interpolation=cv2.INTER_AREA))
(root/"fresh-registration.json").write_text(json.dumps({
    "inputs":[latest_views[n] for n in sorted(frames)], "registered":sorted(transforms), "approach": "fresh image reciprocal feature registration",
    "checks":receipts, "image_to_mosaic":{n:(shift@h).tolist() for n,h in transforms.items()},
    "source":"fresh physical wrist views",
    "scope":"visual mosaic; no image-to-robot-base transform",
},indent=2)+"\n")
print(file, "registered frames", sorted(transforms))
