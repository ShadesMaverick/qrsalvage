# Measurement instruments

Every claim this project makes about itself was produced by one of these scripts, and every
change to the recovery path is expected to re-run the relevant one. They are instruments, not
production code: each answers one question, prints its numbers with confidence intervals where
rates are involved, and is safe to run repeatedly.

| Script | Question it answers |
|---|---|
| `difficulty.py` | How does the success rate degrade along one damage axis (contrast, curvature, resolution, stain, tear, curl, remnant, dome, worn, marker), all else held at baseline? The primary regression instrument. |
| `calibration.py` | Does the posterior mean what it says? Reliability of claimed confidence, split into border (known cells) and middle (data cells) — the split is the point. |
| `multi_image.py` | What do several photographs of one code buy over a single one, and under which fusion rule? Single images scored at the same budget, paired trials. |
| `ab_bow.py` | Flat homography against the bowed grid on curved surfaces; the flat axis is the control. |
| `ab_coherence.py` | The grid objective with and without the coherence term over the unknown cells: does listening to the middle rescue trapped descents without choosing tidy-looking wrong sizes? Result at `COHERENCE_WEIGHT` in `geometry.py`. |
| `ab_dome.py` | No bow, the tied bow and the per-edge bow on radially distorted codes -- the damage that bows opposite edges in opposite directions. Result at `geometry.refine_bow`. |
| `ab_worn.py` | Featureless patches read as confident cells against handed over as unknowns, on codes whose bottom rows are erased whole. Counts *wrong* recoveries separately, because a repair fed wrong erasure positions can produce presentable garbage. |
| `ab_marker.py` | Coloured strokes read as ink against neutralised before the channel is read; zero strokes is the control where both arms must be identical. |
| `ab_anchor.py` | One constructed third finder against the anchor sweep over its scales, on codes whose bottom rows are erased whole -- the geometry with an unwitnessed side. Counts wrong recoveries separately: a decoder given more chances to be wrong must be watched for taking them. |
| `ab_sigma.py` | The two spatial uncertainty terms on and off against localized damage (they measured useless; weights ship at zero — this is the instrument that says so). |
| `ab_robust.py` | The robust level estimate on and off against known cells that lie (torn edge, stain); the contrast axis is the control. Result at `ROBUST_LEVELS` in `sampling.py`. |
| `ab_rounds.py` | How many outlier rounds should the level fit get? The loop cannot oscillate -- it only ever removes cells -- so it spirals instead, and the cap is a stop partway down rather than a convergence. Measures whether stopping there protects or truncates, on `wrong_known` rather than the success rate. Result at `ROBUST_ROUNDS` in `sampling.py`. |
| `ab_restart.py` | The coarse restart of a badly seated grid on and off, on the axes that actually displace grids (curvature, resolution, tear); reports how often it fires, because an escalation that never triggers cannot help. Result at `geometry.restart_coarse`. |
| `ab_ensemble.py` | Single measurement against the within-image ensembles (both measured useless; documented in `ensemble.py`). |
| `runtime.py` | How long does a recovery take, and is a measured difference bigger than the noise it was measured through? Repeats each image from a cold level-fit cache, prints the spread beside the median, and refuses to call a change real when it falls inside that spread. The instrument for any claim about speed. |
| `batch.py` | Run the solver over a folder of images and tabulate outcomes. |
| `diagnose.py` | Why did a photograph fail — is the code invisible, or is the preprocessing tuned for the wrong scale? Writes the binarisations so failure can be looked at. |
| `make_fixtures.py` | Regenerate the public synthetic corpus in `fixtures/` (never edit fixtures by hand). |
| `add_private_fixture.py` | Add a real, solved photograph to the gitignored local corpus, with provenance flags. |
| `build_site.py` | What does the published static site consist of, and does any part of it reach a remote host once it is loaded? Vendors the pinned runtime into `site/`, then audits every shipped script, page and data file for absolute URLs and prints what it found. |

Reading the numbers: rates need intervals (twelve samples cannot distinguish 8 % from 33 %),
and `known cells wrong` moves before the success rate does — it is the honest metric for
sampling changes. Both points are elaborated in `CONTRIBUTING.md`.
