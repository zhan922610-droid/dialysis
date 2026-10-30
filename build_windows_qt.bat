@echo off
rem ============================================================
rem  Сборка AI DialysisDiary_Qt.exe на PySide6 (~140 МБ, «красивый» интерфейс)
rem  Результат: dist\AIDialysisDiary_Qt\AIDialysisDiary_Qt.exe
rem ============================================================
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip || goto :err
python -m pip install -r requirements_qt.txt || goto :err

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller AIDialysisDiary_Qt.spec --clean --noconfirm || goto :err

if exist "dist\AIDialysisDiary_Qt\AIDialysisDiary_Qt.exe" (
    echo.
    echo ГОТОВО: dist\AIDialysisDiary_Qt\AIDialysisDiary_Qt.exe
) else (
    echo ОШИБКА: exe не найден в dist\AIDialysisDiary_Qt
    goto :err
)
goto :eof

:err
echo Сборка завершилась с ошибкой.
exit /b 1
