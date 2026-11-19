#!/usr/bin/env python3
"""
İmza birleştirme çekirdeği — arayüzden bağımsız.

UDF imzası ayrık (detached) CMS'tir ve imzalar paraleldir: her imza doğrudan
content.xml'in özetini imzalar, hiçbiri diğerini kapsamaz. Bu yüzden ayrı ayrı
imzalanmış nüshaların imza kümeleri birleştirilebilir ve hiçbir imza bozulmaz.

Sekiz güvenlik kapısı; hepsi geçilmeden dosya üretilmez.
"""
import hashlib
import io
import os
import zipfile

import cms_imza as cms
import imza_dogrula as dog
from udf_ortak import Durdur, udf_baytlari, udf_oku, farklari_ozetle, zaman_coz, zaman_yaz

ADIMLAR = [
    ("oku",   "Belgeler okundu"),
    ("ayni",  "Belge metni birebir aynı"),
    ("imza",  "Tüm imzalar kriptografik olarak geçerli"),
    ("bag",   "İmzalar bu belgenin özetine bağlı"),
    ("capa",  "Ortak (çapa) imza mevcut"),
    ("muk",   "Mükerrer imzacı ve nüsha yok"),
    ("gecer", "Sertifikalar imza anında geçerliydi"),
    ("son",   "Birleşik belge yeniden doğrulandı"),
]


def _sertifika_dizini(sd):
    dizin = {}
    for c in sd["sertifikalar"]:
        b = cms.sertifika_bilgi(c, cms.coz_tlv(c)[0])
        anahtar = (b["issuer_der"], b["seri"])
        if anahtar in dizin and dizin[anahtar][0] != c:
            # Imza (issuer, seri) ile sertifikaya baglanir; ayni kimlikli iki
            # farkli sertifika hangisinin kullanilacagini belirsiz kilar.
            raise Durdur(f"Aynı seri numaralı iki farklı sertifika var ({b['ad']}). "
                         "Nüshalardan biri değiştirilmiş olabilir.")
        dizin[anahtar] = (c, b)
    return dizin


# UYAP'in yazdigi bolumler; documentproperties.xml imzaya dahil degildir.
BILINEN_BOLUMLER = {"content.xml", "sign.sgn", "documentproperties.xml"}


def _yabanci_bolumler(u):
    return sorted(n for n in u["uyeler"] if n not in BILINEN_BOLUMLER)


def _imza_bilgi_notlari(bi, cert):
    """Imza gecerli olsa da kullaniciya soylenmesi gerekenler."""
    notlar = []
    ad = cert["ad"] if cert else "bilinmeyen imzacı"
    if "signatureTimeStampToken" not in bi["imzasiz_alanlar"]:
        notlar.append(f"{ad} imzasında zaman damgası yok; imza saati "
                      "imzalayanın kendi bilgisayarına ait.")
    if bi.get("ozet_alg") == "sha1" or bi.get("imza_alg_oid") in ("1.2.840.113549.1.1.5",
                                                                   "1.2.840.10045.4.1"):
        notlar.append(f"{ad} imzası eski SHA-1 algoritmasıyla atılmış; bazı "
                      "doğrulayıcılar bu imzayı kabul etmeyebilir.")
    return notlar


def _imza_anindaki_gecerlilik(bi, cert):
    """(z, gecerli_mi): z imza zamani; gecerli_mi None ise denetlenemedi."""
    z = zaman_coz(bi.get("zaman"))
    b1, b2 = zaman_coz(cert["baslangic"]), zaman_coz(cert["bitis"])
    if not (z and b1 and b2):
        return z, None
    return z, b1 <= z <= b2


def _denetlenemedi_notu(ad, bi):
    neden = ("imza zamanı yok" if not zaman_coz(bi.get("zaman"))
             else "sertifikanın geçerlilik tarihleri okunamadı")
    return (f"{ad} imzasında {neden}; sertifikanın imza anında geçerli olup olmadığı "
            "denetlenemedi.")


def _imza_coz(u):
    """sign.sgn'i cozer; bozuk yapida anlasilir bir Durdur verir."""
    ad = os.path.basename(u["yol"])
    try:
        sd = cms.coz(u["sgn"])
        for si in sd["imzalar"]:
            cms.imza_bilgi(si)
        for c in sd["sertifikalar"]:
            cms.sertifika_bilgi(c, cms.coz_tlv(c)[0])
    except (ValueError, IndexError, KeyError, UnicodeError):
        raise Durdur(f"{ad}: imza bölümü (sign.sgn) çözümlenemedi — dosya bozuk "
                     "olabilir ya da UYAP dışı bir araçla üretilmiş olabilir.")
    if not sd["imzalar"]:
        raise Durdur(f"{ad}: belgede imza yok.")
    if not sd["detached"]:
        raise Durdur(f"{ad}: imza belgeye gömülü (ayrık değil). "
                     "Bu araç yalnızca UYAP'ın ürettiği ayrık imzaları işler.")
    return sd


