#!/usr/bin/env python3
"""
CMS/PKCS#7 SignedData okuma ve yeniden kurma — UDF e-imza cekirdegi.

UYAP'in UDF imzasi (sign.sgn) su yapida:
    ContentInfo { signedData, SignedData { version, digestAlgorithms,
                  encapContentInfo(DETACHED), certificates, signerInfos } }

Kritik olgu (arsivdeki 242 imzali UDF, 551 imza uzerinde dogrulandi):
imzalar PARALEL'dir. Her SignerInfo'nun messageDigest'i dogrudan content.xml'in
SHA-256 ozetidir; hicbir imza digerini kapsamaz (counterSignature yok).
Bu yuzden ayri ayri imzalanmis iki nushanin SignerInfo kumeleri birlestirilebilir
ve imzalarin hicbiri bozulmaz.

Bu modul yalniz ayristirir ve yeniden kurar; imza dogrulamasini openssl yapar
(bkz. imza_birlestir.py).
"""
import hashlib


# --------------------------------------------------------------------------
# Asgari DER okuyucu/yazici
# --------------------------------------------------------------------------
def coz_tlv(b, off=0, son=None):
    """Bir seviyedeki TLV'leri (tag, tagno, bas, icerik_bas, icerik_son) dondur."""
    if son is None:
        son = len(b)
    out = []
    i = off
    while i < son:
        bas = i
        t = b[i]; i += 1
        tagno = t & 0x1F
        if tagno == 0x1F:                       # cok baytli etiket
            tagno = 0
            while True:
                tagno = (tagno << 7) | (b[i] & 0x7F)
                devam = b[i] & 0x80
                i += 1
                if not devam:
                    break
        u = b[i]; i += 1
        if u & 0x80:                            # uzun bicim uzunluk
            n = u & 0x7F
            u = int.from_bytes(b[i:i + n], "big")
            i += n
        out.append((t, tagno, bas, i, i + u))
        i += u
    return out


