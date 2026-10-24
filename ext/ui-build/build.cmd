@echo off
setlocal
set "GAME=%~1"
if /I not "%GAME%"=="five" if /I not "%GAME%"=="rdr3" (
  echo OpenV UI: expected game five or rdr3, got "%GAME%" 1>&2
  exit /b 2
)
set "ROOT=%~dp0"
set "LOADSCREEN=%ROOT%loadscreen"
set "COMPILED=%ROOT%loadscreen-fallback"
where python >nul 2>&1 || (echo OpenV UI: Python 3 is required 1>&2 & exit /b 1)
if exist "%LOADSCREEN%\package.json" (
  where yarn >nul 2>&1 || (echo OpenV UI: Yarn required for upstream loadscreen 1>&2 & exit /b 1)
  pushd "%LOADSCREEN%" || exit /b 1
  call yarn install --frozen-lockfile --non-interactive
  if errorlevel 1 (popd & exit /b 1)
  call node_modules\.bin\webpack.cmd --mode production
  if errorlevel 1 (popd & exit /b 1)
  popd
  set "COMPILED=%LOADSCREEN%\dist"
)
python "%ROOT%..\..\tools\build_openv_ui.py" --source "%ROOT%data" --loadscreen-dist "%COMPILED%" --output "%ROOT%"
if errorlevel 1 exit /b 1
exit /b 0
