#!/usr/bin/env python3
"""Güvenlik kapıları, imza doğrulama ve dosya işlemleri testleri.

Yalnız Python standart kütüphanesi kullanılır (Windows'ta da çalışır):

    python -m unittest discover -s testler -v

Veriler testler/veri/ içindedir ve SENTETİKTİR (bkz. veri_uret.py). Olumsuz
senaryolar bu nüshalar bellekte bozularak kurulur.
"""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

import birlestirici as b          # noqa: E402
import cms_imza as cms            # noqa: E402
import imza_dogrula as dog        # noqa: E402
from udf_ortak import Durdur, guvenli_yaz, udf_baytlari, udf_oku   # noqa: E402

VERI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veri")
SHA256_OID = bytes.fromhex("0609608648016503040201")


def veri(ad):
    return os.path.join(VERI, ad + ".udf")


# --------------------------------------------------------------------------
# Yardımcılar: nüshayı bellekte değiştirip geçici klasöre yazmak
# --------------------------------------------------------------------------
def arb_anahtari():
    """Sentetik arabulucunun RSA anahtarı (PKCS#1): (n, d)."""
    with open(os.path.join(VERI, "arb-anahtar.der"), "rb") as f:
        der = f.read()
    s = cms.coz_tlv(der)[0]
    f_ = cms.coz_tlv(der, s[3], s[4])
    sayi = [int.from_bytes(der[x[3]:x[4]], "big") for x in f_]
    return sayi[1], sayi[3]


def rsa_imzala(n, d, veri_, null=True):
    """PKCS#1 v1.5 SHA-256 imzası; null=False ise DigestInfo'da NULL yazılmaz."""
    alg = cms.tlv(0x30, SHA256_OID + (b"\x05\x00" if null else b""))
    di = cms.tlv(0x30, alg + cms.tlv(0x04, hashlib.sha256(veri_).digest()))
    k = (n.bit_length() + 7) // 8
    em = b"\x00\x01" + b"\xff" * (k - 3 - len(di)) + b"\x00" + di
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def imzaci_degistir(si, n, d, null=True, alan_suzgeci=None):
    """SignerInfo'yu arabulucunun anahtarıyla yeniden imzalar.

    alan_suzgeci(ad) False dönen signedAttrs öznitelikleri çıkarılır.
    """
    s = cms.coz_tlv(si)[0]
    f = cms.coz_tlv(si, s[3], s[4])
    assert f[3][0] == 0xA0
    alanlar = cms.coz_tlv(si, f[3][3], f[3][4])
    tut = []
    for a in alanlar:
        p = cms.coz_tlv(si, a[3], a[4])
        ad = cms.ad(cms.oid_metin(si[p[0][3]:p[0][4]]))
        if alan_suzgeci is None or alan_suzgeci(ad):
            tut.append(cms.ham(si, a))
    govde = b"".join(tut)
    imza = rsa_imzala(n, d, cms.tlv(0x31, govde), null=null)
    yeni = (b"".join(cms.ham(si, x) for x in f[:3]) + cms.tlv(0xA0, govde) +
            cms.ham(si, f[4]) + cms.tlv(0x04, imza) +
            b"".join(cms.ham(si, x) for x in f[6:]))
    return cms.tlv(0x30, yeni)


class GeciciKlasor(unittest.TestCase):
    def setUp(self):
        self.gd = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.gd)

    def yaz(self, ad, baytlar):
        yol = os.path.join(self.gd, ad)
        with open(yol, "wb") as f:
            f.write(baytlar)
        return yol

    def kopya(self, kaynak, ad=None):
        yol = os.path.join(self.gd, ad or os.path.basename(kaynak))
        shutil.copy(kaynak, yol)
        return yol

    def sgn_degistir(self, kaynak, ad, islem):
        """Nüshanın çözülmüş SignedData'sı üzerinde islem(sd) uygular."""
        u = udf_oku(kaynak)
        sd = cms.coz(u["sgn"])
        islem(sd)
        return self.yaz(ad, udf_baytlari(u, cms.kur(sd, sirala="giris")))

    def arb_imzasi_indeksi(self, sd):
        for i, si in enumerate(sd["imzalar"]):
            bi = cms.imza_bilgi(si)
            for c in sd["sertifikalar"]:
                bilgi = cms.sertifika_bilgi(c, cms.coz_tlv(c)[0])
                if (bilgi["issuer_der"], bilgi["seri"]) == (bi["issuer_der"], bi["seri"]) \
                        and bilgi["ad"] == "DENEME ARABULUCU":
                    return i
        raise AssertionError("arabulucu imzası yok")

    def durmali(self, yollar, icerir):
        with self.assertRaises(Durdur) as bag:
            b.denetle(yollar)
        self.assertIn(icerir, str(bag.exception))
        return str(bag.exception)


