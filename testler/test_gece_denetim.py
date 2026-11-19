#!/usr/bin/env python3
"""İmza doğrulamada katı kodlama denetimleri (18.11.2026 gece denetimi).

Buradaki imzaların hepsi MATEMATİKSEL olarak doğrudur (sentetik anahtarla
üretilir ya da sentetik nüshadan alınır); bozuk olan yalnız kodlamalarıdır.
Katı doğrulayıcılar bunları reddeder; program "geçerli" derse birleşik belge
başka bir doğrulayıcıda geçersiz imza taşıyabilir.
RSA tarafında gevşek DigestInfo ayrıştırması ayrıca küçük üslü (e=3)
anahtarlarda Bleichenbacher türü sahteciliğin ön koşuludur.

Veriler testler/veri/ içindedir ve SENTETİKTİR (bkz. veri_uret.py).
"""
import hashlib
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cms_imza as cms            # noqa: E402
import imza_dogrula as dog        # noqa: E402
import test_birlestirici as tb    # noqa: E402
from udf_ortak import udf_oku     # noqa: E402

# Özet algoritması OID'leri (etiket + uzunluk + gövde) — programdaki tablodan
# bağımsız yazıldı ki tablo da sınanmış olsun.
OID_DER = {
    "sha1":   bytes.fromhex("06052b0e03021a"),
    "sha256": bytes.fromhex("0609608648016503040201"),
    "sha384": bytes.fromhex("0609608648016503040202"),
    "sha512": bytes.fromhex("0609608648016503040203"),
}
NULL = b"\x05\x00"
VERI = b"deneme"


def ham_imzala(n, d, di):
    """Verilen DigestInfo baytlarını PKCS#1 v1.5 dolgusuyla imzalar."""
    k = (n.bit_length() + 7) // 8
    em = b"\x00\x01" + b"\xff" * (k - 3 - len(di)) + b"\x00" + di
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


