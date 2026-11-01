"""OCRmyPDF eklentisi: ilerleme çubuğu yerine `PA_OCR` satırları yazar (bkz. `_ocr_run.py`)."""

from __future__ import annotations

from ocrmypdf import hookimpl

from pdfatolye.core._ocr_run import emit


class LineProgress:
    def __init__(self, *, total=None, desc=None, unit=None, disable=False, **kwargs) -> None:
        self.total = total
        self.desc = desc or ""
        self.done = 0.0

    def __enter__(self):
        emit(step=self.desc, done=0, total=self.total)
        return self

    def update(self, n=1, *, completed=None, **kwargs) -> None:
        self.done = completed if completed is not None else self.done + (n or 0)
        emit(step=self.desc, done=self.done, total=self.total)

    def __exit__(self, *exc) -> bool:
        return False


@hookimpl
def get_progressbar_class():
    return LineProgress
