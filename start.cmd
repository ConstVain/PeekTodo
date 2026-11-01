@echo off
rem Double-click to start PeekTodo in the background (no console window).
rem Closing this window does not stop the app; use the tray icon to quit.
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw -m peek_todo
) else (
    start "" python -m peek_todo --detach
)
