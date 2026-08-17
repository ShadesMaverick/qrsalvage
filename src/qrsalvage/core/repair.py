"""Hand uncertain cells to Reed-Solomon as erasures.

This closes the chain that ensemble.py leaves open. The ordered probe flips at most a couple of
dozen cells and tries combinations; Reed-Solomon instead is *told* where the doubt is and
computes the right values in one step. With t check symbols it repairs t erasures against only
t/2 errors -- the factor of two that the three-state matrix exists for.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .decoding import _subsets_by_cost
from .galois import ReedSolomonError, correct_block
from .layout import (
    codeword_positions,
    deinterleave,
    extract_codewords,
    interleave,
    place_codewords,
    read_format,
    write_format,
)
from .qrspec import block_plan
from .structure import version_for_modules


@dataclass
class RepairResult:
    """What the repair produced -- informative even when it failed."""

    matrix: np.ndarray | None
    ecc: str | None = None
    mask: int | None = None
    format_distance: int | None = None
    blocks: int = 0
    blocks_repaired: int = 0
    errors_corrected: int = 0
    erasures_used: int = 0
    per_block: list[str] = field(default_factory=list)
    failure: str | None = None

    @property
    def ok(self) -> bool:
        return self.matrix is not None


def _codeword_reliability(posterior: np.ndarray, positions: list[int]) -> float:
    """Reliability of a codeword: its weakest bit.

    Not the average. A codeword is already wrong when a single one of its eight bits flips; an
    average would offset seven solid bits against one shaky one and certify the codeword as
    sound.
    """
    flat = posterior.ravel()
    return min(abs(float(flat[p]) - 0.5) for p in positions)


def repair(
    matrix: np.ndarray,
    posterior: np.ndarray | None = None,
    erasures_per_block: int = 0,
) -> RepairResult:
    """One repair attempt with exactly `erasures_per_block` erasures per block.

    Important and not obvious: with as many erasures as check symbols, Reed-Solomon *always*
    finds a valid solution. Valid does not mean correct -- if the real errors sit outside the
    erased positions, out comes a cleanly computed wrong codeword. This function cannot notice
    that; :func:`repair_progressive` exists to have every attempt refuted from outside.
    """
    n = int(matrix.shape[0])
    version = version_for_modules(n)

    header = read_format(matrix)
    if header is None:
        return RepairResult(matrix=None, failure="format information unreadable")
    ecc, mask, distance = header

    try:
        plan = block_plan(version, ecc)
    except KeyError as exc:
        return RepairResult(matrix=None, ecc=ecc, mask=mask, failure=str(exc))

    codewords = extract_codewords(matrix, mask)[: plan.total_codewords]
    if len(codewords) < plan.total_codewords:
        return RepairResult(matrix=None, ecc=ecc, mask=mask, failure="too few codewords")

    blocks = deinterleave(codewords, version, ecc)
    positions = codeword_positions(n, version, ecc)

    repaired: list[list[int]] = []
    errors_total = 0
    erasures_total = 0
    blocks_touched = 0
    report: list[str] = []

    for index, block in enumerate(blocks):
        nsym = plan.ec_per_block

        erasures: list[int] = []
        if posterior is not None and erasures_per_block > 0:
            scored = [
                (_codeword_reliability(posterior, positions[index][i]), i)
                for i in range(len(block))
            ]
            erasures = [i for _, i in sorted(scored)[:erasures_per_block]]

        try:
            outcome = correct_block(block, nsym, erasures)
        except (ReedSolomonError, ZeroDivisionError):
            outcome = None

        if outcome is None:
            report.append(f"block {index}: not repairable")
            return RepairResult(
                matrix=None,
                ecc=ecc,
                mask=mask,
                format_distance=distance,
                blocks=len(blocks),
                per_block=report,
                failure=f"block {index} of {len(blocks)} could not be repaired",
            )

        corrected, error_positions, used = outcome
        repaired.append(corrected)
        errors_total += len(error_positions)
        erasures_total += len(used)
        if error_positions or used:
            blocks_touched += 1
        report.append(f"block {index}: {len(error_positions)} errors, {len(used)} erasures")

    stream = interleave(repaired, version, ecc)
    rebuilt = np.array(matrix, dtype=bool, copy=True)
    place_codewords(rebuilt, stream, mask)
    write_format(rebuilt, ecc, mask)

    return RepairResult(
        matrix=rebuilt,
        ecc=ecc,
        mask=mask,
        format_distance=distance,
        blocks=len(blocks),
        blocks_repaired=blocks_touched,
        errors_corrected=errors_total,
        erasures_used=erasures_total,
        per_block=report,
    )


def repair_scattered(
    matrix: np.ndarray,
    posterior: np.ndarray,
    verify: Callable[[np.ndarray], bool] | None = None,
    budget: int = 400,
    pool: int = 25,
    on_step: Callable[[int], None] | None = None,
) -> RepairResult:
    """Erasure sets that are not prefixes of the reliability order.

    The ladder in :func:`repair_progressive` always erases the k *least* reliable codewords --
    a prefix. Measured on real photographs, the damaged codewords interleave with sound ones in
    that order (5 to 12 of the 15 cheapest were actually damaged), and every sound codeword
    inside the prefix is a check symbol spent on nothing. A prefix must pay for the good
    codewords standing between the bad ones; an arbitrary subset walks around them.

    Concretely: damage at reliability ranks {2,4,6,8,10,12,14,16,18} is unreachable for any
    prefix -- covering rank 18 costs 18 of 15 symbols -- while the exact set costs 9. The
    subsets are enumerated in ascending total reliability by the same heap generator the cell
    probe uses; the prefixes are among them, so this strictly generalises the ladder, and the
    ladder stays because it reaches *deep* prefixes that cost-ordered enumeration only reaches
    late.

    Every accepted candidate still has to survive `verify` from outside, for the same reason
    the ladder does: with enough erasures Reed-Solomon always finds a valid answer, and valid
    is not correct.

    MEASURED RESULT, mixed. The constructed interleaved case above is real and covered by a
    test (test_rs.py), where every prefix provably fails and the scattered set repairs -- and
    on the way there the test caught the ladder returning a valid-but-wrong solution, which is
    the whole argument for outside verification made flesh. On the synthetic stain axis,
    though, the stage converts nothing: 14/16, 11/16, 8/16 across stain 0.35/0.45/0.55, to the
    image identical with and without it (scripts/ab_sigma.py, before/after comparison). A
    synthetic stain seems to damage codewords either compactly enough for the prefix ladder or
    too many for any subset. It stays in the chain regardless of that measurement, unlike the
    ensembles it echoes: it costs well under a second, only ever runs after the ladder has
    already failed, and the interleaved reliability ranks it exists for are exactly what the
    real photographs measured (5 to 12 damaged among the 15 cheapest).
    """
    header = read_format(matrix)
    if header is None:
        return RepairResult(matrix=None, failure="format information unreadable")
    ecc, mask, distance = header
    n = int(matrix.shape[0])
    version = version_for_modules(n)
    try:
        plan = block_plan(version, ecc)
    except KeyError as exc:
        return RepairResult(matrix=None, ecc=ecc, mask=mask, failure=str(exc))

    codewords = extract_codewords(matrix, mask)[: plan.total_codewords]
    if len(codewords) < plan.total_codewords:
        return RepairResult(matrix=None, ecc=ecc, mask=mask, failure="too few codewords")
    blocks = deinterleave(codewords, version, ecc)
    positions = codeword_positions(n, version, ecc)

    ranked = sorted(
        (_codeword_reliability(posterior, positions[b][i]), b, i)
        for b in range(len(blocks))
        for i in range(len(blocks[b]))
    )[:pool]
    costs = np.array([max(reliability, 1e-6) for reliability, _, _ in ranked])

    tried = 0
    for subset in _subsets_by_cost(costs, budget):
        chosen: dict[int, list[int]] = defaultdict(list)
        for index in subset:
            _, block_index, codeword_index = ranked[index]
            chosen[block_index].append(codeword_index)
        if any(len(erasures) > plan.ec_per_block for erasures in chosen.values()):
            continue

        repaired: list[list[int]] = []
        errors_total = 0
        erasures_total = 0
        for block_index, block in enumerate(blocks):
            try:
                outcome = correct_block(block, plan.ec_per_block, chosen.get(block_index, []))
            except (ReedSolomonError, ZeroDivisionError):
                outcome = None
            if outcome is None:
                break
            corrected, error_positions, used = outcome
            repaired.append(corrected)
            errors_total += len(error_positions)
            erasures_total += len(used)
        if len(repaired) < len(blocks):
            continue

        tried += 1
        if on_step and tried % 100 == 0:
            on_step(tried)
        stream = interleave(repaired, version, ecc)
        rebuilt = np.array(matrix, dtype=bool, copy=True)
        place_codewords(rebuilt, stream, mask)
        write_format(rebuilt, ecc, mask)
        if verify is None or verify(rebuilt):
            return RepairResult(
                matrix=rebuilt,
                ecc=ecc,
                mask=mask,
                format_distance=distance,
                blocks=len(blocks),
                blocks_repaired=len(blocks),
                errors_corrected=errors_total,
                erasures_used=erasures_total,
            )

    return RepairResult(
        matrix=None,
        ecc=ecc,
        mask=mask,
        format_distance=distance,
        blocks=len(blocks),
        failure=f"{tried} scattered erasure sets decoded, none survived verification",
    )


def repair_progressive(
    matrix: np.ndarray,
    posterior: np.ndarray | None = None,
    verify: Callable[[np.ndarray], bool] | None = None,
    max_erasure_fraction: float = 1.0,
    on_step: Callable[[int], None] | None = None,
) -> RepairResult:
    """Raise the erasure count until a solution appears that survives scrutiny.

    Climbing is not laziness, it is necessary: more erasures buy reach at the cost of
    uniqueness. With few of them a solution found is almost certainly the right one; with as
    many as there are check symbols it is arbitrary. So the most frugal one that survives
    `verify` wins -- without that contradiction from outside, the method always returns
    something, and usually nonsense.
    """
    header = read_format(matrix)
    if header is None:
        return RepairResult(matrix=None, failure="format information unreadable")
    ecc, _, _ = header
    try:
        plan = block_plan(version_for_modules(int(matrix.shape[0])), ecc)
    except KeyError as exc:
        return RepairResult(matrix=None, ecc=ecc, failure=str(exc))

    limit = int(plan.ec_per_block * max_erasure_fraction)
    last = RepairResult(matrix=None, ecc=ecc, failure="no attempt made")

    for count in range(0, limit + 1):
        if on_step:
            on_step(count)
        outcome = repair(matrix, posterior=posterior, erasures_per_block=count)
        if not outcome.ok:
            last = outcome
            continue
        assert outcome.matrix is not None  # ok is defined as exactly this
        if verify is None or verify(outcome.matrix):
            return outcome
        last = RepairResult(
            matrix=None,
            ecc=outcome.ecc,
            mask=outcome.mask,
            format_distance=outcome.format_distance,
            blocks=outcome.blocks,
            failure=f"{count} erasures produced a valid but unreadable result",
        )
        if posterior is None:
            break  # without an uncertainty map, erasing more adds nothing new
    return last
