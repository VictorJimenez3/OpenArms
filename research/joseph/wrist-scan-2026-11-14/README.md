# Wrist-camera aerial scan

The supervised November 14 sweep captured six wrist-camera views and returned to the taught HOME. The [capture receipt](evidence/supervised-aerial-capture.json), [annotated ruler view](aerial-vessel-locations.png), and [condensed video](aerial-scan.mp4) describe the run. The video is the previously published replay from `f862596`.

All six views registered into a mosaic. The vessel-base estimates were **A (23.7, 7.7) cm** and **C (6.2, 7.0) cm** in tabletop ruler coordinates. The maximum error on four ruler check ticks was 0.05 cm. The [registration receipt](evidence/supervised-aerial-registration.json) and [vessel estimates](evidence/supervised-aerial-vessel-locations.json) record the image measurements. Physical localization accuracy, robot-base registration, grasp, and pour qualification remain open.

The [offline programs](programs/) stitch saved views, compare overlap, estimate ruler-plane positions, and render the replay. The [route comparison](evidence/aerial-route-ablation.json) checks image overlap after removing individual views. Reproduction uses OpenCV, NumPy, and the saved inputs from the local research archive. The raw takes, physical capture scripts, and full evaluation data are retained in that archive.
