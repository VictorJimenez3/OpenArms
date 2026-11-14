# First-release review receipt

Requirement: D1 geometric reference for simulation, issue #19. User explicitly prioritized the checked model package on main before broader runtime changes. Producer: nine user photographs, independent image audit and parameter generator. Consumer: later two-vessel scene integration. Baseline: main `4c00909`; calibration, trajectories, shared simulator configuration and docks unchanged.

Independent reviewer: external Codex Account 2, separate context; actual model identifier was not exposed. Worker completed successfully (exit 0). Review verdict: **defensible for an isolated first photo-derived release; no blocking findings**.

- Four focused tests passed independently.
- Rebuilt OBJ/STL/XML/summary matched supplied assets byte for byte.
- All nine original HEIC hashes matched.
- Closed oriented meshes, positive signed material volume, no degenerate triangles, metre units and support-plane origins verified.
- Additional MuJoCo rays: 24/24 per vessel reached the declared floor.
- Volume integration and evidence-bound uncertainty checked.
- P3 fixed preview captions corrected: labels now derive from the chosen parameter file, including custom `--parameters` input. Parent reran focused checks and rendered previews after the correction.

Remaining gaps are explicitly represented: photograph perspective, direct dimensions, hidden interior geometry, material/contact properties, capacity and physical qualification. No exact manufacturer identification and no licensed external CAD incorporated. This review does not certify physical grasp, clearance, pouring or kit chemistry.

## Receiver refinement review

Five additional source photos (9267–9271) were inspected. Two separate Account 2 metrology passes support rim OD **78 mm [75–82]** and outside height **32 mm [30–35]**. Upright/inverted side-plane estimates are approximately 33/31 mm. The proposed lower-body envelope remains 59 mm [54–66]; hidden internal thickness is not promoted to measured fact.

The refinement reviewer checked coherent profiles, matching OBJ extents (78 × 78 × 32 mm), parameter-summary hash, conditional cavity volume 110.23 mL and four passing geometry tests. Its publication finding was stale README values and missing new coordinates: corrected with the updated dimension/volume table, superseded-reading explanation, three annotated crops and pixel endpoints. No active scene, calibration, poses or dock configuration changed.

The initial model package is on main at `e3c1b9c`. Revision 2 and catalog notes are presented in PR #24 for the current main owner, Victor. The shared-scene assignment was withdrawn after the ownership update at `d074f0a`; scene hookup belongs to Stefanie, with Victor integrating. This does not imply the live robot scene has adopted these profiles.
