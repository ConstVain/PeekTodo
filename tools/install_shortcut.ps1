# Create or remove a shortcut for this source checkout.
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $root
try {
    if ($Uninstall) {
        python -c "from peek_todo.windows.shortcut import remove; remove()"
    } else {
        python -c "from peek_todo.windows.shortcut import create; path = create(); print(path) if path else exit('Unable to create the PeekTodo shortcut')"
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
