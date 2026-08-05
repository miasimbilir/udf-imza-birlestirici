#!/usr/bin/env python3
"""Derlenen .app'in Info.plist'ine sürüm ve telif bilgisini yazar.

PyInstaller bunları komut satırından kabul etmediği için derleme sonrası
eklenir; macOS'ta Finder > Bilgi Al ve Hakkında penceresinde görünür.
"""
import plistlib
import sys

from uygulama import SURUM, TELIF, UYGULAMA_ADI

yol = (sys.argv[1] if len(sys.argv) > 1
       else "dist/UDF Imza Birlestirici.app/Contents/Info.plist")
with open(yol, "rb") as f:
    p = plistlib.load(f)
p["CFBundleShortVersionString"] = SURUM
p["CFBundleVersion"] = SURUM
p["CFBundleDisplayName"] = UYGULAMA_ADI
p["NSHumanReadableCopyright"] = TELIF
with open(yol, "wb") as f:
    plistlib.dump(p, f)
print(f"Info.plist güncellendi: sürüm {SURUM} · {TELIF}")
