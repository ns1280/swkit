@echo off
rem swkit launcher (plan A: run from source, no install)
rem   swkit.cmd <command> <project> [args]
rem   swkit.cmd test           run unit tests (no SolidWorks needed)
rem Override the interpreter with the SWKIT_PY environment variable.
setlocal
set "SWKIT_HOME=%~dp0"
if defined SWKIT_PY (set "PY=%SWKIT_PY%") else set "PY=D:\miniconda3\envs\data-analysis\python.exe"
if not exist "%PY%" set "PY=python"
if defined PYTHONPATH (set "PYTHONPATH=%SWKIT_HOME%src;%PYTHONPATH%") else (set "PYTHONPATH=%SWKIT_HOME%src")

if /I "%~1"=="test" (
    "%PY%" -m unittest discover -s "%SWKIT_HOME%tests"
    exit /b %ERRORLEVEL%
)

"%PY%" -m swkit %*
exit /b %ERRORLEVEL%
