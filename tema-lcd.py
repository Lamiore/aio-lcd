#!/usr/bin/env python3
"""Pemilih tema layar LCD AIO — GTK4 + libadwaita.

Dijalankan dengan Python sistem (yang punya `gi` dan `yaml`), bukan venv
upstream. Semua penyuntingan berkas dan pengendalian service ada di
lcd_konfig.py; berkas ini murni antarmuka.
"""

import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lcd_gif as lg  # noqa: E402
import lcd_konfig as lk  # noqa: E402
import lcd_tema as lt  # noqa: E402

# Ukuran layar yang dipakai menyaring tema. Panel AIO ini 2.1"; tema ukuran
# lain tetap mau dimuat upstream, tapi tata letaknya melenceng — jadi
# defaultnya disaring, dengan sakelar kalau mau melihat semuanya.
UKURAN_LAYAR = '2.1"'
LEBAR_PREVIEW = 150


class KartuTema(Gtk.FlowBoxChild):
    """Satu tema: gambar preview, namanya, penulisnya."""

    def __init__(self, tema: lk.Tema, milik_pengguna: bool = False):
        super().__init__()
        self.tema = tema
        self.milik_pengguna = milik_pengguna
        self.set_focusable(True)

        kotak = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        kotak.set_margin_top(6)
        kotak.set_margin_bottom(6)
        kotak.set_margin_start(6)
        kotak.set_margin_end(6)

        if tema.punya_preview:
            gambar = Gtk.Picture.new_for_filename(str(tema.preview))
            gambar.set_content_fit(Gtk.ContentFit.COVER)
        else:
            gambar = Gtk.Image.new_from_icon_name("image-missing-symbolic")
            gambar.set_pixel_size(64)
        gambar.set_size_request(LEBAR_PREVIEW, LEBAR_PREVIEW)
        gambar.add_css_class("card")
        kotak.append(gambar)

        baris_judul = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        baris_judul.set_halign(Gtk.Align.CENTER)
        judul = Gtk.Label(label=tema.nama)
        judul.add_css_class("heading")
        judul.set_ellipsize(Pango.EllipsizeMode.END)
        baris_judul.append(judul)
        if milik_pengguna:
            # Penanda ini yang membedakan tema yang boleh dihapus/disunting
            # dari tema bawaan upstream.
            tanda = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
            tanda.set_tooltip_text("Tema buatan sendiri")
            tanda.add_css_class("dim-label")
            baris_judul.append(tanda)
        kotak.append(baris_judul)

        keterangan = tema.penulis or tema.ukuran
        if tema.penulis and tema.ukuran != UKURAN_LAYAR:
            keterangan = f"{tema.penulis} · {tema.ukuran}"
        bawah = Gtk.Label(label=keterangan)
        bawah.add_css_class("caption")
        bawah.add_css_class("dim-label")
        bawah.set_ellipsize(Pango.EllipsizeMode.END)
        kotak.append(bawah)

        self.set_child(kotak)


