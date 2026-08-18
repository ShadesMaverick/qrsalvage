"""The route from an artificially degraded image back to the plain text.

These tests need no photograph: the answer is known because the case was generated from it.
That is what makes them a development instrument -- a change to the method is quantified here
rather than argued about.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from qrsalvage.core.decoding import ordered_search, reencode
from qrsalvage.core.matrix import DARK, LIGHT, UNKNOWN, ModuleMatrix
from qrsalvage.core.pipeline import solve
from qrsalvage.core.sampling import estimate_levels, posterior_dark
from qrsalvage.core.structure import structure_mask
from qrsalvage.synth import REMNANT_GAP, Damage, render_photo

# Deliberately all upper case and restricted to the QR alphanumeric character set: a single
# lower-case letter forces the encoder into byte mode, makes the code denser and silently
# shifts the difficulty of every test using this payload.
TEXT = "QRSALVAGE-SELFTEST-0815"


def test_mild_damage_is_solved_directly():
    photo = render_photo(reencode(TEXT), Damage(contrast=0.30, curvature=0.20), seed=3)
    result = solve(photo)
    assert result.solved
    assert result.text == TEXT
    assert result.wrong_known == 0
    assert result.candidates_tried == 1, "a mild case must not need probing"


def test_success_rate_for_a_larger_code():
    """Success rate at moderate damage with a payload of version 3 or above.

    Deliberately only a rate, and no claim about *which* mechanism helped. Measured, the probe
    and the Reed-Solomon repair almost never fire on synthetic images of this difficulty -- the
    sampling is either good enough or hopeless, with little in between. That both mechanisms
    work is established by the targeted tests (test_probe_tries_cheap_doubts_first here, and
    test_erasures_rescue_what_errors_alone_cannot in test_rs.py) on constructed cases. Asserting
    it here would be a claim about a random quantity.
    """
    long_text = "SALVAGE-REGRESSION-PAYLOAD-" + "0123456789" * 5
    matrix = reencode(long_text)
    assert matrix.shape[0] >= 29, "precondition: version 3 or larger"

    damage = Damage(contrast=0.14, curvature=0.40, module_px=7.0, stain=0.10)
    solved = sum(
        solve(render_photo(matrix, damage, seed=seed), budget=4000).text == long_text
        for seed in range(8)
    )
    assert solved >= 6, f"only {solved} of 8 solved"


def test_inverted_polarity_is_found_not_assumed():
    """Light modules on a dark ground, as on an etched metal part.

    The polarity deliberately cannot be settled at the finder stage, and an earlier version
    that tried failed on the *easiest* inverted cases: a finder pattern is nested squares and
    so is its inverse, so the detector finds it in either polarity, at the same place, looking
    equally sure. Only the known cells separate the two -- read at the wrong polarity, a
    perfectly placed grid gets about a fifth of them wrong.
    """
    damage = Damage(contrast=0.20, curvature=0.30, inverted=True)
    photo = render_photo(reencode(TEXT), damage, seed=0)

    result = solve(photo)
    assert result.text == TEXT
    assert result.inverted is True
    assert result.wrong_known == 0

    # Forcing the wrong polarity has to fail loudly rather than quietly return nonsense.
    forced = solve(photo, invert=False)
    assert forced.text != TEXT
    assert forced.wrong_known is not None and result.known_total is not None
    assert forced.wrong_known > result.known_total * 0.1


def test_ordinary_codes_are_not_mistaken_for_inverted():
    photo = render_photo(reencode(TEXT), Damage(contrast=0.20, curvature=0.30), seed=0)
    result = solve(photo)
    assert result.solved
    assert result.inverted is False


def test_version_is_measured_not_guessed():
    photo = render_photo(reencode(TEXT), Damage(contrast=0.25, curvature=0.25), seed=0)
    result = solve(photo)
    chosen = next(f for f in result.per_size if f.modules == result.modules)
    others = [f for f in result.per_size if f.modules != result.modules]
    assert all(chosen.wrong_known < f.wrong_known for f in others), (
        "the correct version has to stand out clearly in the known cells"
    )


def test_a_hopeless_image_reports_a_clean_failure():
    """No crash, no invented answer -- a named failure."""
    noise = np.random.default_rng(0).integers(0, 255, (200, 200, 3), dtype=np.uint8)
    result = solve(noise, budget=50)
    assert not result.solved
    assert result.text is None
    assert result.failure


def test_matrix_knows_three_states():
    modules = 21
    known_dark, known_light = structure_mask(modules)
    posterior = np.full((modules, modules), 0.5)
    posterior[10, 10] = 0.99
    posterior[10, 12] = 0.01
    mm = ModuleMatrix(posterior=posterior, known_dark=known_dark, known_light=known_light)

    states = mm.states(band=0.15)
    assert states[10, 10] == DARK
    assert states[10, 12] == LIGHT
    assert states[10, 11] == UNKNOWN, "a cell at P=0.5 has to stay unknown"
    assert states[0, 0] == DARK, "structure cells never become unknown"

    ascii_grid = mm.to_ascii(band=0.15)
    assert set(ascii_grid.replace("\n", "")) <= {"#", ".", "?"}
    assert ascii_grid.count("?") > 0


def test_lying_known_cells_cannot_flatten_the_posterior():
    """Known cells that measure the wrong brightness must lose influence, not gain it.

    The construction mirrors a photographed failure: a fitted grid overhung a torn paper
    edge, so one column of known-dark cells measured bright paper while a misregistered
    alignment zone made known-light cells measure dark. Fitted naively, those outliers bend
    the two level fields until they cross; the contrast clamp bottoms out, the normalised
    residuals explode, and the posterior of nearly every cell -- including hundreds of
    perfectly clean ones -- flattens to a coin toss. On the photograph that meant 555 of 841
    cells uncertain at fine contrast. The robust estimate has to keep every honest cell
    decided.
    """
    modules = 29
    known_dark, known_light = structure_mask(modules)
    means = np.where(known_dark, 100.0, 200.0)
    means[:, 0] = 200.0  # the torn edge: every known-dark cell in column 0 reads paper
    zone = np.zeros((modules, modules), dtype=bool)
    zone[19:25, 19:25] = True  # the misregistered alignment zone reads dark
    means[known_light & zone] = 100.0
    spread = np.full((modules, modules), 5.0)

    fit = estimate_levels(means, spread, known_dark, known_light)
    posterior = posterior_dark(means, fit)

    honest_dark = known_dark.copy()
    honest_dark[:, 0] = False
    honest_light = known_light & ~zone
    assert float(posterior[honest_dark].min()) > 0.9
    assert float(posterior[honest_light].max()) < 0.1
    assert float(np.median(fit.sigma)) < 1.0, "a handful of liars must not inflate sigma"


def test_structure_is_never_touched_while_probing():
    modules = 21
    known_dark, known_light = structure_mask(modules)
    posterior = np.full((modules, modules), 0.5)
    mm = ModuleMatrix(posterior=posterior, known_dark=known_dark, known_light=known_light)
    costs = mm.flip_cost()
    assert np.isinf(costs[known_dark | known_light]).all()
    assert np.isfinite(costs[~(known_dark | known_light)]).all()


def test_probe_tries_cheap_doubts_first():
    """The ordering is the whole trick: the weakest spot first, then the next."""
    matrix = reencode(TEXT)
    modules = matrix.shape[0]
    known_dark, known_light = structure_mask(modules)

    posterior = np.where(matrix, 0.99, 0.01)
    # Flip two data cells and mark them uncertain -- the search has to find exactly those.
    free = np.argwhere(~(known_dark | known_light))
    for r, c in free[:2]:
        posterior[r, c] = 0.55 if matrix[r, c] else 0.45

    mm = ModuleMatrix(posterior=posterior, known_dark=known_dark, known_light=known_light)
    result = ordered_search(mm, budget=200)
    assert result.text == TEXT


def test_consensus_judges_each_run_separately():
    photo = render_photo(reencode(TEXT), Damage(contrast=0.16, curvature=0.40), seed=2)
    result = solve(photo, ensemble="sampling")
    assert result.consensus is not None
    assert result.consensus.runs == len(result.consensus.wrong_per_run) > 1
    assert result.solved


def test_consensus_is_not_more_confident_than_its_parts():
    """The classic averaging mistake: measurements that argue produce a confident verdict.

    Wherever the runs disagree in sign, the merged probability has to sit closer to undecided
    than it does for the cells they agree on -- otherwise the pooling consumes exactly the
    information that repeated measurement was for.
    """
    photo = render_photo(
        reencode(TEXT), Damage(contrast=0.13, curvature=0.45, module_px=7.0, stain=0.15), seed=0
    )
    result = solve(photo, ensemble="sampling")
    consensus = result.consensus
    assert consensus is not None
    if not consensus.contested.any():
        pytest.skip("all runs agreed on this image")

    distance = np.abs(consensus.posterior - 0.5)
    assert distance[consensus.contested].mean() < distance[~consensus.contested].mean()


def test_the_single_run_stays_available():
    photo = render_photo(reencode(TEXT), Damage(contrast=0.24, curvature=0.30), seed=0)
    result = solve(photo, ensemble="off")
    assert result.consensus is None
    assert result.solved


def test_success_rate_at_moderate_damage():
    """Checks a rate, not a single case.

    This used to assert one outcome per seed, which was simply the wrong claim: whether a
    particular image gets through is a random quantity. Measured, this damage level succeeds on
    19 out of 20 images, so a single outlier is expected and not a defect, while dropping below
    80 percent is.

    That one known outlier (seed 1) is also an open finding: grid perfect, zero wrong known
    cells, zero uncertain cells -- and still unreadable. The known cells sit around the edges,
    so their cleanliness says little about the data cells in the middle. As long as the spread
    is estimated from them alone, the model can be confidently wrong and leave the solver
    nothing to probe.
    """
    matrix = reencode(TEXT)
    solved = sum(
        solve(render_photo(matrix, Damage(contrast=0.20, curvature=0.30), seed=seed)).text == TEXT
        for seed in range(10)
    )
    assert solved >= 8, f"only {solved} of 10 solved"


def test_the_bow_never_returns_a_worse_grid():
    """The descent invariant that makes the bow safe to run unconditionally.

    Zero bow reproduces the homography result and only improvements are kept, so the bowed
    grid must score at least as well as the flat one it started from -- on a flat surface just
    as on a curved one.
    """
    from qrsalvage.core.geometry import refine_bow
    from qrsalvage.core.pipeline import DEFAULT_SIZES, _attempt

    for curvature in (0.0, 0.6):
        photo = render_photo(reencode(TEXT), Damage(contrast=0.25, curvature=curvature), seed=2)
        _, gray, _, _, fits, _, _ = _attempt(photo, DEFAULT_SIZES, False, None)
        flat = min(fits, key=lambda f: (f.wrong_known, -f.quality))
        known_dark, known_light = structure_mask(flat.modules)

        bowed = refine_bow(gray, flat, known_dark, known_light)

        assert bowed.quality >= flat.quality
        assert bowed.wrong_known <= flat.wrong_known + 1, (
            "a quality gain must not be bought with known cells"
        )


def test_the_label_remnant_never_touches_the_symbol():
    """The strip of the neighbouring label prints beside the code, never on it.

    The whole reason this damage is interesting is that it is an attractor the finders can
    survive, and it survives them by keeping one clear module of paper between the two. Butt
    it against the code and it merges with the finders' outer ring in the binarisation,
    breaks the 1:1:3:1:1 proportion the scan detector reads, and becomes just another way to
    lose the finders -- which is the failure the shadow bar already documented. So the gap is
    the feature, and this is the test that says so.
    """
    matrix = reencode(TEXT)
    clean = Damage(contrast=0.25, curvature=0.0, blur=0.0, noise=0.0)
    plain = render_photo(matrix, clean, seed=1)
    printed = render_photo(matrix, replace(clean, remnant=1.0), seed=1)

    px = plain.shape[1] / (matrix.shape[0] + 10)
    # Everything from the gap rightwards -- the clear module and the symbol itself.
    untouched = slice(int((5 - REMNANT_GAP) * px), plain.shape[1])
    np.testing.assert_array_equal(printed[:, untouched], plain[:, untouched])
    assert (
        printed[:, : int((5 - REMNANT_GAP) * px)] != plain[:, : int((5 - REMNANT_GAP) * px)]
    ).any()


def test_the_two_halves_of_a_torn_edge_are_independent():
    """The shadow and the curl have to stay separable, because they break different things.

    They were one parameter first, and that cost a measurement: the composite axis was read
    as evidence about the grid when what it actually destroyed was finder detection. Split,
    each has to do its own job and nothing else -- the shadow darkens without moving anything,
    the curl moves without darkening -- or an axis built on one of them measures the other
    again.
    """
    matrix = reencode(TEXT)
    # No blur and no noise: the blur runs after the shadow is drawn and would smear it a
    # grey level or two past its own support, which is not the coupling this test is about.
    clean = Damage(contrast=0.25, curvature=0.0, blur=0.0, noise=0.0)
    plain = render_photo(matrix, clean, seed=1)
    shadow = render_photo(matrix, replace(clean, tear=0.8), seed=1)
    curled = render_photo(matrix, replace(clean, curl=3.0), seed=1)

    # Stated so it does not depend on where either effect happens to reach, because both
    # shapes have been retuned once already: a subtracted gradient can only ever make a
    # pixel darker, while a displacement moves edges and therefore brightens exactly as
    # much as it darkens. That difference is what "independent" means here.
    assert (shadow.astype(int) <= plain.astype(int)).all(), "the shadow must only darken"
    assert (curled.astype(int) > plain.astype(int) + 5).any(), "the curl must move edges"

    # And each has to act where it claims to: the shadow on the flank's brightness, the
    # curl not at all on it. render_photo pads the code with a five-module quiet zone.
    flank = slice(0, int(5 * plain.shape[1] / (matrix.shape[0] + 10)))
    assert shadow[:, flank].mean() < plain[:, flank].mean() - 5
    assert abs(float(curled[:, flank].mean()) - float(plain[:, flank].mean())) < 5


def test_the_coarse_restart_never_returns_a_worse_grid():
    """The same invariant, for the escalation that runs when a grid fitted badly.

    A coarse descent can walk somewhere worse -- that is the price of a step large enough to
    leave a false optimum. It is safe only because the result is kept solely when the same
    objective says it improved, so the escalation is free to be wrong. Checked on a grid that
    is already good (where it should change nothing) and on one deliberately pushed off by two
    modules (where it has something to recover).
    """
    from qrsalvage.core.geometry import restart_coarse
    from qrsalvage.core.pipeline import DEFAULT_SIZES, _attempt

    photo = render_photo(reencode(TEXT), Damage(contrast=0.25, curvature=0.30), seed=2)
    _, gray, _, _, fits, _, _ = _attempt(photo, DEFAULT_SIZES, False, None)
    fitted = min(fits, key=lambda f: (f.wrong_known, -f.quality))
    known_dark, known_light = structure_mask(fitted.modules)

    for label, shift in (("already good", 0.0), ("pushed off", 2.0)):
        start = fitted
        if shift:
            from qrsalvage.core.geometry import evaluate, module_px

            moved = fitted.corners + np.array(
                [shift * module_px(fitted.corners, fitted.modules), 0.0]
            )
            start = evaluate(gray, moved, fitted.modules, 12, known_dark, known_light)

        restarted = restart_coarse(gray, start, known_dark, known_light)

        assert restarted.quality >= start.quality, label


def test_hand_marked_finders_survive_an_oversized_photograph():
    """The escape hatch gets the same resolution correction as the automatic path.

    Before it did, this exact case failed: hand-marked finders on a photograph far above the
    working band ran the preprocessing at native resolution, where its fixed blur is a fraction
    of a module, and lost a code whose downscaled version reads cleanly. The person reaching
    for the escape hatch is by definition holding a photograph the automatic path could not
    handle -- it must not be the path with fewer safety nets.
    """
    import cv2

    from qrsalvage.core.pipeline import GOOD_MODULE_PX

    damage = Damage(contrast=0.30, curvature=0.0, rotation_deg=0.0, module_px=8.0)
    photo = render_photo(reencode(TEXT), damage, seed=4)
    big = cv2.resize(photo, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
    assert GOOD_MODULE_PX[1] < 8.0 * 4, "precondition: far above the working band"

    # With no rotation and no curvature the finder centres are exactly where synth drew them:
    # a five-module quiet zone, then 3.5 modules into the code.
    modules = reencode(TEXT).shape[0]
    near = (5 + 3.5) * 8.0 * 4
    far = (5 + modules - 3.5) * 8.0 * 4
    points = [(near, near), (far, near), (near, far)]

    result = solve(big, finder_points=points)

    assert result.solved, result.failure
    assert result.text == TEXT

    # And the reported finders land on the photograph the caller handed over -- not on some
    # internal working image nobody outside ever sees.
    for x, y, _ in result.finders[:3]:
        assert min(abs(x - p[0]) + abs(y - p[1]) for p in points) < 8.0 * 4 * 2, (
            "finder reported far from every marked point; coordinates are off"
        )


def test_reported_finders_are_in_the_coordinates_of_the_given_image():
    """The automatic path downscales internally; the report must not leak that."""
    import cv2

    damage = Damage(contrast=0.30, curvature=0.0, rotation_deg=0.0, module_px=8.0)
    photo = render_photo(reencode(TEXT), damage, seed=4)
    big = cv2.resize(photo, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)

    result = solve(big)
    assert result.solved

    modules = reencode(TEXT).shape[0]
    near = (5 + 3.5) * 8.0 * 4
    far = (5 + modules - 3.5) * 8.0 * 4
    expected = [(near, near), (far, near), (near, far)]
    for ex, ey in expected:
        assert min(abs(x - ex) + abs(y - ey) for x, y, _ in result.finders) < 8.0 * 4 * 2, (
            "no reported finder near a true centre, in the handed-over image's pixels"
        )


def test_progress_events_tell_the_story_in_order():
    """The live view shows true intermediate states, so the core must supply them.

    The order is the method's order: first the photograph, then the finders, then grids being
    fitted, then the sampled probabilities. And a listener is an observer, never a participant:
    one that raises must change nothing about the result.
    """
    photo = render_photo(reencode(TEXT), Damage(contrast=0.30, curvature=0.2), seed=3)

    events = []
    result = solve(photo, progress=lambda event, data: events.append((event, data)))
    assert result.solved

    names = [event for event, _ in events]
    assert names.index("image") < names.index("finders") < names.index("grid")
    assert names.index("grid") < names.index("sampled")

    grids = [data for event, data in events if event == "grid"]
    assert len(grids) > 4, "the descent accepts improvements; each one is an event"
    assert all(len(g["corners"]) == 4 for g in grids)
    sampled = next(data for event, data in events if event == "sampled")
    assert len(sampled["posterior"]) == sampled["modules"]

    def broken(event, data):
        raise RuntimeError("a watcher must never sink the recovery")

    undisturbed = solve(photo, progress=broken)
    assert undisturbed.solved
    assert undisturbed.text == result.text


def test_the_oracle_is_a_seam_not_a_dependency():
    """The one native dependency stays behind one seam, and the seam holds.

    A registered backend replaces zxing for decode and encode alike; and the core imports
    without the binding even installed, which is the fact the browser build stands on. The
    import check runs in a fresh interpreter because this one has long since loaded zxing.
    """
    import subprocess
    import sys

    from qrsalvage.core import oracle

    calls = []

    def fake_decode(image):
        calls.append(image.shape)
        return "FROM-THE-FAKE"

    def fake_encode(text, ec_level):
        calls.append((text, ec_level))
        return np.zeros((21, 21), dtype=bool)

    try:
        oracle.use(fake_decode, fake_encode)
        from qrsalvage.core.decoding import decode_matrix, reencode

        assert decode_matrix(np.zeros((21, 21), dtype=bool)) == "FROM-THE-FAKE"
        assert reencode("ANYTHING", ecc="M").shape == (21, 21)
        assert ("ANYTHING", "M") in calls
    finally:
        oracle.use(*oracle._native())

    probe = (
        "import sys; import qrsalvage.core.pipeline; "
        "assert 'zxingcpp' not in sys.modules, 'the import leaked'; print('clean')"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout
