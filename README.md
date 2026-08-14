# qrsalvage

*recover QR codes from what's left of them*

A QR code laser-engraved onto the curved dome of a light bulb. Grey on white, roughly nine
pixels per module in the only photograph that exists of it, a glare gradient across the middle
and a yellowed stain over one corner. No phone reads it. No online decoder reads it. It took
its owner a year and a half.

qrsalvage reads codes like that.

![input, recovered matrix and re-encoded result](docs/example.png)

## What it does differently

Ordinary decoders are all-or-nothing: they binarise the image, sample a grid, and either return
a string or nothing at all. When they fail you learn nothing about why.

qrsalvage takes the problem apart:

- **It calibrates on what the standard already fixes.** In a version 3 code, 244 of the 841
  cells have a value the specification determines — finders, separators, timing, alignment.
  Their true values are known, so they can be used to measure whether the grid, the version and
  the brightness model are right. Every step is scored against them.
- **It fits the grid by search, not by formula.** A homography cannot represent a curved
  surface. So the four corners are nudged by coordinate descent until the known cells sit as
  well as they can. On the bulb photograph that took the sampling error from 18 wrong cells
  down to 2, and only then did the code decode.
- **It does not decide what it does not know.** Each module gets a probability, not a verdict.
  Cells that stay in doubt become *erasures* — and Reed-Solomon repairs twice as many erasures
  as it does errors, because their position is already accounted for.
- **It tells you how sure it is.** Every run reports how many known cells it got wrong, whether
  the timing pattern is intact, how many cells remain uncertain and what the repair had to do.

## Install

```
pip install qrsalvage
```

From source:

```
git clone https://github.com/<owner>/qrsalvage
cd qrsalvage
pip install -e .
```

Requires Python 3.11 or newer. Dependencies: NumPy, OpenCV, Pillow, zxing-cpp.

## Use

```
qrsalvage solve photo.jpg
```

That is the whole first step. If fewer than three finder patterns are found, narrow the search
with `--crop X0 Y0 X1 Y1`; the finder search does not cope well with busy backgrounds.

Generate an artificially degraded test case with a known answer:

```
qrsalvage synth "HELLO-WORLD" --contrast 0.14 --curvature 0.4
```

## Reading the output

```
chosen: version 3 (29 modules)
known cells wrong: 2 of 244 (grid fit)
timing pattern:    100.0 %
uncertain cells:   4 of 841 (band 0.15)
decode attempts:   1
```

- **The version table** above this block has to show a clear winner. If two candidates are
  close, the grid is not seated and nothing below it means anything.
- **Known cells wrong** is the one number that measures the method honestly. Below 1 % is
  healthy; above 5 % points at a geometry problem, not a contrast problem.
- **Timing pattern** below 100 % means grid drift, even when the image looks plausible.
- **Decode attempts** above 1 means the direct read failed and the repair or the ordered probe
  had to work for it.

`out/grid.txt` holds the sampled matrix as `#`, `.` and `?` — the third symbol marks cells the
tool refuses to guess. `out/clean.png` is the payload re-encoded from scratch, which is a
guaranteed-valid code rather than a reconstruction that happened to pass.

## How well it works

Measured on synthetic cases with known answers, varying contrast while holding the other damage
constant, 20 images per level. `contrast` is the fraction of full black the engraving reaches;
the real bulb photograph sits near 0.15.

| contrast | solved | rate | 95 % interval |
|---|---|---|---|
| 0.30 | 20/20 | 100 % | [84 %, 100 %] |
| 0.24 | 20/20 | 100 % | [84 %, 100 %] |
| 0.20 | 20/20 | 100 % | [84 %, 100 %] |
| 0.16 | 20/20 | 100 % | [84 %, 100 %] |
| 0.13 | 18/20 | 90 % | [70 %, 97 %] |
| 0.11 | 15/20 | 75 % | [53 %, 89 %] |
| 0.09 | 7/20 | 35 % | [18 %, 57 %] |

The fall-off is a ramp, not a cliff: between 0.16 and 0.09 the rate drops across four levels.
A single run at either end would have reported "works" or "does not work" and both would have
been true.

Reproduce with `python scripts/difficulty.py --axis contrast`. Other axes: `curvature`,
`resolution`, `stain`.

The intervals matter. Even 20 successes out of 20 only supports "at least 84 %" — a claim built
on four samples, which is what an earlier version of this table used, supports almost nothing.

## Related projects

qrsalvage is not the first tool in this space, and the honest comparison is short:

- **[QRazyBox](https://github.com/Merricx/qrazybox)** — open source, the reference tool for QR
  forensics. You transcribe the matrix by hand in a paint-like editor, then it brute-forces the
  format information and recovers data through erasures. Excellent at the analysis half; it does
  no image processing at all.
- **[QR Photo Restore](https://www.hashitosystem.com/en/tools/qr-restore/)** — closest in
  approach: flat-fielding, a binarisation sweep, a four-point homography, confidence-ranked
  erasures. Runs in the browser, free, but no source and no licence.
- **[EAN Check](https://eancheck.com/qr-code-recovery)** and commercial SDKs such as Dynamsoft
  cover similar ground behind closed doors.

What qrsalvage adds: **curved surfaces** (the others stop at a plain homography), a
**reproducible benchmark** so improvements can be quantified rather than asserted, and an open,
scriptable pipeline with a text interface that automation can drive.

## Limitations

- **QR Code only.** Not Data Matrix, Aztec or PDF417. The method generalises but each symbology
  needs its own structure model, layout and Reed-Solomon parameters.
- **Reed-Solomon repair covers versions 1 to 10.** Larger codes are read but not repaired; the
  block tables stop there.
- **No graphical interface yet.** Command line only.
- **The finder search needs a reasonably framed photograph.** It is the first thing to fail on
  cluttered backgrounds, and `--crop` is the workaround.

Known open issue: the spread of the brightness model is estimated from the known cells alone.
Those sit around the edges, so when they happen to be clean the model can be confidently wrong
about the data cells in the middle. See `docs/ISSUES.md`.

## Contributing

The test corpus in `fixtures/` is entirely synthetic and regenerated by
`python scripts/make_fixtures.py`. That is deliberate: real photographs of damaged QR codes are
almost always personal, and the decoded content is frequently a secret. Please do not add real
photographs to the repository.

```
pip install -r requirements.txt
ruff check . && ruff format --check .
pytest                      # everything
pytest -m "not regression"  # fast
```

If you change anything in the recovery path, run `python scripts/difficulty.py` before and
after. A change that cannot be measured is a change that cannot be reviewed.

## Licence

Apache License 2.0. See [LICENSE](LICENSE).
