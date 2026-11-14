# Offline perception and policy checks

These modules never import an arm driver or activate a skill. The actual-cup dataset is missing. The recorded benchmark uses four saved mandarin stills from the existing bench, with clearly marked software transformations. It establishes image-processing behavior only.

## Reproduce in an isolated environment

From the repository root (Python 3.12):

```sh
python3.12 -m venv outputs/models-env
outputs/models-env/bin/pip install -r bench_vision/requirements-models.txt pytest==8.4.2
outputs/models-env/bin/python -m pytest bench_vision/tests/test_perception.py bench_vision/tests/test_policy.py -q
outputs/models-env/bin/python -m bench_vision.benchmark bench_vision/evidence/models/dataset.json \
  --root /path/to/recorded/mandarin-bench --out outputs/comparison-new.json \
  --device mps --model grounding-dino --repeats 3
```

Use `--device cuda` on a separately provisioned CUDA host or `--device cpu` for CPU. The selected device must exist; there is no silent GPU-to-CPU fallback. Grounding DINO downloads roughly 690 MB into `outputs/model-cache`, with a pinned revision and no remote-code execution or credentials. SSDLite (`--model ssdlite`) downloads 14 MB. For SSDLite on MPS only, the convolutional backbone/head use the GPU and the official TorchVision postprocessor explicitly uses CPU NMS because the pinned MPS backend lacks that kernel. CPU NMS transfer is included in latency. No network inference or upload is used.

The raw input JPEGs are intentionally not committed. The dataset lists their SHA256 values and every deterministic transform. Supply the original files to rerun the exact comparison; changed bytes reject. A fresh checkout can still run all unit tests and use its own dataset manifest.

`HSVBaseline.detect(image_bgr, metadata)`, `ManualBox(annotations).detect(...)`, `SSDLiteDetector(...).detect(...)`, and `GroundingDinoDetector(...).detect(...)` return the same observation schema. Required metadata: object_id, camera_id, frame_id. Include timestamp_s and calibration_id, or null explicitly for legacy stills. Detection outputs contain box_xyxy, optional pixel point, confidence (null for HSV), unknown reason, method and provenance. These points are box centers or color centroids, **never calibrated table-contact points, cup rims, or grasp poses**. Multiple plausible targets return unknown until an external identity decision. HSV is only an orange-color heuristic, not a generic cup detector.

## Evidence and interpretation

See `evidence/models/dataset.json`, `comparison.json`, `comparison-grounding-dino.json`, `access.json`, `policy_metadata.json`, and `policy_preflight.json`. An agent drew the boxes from 480×640 images before running the detectors; independent human annotation review is pending. The loader applies exactly the same resize to each method. Twelve positive cases derive from only three source images. Four negative/unknown cases derive from one no-visible-orange image and a synthetic blank. Dark, gray and partial-occlusion transformations are correlated stress tests, not independently collected trials. No training or threshold fitting used these examples. The score thresholds were fixed at 0.35 (box) and 0.25 (Grounding DINO text) before inference.

Timing covers original JPEG read/decode, resizing, preprocessing, model computation, synchronization and postprocessing. Detector-only and end-to-end times are separate. Original JPEGs are 4–7 MB; decoding often dominates the small-detector time. Model load/download is separate, and the first inference is recorded as cold. Warm medians/tails use repeats 2–3. Repetition measures latency, not additional accuracy evidence. No physical success, camera alignment, liquid outcome, metric accuracy, policy rollout, or training claim follows from these tests.

## Measured result (Apple M2, 2026-11-14)

| Method | Positive cases IoU ≥0.5 (12) | Negative false positives (4) | Warm end-to-end median / p95 | Warm detector median |
| --- | ---: | ---: | ---: | ---: |
| HSV orange baseline | 1 | 1 | 74 / 81 ms | 0.48 ms |
| SSDLite COCO_V1, MPS + CPU NMS | 1 | 0 | 103 / 112 ms | 29.8 ms |
| Grounding DINO tiny, MPS | 10 | 0 | 1602 / 1802 ms | 1503 ms |

