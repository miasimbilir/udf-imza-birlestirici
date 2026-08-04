#!/usr/bin/env python3
"""
Saf Python imza dogrulama — hicbir dis programa (openssl) bagli degildir.

Neden: masaustu uygulamasi Windows'ta da calisacak; orada openssl yok.
Desteklenen: RSA PKCS#1 v1.5 (sha1/256/384/512) ve ECDSA (P-256/384/521).

RSA tarafinda, DigestInfo'ya NULL parametresi yazmayan imzalama araclarina
(Turkiye'de yaygin, UYAP kabul ediyor) izin verilir; dolgu ve tam kaplama
KATI denetlenir, dolayisiyla imza sahteciligine kapi acilmaz.
"""
import hashlib

from cms_imza import coz_tlv, oid_metin

OZET_OID = {
    "sha1": "1.3.14.3.2.26",
    "sha256": "2.16.840.1.101.3.4.2.1",
    "sha384": "2.16.840.1.101.3.4.2.2",
    "sha512": "2.16.840.1.101.3.4.2.3",
}

# imza algoritmasi OID -> (tip, ozet)   ozet None ise SignerInfo'daki kullanilir
IMZA_ALG = {
    "1.2.840.113549.1.1.11": ("RSA", "sha256"),
    "1.2.840.113549.1.1.12": ("RSA", "sha384"),
    "1.2.840.113549.1.1.13": ("RSA", "sha512"),
    "1.2.840.113549.1.1.5":  ("RSA", "sha1"),
    "1.2.840.113549.1.1.1":  ("RSA", None),
    "1.2.840.10045.4.3.2":   ("EC",  "sha256"),
    "1.2.840.10045.4.3.3":   ("EC",  "sha384"),
    "1.2.840.10045.4.3.4":   ("EC",  "sha512"),
    "1.2.840.10045.4.1":     ("EC",  "sha1"),
}


# --------------------------------------------------------------------------
# Eliptik egriler (NIST) — y^2 = x^3 + ax + b  (mod p),  a = p-3
# --------------------------------------------------------------------------
EGRILER = {
    # OID: (p, b, Gx, Gy, n, bayt)
    "1.2.840.10045.3.1.7": (  # P-256 / secp256r1
        0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff,
        0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b,
        0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,
        0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5,
        0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551, 32),
    "1.3.132.0.34": (          # P-384 / secp384r1
        0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffeffffffff0000000000000000ffffffff,
        0xb3312fa7e23ee7e4988e056be3f82d19181d9c6efe8141120314088f5013875ac656398d8a2ed19d2a85c8edd3ec2aef,
        0xaa87ca22be8b05378eb1c71ef320ad746e1d3b628ba79b9859f741e082542a385502f25dbf55296c3a545e3872760ab7,
        0x3617de4a96262c6f5d9e98bf9292dc29f8f41dbd289a147ce9da3113b5f0b8c00a60b1ce1d7e819d7a431d7c90ea0e5f,
        0xffffffffffffffffffffffffffffffffffffffffffffffffc7634d81f4372ddf581a0db248b0a77aecec196accc52973, 48),
    "1.3.132.0.35": (          # P-521 / secp521r1
        0x01ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff,
        0x0051953eb9618e1c9a1f929a21a0b68540eea2da725b99b315f3b8b489918ef109e156193951ec7e937b1652c0bd3bb1bf073573df883d2c34f1ef451fd46b503f00,
        0x00c6858e06b70404e9cd9e3ecb662395b4429c648139053fb521f828af606b4d3dbaa14b5e77efe75928fe1dc127a2ffa8de3348b3c1856a429bf97e7e31c2e5bd66,
        0x011839296a789a3bc0045c8a5fb42c7d1bd998f54449579b446817afbd17273e662c97ee72995ef42640c550b9013fad0761353c7086a272c24088be94769fd16650,
        0x01fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffa51868783bf2f966b7fcc0148f709a5d03bb5c9b8899c47aebb6fb71e91386409, 66),
}