# --------------------------------------------------------------------------
# Olumlu yol
# --------------------------------------------------------------------------
class Birlestirme(GeciciKlasor):
    def test_iki_nusha_birlesir(self):
        r = b.denetle([veri("nusha-arb-a"), veri("nusha-arb-b")])
        adlar = sorted(i["ad"] for i in r["imzacilar"])
        self.assertEqual(adlar, ["Ayşe DENEME", "DENEME ARABULUCU", "Şükrü DENEME"])
        self.assertEqual([a["durum"] for a in r["adimlar"]], ["tamam"] * 8)
        self.assertEqual([i["ad"] for i in r["imzacilar"] if i["capa"]], ["DENEME ARABULUCU"])

        # üretilen belge ayrıca açılıp incelendiğinde de üç imza geçerli
        yol = self.yaz(r["ad"], r["baytlar"])
        t = b.incele_tek(yol)
        self.assertTrue(t["gecerli"])
        self.assertEqual(len(t["imzacilar"]), 3)
        with zipfile.ZipFile(yol) as z:
            asil = udf_oku(veri("nusha-arb-a"))
            self.assertEqual(z.read("content.xml"), asil["content"])

    def test_tek_nusha_incelemesi(self):
        t = b.incele_tek(veri("nusha-arb-b"))
        self.assertTrue(t["gecerli"])
        self.assertEqual(sorted(i["ad"] for i in t["imzacilar"]),
                         ["DENEME ARABULUCU", "Şükrü DENEME"])

    def test_en_az_iki_nusha(self):
        with self.assertRaises(Durdur):
            b.denetle([veri("nusha-arb-a")])


# --------------------------------------------------------------------------
# Kapılar
# --------------------------------------------------------------------------
class Kapilar(GeciciKlasor):
    def test_farkli_metin(self):
        self.durmali([veri("nusha-arb-a"), veri("nusha-farkli-arb-b")], "aynısı değil")

    def test_ortak_imza_yok(self):
        self.durmali([veri("nusha-a"), veri("nusha-b")], "ortak bir imza")

    def test_ayni_kisi_iki_sertifika(self):
        msj = self.durmali([veri("nusha-arb-a"), veri("nusha-arb-arb2")],
                           "farklı sertifikalarla")
        self.assertIn("DENEME ARABULUCU (T.C. 10000000146)", msj)

    def test_ayni_nusha_iki_kez(self):
        ikinci = self.kopya(veri("nusha-arb-a"), "ikinci kopya.udf")
        msj = self.durmali([veri("nusha-arb-a"), ikinci], "yeni imza katmıyor")
        self.assertIn("ikinci kopya.udf", msj)

    def test_imzalanmadan_donen_nusha(self):
        msj = self.durmali([veri("nusha-arb-a"), veri("nusha-arb-b"), veri("nusha-arb")],
                           "yeni imza katmıyor")
        self.assertIn("nusha-arb.udf", msj)
        self.assertNotIn("nusha-arb-a.udf", msj)

    def test_bozulmus_imza(self):
        def boz(sd):
            si = bytearray(sd["imzalar"][0])
            si[-5] ^= 0x01                          # imza değerinin içinden bir bit
            sd["imzalar"][0] = bytes(si)
        yol = self.sgn_degistir(veri("nusha-arb-a"), "bozuk.udf", boz)
        self.durmali([yol, veri("nusha-arb-b")], "doğrulanamadı")
        self.assertFalse(b.incele_tek(yol)["gecerli"])

    def test_degistirilmis_metin_tek_nusha(self):
        u = udf_oku(veri("nusha-arb-a"))
        u["uyeler"]["content.xml"] = (u["content"].replace(b"testler", b"Testler"),
                                      u["uyeler"]["content.xml"][1])
        yol = self.yaz("degismis.udf", udf_baytlari(u, u["sgn"]))
        t = b.incele_tek(yol)
        self.assertFalse(t["gecerli"])
        self.assertTrue(all(not i["gecerli"] for i in t["imzacilar"]))

    def test_suresi_gecmis_sertifika(self):
        def eskit(sd):
            c = sd["sertifikalar"][0]
            bilgi = cms.sertifika_bilgi(c, cms.coz_tlv(c)[0])
            bitis = bilgi["bitis"].encode("ascii")
            self.assertEqual(len(bitis), 13)        # UTCTime YYMMDDHHMMSSZ
            sd["sertifikalar"][0] = c.replace(bitis, b"200101000000Z", 1)
        yol = self.sgn_degistir(veri("nusha-arb-a"), "eski.udf", eskit)
        self.durmali([yol, veri("nusha-arb-b")], "imza anında geçerli değildi")

    def test_ayni_seri_farkli_sertifika(self):
        # aynı (issuer, seri), farklı içerik: hangisinin kullanılacağı belirsiz
        def ikiz(sd):
            i = self.arb_imzasi_indeksi(sd)
            bi = cms.imza_bilgi(sd["imzalar"][i])
            for c in list(sd["sertifikalar"]):
                bilgi = cms.sertifika_bilgi(c, cms.coz_tlv(c)[0])
                if bilgi["seri"] == bi["seri"]:
                    # kendinden imzalı: ad önce issuer'da, sonra subject'te geçer;
                    # yalnız subject değişmeli ki (issuer, seri) aynı kalsın
                    k = c.rindex(b"DENEME ARABULUCU")
                    sd["sertifikalar"].append(c[:k] + b"DENEME ARABULUCV" + c[k + 16:])
        yol = self.sgn_degistir(veri("nusha-arb-a"), "ikiz.udf", ikiz)
        self.durmali([yol, veri("nusha-arb-b")], "iki farklı sertifika")
        with self.assertRaises(Durdur):
            b.incele_tek(yol)


