@echo off
rem Builds dist\LoLAutoAccept.exe: a single file that runs without Python installed.
rem Used by the GitHub release workflow; can also be run locally on Windows.

python -m pip install --upgrade pip || exit /b 1
python -m pip install -r requirements.txt "pyinstaller>=6.0" || exit /b 1

rem pynput picks its Windows backend at runtime, so PyInstaller cannot see it.
python -m PyInstaller --noconfirm --clean --onefile --windowed --name LoLAutoAccept ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import pynput.mouse._win32 ^
    main.py || exit /b 1

echo.
echo Built dist\LoLAutoAccept.exe
