#!/usr/bin/env python3
"""
İmza birleştirme çekirdeği — arayüzden bağımsız.

UDF imzası ayrık (detached) CMS'tir ve imzalar paraleldir: her imza doğrudan
content.xml'in özetini imzalar, hiçbiri diğerini kapsamaz. Bu yüzden ayrı ayrı
imzalanmış nüshaların imza kümeleri birleştirilebilir ve hiçbir imza bozulmaz.

Sekiz güvenlik kapısı; hepsi geçilmeden dosya üretilmez.
"""
import hashlib
import os

import cms_imza as cms
import imza_dogrula as dog
from udf_ortak import Durdur, udf_baytlari, udf_oku, farklari_ozetle, zaman_coz, zaman_yaz

ADIMLAR = [
    ("oku",   "Belgeler okundu"),
    ("ayni",  "Belge metni birebir aynı"),
    ("imza",  "Tüm imzalar kriptografik olarak geçerli"),
    ("bag",   "İmzalar bu belgenin özetine bağlı"),
    ("capa",  "Ortak (çapa) imza mevcut"),
    ("muk",   "Mükerrer imzacı yok"),
    ("gecer", "Sertifikalar imza anında geçerliydi"),
    ("son",   "Birleşik belge yeniden doğrulandı"),
]


def _sertifika_dizini(sd):
    dizin = {}
    for c in sd["sertifikalar"]:
        b = cms.sertifika_bilgi(c, cms.coz_tlv(c)[0])
        dizin[(b["issuer_der"], b["seri"])] = (c, b)
    return dizin


