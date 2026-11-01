"""OCRmyPDF'i ayrı süreçte çalıştırır (iptal = süreç ağacını öldürmek). `core/ocr.py` çağırır.

Argüman: tek JSON. İlerleme ve sonuç stderr'e `PA_OCR {json}` satırlarıyla yazılır; stdout
kullanılmaz (OCRmyPDF'in kuralı).
"""

from __future__ import annotations

import json
import sys

PREFIX = "PA_OCR "


def emit(**data) -> None:
    sys.stderr.write(PREFIX + json.dumps(data, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def main() -> int:
    import ocrmypdf
    from ocrmypdf.exceptions import ExitCodeException

    # Uyarılar (ör. "page already has text") stderr'e düşsün; ocr.py sayar.
    ocrmypdf.configure_logging(ocrmypdf.Verbosity.default, progress_bar_friendly=False,
                               manage_root_logger=True)
    args = json.loads(sys.argv[1])
    mode = args.pop("mode")
    kwargs = dict(
        language=args["langs"],
        output_type="pdf",
        progress_bar=True,
        plugins=["pdfatolye.core._ocr_plugin"],
        tesseract_timeout=args["page_timeout"],
        rotate_pages=True,
        optimize=1,
    )
    if mode == "skip":
        kwargs.update(skip_text=True, deskew=True)
    elif mode == "redo":
        kwargs.update(redo_ocr=True)  # --deskew ile birlikte kullanılamaz
    else:
        kwargs.update(force_ocr=True, deskew=True)
    try:
        code = ocrmypdf.ocr(args["input"], args["output"], **kwargs)
    except ExitCodeException as e:
        emit(error=int(e.exit_code), message=str(e))
        return int(e.exit_code)
    emit(finished=True, code=int(code))
    return int(code)


if __name__ == "__main__":
    sys.exit(main())
