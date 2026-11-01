@echo off
rem PeekTodo quick verification.
rem ASCII-only on purpose: cmd mangles non-ASCII batch files and arguments.
rem All Chinese text lives inside config JSON, which Python reads as UTF-8.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

set "PY=D:\basicsoftware\anaconda3\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo ============ 1/3 unit tests ============
"%PY%" -m pytest tests -q
if errorlevel 1 goto :failed

echo.
echo ============ 2/3 sample markdown (config.example.json) ============
"%PY%" -m peek_todo.doctor --config config.example.json

echo.
echo ============ 3/3 your own config.json ============
if exist config.json (
  "%PY%" -m peek_todo.doctor --config config.json
) else (
  echo   [skip] config.json not found - copy config.example.json and edit it
)

echo.
echo ============ done. press any key ============
pause >nul
exit /b 0

:failed
echo.
echo   unit tests FAILED - see details above.
pause >nul
exit /b 1
