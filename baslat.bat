@echo off
rem PDF Atolyesi baslatici: bagimliliklari kurar, gerekirse arayuzu derler, sunucuyu acar.
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo [HATA] uv bulunamadi. Kurmak icin: winget install astral-sh.uv
  pause
  exit /b 1
)

uv sync --quiet
if errorlevel 1 (
  echo [HATA] Python bagimliliklari kurulamadi.
  pause
  exit /b 1
)

rem Arayuz hic derlenmediyse veya kaynak dosyalar derlemeden yeniyse yeniden derle.
powershell -NoProfile -Command "$d = Get-Item 'web\dist\index.html' -ErrorAction SilentlyContinue; $s = Get-ChildItem 'web\src','web\index.html','web\package.json' -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if (-not $d -or $s.LastWriteTime -gt $d.LastWriteTime) { exit 1 }"
if errorlevel 1 (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [HATA] Arayuz derlenmemis ve npm yok. Node.js kur: winget install OpenJS.NodeJS.LTS
    pause
    exit /b 1
  )
  echo Arayuz derleniyor...
  if not exist "web\node_modules" call npm --prefix web install --no-fund --no-audit
  call npm --prefix web run build
  if errorlevel 1 (
    echo [HATA] Arayuz derlenemedi.
    pause
    exit /b 1
  )
)

uv run pdfatolye serve %*
if errorlevel 1 pause
