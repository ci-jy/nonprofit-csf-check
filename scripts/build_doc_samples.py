"""Write the sample workbook and report in docs/samples/ from the food bank's two assessments.

    python3 scripts/build_doc_samples.py

The files are committed so they can be opened without installing anything.
Office files stamp the time they were written into docProps/core.xml; that is
taken out so rebuilding them only changes the file when the content changes.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from csfcheck.compare import compare
from csfcheck.engine import Engine
from csfcheck.report import export_report
from csfcheck.samples import load_answers
from csfcheck.workbook import Progress, export_workbook

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "samples"


def strip_timestamps(path: Path) -> None:
    with zipfile.ZipFile(path) as z:
        items = [(info, z.read(info)) for info in z.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for info, data in items:
            if info.filename == "docProps/core.xml":
                data = re.sub(rb"<dcterms:(created|modified)[^>]*>[^<]*</dcterms:\1>", b"", data)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            z.writestr(info, data)


def main() -> None:
    engine = Engine.default()
    old = load_answers(ROOT / "samples" / "food_bank.json")
    new = load_answers(ROOT / "samples" / "retakes" / "food_bank.json")
    before = engine.assess(old.profile, old.answers)
    after = engine.assess(new.profile, new.answers)
    progress = Progress(compare(engine, before, after, old.answers, new.answers), "version 1", "version 2")
    written = [
        export_workbook(OUT / "food_bank_v2.xlsx", engine, after, new.answers, new.evidence, new.name,
                        progress=progress),
        export_report(OUT / "food_bank_v2.docx", engine, after, new.answers, new.evidence, new.name,
                      progress=progress),
    ]
    for path in written:
        strip_timestamps(path)
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
