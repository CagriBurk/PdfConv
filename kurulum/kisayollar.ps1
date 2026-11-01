<#
PDF Atölyesi kısayolları:
  - Masaüstü: "PDF Atölyesi"  -> baslat.bat
  - Sağ tık > Gönder: "PDF'e çevir" -> pdfe-cevir.bat

Kullanım (proje klasöründe):
  powershell -ExecutionPolicy Bypass -File kurulum\kisayollar.ps1
  powershell -ExecutionPolicy Bypass -File kurulum\kisayollar.ps1 -Kaldir
Yalnızca kendi kullanıcı klasörüne kısayol yazar; yönetici izni gerekmez.
#>
param([switch]$Kaldir)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$sendTo = [Environment]::GetFolderPath('SendTo')
$items = @(
  @{ Path = Join-Path $desktop 'PDF Atölyesi.lnk'; Target = Join-Path $root 'baslat.bat';
     Desc = 'PDF Atölyesi: yerel PDF araç seti' },
  @{ Path = Join-Path $sendTo "PDF'e çevir.lnk"; Target = Join-Path $root 'pdfe-cevir.bat';
     Desc = 'Seçili dosyaları PDF Atölyesi ile PDF''e çevirir' }
)

if ($Kaldir) {
  foreach ($i in $items) {
    if (Test-Path -LiteralPath $i.Path) {
      Remove-Item -LiteralPath $i.Path
      Write-Host "Silindi: $($i.Path)"
    }
  }
  return
}

$shell = New-Object -ComObject WScript.Shell
$icon = Join-Path $env:SystemRoot 'System32\imageres.dll'
foreach ($i in $items) {
  if (-not (Test-Path -LiteralPath $i.Target)) { throw "Bulunamadı: $($i.Target)" }
  $lnk = $shell.CreateShortcut($i.Path)
  $lnk.TargetPath = $i.Target
  $lnk.WorkingDirectory = $root
  $lnk.Description = $i.Desc
  $lnk.WindowStyle = 7  # simge durumunda; hata olursa pencere zaten "pause" ile kalır
  $lnk.IconLocation = "$icon,68"
  $lnk.Save()
  Write-Host "Oluşturuldu: $($i.Path)"
}
Write-Host ''
Write-Host 'Bir dosyaya sağ tıkla > Gönder (Windows 11: "Daha fazla seçenek göster") > PDF''e çevir.'