Grounding DINO found all three original visible oranges and their dark/grayscale variants. It returned unknown on two partial-occlusion cases (`A-before-occlude`, `C-before-occlude`), and rejected every negative case. HSV confused the orange table edge with an object in a negative scene and a partial-occlusion scene. This supports Grounding DINO for asynchronous keyframe inspection while retaining explicit unknown behavior. Its ~1.6-second local latency is inappropriate for servo ticks. Actual-cup data and a larger independently annotated scene set are still required before promotion. SSDLite offers insufficient recall and is not selected. `summary.json` preserves the small sample size and case failures; repeats do not multiply accuracy evidence.

## Policy preparation

```sh
outputs/models-env/bin/python -m bench_vision.policy check policy-manifest.json target-conventions.json
outputs/models-env/bin/python -m bench_vision.policy training episode-index.json
```

Blocked preflight exits 2. `check_compatibility` requires exact joint names/order, units, absolute/delta mode, camera keys, finite normalization, horizon/dimension, target limits, embodiment identity and a reviewed mapping receipt. `denormalize_actions` checks the entire chunk shape, normalized range and every denormalized target limit. It returns arrays only and has no executor. `training_preflight` requires distinct aligned physical episodes with observed task outcome, episode-level train/validation splits and disjoint position groups; no adjacent-frame splitting. Metadata compatibility is never physical authorization.

MolmoAct2 SO100_101 metadata is publicly accessible, and its config/norm stats were actually inspected. It declares six named dimensions, absolute joint pose, a 30-step horizon, padded dimension 32 and q01/q99 normalization. Its metadata has empty camera keys and does not establish this Hiwonder robot's joint units/signs/offsets. Thus the checker rejects the current setup. No large policy weights were downloaded and no policy inference/training ran. There are zero aligned actual-cup teaching episodes in the inspected input set. ACT/SmolVLA training remains deferred until task data and a held-out split exist; the generic manifest/array preflight is ready for their exported conventions.

SAM3 anonymous config GET and weight HEAD returned HTTP 401. No local Hugging Face token was available at the follow-up check. This establishes unavailable access in this environment, not that no human account has approval. The official SAM3 repository requires checkpoint approval and CUDA ≥12.6; the tested host is an Apple M2 with MPS, not CUDA. No project-specific Blackwell host was supplied. Unrelated SSH aliases were not used. Grounded-SAM-2 segmentation and SAM3 remain deferred; Grounding DINO supplies an accessible useful open-vocabulary detection comparison independently.

## Attribution and original contribution

Original OpenArms contributions: observation adapters, conservative ambiguity handling, frozen stress manifest, shared benchmark/timing/error reporting, and policy convention/array/data checks. No whole upstream project or motor driver was copied. No model weights or source images are redistributed.

- [TorchVision SSDLite](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.ssdlite320_mobilenet_v3_large.html), TorchVision 0.23.0/Torch 2.8.0, COCO_V1 weights. [TorchVision BSD-3-Clause license](https://github.com/pytorch/vision/blob/v0.23.0/LICENSE); training dataset attribution is COCO. Weight SHA256: `a79551df90c79834bcd3bb3845ef9d966b5449a3a9b2833ae8404778ca5d65d2`.
- [IDEA-Research Grounding DINO tiny](https://huggingface.co/IDEA-Research/grounding-dino-tiny), revision `a2bb814dd30d776dcf7e30523b00659f4f141c71`, Apache-2.0; [official source/license](https://github.com/IDEA-Research/GroundingDINO). Used through Transformers 4.57.3, Apache-2.0, [official API documentation](https://huggingface.co/docs/transformers/model_doc/grounding-dino).
- [OpenCV](https://github.com/opencv/opencv/blob/4.12.0/LICENSE), 4.12.0, Apache-2.0; NumPy 2.2.6, BSD-3-Clause. Dependency licenses remain in installed distributions.
- [Ai2 MolmoAct2](https://github.com/allenai/molmoact2), metadata only from [SO100_101 revision 152569fe57914d97be91055800035f54e250d009](https://huggingface.co/allenai/MolmoAct2-SO100_101/tree/152569fe57914d97be91055800035f54e250d009). No source or weights imported. See upstream license before any later distribution.
- [Meta SAM3](https://github.com/facebookresearch/sam3), access/runtime prerequisites inspected; no code/weights used.

Existing project evidence: [wet-lab scope](../docs/WET_LAB.md), [research index](../research/README.md), [mandarin handoff](../research/joseph/mandarin-transfer-handoff.md). Existing mandarin results are preserved; this benchmark does not rerun physical experiments.
