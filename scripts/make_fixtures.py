"""Erzeugt das oeffentliche Regressionskorpus aus synthetischen Faellen.

Warum synthetisch: Echte Fotos beschaedigter QR-Codes sind fast immer persoenlich. Sie zeigen
Haende, Wohnraeume oder Geraeteaufkleber, und der entschluesselte Inhalt ist haeufig ein
Geheimnis -- bei Zigbee-Lampen etwa der Kopplungscode. Ein oeffentliches Projekt kann so ein
Bild nicht mitliefern, auch nicht "nur zum Testen".

Synthetische Faelle loesen das vollstaendig: Die Antwort ist bekannt, weil der Fall aus ihr
erzeugt wurde, der Inhalt ist harmlos, und jeder kann das Korpus mit einem Befehl reproduzieren.
Private Fotos gehoeren nach fixtures-local/ und bleiben dort.

Aufruf:
    .venv\\Scripts\\python.exe scripts\\make_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import cv2

from qrsalvage.core.decoding import reencode
from qrsalvage.synth import Damage, render_photo

ZIEL = Path(__file__).resolve().parents[1] / "fixtures"

# Die Schadensbilder sind den echten Faellen nachempfunden, die Inhalte sind es nicht.
FAELLE: tuple[tuple[str, str, Damage, int], ...] = (
    (
        "engraved-curved-easy",
        "QRSALVAGE-SYNTHETIC-CASE-001",
        Damage(contrast=0.24, curvature=0.25, module_px=9.0),
        0,
    ),
    (
        "engraved-curved-medium",
        "QRSALVAGE-SYNTHETIC-CASE-002-LONGER-PAYLOAD",
        Damage(contrast=0.16, curvature=0.40, module_px=8.0, stain=0.10),
        1,
    ),
    (
        "engraved-curved-hard",
        "QRSALVAGE-SYNTHETIC-CASE-003-EVEN-LONGER-PAYLOAD-HERE",
        Damage(contrast=0.13, curvature=0.45, module_px=7.0, stain=0.15),
        2,
    ),
    (
        "low-resolution",
        "QRSALVAGE-SYNTHETIC-CASE-004",
        Damage(contrast=0.20, curvature=0.20, module_px=5.5, blur=0.9),
        3,
    ),
)


def main() -> int:
    ZIEL.mkdir(parents=True, exist_ok=True)
    for name, text, damage, seed in FAELLE:
        matrix = reencode(text)
        photo = render_photo(matrix, damage, seed=seed)
        cv2.imwrite(str(ZIEL / f"{name}.png"), photo)

        meta = {
            "source": "synthetisch erzeugt, siehe scripts/make_fixtures.py",
            "expected_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "expected_length": len(text),
            # Bei synthetischen Faellen ist der Klartext harmlos und darf mitstehen -- das
            # erleichtert die Fehlersuche erheblich. Bei echten Fotos waere das ein Leck.
            "expected_prefix": text,
            "crop": None,
            "qr_modules": int(matrix.shape[0]),
            "damage": asdict(damage),
            "seed": seed,
            "synthetic": True,
        }
        (ZIEL / f"{name}.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"{name}: {photo.shape[1]}x{photo.shape[0]} px, {matrix.shape[0]} Module")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
