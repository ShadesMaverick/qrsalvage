"""Take a solved photograph into the private corpus under fixtures-local/.

Kept separate from make_fixtures.py on purpose. That script generates the public, synthetic
corpus and can be re-run at any time; this one touches real photographs, whose decoded content
is usually a secret, and it must never overwrite an existing case.

The expectation is stored as a hash, not as the plain text. A regression only needs to compare,
and a test case is no reason to write a device secret to disk.

Usage:
    python scripts/add_private_fixture.py photo.jpg zigbee-bulb-e27-2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path

import cv2

from qrsalvage.core.pipeline import solve

TARGET = Path(__file__).resolve().parents[1] / "fixtures-local"

# The name becomes a file name under TARGET and nothing else. Unchecked, a name carrying a
# separator walks out of fixtures-local/ -- and one directory over sits the tracked, public
# fixtures/. Nothing hostile is needed for that: a slip of the keyboard is enough, and what the
# slip costs is a private photograph in the corpus that gets published.
FIXTURE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("name", help="short lowercase identifier describing the source")
    parser.add_argument("--source", default="", help="one line on where the photograph is from")
    parser.add_argument("--note", nargs="*", default=[], help="what makes this case difficult")
    parser.add_argument(
        "--provenance",
        default="",
        help="where it came from, if not your own device -- a forum post, a colleague, a photo "
        "someone sent you",
    )
    parser.add_argument(
        "--third-party",
        action="store_true",
        help="the device belongs to someone else; marks the fixture as not ours to publish",
    )
    args = parser.parse_args()

    if not FIXTURE_NAME.match(args.name):
        print(f"the name must be a bare identifier, not a path: {args.name!r}")
        return 1

    TARGET.mkdir(parents=True, exist_ok=True)
    destination = TARGET / f"{args.name}.png"
    meta_path = TARGET / f"{args.name}.json"
    if destination.exists() or meta_path.exists():
        print(f"{args.name} already exists. Fixtures are added, never overwritten.")
        return 1

    image = cv2.imread(str(args.image))
    if image is None:
        print(f"cannot read {args.image}")
        return 1

    # Solve it again rather than trusting a result from earlier in the session: an expectation
    # taken from memory would cement a mistake.
    result = solve(image)
    if not result.solved:
        print(f"not solved, so there is nothing to expect: {result.failure}")
        return 2
    assert result.text is not None

    shutil.copyfile(args.image, destination)
    meta = {
        "source": args.source or "private photograph",
        "expected_sha256": hashlib.sha256(result.text.encode()).hexdigest(),
        # Recorded separately from `source` so it cannot be mistaken for a description. A
        # photograph handed to you does not make the device yours, and the payload of a Zigbee
        # or Matter label is a pairing secret rather than an identifier.
        **(
            {
                "provenance": args.provenance,
                "third_party": True,
                "handling": (
                    "NOT OURS. The decoded payload is someone else's device secret. Do not "
                    "publish it, do not put it in an issue, do not paste it into a forum reply."
                ),
            }
            if args.third_party or args.provenance
            else {}
        ),
        "expected_length": len(result.text),
        "expected_prefix": "",
        "crop": None,
        "qr_version": result.version,
        "qr_modules": result.modules,
        "solved_at_stage": 0 if result.candidates_tried <= 1 else 1,
        "solved_by": "auto",
        "difficulties": list(args.note),
        "added": date.today().isoformat(),
        "synthetic": False,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"{args.name}: version {result.version}, {result.wrong_known}/{result.known_total} wrong")
    print(f"-> {destination.name} and {meta_path.name} (gitignored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
