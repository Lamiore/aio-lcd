"""Editor tata letak — jendela GTK4 untuk menggeser dan mewarnai angka.

Pratinjaunya digambar `lcd_tataletak.render`, penggambar yang sama yang
menghasilkan `preview.png` tema. Sengaja tidak digambar ulang dengan Cairo
atau Pango: dua penggambar berarti dua hasil, dan yang terlihat waktu menyetel
harus sama persis dengan yang keluar di panel. Yang dikerjakan Cairo di sini
cuma hal yang bukan bagian dari tema — bingkai pilihan, penanda tumpang tindih,
dan area di luar kanvas.

Satu bingkai butuh sekitar 1,2 ms, jadi menggambar ulang seluruh kanvas tiap
kali kursor bergerak masih jauh di bawah anggaran 60 bingkai per detik. Tidak
perlu jalur cepat yang terpisah, dan itu yang menjaga pratinjaunya tetap jujur.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from PIL import Image  # noqa: E402

import lcd_tataletak as lt  # noqa: E402

SISI_KANVAS = 430          # ukuran tampil kanvas di jendela, bukan ukuran tema


def _tekstur(im: Image.Image) -> Gdk.Texture:
    """Ubah citra PIL jadi tekstur GDK tanpa lewat berkas."""
    im = im.convert("RGB")
    data = GLib.Bytes.new(im.tobytes())
    return Gdk.MemoryTexture.new(im.width, im.height, Gdk.MemoryFormat.R8G8B8,
                                 data, im.width * 3)


def _rgba(warna) -> Gdk.RGBA:
    r, g, b = warna
    return Gdk.RGBA(red=r / 255, green=g / 255, blue=b / 255, alpha=1.0)


def _dari_rgba(rgba: Gdk.RGBA) -> tuple[int, int, int]:
    return (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))


class Kanvas(Gtk.DrawingArea):
    """Kanvas tema yang elemennya bisa diklik dan diseret."""

    def __init__(self, pada_pilih, pada_ubah):
        super().__init__()
        self.pada_pilih = pada_pilih
        self.pada_ubah = pada_ubah
        self.tata: lt.TataLetak | None = None
        self.latar: Image.Image | None = None
        self.terpilih = -1

        self._tekstur = None
        self._skala = 1.0
        self._geser = (0.0, 0.0)
        self._awal = None          # posisi elemen waktu seretan dimulai

        self.set_size_request(SISI_KANVAS, SISI_KANVAS)
        self.set_hexpand(False)
        self.set_vexpand(False)
        self.set_draw_func(self._gambar)
        self.set_focusable(True)

        seret = Gtk.GestureDrag()
        seret.connect("drag-begin", self._seret_mulai)
        seret.connect("drag-update", self._seret_jalan)
        seret.connect("drag-end", self._seret_selesai)
        self.add_controller(seret)

        # Papan ketik untuk penyetelan halus: menyeret dengan tetikus tidak
        # bisa memilih piksel tertentu, dan menaruh angka rapi di tepi butuh
        # ketelitian satu piksel.
        tombol = Gtk.EventControllerKey()
        tombol.connect("key-pressed", self._tombol)
        self.add_controller(tombol)

    # ------------------------------------------------------------- keadaan

    def pasang(self, tata: lt.TataLetak, latar: Image.Image) -> None:
        self.tata = tata
        self.latar = latar
        self.segarkan()

    def segarkan(self) -> None:
        if self.tata is None or self.latar is None:
            return
        self._tekstur = _tekstur(lt.render(self.tata, self.latar))
        self.queue_draw()

    def pilih(self, indeks: int) -> None:
        self.terpilih = indeks
        self.queue_draw()

    # ----------------------------------------------------------- koordinat

    def _hitung_skala(self, lebar: int, tinggi: int) -> None:
        if self.tata is None:
            return
        kw, kh = self.tata.kanvas
        self._skala = min(lebar / kw, tinggi / kh)
        self._geser = ((lebar - kw * self._skala) / 2, (tinggi - kh * self._skala) / 2)

    def _ke_tema(self, x: float, y: float) -> tuple[float, float]:
        """Koordinat widget → koordinat kanvas tema."""
        gx, gy = self._geser
        return ((x - gx) / self._skala, (y - gy) / self._skala)

    # ------------------------------------------------------------ gambar

    def _gambar(self, _area, cr, lebar, tinggi):
        if self.tata is None or self._tekstur is None:
            return
        self._hitung_skala(lebar, tinggi)
        kw, kh = self.tata.kanvas
        gx, gy = self._geser

        cr.save()
        cr.translate(gx, gy)
        cr.scale(self._skala, self._skala)

        snapshot = Gtk.Snapshot()
        self._tekstur.snapshot(snapshot, kw, kh)
        simpul = snapshot.to_node()
        if simpul is not None:
            simpul.draw(cr)

        bertumpuk = {i for pasangan in lt.bertumpuk(self.tata) for i in pasangan}
        keluar = set(lt.di_luar_kanvas(self.tata))

        for i, elemen in enumerate(self.tata.elemen):
            kiri, atas, kanan, bawah = lt.kotak(elemen)
            lebar_k, tinggi_k = kanan - kiri, bawah - atas
            if i in bertumpuk or i in keluar:
                # Ditandai, bukan dilarang: dua kotak yang beririsan saling
                # menghapus latarnya tiap penyegaran dan yang terlihat berkedip,
                # tapi kadang memang itu yang dimau (angka kecil di dalam angka
                # besar). Yang salah cuma kalau tidak disadari.
                cr.set_source_rgba(1.0, 0.35, 0.25, 0.85)
                cr.set_dash([6 / self._skala, 4 / self._skala])
            elif i == self.terpilih:
                cr.set_source_rgba(0.30, 0.68, 1.0, 1.0)
                cr.set_dash([])
            else:
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.28)
                cr.set_dash([4 / self._skala, 4 / self._skala])
            cr.set_line_width((2.0 if i == self.terpilih else 1.0) / self._skala)
            cr.rectangle(kiri - 2, atas - 2, lebar_k + 4, tinggi_k + 4)
            cr.stroke()
            cr.set_dash([])

        cr.restore()

        # Tepi kanvas, supaya batas layar jelas walaupun latarnya terang.
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.set_line_width(1)
        cr.rectangle(gx + 0.5, gy + 0.5, kw * self._skala - 1, kh * self._skala - 1)
        cr.stroke()

    # ------------------------------------------------------------ seretan

    def _cari(self, x: float, y: float) -> int:
        """Elemen mana yang ada di titik itu; -1 kalau tidak ada.

        Ditelusuri dari belakang supaya elemen yang tergambar paling akhir —
        yang terlihat paling atas — yang tersambar duluan.
        """
        if self.tata is None:
            return -1
        for i in range(len(self.tata.elemen) - 1, -1, -1):
            kiri, atas, kanan, bawah = lt.kotak(self.tata.elemen[i])
            if kiri - 4 <= x <= kanan + 4 and atas - 4 <= y <= bawah + 4:
                return i
        return -1

    def _seret_mulai(self, gerak, x, y):
        self.grab_focus()
        tx, ty = self._ke_tema(x, y)
        indeks = self._cari(tx, ty)
        self.terpilih = indeks
        self._awal = None
        if indeks >= 0 and self.tata is not None:
            e = self.tata.elemen[indeks]
            self._awal = (e.x, e.y)
        self.pada_pilih(indeks)
        self.queue_draw()

    def _seret_jalan(self, gerak, dx, dy):
        if self._awal is None or self.tata is None or self.terpilih < 0:
            return
        x0, y0 = self._awal
        e = self.tata.elemen[self.terpilih]
        e.x = round(x0 + dx / self._skala)
        e.y = round(y0 + dy / self._skala)
        self.segarkan()
        self.pada_ubah(geser_saja=True)

    def _seret_selesai(self, gerak, dx, dy):
        if self._awal is None:
            return
        self._awal = None
        self.pada_ubah(geser_saja=False)

    def _tombol(self, _kendali, tombol, _kode, keadaan):
        if self.tata is None or self.terpilih < 0:
            return False
        arah = {
            Gdk.KEY_Left: (-1, 0), Gdk.KEY_Right: (1, 0),
            Gdk.KEY_Up: (0, -1), Gdk.KEY_Down: (0, 1),
        }.get(tombol)
        if arah is None:
            return False
        # Shift melangkah sepuluh piksel: menggeser dari ujung ke ujung layar
        # satu piksel sekali tekan tidak masuk akal.
        langkah = 10 if keadaan & Gdk.ModifierType.SHIFT_MASK else 1
        e = self.tata.elemen[self.terpilih]
        e.x += arah[0] * langkah
        e.y += arah[1] * langkah
        self.segarkan()
        self.pada_ubah(geser_saja=False)
        return True


class Editor(Adw.Window):
    """Jendela penyetel tata letak.

    Tidak menyentuh berkas sama sekali: hasilnya diserahkan ke `pada_simpan`
    sebagai objek `TataLetak`. Dengan begitu jendela yang sama dipakai untuk
    membuat tema baru (pemanggil yang menuliskannya) dan untuk menyunting tema
    yang sudah ada (pemanggil yang menimpanya), tanpa cabang di dalam sini.
    """

    def __init__(self, induk, latar: Image.Image, tata: lt.TataLetak,
                 judul: str, label_simpan: str, pada_simpan):
        super().__init__(transient_for=induk, modal=True, title=judul)
        self.set_default_size(880, 660)
        self.tata = tata.salin()
        self.latar = latar
        self.pada_simpan = pada_simpan
        self._menyusun = False       # menahan umpan balik waktu baris disetel dari kode

        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)
        tampilan = Adw.ToolbarView()
        self.toast.set_child(tampilan)

        kepala = Adw.HeaderBar()
        self.judul = Adw.WindowTitle(title=judul, subtitle="")
        kepala.set_title_widget(self.judul)
        batal = Gtk.Button(label="Batal")
        batal.connect("clicked", lambda *_: self.close())
        kepala.pack_start(batal)
        self.tombol_simpan = Gtk.Button(label=label_simpan)
        self.tombol_simpan.add_css_class("suggested-action")
        self.tombol_simpan.connect("clicked", self._simpan)
        kepala.pack_end(self.tombol_simpan)
        tampilan.add_top_bar(kepala)

        isi = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        isi.set_margin_top(12)
        isi.set_margin_bottom(12)
        isi.set_margin_start(12)
        isi.set_margin_end(12)
        tampilan.set_content(isi)

        kiri = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        kiri.set_valign(Gtk.Align.START)
        self.kanvas = Kanvas(self._pilih_dari_kanvas, self._kanvas_berubah)
        bingkai = Gtk.Frame()
        bingkai.add_css_class("view")
        bingkai.set_child(self.kanvas)
        kiri.append(bingkai)

        self.petunjuk = Gtk.Label(xalign=0)
        self.petunjuk.set_wrap(True)
        self.petunjuk.add_css_class("caption")
        self.petunjuk.add_css_class("dim-label")
        self.petunjuk.set_size_request(SISI_KANVAS, -1)
        kiri.append(self.petunjuk)
        isi.append(kiri)

        gulir = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        gulir.set_hexpand(True)
        gulir.set_vexpand(True)
        isi.append(gulir)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        gulir.set_child(panel)

        # Urutannya menurut seberapa sering dipakai, bukan menurut urutan
        # kerja. Menyetel angka yang dipilih adalah putaran yang diulang
        # terus-menerus, sedangkan susunan siap pakai biasanya cuma dipakai
        # sekali di awal — menaruhnya di atas berarti panel yang paling sering
        # disentuh selalu harus digulir dulu.
        panel.append(self._grup_setelan())
        panel.append(self._grup_angka())
        panel.append(self._grup_contoh())

        self.kanvas.pasang(self.tata, self.latar)
        self._pilih(0 if self.tata.elemen else -1)
        self._segarkan_petunjuk()

    # ------------------------------------------------------------- panel

    def _grup_contoh(self) -> Adw.PreferencesGroup:
        grup = Adw.PreferencesGroup(
            title="Tata letak siap pakai",
            description="Menerapkannya menyusun ulang semua angka dari awal",
        )
        self.baris_contoh = Adw.ComboRow(
            title="Susunan",
            model=Gtk.StringList.new([nama for _, nama, _ in lt.CONTOH]),
        )
        grup.add(self.baris_contoh)

        terap = Gtk.Button(label="Terapkan susunan")
        terap.set_margin_top(6)
        terap.set_halign(Gtk.Align.END)
        terap.connect("clicked", self._terapkan_contoh)
        grup.add(terap)
        return grup

    def _grup_angka(self) -> Adw.PreferencesGroup:
        grup = Adw.PreferencesGroup(
            title="Angka yang ditampilkan",
            description="Matikan yang tidak dipakai — makin sedikit angka, makin lega layarnya",
        )
        self.saklar = {}
        for jenis in lt.JENIS:
            baris = Adw.SwitchRow(title=jenis.nama, subtitle=f"contoh: {jenis.contoh.strip()}")
            baris.connect("notify::active", self._saklar_berubah, jenis.kunci)
            grup.add(baris)
            self.saklar[jenis.kunci] = baris
        self._segarkan_saklar()
        return grup

    def _grup_setelan(self) -> Adw.PreferencesGroup:
        self.grup_setel = Adw.PreferencesGroup(title="Angka terpilih")

        self.warna_angka = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        self.warna_angka.set_valign(Gtk.Align.CENTER)
        self.warna_angka.connect("notify::rgba", self._ubah_warna)
        baris_warna = Adw.ActionRow(title="Warna angka")
        baris_warna.add_suffix(self.warna_angka)
        self.grup_setel.add(baris_warna)

        self.baris_ukuran = Adw.SpinRow.new_with_range(10, 200, 2)
        self.baris_ukuran.set_title("Ukuran huruf")
        self.baris_ukuran.connect("notify::value", self._ubah_ukuran)
        self.grup_setel.add(self.baris_ukuran)

        self.baris_font = Adw.ComboRow(
            title="Huruf", model=Gtk.StringList.new([n for n, _ in lt.FONT_PILIHAN]))
        self.baris_font.connect("notify::selected", self._ubah_font)
        self.grup_setel.add(self.baris_font)

        self.baris_x = Adw.SpinRow.new_with_range(-200, 1000, 1)
        self.baris_x.set_title("Jarak dari kiri")
        self.baris_x.connect("notify::value", self._ubah_posisi)
        self.grup_setel.add(self.baris_x)

        self.baris_y = Adw.SpinRow.new_with_range(-200, 1000, 1)
        self.baris_y.set_title("Jarak dari atas")
        self.baris_y.connect("notify::value", self._ubah_posisi)
        self.grup_setel.add(self.baris_y)

        self.baris_label = Adw.EntryRow(title="Label (kosongkan kalau tak perlu)")
        self.baris_label.connect("notify::text", self._ubah_label)
        self.grup_setel.add(self.baris_label)

        self.baris_label_ukuran = Adw.SpinRow.new_with_range(8, 90, 1)
        self.baris_label_ukuran.set_title("Ukuran label")
        self.baris_label_ukuran.connect("notify::value", self._ubah_label_ukuran)
        self.grup_setel.add(self.baris_label_ukuran)

        self.baris_label_x = Adw.SpinRow.new_with_range(-300, 300, 1)
        self.baris_label_x.set_title("Geser label ke kanan")
        self.baris_label_x.connect("notify::value", self._ubah_label_geser)
        self.grup_setel.add(self.baris_label_x)

        self.baris_label_y = Adw.SpinRow.new_with_range(-300, 300, 1)
        self.baris_label_y.set_title("Geser label ke bawah")
        self.baris_label_y.connect("notify::value", self._ubah_label_geser)
        self.grup_setel.add(self.baris_label_y)

        semua = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        semua.set_margin_top(8)
        semua.set_halign(Gtk.Align.END)
        for teks, fungsi in (("Samakan warna semua", self._samakan_warna),
                             ("Samakan huruf semua", self._samakan_font)):
            b = Gtk.Button(label=teks)
            b.connect("clicked", fungsi)
            semua.append(b)
        self.grup_setel.add(semua)
        return self.grup_setel

    # ------------------------------------------------------------ pilihan

    @property
    def elemen(self):
        if 0 <= self.kanvas.terpilih < len(self.tata.elemen):
            return self.tata.elemen[self.kanvas.terpilih]
        return None

    def _pilih_dari_kanvas(self, indeks: int) -> None:
        self._pilih(indeks)

    def _pilih(self, indeks: int) -> None:
        self.kanvas.pilih(indeks)
        e = self.elemen
        self.grup_setel.set_sensitive(e is not None)
        if e is None:
            self.grup_setel.set_title("Angka terpilih — belum ada")
            self.grup_setel.set_description("Klik salah satu angka di pratinjau")
            return
        self.grup_setel.set_title(f"Angka terpilih: {e.info.nama}")
        self.grup_setel.set_description(None)

        self._menyusun = True
        try:
            self.warna_angka.set_rgba(_rgba(e.warna))
            self.baris_ukuran.set_value(e.ukuran)
            daftar = [j for _, j in lt.FONT_PILIHAN]
            self.baris_font.set_selected(daftar.index(e.font) if e.font in daftar else 0)
            self.baris_x.set_value(e.x)
            self.baris_y.set_value(e.y)
            self.baris_label.set_text(e.label)
            self.baris_label_ukuran.set_value(e.label_ukuran)
            self.baris_label_x.set_value(e.label_geser[0])
            self.baris_label_y.set_value(e.label_geser[1])
        finally:
            self._menyusun = False

    def _kanvas_berubah(self, geser_saja: bool = False) -> None:
        """Dipanggil kanvas setelah elemen digeser."""
        e = self.elemen
        if e is not None:
            self._menyusun = True
            try:
                self.baris_x.set_value(e.x)
                self.baris_y.set_value(e.y)
            finally:
                self._menyusun = False
        self._segarkan_petunjuk()

    # -------------------------------------------------------- penyuntingan

    def _ubah(self, fungsi) -> None:
        """Terapkan perubahan ke elemen terpilih lalu gambar ulang."""
        if self._menyusun:
            return
        e = self.elemen
        if e is None:
            return
        fungsi(e)
        self.kanvas.segarkan()
        self._segarkan_petunjuk()

    def _ubah_warna(self, *_):
        warna = _dari_rgba(self.warna_angka.get_rgba())

        def terap(e):
            # Warna label yang belum pernah disetel sendiri ikut warna angkanya;
            # kalau tidak, mengganti warna angka meninggalkan label warna lama
            # dan hasilnya terlihat seperti cacat.
            if e.label_warna is None or e.label_warna == e.warna:
                e.label_warna = None
            e.warna = warna
        self._ubah(terap)

    def _ubah_ukuran(self, *_):
        self._ubah(lambda e: setattr(e, "ukuran", int(self.baris_ukuran.get_value())))

    def _ubah_font(self, *_):
        nama = lt.FONT_PILIHAN[self.baris_font.get_selected()][1]
        self._ubah(lambda e: setattr(e, "font", nama))

    def _ubah_posisi(self, *_):
        def terap(e):
            e.x = int(self.baris_x.get_value())
            e.y = int(self.baris_y.get_value())
        self._ubah(terap)

    def _ubah_label(self, *_):
        self._ubah(lambda e: setattr(e, "label", self.baris_label.get_text()))

    def _ubah_label_ukuran(self, *_):
        self._ubah(lambda e: setattr(e, "label_ukuran",
                                     int(self.baris_label_ukuran.get_value())))

    def _ubah_label_geser(self, *_):
        self._ubah(lambda e: setattr(e, "label_geser",
                                     (int(self.baris_label_x.get_value()),
                                      int(self.baris_label_y.get_value()))))

    def _samakan_warna(self, *_):
        e = self.elemen
        if e is None:
            return
        for lain in self.tata.elemen:
            lain.warna = e.warna
            lain.label_warna = None
        self.kanvas.segarkan()
        self._segarkan_petunjuk()

    def _samakan_font(self, *_):
        e = self.elemen
        if e is None:
            return
        for lain in self.tata.elemen:
            lain.font = e.font
        self.kanvas.segarkan()
        self._segarkan_petunjuk()

    # ------------------------------------------------------------- saklar

    def _segarkan_saklar(self) -> None:
        terpakai = self.tata.jenis_terpakai()
        self._menyusun = True
        try:
            for kunci, baris in self.saklar.items():
                baris.set_active(kunci in terpakai)
        finally:
            self._menyusun = False

    def _saklar_berubah(self, baris, _param, kunci: str) -> None:
        if self._menyusun:
            return
        nyala = baris.get_active()
        ada = [i for i, e in enumerate(self.tata.elemen) if e.jenis == kunci]
        if nyala and not ada:
            self.tata.elemen.append(self._elemen_baru(kunci))
            self._pilih(len(self.tata.elemen) - 1)
        elif not nyala and ada:
            for i in reversed(ada):
                self.tata.elemen.pop(i)
            self._pilih(min(self.kanvas.terpilih, len(self.tata.elemen) - 1))
        self.kanvas.segarkan()
        self._segarkan_petunjuk()

    def _elemen_baru(self, kunci: str) -> lt.Elemen:
        """Angka baru ditaruh di tempat kosong, bukan menumpuk yang sudah ada.

        Titik awal yang menumpuk membuat orang mengira angkanya tidak muncul —
        padahal cuma tertimbun. Dicari dari kiri-atas turun ke bawah sampai
        ketemu petak yang kotaknya tidak bersinggungan dengan yang lain.
        """
        contoh = self.tata.elemen[0] if self.tata.elemen else None
        baru = lt.Elemen(
            jenis=kunci, x=40, y=40,
            ukuran=contoh.ukuran if contoh else 54,
            warna=contoh.warna if contoh else (235, 235, 235),
            font=contoh.font if contoh else lt.FONT_BAKU,
            label=lt.PETA_JENIS[kunci].label,
            label_ukuran=contoh.label_ukuran if contoh else 20,
            label_geser=contoh.label_geser if contoh else (2, -26),
        )
        lebar, tinggi = self.tata.kanvas
        kotak_ada = [lt.kotak(e) for e in self.tata.elemen]
        for y in range(24, tinggi - 40, 28):
            for x in range(24, lebar - 60, 28):
                baru.x, baru.y = x, y
                kiri, atas, kanan, bawah = lt.kotak(baru)
                if kanan > lebar or bawah > tinggi:
                    continue
                if not any(kiri < k[2] and k[0] < kanan and atas < k[3] and k[1] < bawah
                           for k in kotak_ada):
                    return baru
        baru.x, baru.y = 40, 40
        return baru

    def _terapkan_contoh(self, *_):
        kunci = lt.CONTOH[self.baris_contoh.get_selected()][0]
        lama = self.tata.elemen[0] if self.tata.elemen else None
        baru = lt.contoh(
            kunci, kanvas=self.tata.kanvas,
            warna=lama.warna if lama else lt.warna_kontras(self.latar),
            font=lama.font if lama else lt.FONT_BAKU,
        )
        self.tata.elemen = baru.elemen
        self.kanvas.pasang(self.tata, self.latar)
        self._segarkan_saklar()
        self._pilih(0 if self.tata.elemen else -1)
        self._segarkan_petunjuk()

    # ---------------------------------------------------------- keterangan

    def _segarkan_petunjuk(self) -> None:
        garis = ["Seret angkanya untuk memindahkan · tombol panah menggeser "
                 "satu piksel, Shift+panah sepuluh"]
        tumpuk = lt.bertumpuk(self.tata)
        if tumpuk:
            nama = {self.tata.elemen[i].info.nama for pasangan in tumpuk for i in pasangan}
            garis.append("Bertumpuk: " + ", ".join(sorted(nama))
                         + " — di layar keduanya akan saling menghapus dan terlihat berkedip")
        keluar = lt.di_luar_kanvas(self.tata)
        if keluar:
            nama = {self.tata.elemen[i].info.nama for i in keluar}
            garis.append("Keluar layar: " + ", ".join(sorted(nama)) + " — bagian yang lewat tepi terpotong")
        if not self.tata.elemen:
            garis.append("Belum ada angka sama sekali — nyalakan salah satu di daftar sebelah")
        self.petunjuk.set_text("\n".join(garis))
        self.judul.set_subtitle(f"{len(self.tata.elemen)} angka")

    # ------------------------------------------------------------- simpan

    def _simpan(self, *_):
        if not self.tata.elemen:
            self.toast.add_toast(Adw.Toast(
                title="Belum ada angka yang ditampilkan", timeout=4))
            return
        self.pada_simpan(self.tata)
        self.close()
