@echo off
rem Launch the source checkout that contains this script.
cd /d "%~dp0" || exit /b 1
if not exist "peek_todo\__main__.py" (
    echo PeekTodo source files not found next to this script.
    exit /b 1
)
python -m peek_todo --detach %*