def _topla(P, Q, p):
    """Jacobian yerine basit afin toplama — dogrulama icin hiz yeterli."""
    if P is None:
        return Q
    if Q is None:
        return P
    x1, y1 = P
    x2, y2 = Q
    if x1 == x2 and (y1 + y2) % p == 0:
        return None
    if P == Q:
        lam = (3 * x1 * x1 - 3) * pow(2 * y1, p - 2, p) % p      # a = -3
    else:
        lam = (y2 - y1) * pow(x2 - x1, p - 2, p) % p
    x3 = (lam * lam - x1 - x2) % p
    return (x3, (lam * (x1 - x3) - y1) % p)


def _carp(k, P, p):
    R = None
    while k:
        if k & 1:
            R = _topla(R, P, p)
        P = _topla(P, P, p)
        k >>= 1
    return R


def ec_nokta(spki):
    """SPKI'den (egri_oid, (x, y)) cikar."""
    sf = coz_tlv(spki)
    alanlar = coz_tlv(spki, sf[0][3], sf[0][4])
    alg = coz_tlv(spki, alanlar[0][3], alanlar[0][4])
    if oid_metin(spki[alg[0][3]:alg[0][4]]) != "1.2.840.10045.2.1" or len(alg) < 2:
        return None, None
    egri = oid_metin(spki[alg[1][3]:alg[1][4]])
    nokta = spki[alanlar[1][3]:alanlar[1][4]][1:]                # kullanilmayan-bit
    if not nokta or nokta[0] != 0x04:                            # yalniz sikistirilmamis
        return egri, None
    boy = (len(nokta) - 1) // 2
    return egri, (int.from_bytes(nokta[1:1 + boy], "big"),
                  int.from_bytes(nokta[1 + boy:], "big"))


def ecdsa_dogrula(spki, imza, veri, ozet_adi):
    egri_oid, Q = ec_nokta(spki)
    if not Q or egri_oid not in EGRILER:
        return False
    p, b, gx, gy, n, _ = EGRILER[egri_oid]
    if (Q[1] * Q[1] - Q[0] ** 3 + 3 * Q[0] - b) % p != 0:        # nokta egri uzerinde mi
        return False
    try:
        s0 = coz_tlv(imza)[0]
        f = coz_tlv(imza, s0[3], s0[4])
        if len(f) != 2:
            return False
        r = int.from_bytes(imza[f[0][3]:f[0][4]], "big")
        s = int.from_bytes(imza[f[1][3]:f[1][4]], "big")
    except Exception:
        return False
    if not (1 <= r < n and 1 <= s < n):
        return False

    ozet = hashlib.new(ozet_adi, veri).digest()
    e = int.from_bytes(ozet, "big")
    fazla = len(ozet) * 8 - n.bit_length()
    if fazla > 0:
        e >>= fazla
    sinv = pow(s, n - 2, n)
    R = _topla(_carp(e * sinv % n, (gx, gy), p), _carp(r * sinv % n, Q, p), p)
    return R is not None and R[0] % n == r


# --------------------------------------------------------------------------
# RSA PKCS#1 v1.5
# --------------------------------------------------------------------------
def rsa_anahtar(spki):
    sf = coz_tlv(spki)
    alanlar = coz_tlv(spki, sf[0][3], sf[0][4])
    alg = coz_tlv(spki, alanlar[0][3], alanlar[0][4])
    if oid_metin(spki[alg[0][3]:alg[0][4]]) != "1.2.840.113549.1.1.1":
        return None
    bit = spki[alanlar[1][3]:alanlar[1][4]][1:]
    kf = coz_tlv(bit)
    rf = coz_tlv(bit, kf[0][3], kf[0][4])
    return (int.from_bytes(bit[rf[0][3]:rf[0][4]], "big"),
            int.from_bytes(bit[rf[1][3]:rf[1][4]], "big"))


