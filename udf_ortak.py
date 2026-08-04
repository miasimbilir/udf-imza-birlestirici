#!/usr/bin/env python3
"""UDF okuma/yazma ve ortak yardimcilar."""
import io
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TSI = ZoneInfo("Europe/Istanbul")
except Exception:                                   # tz veritabani yoksa sabit +3
    TSI = timezone(timedelta(hours=3))


class Durdur(Exception):
    """Denetim kapisi gecilemedi; islem guvenli sekilde durduruldu."""


def udf_oku(yol):
    """UDF'ten content.xml, sign.sgn ve tum ZIP uyelerini dondur."""
    if not os.path.exists(yol):
        raise Durdur(f"dosya bulunamadı: {yol}")
    try:
        with zipfile.ZipFile(yol) as z:
            uyeler = z.namelist()
            if "content.xml" not in uyeler:
                raise Durdur(f"{os.path.basename(yol)}: content.xml yok — "
                             "bu geçerli bir UDF belgesi değil.")
            if "sign.sgn" not in uyeler:
                raise Durdur(f"{os.path.basename(yol)}: belge imzasız (sign.sgn yok).")
            return {
                "yol": yol,
                "content": z.read("content.xml"),
                "sgn": z.read("sign.sgn"),
                # sikistirma yontemi korunur; degismeyen uyeler aynen tasinir
                "uyeler": {n: (z.read(n), z.getinfo(n).compress_type) for n in uyeler},
            }
    except zipfile.BadZipFile:
        raise Durdur(f"{os.path.basename(yol)}: dosya açılamadı (bozuk olabilir).")


def udf_baytlari(asil, yeni_sgn):
    """Asil nushanin ZIP yapisini koruyarak yalniz sign.sgn'i degistir."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for ad, (veri, yontem) in asil["uyeler"].items():
            z.writestr(zipfile.ZipInfo(ad),
                       yeni_sgn if ad == "sign.sgn" else veri,
                       compress_type=yontem)
    return tampon.getvalue()


def zaman_coz(s):
    """CMS UTCTime / GeneralizedTime -> datetime (UTC)."""
    if not s:
        return None
    s = s.strip().rstrip("Z")
    try:
        if len(s) == 12:                                    # YYMMDDHHMMSS
            yy = int(s[:2])
            yil = 2000 + yy if yy < 50 else 1900 + yy
            b = 2
        elif len(s) >= 14:                                  # YYYYMMDDHHMMSS
            yil, b = int(s[:4]), 4
        else:
            return None
        return datetime(yil, int(s[b:b+2]), int(s[b+2:b+4]), int(s[b+4:b+6]),
                        int(s[b+6:b+8]), int(s[b+8:b+10]), tzinfo=timezone.utc)
    except ValueError:
        return None


def zaman_yaz(dt):
    """Imza zamanlari CMS'te UTC'dir; ekranda Turkiye saatiyle gosterilir."""
    if not dt:
        return "—"
    return dt.astimezone(TSI).strftime("%d.%m.%Y %H:%M") + " TSİ"


def udf_metin(content_baytlari):
    """content.xml CDATA'sindaki duz metin (fark gosterimi icin)."""
    xml = content_baytlari.decode("utf-8", "replace")
    m = re.search(r"<content>\s*<!\[CDATA\[(.*?)\]\]>\s*</content>", xml, re.S)
    return m.group(1) if m else xml


def farklari_ozetle(nushalar):
    """Metni tutmayan nushalarin nerede ayrildigini kisaca goster."""
    import difflib
    a = udf_metin(nushalar[0]["content"]).splitlines()
    satirlar = []
    for u in nushalar[1:]:
        b = udf_metin(u["content"]).splitlines()
        if a == b:
            continue
        satirlar.append(f"{os.path.basename(nushalar[0]['yol'])} → "
                        f"{os.path.basename(u['yol'])}:")
        n = 0
        for s in difflib.unified_diff(a, b, lineterm="", n=0):
            if s.startswith(("---", "+++", "@@")):
                continue
            satirlar.append("   " + s[:90])
            n += 1
            if n >= 8:
                satirlar.append("   … (kısaltıldı)")
                break
        if n == 0:
            satirlar.append("   metin aynı; fark biçimlendirme veya boşluklarda.")
    return "\n".join(satirlar)
