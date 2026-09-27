@echo off
rem Launch the current source checkout with its project virtual environment.
setlocal
set "VC_ROOT=%~dp0.."
set "VC_PY=%VC_ROOT%\.venv\Scripts\pythonw.exe"
set "VC_FFPROBE=%VC_ROOT%\.codex-tools\ffmpeg\ffmpeg-9.0.1-essentials_build\bin\ffprobe.exe"

if not exist "%VC_PY%" (
    echo Cannot find the project virtual environment: %VC_PY%
    echo Run "uv sync --extra dev" in the project folder first.
    pause
    exit /b 1
)

set "VC_ARGS=-m video_compare"
if exist "%VC_FFPROBE%" set VC_ARGS=%VC_ARGS% --ffprobe "%VC_FFPROBE%"

start "" /d "%VC_ROOT%" "%VC_PY%" %VC_ARGS% %*
endlocal
