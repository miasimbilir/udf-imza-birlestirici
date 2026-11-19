#!/usr/bin/env python3
"""Gece denetiminin önerilerinden yapılanlar (19.11.2026).

Sertifika sırası, tek belge incelemesinde süre denetimi, imza zamanı yoksa
"denetlenemedi" (karar 07), UYAP dışı ZIP bölümü
uyarısı, zaman damgası ve SHA-1 notları, aşırı büyük RSA anahtarı, iptal
listesi tekrarı, çözümlenemeyen anahtar.

Veriler testler/veri/ içindedir ve SENTETİKTİR (bkz. veri_uret.py).
"""
import io
import os
import sys
import unittest
import zipfile
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import birlestirici as b          # noqa: E402
import cms_imza as cms            # noqa: E402
import imza_dogrula as dog        # noqa: E402
import test_birlestirici as tb    # noqa: E402
from udf_ortak import udf_baytlari, udf_oku   # noqa: E402

RSA_OID = bytes.fromhex("06092a864886f70d010101")


def sertifika_anahtari(c):
    x = cms.sertifika_bilgi(c, cms.coz_tlv(c)[0])
    return x["issuer_der"], x["seri"]


def cikti_sd(sonuc):
    with zipfile.ZipFile(io.BytesIO(sonuc["baytlar"])) as z:
        return cms.coz(z.read("sign.sgn"))


class SertifikaSirasi(tb.GeciciKlasor):
    """UYAP ardışık imzada sertifikaları imza sırasıyla yazar (arşivde 88/88)."""

    def sira_tutarli(self, sd):
        imzalar = [cms.imza_bilgi(s) for s in sd["imzalar"]]
        anahtarlar = [(i["issuer_der"], i["seri"]) for i in imzalar]
        self.assertEqual([sertifika_anahtari(c) for c in sd["sertifikalar"]], anahtarlar)

    def test_sertifikalar_imza_sirasiyla(self):
        for sira in ([tb.veri("nusha-arb-a"), tb.veri("nusha-arb-b")],
                     [tb.veri("nusha-arb-b"), tb.veri("nusha-arb-a")]):
            self.sira_tutarli(cikti_sd(b.denetle(sira)))

    def test_her_nusha_yalniz_kendi_sertifikasini_tasirsa(self):
        # Gerçek eşzamanlı imzada her nüsha yalnız kendi imzacılarının
        # sertifikasını taşır; sertifikalar yine imza sırasına dizilmeli.
        def yalniz_kendi(sd):
            gerekli = {(cms.imza_bilgi(s)["issuer_der"], cms.imza_bilgi(s)["seri"])
                       for s in sd["imzalar"]}
            sd["sertifikalar"] = [c for c in sd["sertifikalar"][::-1]
                                  if sertifika_anahtari(c) in gerekli]
        a = self.sgn_degistir(tb.veri("nusha-arb-a"), "a.udf", yalniz_kendi)
        bb = self.sgn_degistir(tb.veri("nusha-arb-b"), "b.udf", yalniz_kendi)
        self.sira_tutarli(cikti_sd(b.denetle([bb, a])))

    def test_imzaya_bagli_olmayan_sertifika_sona(self):
        sd = cms.coz(udf_oku(tb.veri("nusha-arb-a"))["sgn"])
        fazla = cms.coz(udf_oku(tb.veri("nusha-b"))["sgn"])["sertifikalar"][0]
        sd["sertifikalar"] = [fazla] + sd["sertifikalar"]
        yeni = cms.coz(cms.kur(sd, sirala="zaman"))
        self.assertEqual(yeni["sertifikalar"][-1], fazla)


class TekBelgeSuresi(tb.GeciciKlasor):
    def test_suresi_gecmis_sertifika_tek_belgede_gecersiz(self):
        def eskit(sd):
            for i, c in enumerate(sd["sertifikalar"]):
                bitis = cms.sertifika_bilgi(c, cms.coz_tlv(c)[0])["bitis"].encode("ascii")
                sd["sertifikalar"][i] = c.replace(bitis, b"200101000000Z", 1)
        yol = self.sgn_degistir(tb.veri("nusha-arb-a"), "eski.udf", eskit)
        t = b.incele_tek(yol)
        self.assertFalse(t["gecerli"])
        self.assertIn("imza anında geçerli değildi", t["sebep"])

    def test_gecerli_sertifika_tek_belgede_gecerli(self):
        self.assertTrue(b.incele_tek(tb.veri("nusha-arb-a"))["gecerli"])


class YabanciBolum(tb.GeciciKlasor):
    def ekle(self, ad, bolum):
        u = udf_oku(tb.veri("nusha-arb-a"))
        u["uyeler"][bolum] = (b"<x/>", zipfile.ZIP_DEFLATED)
        return self.yaz(ad, udf_baytlari(u, u["sgn"]))

    def test_bilinmeyen_bolum_uyarilir(self):
        yol = self.ekle("fazla.udf", "gizli.bin")
        r = b.denetle([yol, tb.veri("nusha-arb-b")])
        self.assertTrue(any("gizli.bin" in u and "taşındı" in u for u in r["uyarilar"]))

    def test_documentproperties_uyarilmaz(self):
        yol = self.ekle("ozellik.udf", "documentproperties.xml")
        r = b.denetle([yol, tb.veri("nusha-arb-b")])
        self.assertFalse(any("bulunmayan bölüm" in u for u in r["uyarilar"]))


