#!/usr/bin/env python3
"""
UDF İmza Birleştirici — masaüstü uygulaması.

Aynı belgenin ayrı ayrı e-imzalanmış nüshalarındaki imzaları tek dosyada toplar.
İnternete ve hiçbir dış programa bağlı değildir; belgeler bilgisayardan çıkmaz.

Akış:  nüshaları ekle → İncele → (denetim geçerse) Birleştir → kaydet → raporlar
"""
import json
import os
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

if getattr(sys, "frozen", False):                   # PyInstaller paketi
    sys.path.insert(0, os.path.dirname(os.path.abspath(sys.executable)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from birlestirici import denetle
from udf_ortak import TSI, Durdur

# Sürükle-bırak Tkinter'da yerleşik değil; paket yoksa düğmeyle devam edilir.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TEMEL_PENCERE, SURUKLENEBILIR = TkinterDnD.Tk, True
except Exception:
    TEMEL_PENCERE, SURUKLENEBILIR = tk.Tk, False

UYGULAMA_ADI = "UDF İmza Birleştirici"
SURUM = "1.0"
YAZAR = "Av. Arb. M. İbrahim Asım Bilir"
YAZAR_EK = "av.ibrahimbilir@gmail.com"
TELIF = "© 2026 Av. Arb. M. İbrahim Asım Bilir — MIT Lisansı"

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
# Ayarlar — kullanıcı dizininde saklanır
# --------------------------------------------------------------------------
def ayar_dosyasi():
    if sys.platform == "darwin":
        kok = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        kok = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        kok = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(kok, "UDF Imza Birlestirici", "ayarlar.json")


def ayar_oku():
    try:
        with open(ayar_dosyasi(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ayar_yaz(ayarlar):
    try:
        yol = ayar_dosyasi()
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(ayarlar, f, ensure_ascii=False, indent=1)
    except OSError:
        pass                                        # ayar kaydedilemezse çalışmaya devam


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
        self.ayarlar = ayar_oku()
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
        ttk.Button(ust, text="Ayarlar", width=8,
                   command=self.ayarlari_ac).pack(side="right")

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

        self.btn_birlestir = ttk.Button(dis, text="Birleştir", command=self.birlestir)
        self.rapor_cerceve = ttk.Frame(dis)
        ttk.Button(self.rapor_cerceve, text="Denetim raporu",
                   command=self.denetim_raporu_ac).pack(side="left")
        ttk.Button(self.rapor_cerceve, text="İmza raporu",
                   command=self.imza_raporu_ac).pack(side="left", padx=8)
        self.btn_ayrinti = ttk.Button(dis, text="Ayrıntı", command=self.ayrinti_goster)

        alt_bilgi = ttk.Frame(dis)
        alt_bilgi.pack(side="bottom", fill="x")
        ttk.Label(alt_bilgi, foreground=self.renk["soluk"], font=("Helvetica", 10),
                  text=f"{YAZAR} · s{SURUM}").pack(side="left")
        hakkinda = ttk.Label(alt_bilgi, foreground=self.renk["soluk"],
                             font=("Helvetica", 10, "underline"), cursor="pointinghand",
                             text="Hakkında")
        hakkinda.pack(side="right")
        hakkinda.bind("<Button-1>", lambda e: self.hakkinda_ac())
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
        if len(self.yollar) >= 2:
            self.btn_incele.pack(pady=(0, 4))
        else:
            self.btn_incele.pack_forget()

    def sifirla(self):
        self.sonuc = None
        self.hata_ayrinti = ""
        self.durum_kutu.pack_forget()
        self.btn_birlestir.pack_forget()
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
        try:
            sonuc = denetle(self.yollar, (self.ayarlar.get("capa_tckn") or "").strip())
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
            self.btn_birlestir.pack(pady=(0, 8))
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
        self.durum_goster(True, "Kaydedildi",
                          f"{os.path.basename(yol)}\n"
                          "Kaynak nüshalarınızı delil olarak saklayın.")
        self.btn_birlestir.pack_forget()
        self.rapor_cerceve.pack()

    def denetim_raporu_ac(self):
        RaporPenceresi(self, "Denetim raporu", denetim_raporu(self.sonuc), self.renk)

    def imza_raporu_ac(self):
        RaporPenceresi(self, "İmza raporu", imza_raporu(self.sonuc), self.renk,
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
                       "Belgeler bilgisayardan çıkmaz; internet bağlantısı "
                       "kullanılmaz.\n\n"
                       "Bu bağımsız bir yardımcı araçtır; UYAP ile, Adalet Bakanlığı "
                       "ile veya herhangi bir kurumla ilgisi yoktur."
                  ).pack(anchor="w")
        ttk.Label(c, text=TELIF, foreground=self.renk["soluk"],
                  font=("Helvetica", 10)).pack(anchor="w", pady=(14, 0))
        ttk.Button(c, text="Kapat", command=p.destroy).pack(anchor="e", pady=(16, 0))
        p.bind("<Escape>", lambda e: p.destroy())

    # ---------------------------------------------------------------- ayarlar
    def ayarlari_ac(self):
        p = tk.Toplevel(self)
        p.title("Ayarlar")
        p.transient(self)
        p.resizable(False, False)
        c = ttk.Frame(p, padding=16)
        c.pack(fill="both", expand=True)
        ttk.Label(c, text="Çapa imza TCKN", font=("Helvetica", 13, "bold")).pack(anchor="w")
        ttk.Label(c, foreground=self.renk["soluk"], wraplength=380, justify="left",
                  font=("Helvetica", 11),
                  text="Kendi TC kimlik numaranızı yazarsanız program, sizin imzanızı "
                       "taşımayan nüshaları birleştirmeyi reddeder. Boş bırakılırsa "
                       "yalnızca “nüshalarda ortak bir imzacı var mı” denetlenir.\n\n"
                       "Bu bilgi yalnızca bu bilgisayarda saklanır."
                  ).pack(anchor="w", pady=(4, 10))
        giris = ttk.Entry(c, width=22, font=("Helvetica", 13))
        giris.insert(0, self.ayarlar.get("capa_tckn", ""))
        giris.pack(anchor="w")
        alt = ttk.Frame(c)
        alt.pack(fill="x", pady=(16, 0))

        def kaydet():
            deger = giris.get().strip()
            if deger and (not deger.isdigit() or len(deger) != 11):
                messagebox.showwarning("Geçersiz",
                                       "TC kimlik numarası 11 rakamdan oluşmalıdır.",
                                       parent=p)
                return
            self.ayarlar["capa_tckn"] = deger
            ayar_yaz(self.ayarlar)
            p.destroy()
            self.sifirla()

        ttk.Button(alt, text="Kaydet", command=kaydet).pack(side="right")
        ttk.Button(alt, text="Vazgeç", command=p.destroy).pack(side="right", padx=6)
        giris.focus_set()
        p.bind("<Return>", lambda e: kaydet())
        p.bind("<Escape>", lambda e: p.destroy())


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