def rsa_dogrula(spki, imza, veri, ozet_adi):
    """Doner: (gecerli_mi, standart_disi_kodlama_mi)"""
    ne = rsa_anahtar(spki)
    if not ne:
        return False, False
    n, e = ne
    k = (n.bit_length() + 7) // 8
    if len(imza) != k or n <= 0 or e <= 0:
        return False, False
    kutu = pow(int.from_bytes(imza, "big"), e, n).to_bytes(k, "big")

    if kutu[0] != 0x00 or kutu[1] != 0x01:
        return False, False
    i = 2
    while i < len(kutu) and kutu[i] == 0xFF:
        i += 1
    if i - 2 < 8 or i >= len(kutu) or kutu[i] != 0x00:
        return False, False
    di = kutu[i + 1:]

    try:
        df = coz_tlv(di)
        if len(df) != 1 or df[0][4] != len(di):          # sonrasinda fazladan bayt olamaz
            return False, False
        ic = coz_tlv(di, df[0][3], df[0][4])
        if len(ic) != 2:
            return False, False
        alg = coz_tlv(di, ic[0][3], ic[0][4])
        if len(alg) > 2:
            return False, False
        standart = False
        if len(alg) == 2:                                 # parametre varsa tam olarak NULL
            if alg[1][0] != 0x05 or alg[1][4] != alg[1][3]:
                return False, False
            standart = True
        if oid_metin(di[alg[0][3]:alg[0][4]]) != OZET_OID.get(ozet_adi):
            return False, False
        bildirilen = di[ic[1][3]:ic[1][4]]
    except Exception:
        return False, False

    if bildirilen != hashlib.new(ozet_adi, veri).digest():
        return False, False
    return True, not standart


# --------------------------------------------------------------------------
# Genel giris
# --------------------------------------------------------------------------
def spki_cikar(sertifika):
    s = coz_tlv(sertifika)[0]
    tbs = coz_tlv(sertifika, s[3], s[4])[0]
    f = coz_tlv(sertifika, tbs[3], tbs[4])
    i = 1 if f[0][0] == 0xA0 else 0
    return sertifika[f[i + 5][2]:f[i + 5][4]]


def imzali_alanlar_verisi(si):
    """(imzalanan_veri, imza) — signedAttrs'in DER'i, [0] yerine SET OF (0x31)."""
    b = si
    s = coz_tlv(b)[0]
    f = coz_tlv(b, s[3], s[4])
    if f[3][0] != 0xA0:
        return None, b[f[4][3]:f[4][4]]
    veri = bytearray(b[f[3][2]:f[3][4]])
    veri[0] = 0x31
    return bytes(veri), b[f[5][3]:f[5][4]]


def imza_dogrula(bi, sertifika_ham, content):
    """Bir SignerInfo'yu dogrula.
    Doner: (ok, standart_disi, sebep)"""
    if not sertifika_ham:
        return False, False, "imzalayanın sertifikası dosyada yok"
    alg = IMZA_ALG.get(bi.get("imza_alg_oid"))
    if not alg:
        return False, False, f"desteklenmeyen imza algoritması ({bi.get('imza_alg_oid')})"
    tip, ozet = alg
    ozet = ozet or bi["ozet_alg"]
    if ozet not in OZET_OID:
        return False, False, "özet algoritması çözülemedi"

    veri, imza = imzali_alanlar_verisi(bi["ham"])
    if veri is None:
        veri = content
    spki = spki_cikar(sertifika_ham)

    if tip == "RSA":
        ok, disi = rsa_dogrula(spki, imza, veri, ozet)
    else:
        ok, disi = ecdsa_dogrula(spki, imza, veri, ozet), False
    if not ok:
        return False, False, "imza geçersiz — belge imzalandıktan sonra değişmiş olabilir"

    # signedAttrs kullanildiysa messageDigest gercekten icerigin ozeti mi?
    if bi.get("ozet"):
        if hashlib.new(bi["ozet_alg"], content).hexdigest() != bi["ozet"]:
            return False, False, "imza bu belgenin içeriğine ait değil"
    icerik_turu = bi.get("icerik_turu")
    if icerik_turu and icerik_turu != "1.2.840.113549.1.7.1":
        return False, False, "beklenmeyen içerik türü"
    return True, disi, ""
