# Create a desktop shortcut for PeekTodo (with the app icon).
#
#   powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1
#   powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1 -Uninstall
#
# Difference from the generic PeekTodo.lnk in the repo root:
#   generic  -> cmd.exe + peektodo from PATH, works anywhere, generic icon
#   this one -> points straight at peektodo.exe, uses assets/app.ico
# Requires the package to be installed: pip install -e .

param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "PeekTodo.lnk"

if ($Uninstall) {
    if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force; Write-Host "removed $lnkPath" }
    else { Write-Host "no PeekTodo.lnk on the desktop" }
    exit 0
}

$exe = $null
$cmd = Get-Command peektodo -ErrorAction SilentlyContinue
if ($cmd) { $exe = $cmd.Source }
if (-not $exe) {
    $fallback = Join-Path $env:USERPROFILE "AppData\Roaming\Python\Scripts\peektodo.exe"
    if (Test-Path $fallback) { $exe = $fallback }
}
if (-not $exe) {
    throw "peektodo.exe not found - run: pip install -e ."
}

# 图标必须放在 C: 盘 —— 资源管理器不渲染 D: 等非系统盘上的 .ico，
# 指向那种路径的快捷方式只会显示成白页。
$ico = Join-Path $env:LOCALAPPDATA "PeekTodo\app.ico"
$src = Join-Path $root "peek_todo\assets\app.ico"
if (Test-Path $src) {
    New-Item -ItemType Directory -Force (Split-Path $ico) | Out-Null
    Copy-Item $src $ico -Force
}
if (-not (Test-Path $ico)) { $ico = $exe }

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $exe
$lnk.IconLocation = "$ico,0"
$lnk.WorkingDirectory = $root
$lnk.Description = "PeekTodo - a todo panel that slides out from the screen edge"
$lnk.WindowStyle = 1
$lnk.Save()

Write-Host "created: $lnkPath"
Write-Host "  target: $exe"
Write-Host "  icon:   $ico"
