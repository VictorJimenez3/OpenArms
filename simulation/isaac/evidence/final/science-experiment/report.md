# Mass versus weight — SIMULATED

Measured signed +Z receiver normal force, final closed 1.0 s of settle (121 raw samples at 120 Hz).

| Condition | Mass (kg) | Mean force (N) | Population std (N) | Min–max (N) | Analytic m·g (N) | Relative error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| light | 0.010 | 0.098099999 | 7.221e-08 | 0.098099723–0.09810067 | 0.0981 | 0.000% |
| heavy | 0.040 | 0.39239999 | 7.137e-08 | 0.39239988–0.39240015 | 0.3924 | 0.000% |

Measured heavy/light force ratio: **4**. Known mass ratio and analytic weight prediction: **4×**; relative ratio error 0.000%.

Source commit, robot asset hash, scene, gravity, geometry, friction and protocol match. Only mass/condition vary; measured runtime FK diagnostics are excluded from matching.

- light: `/Users/joeroche/Documents/Codex/2026-11-14/you-are-the-isaac-sim-runtime/outputs/evidence/job-1273420-light-20261114T153654Z-3955123/recording`; 121 samples from 23.00000120 to 24.00000125 sim s; host `rlab7.cs.rutgers.edu`; receipt SHA256 `dbcf84e678bedd63c3949deca09d1e2b65c2d71eaae1389714886455df85c65f`.
- heavy: `/Users/joeroche/Documents/Codex/2026-11-14/you-are-the-isaac-sim-runtime/outputs/evidence/job-1273420-heavy-20261114T153817Z-3955121/recording`; 121 samples from 23.00000120 to 24.00000125 sim s; host `rlab7.cs.rutgers.edu`; receipt SHA256 `5ce256e82553f4b43fb8b762dca4bce92dfb1b58638cd4177c1efdc6eee92465`.

Source commit: `6afba01407b8036a0a22d5d8d6f261ac26424051`.

Full artifact paths, SHA256 values, GPU details and control metadata are in report.json.

Analytic m·g values are predictions, separate from recorded forces. No failed samples are discarded.

- Simulated contact-force measurements; no physical robot or laboratory outcome established.
- One trial per condition does not establish repeatability or statistical significance.
- Artifact hashes are checked against the receipt, not independently authenticated.
- Video visual review remains required; this helper audits numeric evidence.
