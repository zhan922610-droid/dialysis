@echo off
rem ============================================================
rem  Сборка ЛЁГКОГО AI DialysisDiary.exe (~10 МБ, интерфейс tkinter)
rem  Требуется: Windows 10/11, Python 3.10-3.12 (python.org, галочка "Add to PATH")
rem  Результат: dist\AIDialysisDiary\AIDialysisDiary.exe
rem ============================================================
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip || goto :err
python -m pip install pyinstaller || goto :err

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller AIDialysisDiary.spec --clean --noconfirm || goto :err

if exist "dist\AIDialysisDiary\AIDialysisDiary.exe" (
    echo.
    echo ГОТОВО: dist\AIDialysisDiary\AIDialysisDiary.exe
    echo Папку dist\AIDialysisDiary целиком можно скопировать врачу; запуск без Python.
) else (
    echo ОШИБКА: exe не найден в dist\AIDialysisDiary
    goto :err
)
goto :eof

:err
echo Сборка завершилась с ошибкой. Проверьте, что Python установлен и в PATH.
exit /b 1
