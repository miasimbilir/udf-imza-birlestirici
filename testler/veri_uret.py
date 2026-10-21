#!/usr/bin/env python3
"""Testlerin kullandigi SENTETIK sertifika ve UDF nushalarini uretir.

Gercek kisi, gercek T.C. kimlik numarasi ya da gercek belge YOKTUR; adlar
"DENEME", numaralar uydurmadir. Bir kez calistirilir, cikti (testler/veri/)
depoya konur; testlerin kendisi openssl gerektirmez.

    python3 testler/veri_uret.py        # openssl 3+ gerekir
"""
import os
import shutil
import subprocess
import tempfile
import zipfile

KOK = os.path.dirname(os.path.abspath(__file__))
VERI = os.path.join(KOK, "veri")

KISILER = {
    # ad: (anahtar turu, konu)
    "arb":  ("rsa", "/C=TR/serialNumber=10000000146/CN=DENEME ARABULUCU"),
    "a":    ("rsa", "/C=TR/serialNumber=20000000046/CN=Ayşe DENEME"),
    "b":    ("ec",  "/C=TR/serialNumber=30000000082/CN=Şükrü DENEME"),
    # arabulucuyla AYNI kisi (ayni T.C.), FARKLI anahtar ve sertifika
    "arb2": ("rsa", "/C=TR/serialNumber=10000000146/CN=DENEME ARABULUCU"),
}

METIN = "DENEME TUTANAĞI\n\nBu belge yalnızca otomatik testler içindir.\n"


def content_xml(metin):
    return ('<?xml version="1.0" encoding="UTF-8" ?>\n<template format_id="1.8">'
            f"<content><![CDATA[{metin}]]></content>"
            '<properties><pageFormat mediaSizeName="1" /></properties>'
            "<elements resolver=\"hvl-default\"><paragraph><content startOffset=\"0\" "
            f'length="{len(metin)}" /></paragraph></elements></template>\n').encode("utf-8")


def calistir(*arg, cwd):
    subprocess.run(["openssl", *arg], cwd=cwd, check=True, capture_output=True)


def main():
    gd = tempfile.mkdtemp()
    try:
        for ad, (tur, konu) in KISILER.items():
            anahtar = (["-newkey", "rsa:2048"] if tur == "rsa" else
                       ["-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256"])
            calistir("req", "-x509", "-utf8", "-nodes", *anahtar, "-sha256",
                     "-keyout", f"{ad}.key", "-out", f"{ad}.pem", "-days", "7300",
                     "-subj", konu, cwd=gd)
        # testlerin NULL'suz imza uretebilmesi icin arabulucunun RSA anahtari
        calistir("rsa", "-in", "arb.key", "-outform", "DER", "-traditional",
                 "-out", "arb-anahtar.der", cwd=gd)

        icerikler = {"asil": content_xml(METIN),
                     "farkli": content_xml(METIN.replace("içindir", "içindir.."))}
        for k, v in icerikler.items():
            with open(os.path.join(gd, f"{k}.xml"), "wb") as f:
                f.write(v)

        nushalar = {
            "nusha-arb-a":        ("asil",   ["arb", "a"]),
            "nusha-arb-b":        ("asil",   ["arb", "b"]),
            "nusha-arb":          ("asil",   ["arb"]),
            "nusha-a":            ("asil",   ["a"]),
            "nusha-b":            ("asil",   ["b"]),
            "nusha-arb-arb2":     ("asil",   ["arb", "arb2"]),
            "nusha-farkli-arb-b": ("farkli", ["arb", "b"]),
        }
        os.makedirs(VERI, exist_ok=True)
        for ad, (icerik, imzacilar) in nushalar.items():
            imzaci_arg = []
            for kim in imzacilar:
                imzaci_arg += ["-signer", f"{kim}.pem", "-inkey", f"{kim}.key"]
            calistir("cms", "-sign", "-binary", "-md", "sha256", "-in", f"{icerik}.xml",
                     *imzaci_arg, "-outform", "DER", "-out", f"{ad}.sgn", cwd=gd)
            with open(os.path.join(gd, f"{ad}.sgn"), "rb") as f:
                sgn = f.read()
            with zipfile.ZipFile(os.path.join(VERI, f"{ad}.udf"), "w") as z:
                z.writestr(zipfile.ZipInfo("content.xml"), icerikler[icerik],
                           compress_type=zipfile.ZIP_DEFLATED)
                z.writestr(zipfile.ZipInfo("sign.sgn"), sgn,
                           compress_type=zipfile.ZIP_DEFLATED)
        shutil.copy(os.path.join(gd, "arb-anahtar.der"), VERI)
        print("üretildi:", ", ".join(sorted(os.listdir(VERI))))
    finally:
        shutil.rmtree(gd)


if __name__ == "__main__":
    main()