# --------------------------------------------------------------------------
# İmza doğrulama ayrıntıları
# --------------------------------------------------------------------------
class ImzaDogrulama(GeciciKlasor):
    def arb_yeniden_imzala(self, ad, **kw):
        n, d = arb_anahtari()

        def islem(sd):
            i = self.arb_imzasi_indeksi(sd)
            sd["imzalar"][i] = imzaci_degistir(sd["imzalar"][i], n, d, **kw)
        return self.sgn_degistir(veri("nusha-arb-a"), ad, islem)

    def test_anahtar_gercekten_arabulucunun(self):
        # yardımcıların doğru çalıştığının kanıtı: NULL'lu yeniden imza geçerli
        yol = self.arb_yeniden_imzala("standart.udf", null=True)
        t = b.incele_tek(yol)
        self.assertTrue(t["gecerli"])
        self.assertFalse(any(i["disi"] for i in t["imzacilar"]))

    def test_null_siz_digestinfo_kabul_ve_isaret(self):
        yol = self.arb_yeniden_imzala("nullsuz.udf", null=False)
        t = b.incele_tek(yol)
        self.assertTrue(t["gecerli"])
        arb = [i for i in t["imzacilar"] if i["ad"] == "DENEME ARABULUCU"][0]
        self.assertTrue(arb["disi"])
        r = b.denetle([yol, veri("nusha-arb-b")])
        self.assertTrue(any("standart dışı" in u for u in r["uyarilar"]))

    def test_messageDigest_olmayan_imza_reddedilir(self):
        # imza matematiksel olarak geçerli ama belgeye bağlanmıyor
        yol = self.arb_yeniden_imzala("ozetsiz.udf",
                                      alan_suzgeci=lambda ad: ad != "messageDigest")
        t = b.incele_tek(yol)
        self.assertFalse(t["gecerli"])
        self.assertIn("messageDigest", t["sebep"])

    def test_digestinfo_sonunda_fazla_bayt(self):
        n, d = arb_anahtari()
        veri_ = b"deneme"
        alg = cms.tlv(0x30, SHA256_OID + b"\x05\x00")
        di = cms.tlv(0x30, alg + cms.tlv(0x04, hashlib.sha256(veri_).digest())) + b"\x00"
        k = (n.bit_length() + 7) // 8
        em = b"\x00\x01" + b"\xff" * (k - 3 - len(di)) + b"\x00" + di
        imza = pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")
        u = udf_oku(veri("nusha-arb"))
        spki = dog.spki_cikar(cms.coz(u["sgn"])["sertifikalar"][0])
        self.assertEqual(dog.rsa_dogrula(spki, imza, veri_, "sha256"), (False, False))
        self.assertEqual(dog.rsa_dogrula(spki, rsa_imzala(n, d, veri_), veri_, "sha256"),
                         (True, False))