def denetle(yollar, capa_tckn="", bildir=None):
    """Kapıları uygular ve birleşik belgeyi üretir.

    bildir(adim, durum, detay) ile ilerleme bildirilir; durum:
    "calisiyor" | "tamam" | "hata".

    Döner: {baytlar, ad, imzacilar, uyarilar, ozet, nushalar, adimlar}
    — adimlar, denetim raporunu yazmak için (başlık, sonuç) çiftleri.
    """
    dis_bildir = bildir or (lambda *a: None)
    adimlar = []
    basliklar = dict(ADIMLAR)

    def bildir(adim, durum, detay=""):
        dis_bildir(adim, durum, detay)
        if durum in ("tamam", "hata"):
            adimlar.append({"adim": adim, "baslik": basliklar.get(adim, adim),
                            "durum": durum, "detay": detay})

    uyarilar = []
    if len(yollar) < 2:
        raise Durdur("Birleştirme için en az iki nüsha gerekir.")

    # ---- nüshaları oku -----------------------------------------------------
    bildir("oku", "calisiyor", "okunuyor…")
    nushalar = []
    for y in yollar:
        u = udf_oku(y)
        u["sd"] = cms.coz(u["sgn"])
        if not u["sd"]["detached"]:
            bildir("oku", "hata", f"{os.path.basename(y)}: imza belgeye gömülü")
            raise Durdur(f"{os.path.basename(y)}: imza belgeye gömülü (ayrık değil). "
                         "Bu araç yalnızca UYAP'ın ürettiği ayrık imzaları birleştirir.")
        nushalar.append(u)
    bildir("oku", "tamam", f"{len(nushalar)} nüsha · " +
           " · ".join(f"{len(u['sd']['imzalar'])} imza" for u in nushalar))

    # ---- KAPI 1: belge metni birebir aynı ----------------------------------
    bildir("ayni", "calisiyor", "")
    ozetler = {hashlib.sha256(u["content"]).hexdigest() for u in nushalar}
    if len(ozetler) != 1:
        bildir("ayni", "hata", "nüshaların metni aynı değil")
        raise Durdur(
            "Nüshaların belge metni birbirinin aynısı değil. İmzalar farklı metinlere "
            "ait olduğu için birleştirilemez.\n\n"
            "Taraflara mutlaka aynı dosyanın kopyası gönderilmelidir.\n\n"
            + farklari_ozetle(nushalar))
    icerik_ozeti = ozetler.pop()
    bildir("ayni", "tamam", "SHA-256 " + icerik_ozeti)

    # ---- KAPI 2 ve 3: imza doğrulama, özete bağlılık -----------------------
    bildir("imza", "calisiyor", "imzalar doğrulanıyor…")
    tum = []
    for u in nushalar:
        dizin = _sertifika_dizini(u["sd"])
        for si in u["sd"]["imzalar"]:
            bi = cms.imza_bilgi(si)
            if "counterSignature" in bi["imzali_alanlar"] + bi["imzasiz_alanlar"]:
                bildir("imza", "hata", "zincirli imza (counterSignature)")
                raise Durdur("Belgede zincirli imza var; bu yapı birleştirmeye uygun değil.")
            cert_ham, cert = dizin.get((bi.get("issuer_der"), bi.get("seri")), (None, None))
            ok, disi, sebep = dog.imza_dogrula(bi, cert_ham, u["content"])
            if not ok:
                kim = cert["ad"] if cert else "bilinmeyen imzacı"
                bildir("imza", "hata", f"{os.path.basename(u['yol'])} → {kim}: {sebep}")
                raise Durdur(f"“{os.path.basename(u['yol'])}” dosyasındaki bir imza "
                             f"doğrulanamadı.\n\n{kim}: {sebep}")
            if not bi["imzasiz_alanlar"]:
                uyarilar.append(f"{cert['ad']} imzasında zaman damgası yok; imza saati "
                                "imzalayanın kendi bilgisayarına ait.")
            if disi:
                uyarilar.append(
                    f"{cert['ad']} imzası standart dışı kodlanmış (DigestInfo'da NULL "
                    "parametresi eksik). İmza matematiksel olarak doğrulandı; bazı katı "
                    "doğrulayıcılar bu imzayı geçersiz gösterebilir.")
            tum.append({"u": u, "bi": bi, "cert": cert, "disi": disi})
    disi_sayi = sum(1 for t in tum if t["disi"])
    bildir("imza", "tamam", f"{len(tum)} imzanın tamamı geçerli" +
           (f" ({disi_sayi} tanesinde standart dışı kodlama)" if disi_sayi else ""))
    bildir("bag", "tamam", "her imza bu belgenin SHA-256 özetine bağlı")

    # ---- KAPI 4: ortak (çapa) imza -----------------------------------------
    bildir("capa", "calisiyor", "")
    kumeler = [{t["bi"]["anahtar"] for t in tum if t["u"] is u} for u in nushalar]
    ortak = [a for a in kumeler[0] if all(a in k for k in kumeler)]
    if not ortak:
        bildir("capa", "hata", "nüshalarda ortak imzacı yok")
        raise Durdur("Nüshalarda ortak bir imza bulunamadı.\n\nBirleştirme yalnızca aynı "
                     "gönderime ait, en az bir ortak imzacı (arabulucu) taşıyan nüshalar "
                     "arasında yapılır.")
    ortak_certler = [next(t["cert"] for t in tum if t["bi"]["anahtar"] == a) for a in ortak]
    if capa_tckn:
        bulunan = next((c for c in ortak_certler if c.get("tckn") == capa_tckn), None)
        if not bulunan:
            bildir("capa", "hata", f"TCKN {capa_tckn} tüm nüshalarda ortak değil")
            raise Durdur(f"Belirttiğiniz çapa imza (TCKN {capa_tckn}) nüshaların "
                         "tamamında bulunmuyor.")
        bildir("capa", "tamam", f"{bulunan['ad']} — her nüshada aynı sertifika")
    else:
        bildir("capa", "tamam", ", ".join(c["ad"] for c in ortak_certler) +
               " — her nüshada ortak")

    # ---- KAPI 5: mükerrer imzacı -------------------------------------------
    bildir("muk", "calisiyor", "")
    kisiler = {}
    for t in tum:
        kisiler.setdefault(t["cert"].get("tckn") or t["cert"]["ad"], set()).add(
            t["bi"]["anahtar"])
    coklu = [k for k, v in kisiler.items() if len(v) > 1]
    if coklu:
        bildir("muk", "hata", "aynı kişi birden çok sertifikayla imzalamış")
        raise Durdur("Aynı kişi farklı sertifikalarla imzalamış: " + ", ".join(coklu) +
                     "\n\nNüshaların doğru dosyalar olduğunu kontrol edin.")
    bildir("muk", "tamam", f"{len(kisiler)} ayrı imzacı")

    # ---- KAPI 6: sertifika imza anında geçerli miydi ------------------------
    bildir("gecer", "calisiyor", "")
    for t in tum:
        z = zaman_coz(t["bi"].get("zaman"))
        b1, b2 = zaman_coz(t["cert"]["baslangic"]), zaman_coz(t["cert"]["bitis"])
        if z and b1 and b2 and not (b1 <= z <= b2):
            bildir("gecer", "hata", f"{t['cert']['ad']}: sertifika imza anında geçersiz")
            raise Durdur(f"{t['cert']['ad']} sertifikası imza anında geçerli değildi "
                         f"({zaman_yaz(z)}).")
    bildir("gecer", "tamam", f"{len(tum)} sertifikanın tamamı imza anında geçerliydi")
    uyarilar.append("Sertifika zinciri (kök makam) doğrulanmadı.")

    # ---- birleştir ve KAPI 7/8: çıktıyı yeniden doğrula --------------------
    bildir("son", "calisiyor", "birleştiriliyor…")
    asil = nushalar[0]
    yeni_sgn = cms.birlestir([u["sd"] for u in nushalar], sirala="zaman")
    yeni_sd = cms.coz(yeni_sgn)
    beklenen = len({t["bi"]["anahtar"] for t in tum})
    if len(yeni_sd["imzalar"]) != beklenen:
        bildir("son", "hata", "imza sayısı tutmuyor")
        raise Durdur("Birleştirme beklenen imza sayısını vermedi; dosya üretilmedi.")

    dizin = _sertifika_dizini(yeni_sd)
    imzacilar = []
    for si in yeni_sd["imzalar"]:
        bi = cms.imza_bilgi(si)
        cert_ham, cert = dizin.get((bi.get("issuer_der"), bi.get("seri")), (None, None))
        ok, disi, sebep = dog.imza_dogrula(bi, cert_ham, asil["content"])
        if not ok:
            bildir("son", "hata", f"{cert['ad'] if cert else '?'}: {sebep}")
            raise Durdur("Birleşik belge doğrulanamadı; dosya üretilmedi.")
        imzacilar.append({
            "ad": cert["ad"], "tckn": cert.get("tckn"), "unvan": cert.get("unvan"),
            "zaman": zaman_yaz(zaman_coz(bi.get("zaman"))),
            "capa": bi["anahtar"] in ortak, "disi": disi,
        })
    bildir("son", "tamam", f"{len(imzacilar)} imzanın tamamı birleşik belgede geçerli")

    ad = os.path.basename(asil["yol"])
    if ad.lower().endswith(".udf"):
        ad = ad[:-4]
    return {
        "baytlar": udf_baytlari(asil, yeni_sgn),
        "ad": ad + " (birleşik imzalı).udf",
        "imzacilar": imzacilar,
        "uyarilar": list(dict.fromkeys(uyarilar)),
        "ozet": icerik_ozeti,
        "nushalar": [{"ad": os.path.basename(u["yol"]),
                      "imza": len(u["sd"]["imzalar"])} for u in nushalar],
        "adimlar": adimlar,
    }
