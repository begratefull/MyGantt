@echo off
echo ==============================================
echo  1. Activating Virtual Environment...
echo ==============================================
call .venv\Scripts\activate

echo.
echo ==============================================
echo  2. Cleaning up old build files...
echo ==============================================
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo ==============================================
echo  3. Compiling MyGantt Application...
echo ==============================================
pyinstaller --clean MyGantt.spec

echo.
echo ==============================================
echo  BUILD COMPLETE!
echo  Your release is ready in the 'dist/MyGantt_App' folder.
echo ==============================================
pause