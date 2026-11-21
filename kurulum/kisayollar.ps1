<#
Toolia kısayolları:
  - Masaüstü: "Toolia"  -> baslat.bat
  - Sağ tık > Gönder: "PDF'e çevir" -> uv run python -I -m toolia.gonder_menu pdf
  - Sağ tık > Gönder: "JPG'ye çevir" -> uv run python -I -m toolia.gonder_menu jpg (HEIC, PNG...)

Gönder kısayolları bir .bat dosyasını değil, doğrudan uv.exe'yi çalıştırır: Gezgin boşluksuz
yolları tırnaklamaz, cmd.exe de dosya adındaki `&`'den sonrasını komut olarak çalıştırırdı
(GUVENLIK_PLANI.md, adım 1).

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
$uv = if ($Kaldir) { '' } else { (Get-Command uv -ErrorAction Stop).Source }
$items = @(
  @{ Path = Join-Path $desktop 'Toolia.lnk'; Target = Join-Path $root 'baslat.bat'; Args = '';
     Desc = 'Toolia: çevrimdışı PDF ve dosya araçları' },
  @{ Path = Join-Path $sendTo "PDF'e çevir.lnk"; Target = $uv;
     Args = 'run --quiet python -I -m toolia.gonder_menu pdf';
     Desc = 'Seçili dosyaları Toolia ile PDF''e çevirir' },
  @{ Path = Join-Path $sendTo "JPG'ye çevir.lnk"; Target = $uv;
     Args = 'run --quiet python -I -m toolia.gonder_menu jpg';
     Desc = 'Seçili resimleri JPG''ye çevirir' }
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
  $lnk.Arguments = $i.Args
  $lnk.WorkingDirectory = $root
  $lnk.Description = $i.Desc
  $lnk.WindowStyle = 7  # simge durumunda; hata olursa pencere zaten "pause" ile kalır
  $lnk.IconLocation = "$icon,68"
  $lnk.Save()
  Write-Host "Oluşturuldu: $($i.Path)"
}
Write-Host ''
Write-Host 'Bir dosyaya sağ tıkla > Gönder (Windows 11: "Daha fazla seçenek göster") > PDF''e çevir ya da JPG''ye çevir.'
