#!/usr/bin/env python3
"""
UDF İmza Birleştirici — masaüstü uygulaması.

Aynı belgenin ayrı ayrı e-imzalanmış nüshalarındaki imzaları tek dosyada toplar.
Hiçbir dış programa bağlı değildir; belgeler bilgisayardan çıkmaz. İnternet
yalnızca kullanıcı güncelleme denetimi düğmesine bastığında kullanılır.

Akış:  nüshaları ekle → İncele → (denetim geçerse) Birleştir → kaydet → raporlar
"""
import json
import os
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

if getattr(sys, "frozen", False):                   # PyInstaller paketi
    sys.path.insert(0, os.path.dirname(os.path.abspath(sys.executable)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from birlestirici import denetle, incele_tek
from udf_ortak import TSI, Durdur

# Sürükle-bırak Tkinter'da yerleşik değil; paket yoksa düğmeyle devam edilir.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TEMEL_PENCERE, SURUKLENEBILIR = TkinterDnD.Tk, True
except Exception:
    TEMEL_PENCERE, SURUKLENEBILIR = tk.Tk, False

UYGULAMA_ADI = "UDF İmza Birleştirici"
SURUM = "1.0"
YAZAR = "Av. Arb. Mevlana İbrahim Asım Bilir"
YAZAR_EK = "av.ibrahimbilir@gmail.com"
TELIF = "© 2026 Av. Arb. Mevlana İbrahim Asım Bilir"
LISANS = "Ücretsiz kullanılabilir ve dağıtılabilir; satılamaz."

# Güncelleme denetimi YALNIZCA kullanıcı düğmeye bastığında yapılır; program
# kendiliğinden internete çıkmaz ve hiçbir belge gönderilmez — sorulan tek şey
# en son sürümün numarasıdır.
DEPO = "miasimbilir/udf-imza-birlestirici"
SURUM_API = f"https://api.github.com/repos/{DEPO}/releases/latest"
SURUM_SAYFA = f"https://github.com/{DEPO}/releases/latest"


def surum_sayilari(etiket):
    """'v1.2' → (1, 2). Karşılaştırma için sayıya çevirir."""
    parcalar = []
    for p in str(etiket).lstrip("vVsS").split("."):
        rakam = "".join(c for c in p if c.isdigit())
        parcalar.append(int(rakam) if rakam else 0)
    return tuple(parcalar) or (0,)


def son_surumu_sor():
    """Depodaki en son sürüm etiketini döndürür. Ağ hatasında istisna atar."""
    istek = urllib.request.Request(SURUM_API, headers={
        "User-Agent": f"UDF-Imza-Birlestirici/{SURUM}",
        "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(istek, timeout=8) as yanit:
        return json.load(yanit).get("tag_name") or ""

ACIK_TEMA = {"yesil": "#127a3d", "kirmizi": "#b4232a", "soluk": "#6b7280",
             "cizgi": "#d7d9dd", "kagit": "#ffffff", "yazi": "#1c1f24",
             "secim": "#d3e3f5"}
KOYU_TEMA = {"yesil": "#5fd08a", "kirmizi": "#f08d92", "soluk": "#9aa3ae",
             "cizgi": "#3a4048", "kagit": "#242a31", "yazi": "#e8eaed",
             "secim": "#33415a"}


def tema_sec(pencere):
    """Arka planın parlaklığına göre okunur renk kümesi."""
    try:
        r, g, b = pencere.winfo_rgb(ttk.Style().lookup("TFrame", "background")
                                    or pencere.cget("background"))
        return KOYU_TEMA if (r + g + b) / 3 < 32768 else ACIK_TEMA
    except Exception:
        return ACIK_TEMA


# --------------------------------------------------------------------------
# Rapor metinleri
# --------------------------------------------------------------------------
def imza_raporu(sonuc):
    """Belgeye yapıştırılmak üzere: yalnız ad, TC ve imza zamanı."""
    satirlar = ["Bu belge aşağıdaki kişiler tarafından elektronik olarak imzalanmıştır:", ""]
    for i, imz in enumerate(sonuc["imzacilar"], 1):
        tc = f" (T.C. {imz['tckn']})" if imz.get("tckn") else ""
        satirlar.append(f"{i}. {imz['ad']}{tc} — {imz['zaman']}")
    satirlar += ["", f"Belge özeti (SHA-256): {sonuc['ozet']}"]
    return "\n".join(satirlar)


def denetim_raporu(sonuc):
    """Teknik rapor: hangi denetimden ne sonuç çıktı."""
    simdi = datetime.now(TSI).strftime("%d.%m.%Y %H:%M")
    # Python'un upper()'ı Türkçe'de bozuk: "i" → "I" (doğrusu "İ"). Elle yazılır.
    s = ["UDF İMZA BİRLEŞTİRİCİ — DENETİM RAPORU",
         f"Rapor tarihi: {simdi} TSİ", "",
         "BİRLEŞTİRİLEN NÜSHALAR"]
    for i, n in enumerate(sonuc["nushalar"], 1):
        s.append(f"  {i}. {n['ad']}  ({n['imza']} imza)")
    s += ["", "GÜVENLİK DENETİMLERİ"]
    for a in sonuc["adimlar"]:
        im = "✓" if a["durum"] == "tamam" else "✕"
        s.append(f"  {im} {a['baslik']}")
        if a["detay"]:
            s.append(f"      {a['detay']}")
    s += ["", "İMZACILAR"]
    for i, imz in enumerate(sonuc["imzacilar"], 1):
        notlar = []
        if imz.get("capa"):
            notlar.append("ortak imza")
        if imz.get("disi"):
            notlar.append("standart dışı kodlama")
        ek = ("  [" + ", ".join(notlar) + "]") if notlar else ""
        s.append(f"  {i}. {imz['ad']}  (T.C. {imz.get('tckn') or '—'})  "
                 f"{imz['zaman']}{ek}")
    s += ["", f"BELGE ÖZETİ (SHA-256)", f"  {sonuc['ozet']}"]
    if sonuc["uyarilar"]:
        s += ["", "BİLGİ NOTLARI"]
        s += [f"  • {u}" for u in sonuc["uyarilar"]]
    s += ["", "Bu rapor, imzaların birleştirilmesi sırasında yapılan denetimleri",
          "gösterir. Belgeler bilgisayardan çıkarılmamış, internet kullanılmamıştır.",
          "", f"{UYGULAMA_ADI} s{SURUM} · {YAZAR}"]
    return "\n".join(s)


def tek_dosya_raporu(t):
    """Tek belge incelemesi — birleştirme yapılmadan."""
    s = ["UDF İMZA BİRLEŞTİRİCİ — BELGE BİLGİSİ",
         f"Rapor tarihi: {datetime.now(TSI).strftime('%d.%m.%Y %H:%M')} TSİ", "",
         f"BELGE: {t['ad']}", "", "İMZACILAR"]
    for i, imz in enumerate(t["imzacilar"], 1):
        notlar = []
        if not imz.get("gecerli"):
            notlar.append("İMZA DOĞRULANAMADI")
        if imz.get("disi"):
            notlar.append("standart dışı kodlama")
        ek = ("  [" + ", ".join(notlar) + "]") if notlar else ""
        s.append(f"  {i}. {imz['ad']}  (T.C. {imz.get('tckn') or '—'})  "
                 f"{imz['zaman']}{ek}")
    s += ["", "BELGE ÖZETİ (SHA-256)", f"  {t['ozet']}",
          "", f"{UYGULAMA_ADI} s{SURUM} · {YAZAR}"]
    return "\n".join(s)


class RaporPenceresi(tk.Toplevel):
    """Kopyalanabilir metin penceresi."""

    def __init__(self, ana, baslik, metin, renk, genislik=74, yukseklik=22):
        super().__init__(ana)
        self.title(baslik)
        self.transient(ana)
        cerceve = ttk.Frame(self, padding=12)
        cerceve.pack(fill="both", expand=True)

        kutu = tk.Text(cerceve, width=genislik, height=yukseklik, wrap="word",
                       borderwidth=1, relief="solid", highlightthickness=0,
                       background=renk["kagit"], foreground=renk["yazi"],
                       insertbackground=renk["yazi"], selectbackground=renk["secim"],
                       font=("Menlo" if sys.platform == "darwin" else "Consolas", 11))
        kaydirici = ttk.Scrollbar(cerceve, orient="vertical", command=kutu.yview)
        kutu.configure(yscrollcommand=kaydirici.set)
        kutu.insert("1.0", metin)
        kutu.configure(state="disabled")
        kutu.pack(side="left", fill="both", expand=True)
        kaydirici.pack(side="right", fill="y")

        alt = ttk.Frame(self, padding=(12, 0, 12, 12))
        alt.pack(fill="x")
        self.durum = ttk.Label(alt, text="", foreground=renk["yesil"])
        self.durum.pack(side="left")
        ttk.Button(alt, text="Kapat", command=self.destroy).pack(side="right")
        ttk.Button(alt, text="Panoya kopyala",
                   command=lambda: self.kopyala(metin)).pack(side="right", padx=6)
        self.metin = metin
        self.bind("<Escape>", lambda e: self.destroy())

    def kopyala(self, metin):
        self.clipboard_clear()
        self.clipboard_append(metin)
        self.update()
        self.durum.config(text="Kopyalandı ✓")
        self.after(2500, lambda: self.durum.config(text=""))


# --------------------------------------------------------------------------
# Ana pencere
# --------------------------------------------------------------------------
class Uygulama(TEMEL_PENCERE):
    def __init__(self):
        super().__init__()
        self.title(UYGULAMA_ADI)
        self.geometry("560x560")
        self.minsize(520, 500)
        self.yollar = []
        self.sonuc = None
        self.tek_sonuc = None
        self.renk = tema_sec(self)
        self._kur()
        try:                                        # Finder'dan uygulamaya sürükleme
            self.createcommand("::tk::mac::OpenDocument", lambda *y: self.ekle(list(y)))
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- yerleşim
    def _kur(self):
        dis = ttk.Frame(self, padding=14)
        dis.pack(fill="both", expand=True)

        ust = ttk.Frame(dis)
        ust.pack(fill="x")
        ttk.Label(ust, text=UYGULAMA_ADI,
                  font=("Helvetica", 15, "bold")).pack(side="left")
        ttk.Button(ust, text="Hakkında", width=9,
                   command=self.hakkinda_ac).pack(side="right")

        # --- bırakma alanı ---
        self.birak = tk.Frame(dis, highlightthickness=2, highlightbackground=self.renk["cizgi"],
                              highlightcolor=self.renk["cizgi"], bd=0)
        self.birak.pack(fill="x", pady=(12, 10))
        ic = ttk.Frame(self.birak, padding=18)
        ic.pack(fill="both", expand=True)

        # Sürükle-bırak yazısı ancak GERÇEKTEN kurulabildiyse yazılır: paket
        # içinde tkdnd kütüphanesi eksikse import başarılı olur ama kayıt çöker.
        surukleme = False
        if SURUKLENEBILIR:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self._birakildi)
                surukleme = True
            except Exception:
                surukleme = False

        self.birak_yazi = ttk.Label(
            ic, font=("Helvetica", 13),
            text="Nüshaları buraya bırakın" if surukleme
                 else "Birleştirilecek nüshaları seçin")
        self.birak_yazi.pack()
        alt_yazi = ttk.Label(
            ic, foreground=self.renk["soluk"], font=("Helvetica", 11),
            text="veya tıklayıp seçin · en az 2 adet .udf" if surukleme
                 else "tıklayıp seçin · en az 2 adet .udf")
        alt_yazi.pack(pady=(3, 0))
        for w in (self.birak, ic, self.birak_yazi, alt_yazi):
            w.bind("<Button-1>", lambda e: self.dosya_ekle())

        # --- dosya listesi ---
        self.liste_cerceve = ttk.Frame(dis)
        self.liste = tk.Listbox(self.liste_cerceve, height=3, activestyle="none",
                                highlightthickness=0, borderwidth=1, relief="solid",
                                selectmode="extended", font=("Helvetica", 12),
                                background=self.renk["kagit"],
                                foreground=self.renk["yazi"],
                                selectbackground=self.renk["secim"],
                                selectforeground=self.renk["yazi"])
        self.liste.pack(fill="x")
        alt_liste = ttk.Frame(self.liste_cerceve)
        alt_liste.pack(fill="x", pady=(5, 0))
        self.sayi_yazi = ttk.Label(alt_liste, text="", foreground=self.renk["soluk"],
                                   font=("Helvetica", 11))
        self.sayi_yazi.pack(side="left")
        ttk.Button(alt_liste, text="Temizle", width=8,
                   command=self.temizle).pack(side="right")
        ttk.Button(alt_liste, text="Çıkar", width=7,
                   command=self.sil).pack(side="right", padx=5)

        # --- eylem ve durum ---
        self.btn_incele = ttk.Button(dis, text="İncele", command=self.incele)
        self.durum_kutu = tk.Frame(dis, highlightthickness=1, bd=0)
        durum_ic = ttk.Frame(self.durum_kutu, padding=11)
        durum_ic.pack(fill="both", expand=True)
        self.durum_baslik = ttk.Label(durum_ic, text="", font=("Helvetica", 13, "bold"))
        self.durum_baslik.pack(anchor="w")
        self.durum_detay = ttk.Label(durum_ic, text="", foreground=self.renk["soluk"],
                                     font=("Helvetica", 11), wraplength=440,
                                     justify="left")
        self.durum_detay.pack(anchor="w", pady=(2, 0))

        birlestir_kutu = ttk.Frame(dis)
        self.btn_birlestir = ttk.Button(birlestir_kutu, text="Birleştir",
                                        command=self.birlestir)
        self.btn_birlestir.pack()
        # Denetim kaydı: belgenin yanına, ne birleştirildiğinin kalıcı kaydı.
        self.kayit_istegi = tk.BooleanVar(value=True)
        ttk.Checkbutton(birlestir_kutu, variable=self.kayit_istegi,
                        text="Denetim kaydını belgenin yanına yaz"
                        ).pack(pady=(6, 0))
        self.birlestir_kutu = birlestir_kutu
        self.rapor_cerceve = ttk.Frame(dis)
        ttk.Button(self.rapor_cerceve, text="Denetim raporu",
                   command=self.denetim_raporu_ac).pack(side="left")
        ttk.Button(self.rapor_cerceve, text="İmza raporu",
                   command=self.imza_raporu_ac).pack(side="left", padx=8)
        self.btn_ayrinti = ttk.Button(dis, text="Ayrıntı", command=self.ayrinti_goster)

        ttk.Label(dis, foreground=self.renk["soluk"], font=("Helvetica", 10),
                  text=f"{YAZAR} · s{SURUM}").pack(side="bottom", anchor="w")
        self.listeyi_ciz()

    # ------------------------------------------------------------ dosya işleri
    def _birakildi(self, olay):
        self.ekle(self.tk.splitlist(olay.data))

    def dosya_ekle(self):
        self.ekle(filedialog.askopenfilenames(
            title="Nüshaları seçin",
            filetypes=[("UYAP belgesi", "*.udf"), ("Tüm dosyalar", "*.*")]))

    def ekle(self, yeni):
        atlanan = []
        for y in yeni:
            if not y:
                continue
            if not y.lower().endswith(".udf"):
                atlanan.append(os.path.basename(y))
            elif y not in self.yollar:
                self.yollar.append(y)
        self.listeyi_ciz()
        if atlanan:
            messagebox.showwarning("Eklenmedi",
                                   ".udf olmayan dosyalar atlandı:\n\n" + "\n".join(atlanan),
                                   parent=self)

    def sil(self):
        for i in sorted(self.liste.curselection(), reverse=True):
            del self.yollar[i]
        self.listeyi_ciz()

    def temizle(self):
        self.yollar = []
        self.listeyi_ciz()

    def listeyi_ciz(self):
        self.liste.delete(0, "end")
        for y in self.yollar:
            self.liste.insert("end", "  " + os.path.basename(y))
        self.sayi_yazi.config(
            text=f"{len(self.yollar)} nüsha" if self.yollar else "")
        if self.yollar:
            self.liste_cerceve.pack(fill="x", pady=(0, 12))
        else:
            self.liste_cerceve.pack_forget()
        self.sifirla()
        if self.yollar:
            self.btn_incele.config(text="İncele" if len(self.yollar) >= 2
                                   else "İmzaları göster")
            self.btn_incele.pack(pady=(0, 4))
        else:
            self.btn_incele.pack_forget()

    def sifirla(self):
        self.sonuc = None
        self.tek_sonuc = None
        self.hata_ayrinti = ""
        self.durum_kutu.pack_forget()
        self.birlestir_kutu.pack_forget()
        self.rapor_cerceve.pack_forget()
        self.btn_ayrinti.pack_forget()

    # ---------------------------------------------------------------- denetim
    def durum_goster(self, basarili, baslik, detay):
        renk = self.renk["yesil"] if basarili else self.renk["kirmizi"]
        self.durum_kutu.configure(highlightbackground=renk, highlightcolor=renk)
        self.durum_baslik.config(text=baslik, foreground=renk)
        self.durum_detay.config(text=detay)
        self.durum_kutu.pack(fill="x", pady=(6, 10))

    def incele(self):
        self.sifirla()
        self.config(cursor="watch")
        self.update_idletasks()
        if len(self.yollar) == 1:
            try:
                self.tek_sonuc = incele_tek(self.yollar[0])
            except Durdur as e:
                self.hata_ayrinti = str(e)
                self.durum_goster(False, "Okunamadı", str(e).split("\n")[0])
                self.btn_ayrinti.pack(pady=(0, 6))
            else:
                t = self.tek_sonuc
                n = len(t["imzacilar"])
                self.durum_goster(
                    t["gecerli"],
                    f"{n} imza" if t["gecerli"] else "İmza doğrulanamadı",
                    (", ".join(i["ad"] for i in t["imzacilar"]) if t["gecerli"]
                     else t["sebep"]) +
                    ("\nBirleştirmek için ikinci nüshayı da ekleyin."
                     if t["gecerli"] else ""))
                if t["gecerli"]:
                    self.rapor_cerceve.pack()
            finally:
                self.config(cursor="")
            return
        try:
            sonuc = denetle(self.yollar)
        except Durdur as e:
            self.hata_ayrinti = str(e)
            self.durum_goster(False, "Birleştirilemez", str(e).split("\n")[0])
            self.btn_ayrinti.pack(pady=(0, 6))
        except Exception as e:
            self.hata_ayrinti = f"{type(e).__name__}: {e}"
            self.durum_goster(False, "Beklenmeyen hata", str(e))
            self.btn_ayrinti.pack(pady=(0, 6))
        else:
            self.sonuc = sonuc
            ortak = [i["ad"] for i in sonuc["imzacilar"] if i.get("capa")]
            self.durum_goster(
                True, "Birleştirmeye uygun",
                f"{len(sonuc['imzacilar'])} imza · 8 denetim geçildi\n"
                f"Ortak imza: {', '.join(ortak) if ortak else '—'}")
            self.birlestir_kutu.pack(pady=(0, 8))
            self.rapor_cerceve.pack()
        finally:
            self.config(cursor="")

    def ayrinti_goster(self):
        RaporPenceresi(self, "Ayrıntı", self.hata_ayrinti or "—", self.renk,
                       genislik=70, yukseklik=16)

    # -------------------------------------------------------------- birleştir
    def birlestir(self):
        if not self.sonuc:
            return
        yol = filedialog.asksaveasfilename(
            title="Birleşik belgeyi kaydet", initialfile=self.sonuc["ad"],
            defaultextension=".udf", initialdir=os.path.dirname(self.yollar[0]),
            filetypes=[("UYAP belgesi", "*.udf")])
        if not yol:
            return
        try:
            with open(yol, "wb") as f:
                f.write(self.sonuc["baytlar"])
        except OSError as e:
            messagebox.showerror("Kaydedilemedi", str(e), parent=self)
            return

        satirlar = [os.path.basename(yol)]
        if self.kayit_istegi.get():
            kok = yol[:-4] if yol.lower().endswith(".udf") else yol
            kayit_yolu = kok + " - denetim kaydi.txt"
            try:
                with open(kayit_yolu, "w", encoding="utf-8") as f:
                    f.write(denetim_raporu(self.sonuc) + "\n")
                satirlar.append(os.path.basename(kayit_yolu))
            except OSError as e:
                messagebox.showwarning(
                    "Denetim kaydı yazılamadı",
                    f"Belge kaydedildi, ancak denetim kaydı yazılamadı:\n\n{e}",
                    parent=self)
        self.durum_goster(True, "Kaydedildi",
                          "\n".join(satirlar) +
                          "\nKaynak nüshalarınızı delil olarak saklayın.")
        self.birlestir_kutu.pack_forget()
        self.rapor_cerceve.pack()

    def denetim_raporu_ac(self):
        if self.sonuc:
            RaporPenceresi(self, "Denetim raporu", denetim_raporu(self.sonuc), self.renk)
        else:                                        # tek dosya incelemesi
            RaporPenceresi(self, "Belge bilgisi", tek_dosya_raporu(self.tek_sonuc),
                           self.renk, genislik=70, yukseklik=16)

    def imza_raporu_ac(self):
        RaporPenceresi(self, "İmza raporu",
                       imza_raporu(self.sonuc or self.tek_sonuc), self.renk,
                       genislik=66, yukseklik=14)

    def hakkinda_ac(self):
        p = tk.Toplevel(self)
        p.title("Hakkında")
        p.transient(self)
        p.resizable(False, False)
        c = ttk.Frame(p, padding=20)
        c.pack(fill="both", expand=True)
        ttk.Label(c, text=UYGULAMA_ADI,
                  font=("Helvetica", 16, "bold")).pack(anchor="w")
        ttk.Label(c, text=f"Sürüm {SURUM}", foreground=self.renk["soluk"],
                  font=("Helvetica", 11)).pack(anchor="w", pady=(1, 12))
        ttk.Label(c, text=YAZAR, font=("Helvetica", 13)).pack(anchor="w")
        ttk.Label(c, text=YAZAR_EK, foreground=self.renk["soluk"],
                  font=("Helvetica", 11)).pack(anchor="w", pady=(1, 12))
        ttk.Label(c, wraplength=400, justify="left", font=("Helvetica", 11),
                  text="Aynı belgenin ayrı ayrı e-imzalanmış nüshalarındaki imzaları "
                       "tek dosyada toplar. Yeni imza atmaz, belge metnine dokunmaz.\n\n"
                       "Belgeler bilgisayardan çıkmaz; işlem için internet "
                       "gerekmez.\n\n"
                       "Bu bağımsız bir yardımcı araçtır; UYAP ile, Adalet Bakanlığı "
                       "ile veya herhangi bir kurumla ilgisi yoktur."
                  ).pack(anchor="w")
        ttk.Label(c, text=TELIF, foreground=self.renk["soluk"],
                  font=("Helvetica", 10)).pack(anchor="w", pady=(14, 0))
        ttk.Label(c, text=LISANS, foreground=self.renk["soluk"],
                  font=("Helvetica", 10)).pack(anchor="w")

        ttk.Separator(c, orient="horizontal").pack(fill="x", pady=(16, 14))
        g = ttk.Frame(c)
        g.pack(fill="x")
        btn_g = ttk.Button(g, text="Güncellemeleri kontrol et")
        btn_g.pack(side="left")
        yazi_g = ttk.Label(g, text="", foreground=self.renk["soluk"],
                           font=("Helvetica", 11))
        yazi_g.pack(side="left", padx=12)
        btn_indir = ttk.Button(c, text="İndirme sayfasını aç",
                               command=lambda: webbrowser.open(SURUM_SAYFA))
        btn_g.config(command=lambda: self.guncelleme_kontrol(p, btn_g, yazi_g, btn_indir))
        ttk.Label(c, foreground=self.renk["soluk"], font=("Helvetica", 10),
                  wraplength=400, justify="left",
                  text="Denetim yalnızca siz bu düğmeye bastığınızda yapılır; "
                       "belge gönderilmez, yalnızca en son sürüm numarası sorulur."
                  ).pack(anchor="w", pady=(10, 0))

        ttk.Button(c, text="Kapat", command=p.destroy).pack(anchor="e", pady=(16, 0))
        p.bind("<Escape>", lambda e: p.destroy())

    def guncelleme_kontrol(self, pencere, dugme, yazi, btn_indir):
        """Arka planda sürüm sorar; arayüz donmasın diye ayrı iş parçacığında."""
        dugme.config(state="disabled")
        yazi.config(text="kontrol ediliyor…", foreground=self.renk["soluk"])
        btn_indir.pack_forget()

        def bitti(etiket, hata):
            if not pencere.winfo_exists():
                return
            dugme.config(state="normal")
            if hata is not None:
                yazi.config(text="Kontrol edilemedi", foreground=self.renk["kirmizi"])
                messagebox.showwarning(
                    "Güncelleme kontrolü",
                    "En son sürüm bilgisine ulaşılamadı.\n\n"
                    "İnternet bağlantınızı denetleyin. Programın çalışması için "
                    "internet gerekmez; bu denetim isteğe bağlıdır.",
                    parent=pencere)
                return
            if surum_sayilari(etiket) > surum_sayilari(SURUM):
                yazi.config(text=f"Yeni sürüm var: {etiket.lstrip('vV')}",
                            foreground=self.renk["yesil"])
                btn_indir.pack(anchor="w", pady=(10, 0))
            else:
                yazi.config(text="En güncel sürümü kullanıyorsunuz",
                            foreground=self.renk["yesil"])

        def is_parcacigi():
            try:
                etiket, hata = son_surumu_sor(), None
            except Exception as e:
                etiket, hata = None, e
            try:                                     # pencere kapanmış olabilir
                pencere.after(0, lambda: bitti(etiket, hata))
            except Exception:
                pass

        threading.Thread(target=is_parcacigi, daemon=True).start()



# --------------------------------------------------------------------------
def sinama(yollar=None, rapor_yolu=None):
    """Paketin bütünlüğünü doğrular (arayüz açmadan).

    Windows'ta --windowed derlenen exe'nin KONSOLU YOKTUR; print çıktısı hiçbir
    yere gitmez. Bu yüzden sonuç istenirse bir dosyaya da yazılır.
    """
    satirlar = []

    def yaz(*p):
        metin = " ".join(str(x) for x in p)
        satirlar.append(metin)
        print(metin)
    from udf_ortak import zaman_coz, zaman_yaz
    assert zaman_yaz(zaman_coz("260727191600Z")).startswith("27.07.2026 22:16"), \
        "TSİ dönüşümü hatalı"
    assert tk.TkVersion >= 8.6, f"Tcl/Tk {tk.TkVersion} çok eski (8.6+ gerekir)"
    if yollar and len(yollar) >= 2:
        sonuc = denetle(yollar, "", lambda a, d, t="": yaz(f"  [{d:9s}] {a:6s} {t}"))
        yaz(f"ÇIKTI: {sonuc['ad']}  ({len(sonuc['baytlar'])} bayt)")
        for i in sonuc["imzacilar"]:
            yaz(f"  · {i['ad']} — {i['zaman']}")
    # Sürükle-bırak yalnız import edilebiliyor mu değil, KAYIT da oluyor mu?
    dnd = "yok"
    if SURUKLENEBILIR:
        try:
            p = TEMEL_PENCERE()
            p.withdraw()
            p.drop_target_register(DND_FILES)
            p.destroy()
            dnd = "çalışıyor"
        except Exception as e:
            dnd = f"KURULAMADI ({type(e).__name__})"
    yaz(f"SINAMA TAMAM — modüller yüklendi, çekirdek çalışıyor "
        f"(Tcl/Tk {tk.TkVersion}, sürükle-bırak: {dnd}).")
    if rapor_yolu:
        try:
            with open(rapor_yolu, "w", encoding="utf-8") as f:
                f.write("\n".join(satirlar) + "\n")
        except OSError as e:
            print("rapor yazılamadı:", e, file=sys.stderr)
    return 0


def main():
    if "--sinama" in sys.argv:
        rapor = None
        if "--rapor" in sys.argv:
            i = sys.argv.index("--rapor")
            rapor = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        return sinama([y for y in sys.argv[1:] if y.lower().endswith(".udf")], rapor)
    if tk.TkVersion < 8.6:
        print(f"UYARI: Tcl/Tk {tk.TkVersion} çok eski; pencere boş görünebilir.",
              file=sys.stderr)
    uyg = Uygulama()
    uyg.ekle([y for y in sys.argv[1:] if os.path.exists(y)])
    uyg.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