def uzunluk(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def tlv(tag, icerik):
    return bytes([tag]) + uzunluk(len(icerik)) + icerik


def ham(b, dugum):
    """Dugumun etiketiyle birlikte tum baytlari."""
    return b[dugum[2]:dugum[4]]


def oid_metin(b):
    if not b:
        return ""
    ilk = b[0]
    parca = [ilk // 40, ilk % 40]
    v = 0
    for c in b[1:]:
        v = (v << 7) | (c & 0x7F)
        if not c & 0x80:
            parca.append(v)
            v = 0
    return ".".join(map(str, parca))


OID = {
    "1.2.840.113549.1.7.2": "signedData",
    "1.2.840.113549.1.7.1": "data",
    "1.2.840.113549.1.9.3": "contentType",
    "1.2.840.113549.1.9.4": "messageDigest",
    "1.2.840.113549.1.9.5": "signingTime",
    "1.2.840.113549.1.9.6": "counterSignature",
    "1.2.840.113549.1.9.16.2.14": "signatureTimeStampToken",
    "1.2.840.113549.1.9.16.2.47": "signingCertificateV2",
    "1.2.840.113549.1.9.16.2.12": "signingCertificate",
    "2.16.840.1.101.3.4.2.1": "sha256",
    "2.16.840.1.101.3.4.2.2": "sha384",
    "2.16.840.1.101.3.4.2.3": "sha512",
    "1.3.14.3.2.26": "sha1",
    "2.5.4.3": "CN", "2.5.4.5": "serialNumber", "2.5.4.10": "O",
    "2.5.4.12": "title", "2.5.4.6": "C", "2.5.4.7": "L",
}
OZET_ADI = {"sha1": "sha1", "sha256": "sha256", "sha384": "sha384", "sha512": "sha512"}


def ad(o):
    return OID.get(o, o)


# --------------------------------------------------------------------------
# Sertifika
# --------------------------------------------------------------------------
def sertifika_bilgi(b, dugum):
    """Certificate SEQ -> {issuer_der, serial, CN, TCKN, unvan, gecerli_*}"""
    tbs = coz_tlv(b, dugum[3], dugum[4])[0]
    f = coz_tlv(b, tbs[3], tbs[4])
    i = 1 if f[0][0] == 0xA0 else 0             # [0] EXPLICIT version istege bagli
    seri = int.from_bytes(b[f[i][3]:f[i][4]], "big")
    issuer = ham(b, f[i + 2])
    gecerlilik = coz_tlv(b, f[i + 3][3], f[i + 3][4])
    subject = f[i + 4]

    alan = {}
    for rdn in coz_tlv(b, subject[3], subject[4]):
        for atv in coz_tlv(b, rdn[3], rdn[4]):
            p = coz_tlv(b, atv[3], atv[4])
            alan[ad(oid_metin(b[p[0][3]:p[0][4]]))] = \
                b[p[1][3]:p[1][4]].decode("utf-8", "replace")

    return {
        "issuer_der": issuer,
        "seri": seri,
        "ad": alan.get("CN", "?"),
        "tckn": alan.get("serialNumber"),
        "unvan": alan.get("title"),
        "kurum": alan.get("O"),
        "baslangic": b[gecerlilik[0][3]:gecerlilik[0][4]].decode("ascii", "replace"),
        "bitis": b[gecerlilik[1][3]:gecerlilik[1][4]].decode("ascii", "replace"),
    }


# --------------------------------------------------------------------------
# SignedData
# --------------------------------------------------------------------------
def coz(sgn):
    """sign.sgn -> ham parcalar sozlugu. Parcalar DER baytlari olarak saklanir,
    boylece yeniden kurarken imzalanmis hicbir sey yeniden kodlanmaz."""
    ust = coz_tlv(sgn)[0]
    ic = coz_tlv(sgn, ust[3], ust[4])
    if oid_metin(sgn[ic[0][3]:ic[0][4]]) != "1.2.840.113549.1.7.2":
        raise ValueError("signedData degil")
    sd = coz_tlv(sgn, ic[1][3], ic[1][4])[0]
    f = coz_tlv(sgn, sd[3], sd[4])

    d = {
        "ctype_ham": ham(sgn, ic[0]),
        "surum": ham(sgn, f[0]),
        "ozet_algs": [ham(sgn, x) for x in coz_tlv(sgn, f[1][3], f[1][4])],
        "encap": ham(sgn, f[2]),
        "sertifikalar": [], "criller": [], "imzalar": [],
    }
    for x in f[3:]:
        if x[0] == 0xA0:
            d["sertifikalar"] = [ham(sgn, c) for c in coz_tlv(sgn, x[3], x[4])]
        elif x[0] == 0xA1:
            d["criller"] = [ham(sgn, c) for c in coz_tlv(sgn, x[3], x[4])]
        elif x[0] == 0x31:
            d["imzalar"] = [ham(sgn, c) for c in coz_tlv(sgn, x[3], x[4])]

    # encapContentInfo tek elemanliysa icerik ekli degil (detached)
    e = coz_tlv(d["encap"])[0]
    d["detached"] = len(coz_tlv(d["encap"], e[3], e[4])) == 1
    return d


def kur(d, sirala="zaman"):
    """Parcalardan ContentInfo DER'i uret.

    sirala: SET OF elemanlarinin yazim sirasi.
      zaman — imza zamanina gore (UYAP'in kendi yazdigi sira budur)
      der   — DER kanonik (bayt) sirasi
      giris — verilen sirayi koru
    """
    imzalar = list(d["imzalar"])
    sertler = list(d["sertifikalar"])
    if sirala == "der":
        imzalar.sort()
        sertler.sort()
    elif sirala == "zaman":
        imzalar.sort(key=lambda s: (imza_bilgi(s).get("zaman") or ""))

    govde = d["surum"]
    govde += tlv(0x31, b"".join(sorted(set(d["ozet_algs"]))))
    govde += d["encap"]
    if sertler:
        govde += tlv(0xA0, b"".join(sertler))
    if d["criller"]:
        govde += tlv(0xA1, b"".join(d["criller"]))
    govde += tlv(0x31, b"".join(imzalar))
    return tlv(0x30, d["ctype_ham"] + tlv(0xA0, tlv(0x30, govde)))


def imza_bilgi(si):
    """SignerInfo DER -> {sid, ozet_alg, ozet, zaman, imzali_alanlar, ...}"""
    b = si
    s = coz_tlv(b)[0]
    f = coz_tlv(b, s[3], s[4])
    out = {"ham": si}
    sid = f[1]
    if sid[0] == 0x30:                          # issuerAndSerialNumber
        ff = coz_tlv(b, sid[3], sid[4])
        out["issuer_der"] = ham(b, ff[0])
        out["seri"] = int.from_bytes(b[ff[1][3]:ff[1][4]], "big")
        out["sid"] = "issuerAndSerial"
    else:                                       # [0] subjectKeyIdentifier
        out["skid"] = b[sid[3]:sid[4]].hex()
        out["sid"] = "subjectKeyId"

    da = coz_tlv(b, f[2][3], f[2][4])[0]
    out["ozet_alg"] = ad(oid_metin(b[da[3]:da[4]]))

    i = 3
    out["imzali_alanlar"] = []
    if f[i][0] == 0xA0:
        for a in coz_tlv(b, f[i][3], f[i][4]):
            p = coz_tlv(b, a[3], a[4])
            an = ad(oid_metin(b[p[0][3]:p[0][4]]))
            out["imzali_alanlar"].append(an)
            deger = coz_tlv(b, p[1][3], p[1][4])
            if not deger:
                continue
            v = b[deger[0][3]:deger[0][4]]
            if an == "messageDigest":
                out["ozet"] = v.hex()
            elif an == "signingTime":
                out["zaman"] = v.decode("ascii", "replace")
            elif an == "contentType":
                out["icerik_turu"] = oid_metin(v)
        i += 1
    out["imzasiz_alanlar"] = []
    # imzaAlg, imza, sonra istege bagli [1] unsignedAttrs
    alg_d = coz_tlv(b, f[i][3], f[i][4])[0]
    out["imza_alg_oid"] = oid_metin(b[alg_d[3]:alg_d[4]])
    out["imza"] = b[f[i + 1][3]:f[i + 1][4]]
    i += 2
    if i < len(f) and f[i][0] == 0xA1:
        for a in coz_tlv(b, f[i][3], f[i][4]):
            p = coz_tlv(b, a[3], a[4])
            out["imzasiz_alanlar"].append(ad(oid_metin(b[p[0][3]:p[0][4]])))
    # imzayi tekillestirmek icin kimlik: (issuer, seri) veya subjectKeyIdentifier
    out["anahtar"] = ("k:" + out["skid"] if "skid" in out
                      else out["issuer_der"].hex() + "|" + format(out["seri"], "x"))
    return out


def sertifika_esle(d):
    """imza -> sertifika eslestirmesi. (issuer, seri) uzerinden."""
    dizin = {}
    for c in d["sertifikalar"]:
        s = coz_tlv(c)[0]
        bilgi = sertifika_bilgi(c, s)
        dizin[(bilgi["issuer_der"], bilgi["seri"])] = bilgi
    ciftler = []
    for si in d["imzalar"]:
        bi = imza_bilgi(si)
        cert = dizin.get((bi.get("issuer_der"), bi.get("seri")))
        ciftler.append((bi, cert))
    return ciftler


def ozet_dogrula(bi, icerik):
    """SignerInfo'nun messageDigest'i verilen icerigin ozeti mi?"""
    alg = OZET_ADI.get(bi["ozet_alg"])
    if not alg or "ozet" not in bi:
        return False
    return hashlib.new(alg, icerik).hexdigest() == bi["ozet"]


# --------------------------------------------------------------------------
# Standart disi ama gecerli RSA imzalari
# --------------------------------------------------------------------------
# Bazi imzalama araclari PKCS#1 v1.5 DigestInfo'sundaki NULL parametresini
# yazmaz:  standart 3031300d0609<OID>0500 0420<ozet>
#          eksik    302f300b0609<OID>     0420<ozet>
# openssl bunu reddeder, UYAP kabul eder; imza aslinda gecerlidir.
# Asagidaki dogrulayici dolguyu ve tam kaplamayi KATI denetler, yalniz eksik
# NULL'a izin verir.
OZET_OID = {
    "sha1": "1.3.14.3.2.26",
    "sha256": "2.16.840.1.101.3.4.2.1",
    "sha384": "2.16.840.1.101.3.4.2.2",
    "sha512": "2.16.840.1.101.3.4.2.3",
}


def rsa_acik_anahtar(sertifika):
    """Sertifikadan (n, e) cikar. RSA degilse None."""
    s = coz_tlv(sertifika)[0]
    tbs = coz_tlv(sertifika, s[3], s[4])[0]
    f = coz_tlv(sertifika, tbs[3], tbs[4])
    i = 1 if f[0][0] == 0xA0 else 0
    spki = f[i + 5]
    parcalar = coz_tlv(sertifika, spki[3], spki[4])
    alg = coz_tlv(sertifika, parcalar[0][3], parcalar[0][4])
    if oid_metin(sertifika[alg[0][3]:alg[0][4]]) != "1.2.840.113549.1.1.1":
        return None
    bit = sertifika[parcalar[1][3]:parcalar[1][4]][1:]     # kullanilmayan-bit bayti
    kf = coz_tlv(bit)
    rf = coz_tlv(bit, kf[0][3], kf[0][4])
    return (int.from_bytes(bit[rf[0][3]:rf[0][4]], "big"),
            int.from_bytes(bit[rf[1][3]:rf[1][4]], "big"))


def rsa_gevsek_dogrula(sertifika, imza, veri, ozet_adi):
    """NULL'suz DigestInfo'ya izin veren KATI PKCS#1 v1.5 dogrulamasi."""
    ne = rsa_acik_anahtar(sertifika)
    if not ne:
        return False
    n, e = ne
    k = (n.bit_length() + 7) // 8
    if len(imza) != k:
        return False
    kutu = pow(int.from_bytes(imza, "big"), e, n).to_bytes(k, "big")

    if kutu[0] != 0x00 or kutu[1] != 0x01:
        return False
    i = 2
    while i < len(kutu) and kutu[i] == 0xFF:
        i += 1
    if i - 2 < 8 or kutu[i] != 0x00:
        return False
    di = kutu[i + 1:]

    try:
        df = coz_tlv(di)
        if len(df) != 1 or df[0][4] != len(di):          # fazladan bayt olamaz
            return False
        ic = coz_tlv(di, df[0][3], df[0][4])
        if len(ic) != 2:
            return False
        alg = coz_tlv(di, ic[0][3], ic[0][4])
        if len(alg) > 2:
            return False
        if len(alg) == 2:                                 # varsa tam olarak NULL
            if alg[1][0] != 0x05 or alg[1][4] != alg[1][3]:
                return False
        if oid_metin(di[alg[0][3]:alg[0][4]]) != OZET_OID.get(ozet_adi):
            return False
        bildirilen = di[ic[1][3]:ic[1][4]]
    except Exception:
        return False
    return bildirilen == hashlib.new(ozet_adi, veri).digest()


def imzali_alanlar_verisi(si):
    """Imzalanan bayt dizisi: signedAttrs'in DER'i, [0] yerine SET OF (0x31)."""
    b = si
    s = coz_tlv(b)[0]
    f = coz_tlv(b, s[3], s[4])
    if f[3][0] != 0xA0:
        return None, None
    veri = bytearray(b[f[3][2]:f[3][4]])
    veri[0] = 0x31
    return bytes(veri), b[f[5][3]:f[5][4]]                 # (veri, imza)


def birlestir(cozulmusler, sirala="zaman"):
    """Ayni icerige ait SignedData'lari tek SignedData'da topla.

    Imzalar (issuer, seri) anahtariyla tekillestirilir; ayni imza iki nushada
    varsa (arabulucunun capa imzasi) bir kez yazilir.
    """
    ilk = cozulmusler[0]
    for d in cozulmusler[1:]:
        if d["encap"] != ilk["encap"]:
            raise ValueError("encapContentInfo farkli — ayni belge degil")

    imzalar, gorulen = [], set()
    for d in cozulmusler:
        for si in d["imzalar"]:
            bi = imza_bilgi(si)
            k = (bi.get("issuer_der"), bi.get("seri"), bi.get("skid"))
            if k in gorulen:
                continue
            gorulen.add(k)
            imzalar.append(si)

    sertler, gorulen_c = [], set()
    for d in cozulmusler:
        for c in d["sertifikalar"]:
            if c in gorulen_c:
                continue
            gorulen_c.add(c)
            sertler.append(c)

    m = {
        "ctype_ham": ilk["ctype_ham"], "surum": ilk["surum"], "encap": ilk["encap"],
        "ozet_algs": [x for d in cozulmusler for x in d["ozet_algs"]],
        "sertifikalar": sertler,
        "criller": [x for d in cozulmusler for x in d["criller"]],
        "imzalar": imzalar,
    }
    return kur(m, sirala=sirala)
