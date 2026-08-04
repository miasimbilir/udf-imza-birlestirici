# Uygulamayı derleme

Programı çalıştırmak için derlemek şart değil — `python3 uygulama.py` yeterlidir.
Derleme, Python kurulu olmayan bir bilgisayara **tek dosya** olarak vermek içindir.

## Windows — tek dosya .exe

Bir Windows bilgisayarda:

1. **Python kurun:** <https://www.python.org/downloads/windows/>
   Kurulumda **"Add python.exe to PATH"** kutusunu işaretleyin.
   (Microsoft Store sürümünü değil, python.org sürümünü kullanın.)

2. Bu klasörü (`dagitim`) Windows makineye kopyalayın.

3. Klasörde bir komut istemi açıp:

```bat
python -m pip install --upgrade pip pyinstaller tkinterdnd2

pyinstaller --noconfirm --clean --onefile --windowed ^
  --name "UDF Imza Birlestirici" --icon ikon\uygulama.ico ^
  --collect-all tkinterdnd2 ^
  --add-data "cms_imza.py;." --add-data "imza_dogrula.py;." ^
  --add-data "udf_ortak.py;." --add-data "birlestirici.py;." ^
  --hidden-import cms_imza --hidden-import imza_dogrula ^
  --hidden-import udf_ortak --hidden-import birlestirici ^
  uygulama.py
```

4. Sonuç: `dist\UDF Imza Birlestirici.exe` — tek dosya, kurulum gerekmez.

5. **Çalıştığını doğrulayın:**

```bat
"dist\UDF Imza Birlestirici.exe" --sinama
```

`SINAMA TAMAM` yazmalı. Yazmıyorsa exe'yi dağıtmayın.

## macOS — .app paketi

macOS'un sistem Python'u 2010 tarihli Tcl/Tk 8.5 ile gelir ve **pencereyi boş
çizer.** Güncel Tk'li bir Python şarttır:

```bash
brew install python-tk@3.13
/opt/homebrew/bin/python3.13 -m venv /tmp/derleme
/tmp/derleme/bin/pip install pyinstaller tkinterdnd2

/tmp/derleme/bin/pyinstaller --noconfirm --clean --windowed \
  --name "UDF Imza Birlestirici" --icon ikon/uygulama.icns \
  --collect-all tkinterdnd2 \
  --osx-bundle-identifier "tr.arabuluculuk.udfimza" \
  --add-data "cms_imza.py:." --add-data "imza_dogrula.py:." \
  --add-data "udf_ortak.py:." --add-data "birlestirici.py:." \
  --hidden-import cms_imza --hidden-import imza_dogrula \
  --hidden-import udf_ortak --hidden-import birlestirici \
  uygulama.py
```

Sonuç: `dist/UDF Imza Birlestirici.app`

Doğrulama:

```bash
"dist/UDF Imza Birlestirici.app/Contents/MacOS/UDF Imza Birlestirici" --sinama
```

Çıktıda Tcl/Tk sürümü de yazar; **8.6'dan küçükse sınama başarısız olur** ve
paketi dağıtmamalısınız.

> Apple Silicon Mac'te derlenen uygulama Intel Mac'te çalışmaz; her mimari
> kendi makinesinde derlenmelidir.

## GitHub üzerinden otomatik derleme

`.github/workflows/derle.yml` hazırdır. Klasörü bir GitHub deposuna
yüklerseniz, Windows ve iki macOS mimarisi için paketleri kendisi derler,
her birini yayımlamadan önce sınamadan geçirir ve Sürümler sayfasına koyar.

Depoyu yükledikten sonra elle başlatmak için: **Actions → Uygulamayı derle →
Run workflow**. Sürüm oluşturmak için `s1.0` gibi bir etiket gönderin.

## Kod imzalama

Paketler imzalanmadığı için Windows SmartScreen ve macOS Gatekeeper uyarı
gösterir. Kaldırmak için ücretli sertifika gerekir:

- **macOS:** Apple Developer Program (yıllık 99 $) + `codesign` ve noter onayı
- **Windows:** OV/EV kod imzalama sertifikası (yıllık birkaç yüz dolar)

Uyarılar aşılabilir olduğu için küçük bir kullanıcı çevresi için şart değildir.