class Jendela(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Tema LCD AIO")
        self.set_default_size(620, 640)

        self.konfig = lk.Konfig()
        self.sedang_terapkan = False
        self.gif_berjalan = False
        try:
            self.tema_terpasang = self.konfig.tema
            self.terbalik_terpasang = self.konfig.terbalik
        except (lk.GalatKonfig, OSError) as galat:
            self.tema_terpasang = ""
            self.terbalik_terpasang = False
            self._galat_fatal(galat)
            return

        self.tema_dipilih = self.tema_terpasang

        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)

        tampilan = Adw.ToolbarView()
        self.toast.set_child(tampilan)

        # --- bilah atas
        self.header = Adw.HeaderBar()
        self.judul = Adw.WindowTitle(title="Tema LCD AIO", subtitle="")
        self.header.set_title_widget(self.judul)

        self.tombol_terap = Gtk.Button(label="Terapkan")
        self.tombol_terap.add_css_class("suggested-action")
        self.tombol_terap.connect("clicked", self.on_terapkan)
        self.header.pack_end(self.tombol_terap)

        self.putaran = Gtk.Spinner()
        self.header.pack_end(self.putaran)

        self.pustaka = lt.PustakaTema()
        self._siapkan_aksi()

        menu = Gio.Menu()
        bagian_buat = Gio.Menu()
        bagian_buat.append("Bikin dari gambar…", "win.bikin")
        bagian_buat.append("Duplikat tema terpilih…", "win.duplikat")
        menu.append_section(None, bagian_buat)
        bagian_impor = Gio.Menu()
        bagian_impor.append("Impor dari folder…", "win.impor-folder")
        bagian_impor.append("Impor dari zip…", "win.impor-zip")
        menu.append_section(None, bagian_impor)
        bagian_gif = Gio.Menu()
        bagian_gif.append("Putar GIF…", "win.putar-gif")
        menu.append_section(None, bagian_gif)
        bagian_hapus = Gio.Menu()
        bagian_hapus.append("Hapus tema terpilih…", "win.hapus")
        menu.append_section(None, bagian_hapus)

        self.tombol_tambah = Gtk.MenuButton(icon_name="list-add-symbolic", menu_model=menu)
        self.tombol_tambah.set_tooltip_text("Tambah atau hapus tema")
        self.header.pack_start(self.tombol_tambah)

        tampilan.add_top_bar(self.header)

        # --- isi
        gulir = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        gulir.set_vexpand(True)
        tampilan.set_content(gulir)

        penjepit = Adw.Clamp(maximum_size=760)
        penjepit.set_margin_top(12)
        penjepit.set_margin_bottom(18)
        penjepit.set_margin_start(12)
        penjepit.set_margin_end(12)
        gulir.set_child(penjepit)

        isi = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        penjepit.set_child(isi)

        self.spanduk = Adw.Banner()
        self.spanduk.set_revealed(False)
        self.spanduk.connect("button-clicked", self.on_hentikan_gif)
        isi.append(self.spanduk)

        grup_tampilan = Adw.PreferencesGroup(title="Tampilan")
        isi.append(grup_tampilan)

        self.baris_balik = Adw.SwitchRow(
            title="Balik 180°",
            subtitle="Nyalakan kalau blok pompa terpasang terbalik",
        )
        self.baris_balik.set_active(self.terbalik_terpasang)
        self.baris_balik.connect("notify::active", lambda *_: self._segarkan_tombol())
        grup_tampilan.add(self.baris_balik)

        self.baris_semua = Adw.SwitchRow(
            title="Tampilkan semua ukuran",
            subtitle=f"Biasanya cuma tema {UKURAN_LAYAR} yang pas di layar ini",
        )
        self.baris_semua.connect("notify::active", lambda *_: self._muat_tema())
        grup_tampilan.add(self.baris_semua)

        self.grup_tema = Adw.PreferencesGroup(title="Tema")
        isi.append(self.grup_tema)

        self.petak = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            homogeneous=True,
            min_children_per_line=2,
            max_children_per_line=4,
            row_spacing=6,
            column_spacing=6,
        )
        self.petak.connect("selected-children-changed", self.on_pilih)
        self.grup_tema.add(self.petak)

        self._muat_tema()
        self._segarkan_status()
        GLib.timeout_add_seconds(3, self._pantau_gif)

    # ------------------------------------------------------------- pemuatan

    def _muat_tema(self):
        anak = self.petak.get_first_child()
        while anak is not None:
            berikut = anak.get_next_sibling()
            self.petak.remove(anak)
            anak = berikut

        ukuran = None if self.baris_semua.get_active() else UKURAN_LAYAR
        daftar = lk.daftar_tema(ukuran)
        punya_sendiri = set(self.pustaka.daftar_pengguna())

        # Tema yang sedang terpasang harus selalu kelihatan, walaupun ukurannya
        # di luar saringan — kalau tidak, tampilannya seperti tak ada yang aktif.
        if self.tema_terpasang and not any(t.nama == self.tema_terpasang for t in daftar):
            tambahan = [t for t in lk.daftar_tema(None) if t.nama == self.tema_terpasang]
            daftar = tambahan + daftar

        if not daftar:
            self.grup_tema.set_description(
                f"Tidak ada tema {UKURAN_LAYAR} di {lk.DIR_UPSTREAM / 'res/themes'}"
            )
            return

        jumlah_sendiri = sum(1 for t in daftar if t.nama in punya_sendiri)
        keterangan = f"{len(daftar)} tema tersedia"
        if jumlah_sendiri:
            keterangan += f" · {jumlah_sendiri} buatan sendiri"
        self.grup_tema.set_description(keterangan)

        terpilih = None
        for tema in daftar:
            kartu = KartuTema(tema, milik_pengguna=tema.nama in punya_sendiri)
            self.petak.append(kartu)
            if tema.nama == self.tema_dipilih:
                terpilih = kartu
        if terpilih is not None:
            self.petak.select_child(terpilih)
        self._segarkan_tombol()

    # -------------------------------------------------------------- keadaan

    def _segarkan_status(self):
        self.gif_berjalan = lk.gif_aktif()
        if self.gif_berjalan:
            self.spanduk.set_title("GIF sedang diputar — statistik berhenti sementara")
            self.spanduk.set_button_label("Hentikan")
            self.spanduk.set_revealed(True)
        elif not lk.service_terpasang():
            self.spanduk.set_title(
                f"{lk.NAMA_SERVICE} belum terpasang — perubahan disimpan, tapi layar tidak ikut berubah"
            )
            self.spanduk.set_button_label(None)
            self.spanduk.set_revealed(True)
        elif not lk.service_aktif():
            self.spanduk.set_title(f"{lk.NAMA_SERVICE} sedang mati — Terapkan akan menyalakannya")
            self.spanduk.set_button_label(None)
            self.spanduk.set_revealed(True)
        else:
            self.spanduk.set_revealed(False)
        self.judul.set_subtitle(f"tema aktif: {self.tema_terpasang or '—'}")
        self._segarkan_tombol()

    def _pantau_gif(self):
        """Periksa berkala: pemutar bisa berhenti sendiri (GIF rusak, panel
        tidak terdeteksi), dan spanduknya harus ikut hilang tanpa perlu
        aplikasinya dibuka ulang."""
        if lk.gif_aktif() != self.gif_berjalan:
            self._segarkan_status()
        return True  # terus berjalan

    def _ada_perubahan(self) -> bool:
        return (
            self.tema_dipilih != self.tema_terpasang
            or self.baris_balik.get_active() != self.terbalik_terpasang
        )

    def _segarkan_tombol(self):
        self.tombol_terap.set_sensitive(
            not self.sedang_terapkan and not self.gif_berjalan and self._ada_perubahan()
        )
        self._segarkan_aksi()

    def on_pilih(self, petak):
        anak = petak.get_selected_children()
        if anak:
            self.tema_dipilih = anak[0].tema.nama
            self._segarkan_tombol()

    def _kartu_terpilih(self):
        anak = self.petak.get_selected_children()
        return anak[0] if anak else None

    # ------------------------------------------------------ kelola pustaka

    def _siapkan_aksi(self):
        self.aksi = {}
        for nama, fungsi in (
            ("bikin", self.on_bikin),
            ("duplikat", self.on_duplikat),
            ("impor-folder", self.on_impor_folder),
            ("impor-zip", self.on_impor_zip),
            ("hapus", self.on_hapus),
            ("putar-gif", self.on_putar_gif),
        ):
            a = Gio.SimpleAction.new(nama, None)
            a.connect("activate", fungsi)
            self.add_action(a)
            self.aksi[nama] = a

    def _segarkan_aksi(self):
        kartu = self._kartu_terpilih()
        # Selama GIF diputar, monitor sengaja mati dan port serialnya dipegang
        # pemutar — mengubah tema saat itu tidak akan kelihatan.
        bebas = not self.sedang_terapkan and not self.gif_berjalan
        ada = kartu is not None
        self.aksi["bikin"].set_enabled(bebas and ada)
        self.aksi["duplikat"].set_enabled(bebas and ada)
        self.aksi["impor-folder"].set_enabled(bebas)
        self.aksi["impor-zip"].set_enabled(bebas)
        self.aksi["putar-gif"].set_enabled(bebas)
        # Tema bawaan upstream tidak dihapus dari sini, dan tema yang sedang
        # dipakai layar juga tidak — menghapusnya bikin service gagal memuat.
        self.aksi["hapus"].set_enabled(
            bebas and ada and kartu.milik_pengguna and kartu.tema.nama != self.tema_terpasang
        )

    def _tanya_nama(self, judul, awalan, label_tombol, lanjut):
        entri = Gtk.Entry(text=awalan, activates_default=True)
        entri.set_margin_top(6)
        dialog = Adw.AlertDialog(heading=judul, body="Nama ini dipakai sebagai nama folder tema.")
        dialog.set_extra_child(entri)
        dialog.add_response("batal", "Batal")
        dialog.add_response("ok", label_tombol)
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")
        dialog.set_close_response("batal")
        dialog.connect("response", lambda _d, resp: resp == "ok" and lanjut(entri.get_text().strip()))
        dialog.present(self)

    def _jalankan(self, kerja, nama_baru, pesan_sukses):
        """Jalankan operasi pustaka, lalu muat ulang petak dan pilih hasilnya."""
        try:
            kerja()
        except (lt.GalatTema, OSError) as galat:
            self._toast(str(galat))
            return
        self.tema_dipilih = nama_baru
        self._muat_tema()
        self._toast(pesan_sukses)

    def _saringan(self, nama, *mime):
        saring = Gtk.FileFilter()
        saring.set_name(nama)
        for m in mime:
            saring.add_mime_type(m)
        daftar = Gio.ListStore.new(Gtk.FileFilter)
        daftar.append(saring)
        return saring, daftar

    def on_bikin(self, *_):
        kartu = self._kartu_terpilih()
        if kartu is None:
            return
        donor = kartu.tema.nama
        dialog = Gtk.FileDialog(title="Pilih gambar untuk jadi latar")
        saring, daftar = self._saringan(
            "Gambar", "image/png", "image/jpeg", "image/webp", "image/bmp", "image/gif"
        )
        dialog.set_filters(daftar)
        dialog.set_default_filter(saring)

        def selesai(d, hasil):
            try:
                berkas = d.open_finish(hasil)
            except GLib.Error:
                return  # dibatalkan
            jalur = Path(berkas.get_path())
            self._tanya_nama(
                "Nama tema baru", jalur.stem[:40], "Buat",
                lambda nama: self._jalankan(
                    lambda: self.pustaka.buat_dari_gambar(jalur, nama, donor=donor),
                    nama,
                    f"Tema {nama} dibuat — tata letak dari {donor}",
                ),
            )

        dialog.open(self, None, selesai)

    def on_duplikat(self, *_):
        kartu = self._kartu_terpilih()
        if kartu is None:
            return
        sumber = kartu.tema.nama
        self._tanya_nama(
            f"Duplikat tema {sumber}", f"{sumber} salinan", "Duplikat",
            lambda nama: self._jalankan(
                lambda: self.pustaka.duplikat(sumber, nama), nama, f"Tema {nama} dibuat"
            ),
        )

    def _impor(self, dialog, buka, judul_nama):
        def selesai(d, hasil):
            try:
                berkas = buka(d, hasil)
            except GLib.Error:
                return
            jalur = Path(berkas.get_path())
            awalan = (jalur.stem if jalur.is_file() else jalur.name)[:40]
            self._tanya_nama(
                judul_nama, awalan, "Impor",
                lambda nama: self._jalankan(
                    lambda: self.pustaka.impor(jalur, nama_baru=nama), nama, f"Tema {nama} diimpor"
                ),
            )

        return selesai

    def on_impor_folder(self, *_):
        dialog = Gtk.FileDialog(title="Pilih folder tema")
        dialog.select_folder(
            self, None,
            self._impor(dialog, lambda d, h: d.select_folder_finish(h), "Nama tema hasil impor"),
        )

    def on_impor_zip(self, *_):
        dialog = Gtk.FileDialog(title="Pilih berkas zip tema")
        saring, daftar = self._saringan("Arsip zip", "application/zip")
        dialog.set_filters(daftar)
        dialog.set_default_filter(saring)
        dialog.open(
            self, None,
            self._impor(dialog, lambda d, h: d.open_finish(h), "Nama tema hasil impor"),
        )

    def on_hapus(self, *_):
        kartu = self._kartu_terpilih()
        if kartu is None or not kartu.milik_pengguna:
            return
        nama = kartu.tema.nama
        dialog = Adw.AlertDialog(
            heading=f"Hapus tema {nama}?",
            body="Folder temanya dihapus permanen. Tema bawaan tidak terpengaruh.",
        )
        dialog.add_response("batal", "Batal")
        dialog.add_response("hapus", "Hapus")
        dialog.set_response_appearance("hapus", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("batal")
        dialog.set_close_response("batal")

        def jawab(_d, resp):
            if resp != "hapus":
                return
            try:
                self.pustaka.hapus(nama)
            except (lt.GalatTema, OSError) as galat:
                self._toast(str(galat))
                return
            if self.tema_dipilih == nama:
                self.tema_dipilih = self.tema_terpasang
            self._muat_tema()
            self._toast(f"Tema {nama} dihapus")

        dialog.connect("response", jawab)
        dialog.present(self)

    # ---------------------------------------------------------------- GIF

    def on_putar_gif(self, *_):
        dialog = Gtk.FileDialog(title="Pilih GIF untuk diputar")
        saring, daftar = self._saringan("GIF", "image/gif")
        dialog.set_filters(daftar)
        dialog.set_default_filter(saring)

        def selesai(d, hasil):
            try:
                berkas = d.open_finish(hasil)
            except GLib.Error:
                return
            self._dialog_gif(Path(berkas.get_path()))

        dialog.open(self, None, selesai)

    def _dialog_gif(self, jalur: Path):
        ukuran = list(lg.UKURAN_PILIHAN)
        label = [f"{u}×{u}" + (" — layar penuh" if u == lg.KANVAS_BAKU else "") for u in ukuran]
        pilihan = Adw.ComboRow(title="Ukuran tayang", model=Gtk.StringList.new(label))
        pilihan.set_selected(ukuran.index(240) if 240 in ukuran else 0)

        keterangan = Gtk.Label(xalign=0)
        keterangan.set_wrap(True)
        keterangan.add_css_class("dim-label")
        keterangan.set_margin_top(8)

        grup = Adw.PreferencesGroup()
        grup.add(pilihan)
        kotak = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        kotak.set_size_request(360, -1)
        kotak.append(grup)
        kotak.append(keterangan)

        def segarkan(*_):
            u = ukuran[pilihan.get_selected()]
            try:
                r = lg.ringkasan(jalur, u)
            except (OSError, ValueError) as galat:
                keterangan.set_text(f"Tidak bisa membaca GIF: {galat}")
                return
            garis = (f"{r['jumlah_bingkai']} bingkai · GIF minta "
                     f"{r['fps_diminta']:.1f} fps · panel sanggup ~{r['fps_sanggup']:.1f} fps")
            if not r["mulus"]:
                garis += ("\nAkan diputar lebih lambat dari aslinya. Pilih ukuran "
                          "lebih kecil kalau mau mulus — fps naik sebanding luas area.")
            keterangan.set_text(garis)

        pilihan.connect("notify::selected", segarkan)
        segarkan()

        dialog = Adw.AlertDialog(
            heading=f"Putar {jalur.name}",
            body="Statistik berhenti selama GIF diputar — cuma satu program "
                 "yang boleh memakai layarnya.",
        )
        dialog.set_extra_child(kotak)
        dialog.add_response("batal", "Batal")
        dialog.add_response("putar", "Putar")
        dialog.set_response_appearance("putar", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("putar")
        dialog.set_close_response("batal")

        def jawab(_d, resp):
            if resp != "putar":
                return
            berhasil, pesan = lk.mulai_gif(jalur, ukuran[pilihan.get_selected()])
            self._toast(pesan)
            if berhasil:
                # Pemutar butuh beberapa detik membangunkan panel; pantau
                # berkala yang akan memunculkan spanduknya.
                GLib.timeout_add_seconds(2, lambda: (self._segarkan_status(), False)[1])

        dialog.connect("response", jawab)
        dialog.present(self)

    def on_hentikan_gif(self, *_):
        berhasil, pesan = lk.hentikan_gif()
        self._toast(pesan)
        if berhasil:
            self._segarkan_status()

    # ----------------------------------------------------------- penerapan

    def on_terapkan(self, _tombol):
        if self.sedang_terapkan:
            return
        tema = self.tema_dipilih
        balik = self.baris_balik.get_active()

        try:
            if tema != self.tema_terpasang:
                self.konfig.tema = tema
            if balik != self.terbalik_terpasang:
                self.konfig.terbalik = balik
        except (lk.GalatKonfig, OSError) as galat:
            self._toast(f"Gagal menulis config: {galat}")
            return

        self.tema_terpasang = tema
        self.terbalik_terpasang = balik
        self._kunci(True, "menyalakan ulang layar…")

        threading.Thread(target=self._kerja_restart, daemon=True).start()

    def _kerja_restart(self):
        berhasil, pesan = lk.restart_service()
        GLib.idle_add(self._selesai_restart, berhasil, pesan)

    def _selesai_restart(self, berhasil, pesan):
        self._kunci(False, "")
        self._segarkan_status()
        self._toast(f"Tema {self.tema_terpasang} aktif" if berhasil else f"Belum berhasil: {pesan}")
        return False

    def _kunci(self, terkunci: bool, keterangan: str):
        self.sedang_terapkan = terkunci
        self.petak.set_sensitive(not terkunci)
        self.baris_balik.set_sensitive(not terkunci)
        self.baris_semua.set_sensitive(not terkunci)
        self.tombol_tambah.set_sensitive(not terkunci)
        if terkunci:
            self.putaran.start()
            self.judul.set_subtitle(keterangan)
        else:
            self.putaran.stop()
        self._segarkan_tombol()

    def _toast(self, pesan: str):
        self.toast.add_toast(Adw.Toast(title=pesan, timeout=4))

    def _galat_fatal(self, galat):
        dialog = Adw.AlertDialog(
            heading="Tidak bisa membaca config",
            body=f"{galat}\n\nDicari di: {self.konfig.jalur}\n\n"
                 "Kalau klon upstream ada di tempat lain, setel AIO_LCD_UPSTREAM.",
        )
        dialog.add_response("tutup", "Tutup")
        dialog.connect("response", lambda *_: self.close())
        self.set_content(Adw.ToolbarView())
        GLib.idle_add(dialog.present, self)


class Aplikasi(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.lamiore.AioLcdTema")

    def do_activate(self):
        jendela = self.props.active_window or Jendela(self)
        jendela.present()


if __name__ == "__main__":
    sys.exit(Aplikasi().run(sys.argv))
