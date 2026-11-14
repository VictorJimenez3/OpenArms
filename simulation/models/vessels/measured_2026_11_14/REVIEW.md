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
