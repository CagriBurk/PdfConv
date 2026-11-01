@echo off
rem Sag tik > Gonder > "PDF'e cevir" kisayolu bunu cagirir (kurulum\kisayollar.ps1).
rem Dosyalari turune gore PDF'e cevirir; ciktilar dosyalarin yanina yazilir.
setlocal
cd /d "%~dp0"
uv run python -m pdfatolye gonder %*
if errorlevel 1 (
  echo.
  echo Bazi dosyalar cevrilemedi. Ayrinti yukarida.
  pause
) else (
  timeout /t 3 >nul
)