class RsaKatiKodlama(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n, cls.d = tb.arb_anahtari()
        u = udf_oku(tb.veri("nusha-arb"))
        cls.spki = dog.spki_cikar(cms.coz(u["sgn"])["sertifikalar"][0])
        cls.ozet = hashlib.sha256(VERI).digest()

    def dogrula(self, di, ozet_adi="sha256"):
        return dog.rsa_dogrula(self.spki, ham_imzala(self.n, self.d, di), VERI, ozet_adi)

    def test_butun_ozetlerde_standart_ve_nullsuz(self):
        for ad, oid in OID_DER.items():
            ozet = hashlib.new(ad, VERI).digest()
            for null in (True, False):
                di = cms.tlv(0x30, cms.tlv(0x30, oid + (NULL if null else b"")) +
                             cms.tlv(0x04, ozet))
                self.assertEqual(self.dogrula(di, ad), (True, not null), (ad, null))

    def test_baska_ozetin_oid_i(self):
        # imza sha256 DigestInfo'su taşıyor, doğrulama sha1 ile isteniyor
        di = cms.tlv(0x30, cms.tlv(0x30, OID_DER["sha256"] + NULL) +
                     cms.tlv(0x04, self.ozet))
        self.assertEqual(self.dogrula(di, "sha1"), (False, False))

    def test_cok_baytli_etiket_icinde_cop(self):
        # 0x3F: çok baytlı etiket; ardından yüksek biti açık 40 serbest bayt
        ic = cms.tlv(0x30, OID_DER["sha256"] + NULL) + cms.tlv(0x04, self.ozet)
        di = b"\x3f" + bytes(range(0x80, 0xA8)) + b"\x10" + cms.uzunluk(len(ic)) + ic
        self.assertEqual(self.dogrula(di), (False, False))

    def test_yanlis_etiketler(self):
        alg = cms.tlv(0x30, OID_DER["sha256"] + NULL)
        for di in (
            cms.tlv(0x31, alg + cms.tlv(0x04, self.ozet)),          # dış SEQUENCE değil
            cms.tlv(0x30, alg + cms.tlv(0x0C, self.ozet)),          # özet OCTET STRING değil
            cms.tlv(0x30, cms.tlv(0x31, OID_DER["sha256"] + NULL) +
                    cms.tlv(0x04, self.ozet)),                      # algoritma SET
            cms.tlv(0x30, cms.tlv(0x30, b"\x04" + OID_DER["sha256"][1:] + NULL) +
                    cms.tlv(0x04, self.ozet)),                      # OID etiketi yanlış
        ):
            self.assertEqual(self.dogrula(di), (False, False), di.hex())

    def test_asgari_olmayan_uzunluk(self):
        ic = cms.tlv(0x30, OID_DER["sha256"] + NULL) + cms.tlv(0x04, self.ozet)
        di = b"\x30\x82\x00" + bytes([len(ic)]) + ic                # 0x31 yerine 82 00 31
        self.assertEqual(self.dogrula(di), (False, False))
        di = cms.tlv(0x30, cms.tlv(0x30, OID_DER["sha256"] + b"\x05\x81\x00") +
                     cms.tlv(0x04, self.ozet))                      # NULL uzun biçimde
        self.assertEqual(self.dogrula(di), (False, False))

    def test_oid_sonunda_cop(self):
        # tamamlanmamış alt tanımlayıcı: OID okuyucu sondaki baytları yok sayıyordu
        oid = cms.tlv(0x06, OID_DER["sha256"][2:] + b"\xff\xfe\xfd")
        di = cms.tlv(0x30, cms.tlv(0x30, oid + NULL) + cms.tlv(0x04, self.ozet))
        self.assertEqual(self.dogrula(di), (False, False))

    def test_imza_degeri_modulden_buyuk(self):
        # s ve s+n aynı sonucu verir; RFC 8017 m.8.2.2 s >= n olanı reddeder
        k = (self.n.bit_length() + 7) // 8
        for i in range(400):
            veri_ = b"deneme %d" % i
            s = int.from_bytes(tb.rsa_imzala(self.n, self.d, veri_), "big")
            if s + self.n < 1 << (8 * k):
                break
        else:
            self.skipTest("uygun imza bulunamadı")
        self.assertEqual(dog.rsa_dogrula(self.spki, s.to_bytes(k, "big"), veri_, "sha256"),
                         (True, False))
        self.assertEqual(dog.rsa_dogrula(self.spki, (s + self.n).to_bytes(k, "big"),
                                         veri_, "sha256"), (False, False))


class EcdsaKatiKodlama(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        u = udf_oku(tb.veri("nusha-b"))                 # yalnız EC (P-256) imzası
        sd = cms.coz(u["sgn"])
        cls.spki = dog.spki_cikar(sd["sertifikalar"][0])
        cls.veri, cls.imza = dog.imzali_alanlar_verisi(sd["imzalar"][0])

    def dogrula(self, imza, spki=None):
        return dog.ecdsa_dogrula(spki or self.spki, imza, self.veri, "sha256")

    def test_ozgun_imza_gecerli(self):
        self.assertTrue(self.dogrula(self.imza))
        self.assertFalse(dog.ecdsa_dogrula(self.spki, self.imza, self.veri + b".", "sha256"))

    def test_imzadan_sonra_fazla_bayt(self):
        self.assertFalse(self.dogrula(self.imza + b"\x05\x00"))

    def test_yanlis_etiketler(self):
        self.assertFalse(self.dogrula(b"\x31" + self.imza[1:]))        # SEQUENCE değil
        s0 = cms.coz_tlv(self.imza)[0]
        r, s = cms.coz_tlv(self.imza, s0[3], s0[4])
        ic = cms.tlv(0x04, self.imza[r[3]:r[4]]) + cms.ham(self.imza, s)
        self.assertFalse(self.dogrula(cms.tlv(0x30, ic)))              # r INTEGER değil

    def test_uc_elemanli_imza(self):
        s0 = cms.coz_tlv(self.imza)[0]
        self.assertFalse(self.dogrula(cms.tlv(0x30, self.imza[s0[3]:s0[4]] + b"\x02\x01\x01")))

    def test_indirgenmemis_nokta(self):
        # (x+p, y+p) aynı noktayı gösterir ama geçerli bir açık anahtar kodlaması değildir
        sf = cms.coz_tlv(self.spki)[0]
        alg, bit = cms.coz_tlv(self.spki, sf[3], sf[4])
        nokta = self.spki[bit[3]:bit[4]][1:]
        self.assertEqual(len(nokta), 65)
        p = dog.EGRILER["1.2.840.10045.3.1.7"][0]
        x = int.from_bytes(nokta[1:33], "big") + p
        y = int.from_bytes(nokta[33:], "big") + p
        yeni = b"\x00\x04" + x.to_bytes(33, "big") + y.to_bytes(33, "big")
        spki = cms.tlv(0x30, cms.ham(self.spki, alg) + cms.tlv(0x03, yeni))
        self.assertFalse(self.dogrula(self.imza, spki))

    def test_egri_sabitleri(self):
        # yazım hatasına karşı: p bilinen formülle aynı, G eğri üzerinde, n·G = sonsuzdaki nokta
        asallar = {
            "1.2.840.10045.3.1.7": 2**256 - 2**224 + 2**192 + 2**96 - 1,
            "1.3.132.0.34": 2**384 - 2**128 - 2**96 + 2**32 - 1,
            "1.3.132.0.35": 2**521 - 1,
        }
        for oid, (p, b, gx, gy, n, bayt) in dog.EGRILER.items():
            self.assertEqual(p, asallar[oid], f"{oid}: p {p.bit_length()} bit")
            self.assertEqual((gy * gy - gx ** 3 + 3 * gx - b) % p, 0, oid)
            self.assertIsNone(dog._carp(n, (gx, gy), p), oid)
            self.assertEqual((p.bit_length() + 7) // 8, bayt, oid)


EC_ACIK_ANAHTAR = bytes.fromhex("06072a8648ce3d0201")
EGRI_OID_DER = {
    "1.2.840.10045.3.1.7": bytes.fromhex("06082a8648ce3d030107"),
    "1.3.132.0.34": bytes.fromhex("06052b81040022"),
    "1.3.132.0.35": bytes.fromhex("06052b81040023"),
}


def der_tamsayi(v):
    return cms.tlv(0x02, v.to_bytes((v.bit_length() + 8) // 8, "big"))


def sinama_sayisi(etiket, n):
    """Tekrarlanabilir sözde rastgele sayı, [1, n-1] aralığında."""
    return int.from_bytes(hashlib.sha512(etiket.encode()).digest() * 2, "big") % (n - 1) + 1


class EcdsaButunEgriler(unittest.TestCase):
    """testler/veri yalnız P-256 imzası içerir; P-384 ve P-521 burada, sentetik
    anahtarla imzalanıp doğrulanır (özet kısaltması dahil)."""

    def test_imzala_ve_dogrula(self):
        for oid, (p, b, gx, gy, n, bayt) in dog.EGRILER.items():
            d = sinama_sayisi("anahtar" + oid, n)
            x, y = dog._carp(d, (gx, gy), p)
            nokta = b"\x00\x04" + x.to_bytes(bayt, "big") + y.to_bytes(bayt, "big")
            spki = cms.tlv(0x30, cms.tlv(0x30, EC_ACIK_ANAHTAR + EGRI_OID_DER[oid]) +
                           cms.tlv(0x03, nokta))
            # saf Python eğri çarpımı yavaştır: büyük eğrilerde tek özet yeter
            for ozet_adi in (("sha256", "sha512") if bayt == 32 else ("sha512",)):
                k = sinama_sayisi("k" + oid + ozet_adi, n)
                ozet = hashlib.new(ozet_adi, VERI).digest()
                e = int.from_bytes(ozet, "big")
                if len(ozet) * 8 > n.bit_length():          # FIPS 186: soldaki bitler
                    e >>= len(ozet) * 8 - n.bit_length()
                r = dog._carp(k, (gx, gy), p)[0] % n
                s = pow(k, n - 2, n) * (e + r * d) % n
                imza = cms.tlv(0x30, der_tamsayi(r) + der_tamsayi(s))
                self.assertTrue(dog.ecdsa_dogrula(spki, imza, VERI, ozet_adi), (oid, ozet_adi))
                self.assertFalse(dog.ecdsa_dogrula(spki, imza, VERI + b".", ozet_adi))
                for rr, ss in ((0, s), (r, 0), (n, s), (r, n), (r + n, s)):
                    kotu = cms.tlv(0x30, der_tamsayi(rr) + der_tamsayi(ss))
                    self.assertFalse(dog.ecdsa_dogrula(spki, kotu, VERI, ozet_adi))


class ImzaliAlanlar(tb.GeciciKlasor):
    def test_imzali_alanlar_belge_yerine_konamaz(self):
        # Arabulucunun gerçek imzasının signedAttrs baytları content.xml yapılır,
        # SignerInfo'dan signedAttrs çıkarılır: imza değeri o baytlar üzerinde
        # matematiksel olarak doğrudur ama arabulucu bu "belgeyi" imzalamamıştır.
        u = udf_oku(tb.veri("nusha-arb"))
        sd = cms.coz(u["sgn"])
        si = sd["imzalar"][0]
        veri_, _ = dog.imzali_alanlar_verisi(si)
        s = cms.coz_tlv(si)[0]
        f = cms.coz_tlv(si, s[3], s[4])
        sd["imzalar"][0] = cms.tlv(0x30, b"".join(cms.ham(si, x) for x in f[:3] + f[4:]))
        u["uyeler"]["content.xml"] = (veri_, u["uyeler"]["content.xml"][1])
        yol = self.yaz("sahte.udf", tb.udf_baytlari(u, cms.kur(sd, sirala="giris")))
        t = tb.b.incele_tek(yol)
        self.assertFalse(t["gecerli"])
        self.assertIn("messageDigest", t["sebep"])


if __name__ == "__main__":
    unittest.main()
