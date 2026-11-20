@echo off
rem Sag tik > Gonder > "JPG'ye cevir" kisayolu bunu cagirir (kurulum\kisayollar.ps1).
rem Resimleri (HEIC, PNG, WEBP...) JPG'ye cevirir; ciktilar dosyalarin yanina yazilir.
setlocal
cd /d "%~dp0"
uv run python -m pdfatolye donustur --hedef jpg %*
if errorlevel 1 (
  echo.
  echo Bazi dosyalar cevrilemedi. Ayrinti yukarida.
  pause
) else (
  timeout /t 3 >nul
)
