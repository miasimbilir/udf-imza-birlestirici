@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title UDF Imza Birlestirici - Windows derleyici

echo.
echo ============================================================
echo   UDF Imza Birlestirici - Windows icin .exe uretir
echo ============================================================
echo.

cd /d "%~dp0"

REM --- Python var mi? ---------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi.
    echo.
    echo   1. https://www.python.org/downloads/windows/ adresinden Python kurun
    echo   2. Kurulumda "Add python.exe to PATH" kutusunu MUTLAKA isaretleyin
    echo   3. Bu dosyayi tekrar calistirin
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python --version') do echo Python bulundu: %%v

REM --- Gerekli paketler -------------------------------------------------
echo.
echo [1/4] Gerekli paketler kuruluyor (birkac dakika surebilir)...
python -m pip install --quiet --upgrade pip pyinstaller tkinterdnd2
if errorlevel 1 (
    echo [HATA] Paketler kurulamadi. Internet baglantinizi kontrol edin.
    pause
    exit /b 1
)

REM --- Tcl/Tk surumu ----------------------------------------------------
echo.
echo [2/4] Tcl/Tk surumu kontrol ediliyor...
python -c "import tkinter; print('  Tcl/Tk', tkinter.TkVersion); exit(0 if tkinter.TkVersion>=8.6 else 1)"
if errorlevel 1 (
    echo [HATA] Tcl/Tk surumu cok eski. Python'u python.org surumuyle kurun.
    pause
    exit /b 1
)

REM --- Derle ------------------------------------------------------------
echo.
echo [3/4] Uygulama derleniyor...
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name "UDF Imza Birlestirici" --icon ikon\uygulama.ico ^
  --version-file surum_bilgisi.txt ^
  --collect-all tkinterdnd2 ^
  --add-data "cms_imza.py;." --add-data "imza_dogrula.py;." ^
  --add-data "udf_ortak.py;." --add-data "birlestirici.py;." ^
  --hidden-import cms_imza --hidden-import imza_dogrula ^
  --hidden-import udf_ortak --hidden-import birlestirici ^
  uygulama.py
if errorlevel 1 (
    echo [HATA] Derleme basarisiz oldu. Yukaridaki mesajlari inceleyin.
    pause
    exit /b 1
)

REM --- Sinama -----------------------------------------------------------
echo.
echo [4/4] Uretilen dosya sinaniyor...
if exist sinama.txt del sinama.txt
start /wait "" "dist\UDF Imza Birlestirici.exe" --sinama --rapor sinama.txt
if not exist sinama.txt (
    echo [HATA] Uygulama sinama raporu uretmedi; paket bozuk olabilir.
    pause
    exit /b 1
)
type sinama.txt | findstr /C:"SINAMA TAMAM" >nul
if errorlevel 1 (
    echo [HATA] Sinama basarisiz:
    type sinama.txt
    pause
    exit /b 1
)
echo.
type sinama.txt

echo.
echo ============================================================
echo   TAMAMLANDI
echo.
echo   Dosya:  %cd%\dist\UDF Imza Birlestirici.exe
echo.
echo   Bu tek dosyayi baska bir Windows bilgisayara kopyalayip
echo   dogrudan calistirabilirsiniz; kurulum gerekmez.
echo ============================================================
echo.
pause
