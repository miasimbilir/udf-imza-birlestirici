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
  --version-file surum_bilgisi.txt ^
  --collect-all tkinterdnd2 ^
  --add-data "cms_imza.py;." --add-data "imza_dogrula.py;." ^
  --add-data "udf_ortak.py;." --add-data "birlestirici.py;." ^
  --hidden-import cms_imza --hidden-import imza_dogrula ^
  --hidden-import udf_ortak --hidden-import birlestirici ^
  uygulama.py
```

4. Sonuç: `dist\UDF Imza Birlestirici.exe` — tek dosya, kurulum gerekmez.

5. **Çalıştığını doğrulayın** (exe'nin konsolu olmadığı için sonuç dosyaya yazılır):

```bat
"dist\UDF Imza Birlestirici.exe" --sinama --rapor sinama.txt
type sinama.txt
```

`SINAMA TAMAM` yazmalı. Yazmıyorsa exe'yi dağıtmayın.

Bu adımların hepsini (testler dahil) `derle-windows.bat` sırayla yapar.

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

/tmp/derleme/bin/python plist_yaz.py   # sürüm ve telif bilgisini Info.plist'e göm
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

`.github/workflows/derle.yml` iki macOS mimarisi (Apple Silicon ve Intel) için
paketleri derler; derlemeden önce testleri, derledikten sonra `--sinama`'yı
çalıştırır.

Windows bu akışta **yoktur**: bu hesapta Windows runner alınamıyor (iş kuyrukta
bekleyip iptal ediliyor). Windows exe'si Windows bir bilgisayarda
`derle-windows.bat` ile elle derlenir. Adımlar akış dosyasında yerinde duruyor;
runner çalışır hâle gelirse matristeki satır geri açılır.

Elle başlatmak için: **Actions → Uygulamayı derle → Run workflow**
(ya da `gh workflow run derle.yml`). `s` ile başlayan bir etiket (`s1.1`)
gönderilirse akış sürüm de oluşturur.

## Testler

```bash
python3 -m unittest discover -s testler -v
```

Yalnız Python standart kütüphanesini kullanır; Windows'ta da çalışır. Sekiz
güvenlik kapısını, imza doğrulamayı (NULL'suz DigestInfo dahil), bozuk ve
kötü niyetli dosyaları ve güvenli yazmayı sınar. Veriler `testler/veri/`
içindedir ve **sentetiktir**; yeniden üretmek için `python3 testler/veri_uret.py`
(openssl 3+ gerekir).

## Kod imzalama

Paketler imzalanmadığı için Windows SmartScreen ve macOS Gatekeeper uyarı
gösterir. Kaldırmak için ücretli sertifika gerekir:

- **macOS:** Apple Developer Program (yıllık 99 $) + `codesign` ve noter onayı
- **Windows:** OV/EV kod imzalama sertifikası (yıllık birkaç yüz dolar)

Uyarılar aşılabilir olduğu için küçük bir kullanıcı çevresi için şart değildir.