class ImzaNotlari(unittest.TestCase):
    CERT = {"ad": "DENEME"}

    def notlar(self, **bi):
        temel = {"imzasiz_alanlar": [], "ozet_alg": "sha256",
                 "imza_alg_oid": "1.2.840.113549.1.1.11"}
        temel.update(bi)
        return b._imza_bilgi_notlari(temel, self.CERT)

    def test_zaman_damgasi_adina_bakilir(self):
        self.assertTrue(any("zaman damgası yok" in n for n in self.notlar()))
        # başka bir imzasız öznitelik zaman damgası sayılmaz
        self.assertTrue(any("zaman damgası yok" in n
                            for n in self.notlar(imzasiz_alanlar=["1.2.3.4"])))
        self.assertFalse(any("zaman damgası yok" in n for n in
                             self.notlar(imzasiz_alanlar=["signatureTimeStampToken"])))

    def test_sha1_notu(self):
        self.assertFalse(any("SHA-1" in n for n in self.notlar()))
        self.assertTrue(any("SHA-1" in n for n in self.notlar(ozet_alg="sha1")))
        self.assertTrue(any("SHA-1" in n for n in
                            self.notlar(imza_alg_oid="1.2.840.113549.1.1.5")))


class Dayaniklilik(tb.GeciciKlasor):
    def test_asiri_buyuk_rsa_anahtari_hesaplanmaz(self):
        n = (1 << (dog.AZAMI_RSA_BIT + 8)) + 1
        anahtar = cms.tlv(0x30, cms.tlv(0x02, n.to_bytes((n.bit_length() + 8) // 8, "big")) +
                          cms.tlv(0x02, b"\x01\x00\x01"))
        spki = cms.tlv(0x30, cms.tlv(0x30, RSA_OID + b"\x05\x00") +
                       cms.tlv(0x03, b"\x00" + anahtar))
        imza = b"\x01" * ((n.bit_length() + 7) // 8)
        with mock.patch("builtins.pow", side_effect=AssertionError("hesaplanmamalı")):
            self.assertEqual(dog.rsa_dogrula(spki, imza, b"x", "sha256"), (False, False))

    def test_iptal_listesi_tekrarlanmaz(self):
        sd1 = cms.coz(udf_oku(tb.veri("nusha-arb-a"))["sgn"])
        sd2 = cms.coz(udf_oku(tb.veri("nusha-arb-b"))["sgn"])
        sil = cms.tlv(0x30, b"\x05\x00")
        sd1["criller"] = [sil]
        sd2["criller"] = [sil]
        self.assertEqual(cms.coz(cms.birlestir([sd1, sd2]))["criller"], [sil])

    def test_cozumlenemeyen_anahtar_anlasilir_sebep(self):
        u = udf_oku(tb.veri("nusha-arb"))
        sd = cms.coz(u["sgn"])
        bi = cms.imza_bilgi(sd["imzalar"][0])
        with mock.patch.object(dog, "spki_cikar", side_effect=ValueError("bozuk")):
            ok, _, sebep = dog.imza_dogrula(bi, sd["sertifikalar"][0], u["content"])
        self.assertFalse(ok)
        self.assertIn("çözümlenemedi", sebep)

    def test_birlestirme_hatasi_durdur_olur(self):
        with mock.patch.object(cms, "birlestir", side_effect=ValueError("encap farklı")):
            self.durmali([tb.veri("nusha-arb-a"), tb.veri("nusha-arb-b")],
                         "birleştirilemedi")


class ImzaZamaniYok(tb.GeciciKlasor):
    """Karar 07 (19.11.2026): imza zamanı okunamazsa durdurulmaz, "denetlenemedi" denir."""

    def zamansiz(self, ad):
        n, d = tb.arb_anahtari()

        def islem(sd):
            i = self.arb_imzasi_indeksi(sd)
            sd["imzalar"][i] = tb.imzaci_degistir(sd["imzalar"][i], n, d,
                                                  alan_suzgeci=lambda a: a != "signingTime")
        return self.sgn_degistir(tb.veri("nusha-arb-a"), ad, islem)

    def test_birlestirmede_denetlenemedi_yazilir(self):
        r = b.denetle([self.zamansiz("z.udf"), tb.veri("nusha-arb-b")])
        self.assertTrue(r["denetlenemeyen"])
        self.assertTrue(any("imza zamanı yok" in u and "denetlenemedi" in u for u in r["uyarilar"]))
        gecer = [a for a in r["adimlar"] if a["adim"] == "gecer"][0]
        self.assertIn("denetlenemedi", gecer["detay"])
        self.assertNotIn("tamamı", gecer["detay"])

    def test_suresi_gecmis_ve_zamansiz_imza_denetlenemedi_sayilir(self):
        # gece raporundaki senaryo: sertifikanın süresi geçmiş ama imza zamanı
        # yok. "Geçerliydi" de "geçersizdi" de denemez; sonuç "denetlenemedi".
        sert = {"baslangic": "200101000000Z", "bitis": "210101000000Z"}
        self.assertEqual(b._imza_anindaki_gecerlilik({}, sert), (None, None))
        self.assertIs(b._imza_anindaki_gecerlilik({"zaman": "261021114548Z"}, sert)[1], False)

    def test_zamani_olan_imzada_uyari_yok(self):
        r = b.denetle([tb.veri("nusha-arb-a"), tb.veri("nusha-arb-b")])
        self.assertEqual(r["denetlenemeyen"], [])

    def test_tek_belgede_denetlenemedi_isareti(self):
        t = b.incele_tek(self.zamansiz("zt.udf"))
        self.assertTrue(t["gecerli"])
        self.assertTrue(any("denetlenemedi" in n for n in t["notlar"]))
        arb = [i for i in t["imzacilar"] if i["ad"] == "DENEME ARABULUCU"][0]
        self.assertTrue(arb["sure_denetlenemedi"])


if __name__ == "__main__":
    unittest.main()