# --------------------------------------------------------------------------
# Bozuk ve kötü niyetli dosyalar
# --------------------------------------------------------------------------
class BozukDosyalar(GeciciKlasor):
    def test_kesik_sign_sgn(self):
        u = udf_oku(veri("nusha-arb-a"))
        yol = self.yaz("kesik.udf", udf_baytlari(u, u["sgn"][:len(u["sgn"]) // 2]))
        with self.assertRaises(Durdur) as bag:
            b.incele_tek(yol)
        self.assertIn("çözümlenemedi", str(bag.exception))
        self.durmali([yol, veri("nusha-arb-b")], "çözümlenemedi")

    def test_cop_sign_sgn(self):
        u = udf_oku(veri("nusha-arb-a"))
        yol = self.yaz("cop.udf", udf_baytlari(u, b"\x30\x03\x02\x01\x00"))
        with self.assertRaises(Durdur):
            b.incele_tek(yol)

    def test_zip_degil(self):
        yol = self.yaz("duz.udf", b"bu bir zip degil")
        with self.assertRaises(Durdur):
            b.incele_tek(yol)

    def test_imzasiz_udf(self):
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w") as z:
            z.writestr("content.xml", b"<template/>")
        yol = self.yaz("imzasiz.udf", tampon.getvalue())
        with self.assertRaises(Durdur) as bag:
            b.incele_tek(yol)
        self.assertIn("imzasız", str(bag.exception))

    def test_ayni_adli_iki_bolum(self):
        u = udf_oku(veri("nusha-arb-a"))
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w") as z, \
                mock.patch("warnings.warn"):        # zipfile "Duplicate name" uyarısı
            z.writestr("content.xml", b"<template>sahte</template>")
            z.writestr("content.xml", u["content"])
            z.writestr("sign.sgn", u["sgn"])
        yol = self.yaz("cift.udf", tampon.getvalue())
        with self.assertRaises(Durdur) as bag:
            b.incele_tek(yol)
        self.assertIn("aynı adlı", str(bag.exception))

    def test_der_uzunluk_tasmasi(self):
        with self.assertRaises(ValueError):
            cms.coz_tlv(b"\x30\x05\x02\x01")
        with self.assertRaises(ValueError):
            cms.coz_tlv(b"\x30\x80\x02\x01\x00\x00\x00")   # BER belirsiz uzunluk
        with self.assertRaises(ValueError):
            cms.coz_tlv(b"\x30\x84\xff\xff")


# --------------------------------------------------------------------------
# Güvenli yazma
# --------------------------------------------------------------------------
class GuvenliYazma(GeciciKlasor):
    def test_yeni_dosya_ve_uzerine_yazma(self):
        yol = os.path.join(self.gd, "çıktı (birleşik imzalı).udf")
        guvenli_yaz(yol, b"birinci")
        guvenli_yaz(yol, b"ikinci")
        with open(yol, "rb") as f:
            self.assertEqual(f.read(), b"ikinci")
        self.assertEqual(os.listdir(self.gd), ["çıktı (birleşik imzalı).udf"])

    def test_yarida_kalan_yazma_hedefi_bozmaz(self):
        yol = self.yaz("mevcut.udf", b"eski icerik")
        with mock.patch("os.replace", side_effect=OSError("zaman aşımı")):
            with self.assertRaises(OSError):
                guvenli_yaz(yol, b"yeni icerik")
        with open(yol, "rb") as f:
            self.assertEqual(f.read(), b"eski icerik")
        self.assertEqual(os.listdir(self.gd), ["mevcut.udf"])     # geçici dosya kalmadı

    def test_geri_okuma_tutmazsa_yazilmaz(self):
        yol = os.path.join(self.gd, "hedef.udf")
        gercek_ac = open

        def bozuk_ac(p, kip="r", *a, **kw):
            f = gercek_ac(p, kip, *a, **kw)
            if "r" in kip and "b" in kip and os.path.basename(p).startswith(".udf-imza-"):
                with f:
                    return io.BytesIO(f.read()[:-1])
            return f
        with mock.patch("builtins.open", side_effect=bozuk_ac):
            with self.assertRaises(OSError):
                guvenli_yaz(yol, b"tam icerik")
        self.assertEqual(os.listdir(self.gd), [])


if __name__ == "__main__":
    unittest.main()