def incele_tek(yol):
    """Tek bir UDF'yi inceler: kimler imzalamış, imzalar geçerli mi.

    Birleştirme yapmaz. Döner: {ad, imzacilar, ozet, gecerli, sebep}
    """
    u = udf_oku(yol)
    sd = _imza_coz(u)
    dizin = _sertifika_dizini(sd)
    imzacilar, gecerli, sebep, notlar = [], True, "", []
    for si in sd["imzalar"]:
        bi = cms.imza_bilgi(si)
        cert_ham, cert = dizin.get((bi.get("issuer_der"), bi.get("seri")), (None, None))
        ok, disi, s = dog.imza_dogrula(bi, cert_ham, u["content"])
        zamaninda = None
        if ok:
            z, zamaninda = _imza_anindaki_gecerlilik(bi, cert)
            if zamaninda is None:
                notlar.append(_denetlenemedi_notu(cert["ad"], bi))
            if zamaninda is False:
                ok, s = False, f"sertifika imza anında geçerli değildi ({zaman_yaz(z)})"
        if not ok:
            gecerli = False
            sebep = f"{cert['ad'] if cert else 'bilinmeyen imzacı'}: {s}"
        imzacilar.append({
            "ad": cert["ad"] if cert else "?", "tckn": cert.get("tckn") if cert else None,
            "unvan": cert.get("unvan") if cert else None,
            "zaman": zaman_yaz(zaman_coz(bi.get("zaman"))),
            "capa": False, "disi": disi, "gecerli": ok,
            "sure_denetlenemedi": ok and zamaninda is None,
        })
    return {"ad": os.path.basename(yol), "imzacilar": imzacilar, "gecerli": gecerli,
            "sebep": sebep, "detached": sd["detached"], "notlar": notlar,
            "ozet": hashlib.sha256(u["content"]).hexdigest()}


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
        try:
            u = udf_oku(y)
            u["sd"] = _imza_coz(u)
        except Durdur as e:
            bildir("oku", "hata", str(e).split("\n")[0])
            raise
        nushalar.append(u)
    for u in nushalar:
        yabanci = _yabanci_bolumler(u)
        if yabanci:
            nereye = ("birleşik belgeye aynen taşındı" if u is nushalar[0]
                      else "birleşik belgeye alınmadı")
            uyarilar.append(f"“{os.path.basename(u['yol'])}” dosyasında UYAP belgesinde "
                            f"bulunmayan bölüm var ({', '.join(yabanci)}). Bu bölüm imzaya "
                            f"dahil değildir; {nereye}.")
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
            uyarilar.extend(_imza_bilgi_notlari(bi, cert))
            if disi:
                uyarilar.append(
                    f"{cert['ad']} imzası standart dışı kodlanmış (DigestInfo'da NULL "
                    "parametresi eksik). İmza matematiksel olarak doğrulandı; bazı katı "
                    "doğrulayıcılar bu imzayı geçersiz gösterebilir.")
            tum.append({"u": u, "bi": bi, "cert": cert, "disi": disi})
    disi_sayi = sum(1 for t in tum if t["disi"])
    bildir("imza", "tamam", f"{len(tum)} imzanın tamamı geçerli" +
           (f" ({disi_sayi} tanesinde standart dışı kodlama)" if disi_sayi else ""))
    algler = sorted({t["bi"]["ozet_alg"].upper().replace("SHA", "SHA-") for t in tum})
    bildir("bag", "tamam", f"her imza bu belgenin özetine bağlı ({', '.join(algler)})")

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

    # ---- KAPI 5: mükerrer imzacı ve mükerrer nüsha -------------------------
    bildir("muk", "calisiyor", "")
    kisiler, adlar = {}, {}
    for t in tum:
        kim = t["cert"].get("tckn") or t["cert"]["ad"]
        kisiler.setdefault(kim, set()).add(t["bi"]["anahtar"])
        adlar[kim] = t["cert"]["ad"] + (f" (T.C. {t['cert']['tckn']})"
                                        if t["cert"].get("tckn") else "")
    coklu = [adlar[k] for k, v in kisiler.items() if len(v) > 1]
    if coklu:
        bildir("muk", "hata", "aynı kişi birden çok sertifikayla imzalamış")
        raise Durdur("Aynı kişi farklı sertifikalarla imzalamış: " + ", ".join(coklu) +
                     "\n\nNüshaların doğru dosyalar olduğunu kontrol edin.")
    # Yeni imza katmayan nüsha: ayni dosya iki kez eklenmis ya da taraf belgeyi
    # imzalamadan geri gondermis. Birlesik belgede o tarafin imzasi eksik kalir.
    katkisiz, adlar_k = [], []
    for i, u in enumerate(nushalar):
        digerleri = set().union(*(k for j, k in enumerate(kumeler) if j != i))
        if kumeler[i] <= digerleri:
            kimler = sorted({t["cert"]["ad"] for t in tum if t["u"] is u})
            adlar_k.append(f"“{os.path.basename(u['yol'])}”")
            katkisiz.append(f"{adlar_k[-1]}: {', '.join(kimler)}")
    if katkisiz:
        bildir("muk", "hata", "yeni imza katmayan nüsha var")
        # Ilk satir ana pencerede tek basina gosterilir: dosya adi orada olmali.
        raise Durdur(
            ", ".join(adlar_k) + " birleşik belgeye yeni imza katmıyor.\n\n"
            "Nüshadaki imzalar:\n" + "\n".join(katkisiz) +
            "\n\nBu nüshadaki imzaların tamamı diğer nüshalarda zaten var. Aynı dosya "
            "iki kez eklenmiş ya da taraf belgeyi imzalamadan geri göndermiş olabilir. "
            "Nüshayı listeden çıkarın ya da imzalı nüshayı isteyin.")
    bildir("muk", "tamam", f"{len(kisiler)} ayrı imzacı · her nüsha yeni imza katıyor")

    # ---- KAPI 6: sertifika imza anında geçerli miydi ------------------------
    bildir("gecer", "calisiyor", "")
    denetlenemeyen = []
    for t in tum:
        z, zamaninda = _imza_anindaki_gecerlilik(t["bi"], t["cert"])
        if zamaninda is False:
            bildir("gecer", "hata", f"{t['cert']['ad']}: sertifika imza anında geçersiz")
            raise Durdur(f"{t['cert']['ad']} sertifikası imza anında geçerli değildi "
                         f"({zaman_yaz(z)}).")
        if zamaninda is None:
            # Durdurulmaz (kullanici karari 19.11.2026): bilerek "denetlenemedi" denir;
            # kayda "tamami gecerliydi" yazilmaz.
            not_ = _denetlenemedi_notu(t["cert"]["ad"], t["bi"])
            if not_ not in denetlenemeyen:
                denetlenemeyen.append(not_)
    if denetlenemeyen:
        uyarilar.extend(denetlenemeyen)
        bildir("gecer", "tamam",
               f"{len(tum) - len(denetlenemeyen)} imzada sertifika imza anında geçerliydi; "
               f"{len(denetlenemeyen)} imzada denetlenemedi (imza zamanı yok)")
    else:
        bildir("gecer", "tamam", f"{len(tum)} sertifikanın tamamı imza anında geçerliydi")
    uyarilar.append("Sertifika zinciri (kök makam) doğrulanmadı.")

    # ---- birleştir ve KAPI 7/8: çıktıyı yeniden doğrula --------------------
    bildir("son", "calisiyor", "birleştiriliyor…")
    asil = nushalar[0]
    try:
        yeni_sgn = cms.birlestir([u["sd"] for u in nushalar], sirala="zaman")
    except ValueError as e:
        bildir("son", "hata", "imza bölümleri birleştirilemedi")
        raise Durdur(f"Nüshaların imza bölümleri birleştirilemedi ({e}); dosya üretilmedi.")
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
    baytlar = udf_baytlari(asil, yeni_sgn)
    with zipfile.ZipFile(io.BytesIO(baytlar)) as z:
        if (z.testzip() is not None or z.read("sign.sgn") != yeni_sgn or
                hashlib.sha256(z.read("content.xml")).hexdigest() != icerik_ozeti):
            bildir("son", "hata", "üretilen dosya doğrulanamadı")
            raise Durdur("Birleşik belge doğrulanamadı; dosya üretilmedi.")
    bildir("son", "tamam", f"{len(imzacilar)} imzanın tamamı birleşik belgede geçerli")

    ad = os.path.basename(asil["yol"])
    if ad.lower().endswith(".udf"):
        ad = ad[:-4]
    return {
        "baytlar": baytlar,
        "ad": ad + " (birleşik imzalı).udf",
        "imzacilar": imzacilar,
        "uyarilar": list(dict.fromkeys(uyarilar)),
        "denetlenemeyen": denetlenemeyen,
        "ozet": icerik_ozeti,
        "nushalar": [{"ad": os.path.basename(u["yol"]),
                      "imza": len(u["sd"]["imzalar"])} for u in nushalar],
        "adimlar": adimlar,
    }
