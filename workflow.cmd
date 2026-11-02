@echo off
setlocal
if not defined WORKFLOW_PYTHON set "WORKFLOW_PYTHON=python"
pushd "%~dp0"
if errorlevel 1 exit /b 2
"%WORKFLOW_PYTHON%" -B -m wecom_rusher.workflow_start %*
set "WORKFLOW_EXIT=%errorlevel%"
popd
exit /b %WORKFLOW_EXIT%
