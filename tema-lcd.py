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
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lcd_konfig as lk  # noqa: E402

# Ukuran layar yang dipakai menyaring tema. Panel AIO ini 2.1"; tema ukuran
# lain tetap mau dimuat upstream, tapi tata letaknya melenceng — jadi
# defaultnya disaring, dengan sakelar kalau mau melihat semuanya.
UKURAN_LAYAR = '2.1"'
LEBAR_PREVIEW = 150


class KartuTema(Gtk.FlowBoxChild):
    """Satu tema: gambar preview, namanya, penulisnya."""

    def __init__(self, tema: lk.Tema):
        super().__init__()
        self.tema = tema
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

        judul = Gtk.Label(label=tema.nama)
        judul.add_css_class("heading")
        judul.set_ellipsize(Pango.EllipsizeMode.END)
        kotak.append(judul)

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

    # ------------------------------------------------------------- pemuatan

    def _muat_tema(self):
        anak = self.petak.get_first_child()
        while anak is not None:
            berikut = anak.get_next_sibling()
            self.petak.remove(anak)
            anak = berikut

        ukuran = None if self.baris_semua.get_active() else UKURAN_LAYAR
        daftar = lk.daftar_tema(ukuran)

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

        self.grup_tema.set_description(f"{len(daftar)} tema tersedia")
        terpilih = None
        for tema in daftar:
            kartu = KartuTema(tema)
            self.petak.append(kartu)
            if tema.nama == self.tema_dipilih:
                terpilih = kartu
        if terpilih is not None:
            self.petak.select_child(terpilih)
        self._segarkan_tombol()

    # -------------------------------------------------------------- keadaan

    def _segarkan_status(self):
        if not lk.service_terpasang():
            self.spanduk.set_title(
                f"{lk.NAMA_SERVICE} belum terpasang — perubahan disimpan, tapi layar tidak ikut berubah"
            )
            self.spanduk.set_revealed(True)
        elif not lk.service_aktif():
            self.spanduk.set_title(f"{lk.NAMA_SERVICE} sedang mati — Terapkan akan menyalakannya")
            self.spanduk.set_revealed(True)
        else:
            self.spanduk.set_revealed(False)
        self.judul.set_subtitle(f"tema aktif: {self.tema_terpasang or '—'}")

    def _ada_perubahan(self) -> bool:
        return (
            self.tema_dipilih != self.tema_terpasang
            or self.baris_balik.get_active() != self.terbalik_terpasang
        )

    def _segarkan_tombol(self):
        self.tombol_terap.set_sensitive(not self.sedang_terapkan and self._ada_perubahan())

    def on_pilih(self, petak):
        anak = petak.get_selected_children()
        if anak:
            self.tema_dipilih = anak[0].tema.nama
            self._segarkan_tombol()

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
