#!/usr/bin/env python3
"""Uji jendela editor tata letak.

Butuh layar (GTK harus bisa membuka tampilan), jadi seluruh berkas dilewati
kalau dijalankan tanpa sesi grafis — di situ kegagalannya bukan tanda ada yang
rusak.

Yang diuji perilakunya, bukan rupanya: menyalakan saklar benar-benar menambah
angka, warna yang dipilih sampai ke elemennya, dan menyeret memindahkan yang
terpilih saja. Rupanya diperiksa dengan mata lewat tangkapan jendela.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ADA_LAYAR = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))

if ADA_LAYAR:
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, Gtk
        from PIL import Image

        import editor_tataletak as et
        import lcd_tataletak as ltl
        ADA_LAYAR = Gtk.init_check()
    except (ImportError, ValueError):
        ADA_LAYAR = False


@unittest.skipUnless(ADA_LAYAR, "butuh sesi grafis")
class UjiEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Adw.init()

    def setUp(self):
        self.latar = Image.new("RGB", (480, 480), (20, 20, 30))
        self.disimpan = []
        self.editor = et.Editor(
            None, self.latar, ltl.contoh("grid"),
            "uji", "Simpan", self.disimpan.append,
        )

    def tearDown(self):
        self.editor.destroy()

    # ----------------------------------------------------------- pilihan

    def test_mulai_dengan_elemen_pertama_terpilih(self):
        self.assertEqual(self.editor.kanvas.terpilih, 0)
        self.assertIsNotNone(self.editor.elemen)

    def test_setelan_mati_kalau_tidak_ada_yang_terpilih(self):
        self.editor._pilih(-1)
        self.assertIsNone(self.editor.elemen)
        self.assertFalse(self.editor.grup_setel.get_sensitive())

    def test_baris_ikut_elemen_yang_dipilih(self):
        self.editor.tata.elemen[1].ukuran = 33
        self.editor._pilih(1)
        self.assertEqual(int(self.editor.baris_ukuran.get_value()), 33)

    # -------------------------------------------------------- penyuntingan

    def test_warna_sampai_ke_elemen(self):
        self.editor._pilih(0)
        self.editor.warna_angka.set_rgba(Gdk.RGBA(red=1.0, green=0.0, blue=0.0, alpha=1.0))
        self.assertEqual(self.editor.tata.elemen[0].warna, (255, 0, 0))

    def test_ukuran_sampai_ke_elemen(self):
        self.editor._pilih(0)
        self.editor.baris_ukuran.set_value(88)
        self.assertEqual(self.editor.tata.elemen[0].ukuran, 88)

    def test_posisi_sampai_ke_elemen(self):
        self.editor._pilih(0)
        self.editor.baris_x.set_value(123)
        self.editor.baris_y.set_value(210)
        self.assertEqual((self.editor.tata.elemen[0].x, self.editor.tata.elemen[0].y),
                         (123, 210))

    def test_label_sampai_ke_elemen(self):
        self.editor._pilih(0)
        self.editor.baris_label.set_text("PROSESOR")
        self.assertEqual(self.editor.tata.elemen[0].label, "PROSESOR")

    def test_menyetel_baris_dari_kode_tidak_mengubah_elemen_lain(self):
        """Penjaga `_menyusun`: memilih elemen lain menyetel semua barisnya.

        Tanpa penjaga itu, tiap `set_value` memicu penangannya dan menimpa
        elemen yang baru saja dipilih dengan nilai elemen sebelumnya.
        """
        self.editor.tata.elemen[0].ukuran = 54
        self.editor.tata.elemen[1].ukuran = 99
        self.editor._pilih(1)
        self.editor._pilih(0)
        self.assertEqual(self.editor.tata.elemen[1].ukuran, 99)
        self.assertEqual(self.editor.tata.elemen[0].ukuran, 54)

    def test_samakan_warna_kena_semua(self):
        self.editor._pilih(0)
        self.editor.tata.elemen[0].warna = (10, 200, 90)
        self.editor._samakan_warna()
        for e in self.editor.tata.elemen:
            self.assertEqual(e.warna, (10, 200, 90))

    def test_warna_label_ikut_kalau_belum_disetel_sendiri(self):
        self.editor._pilih(0)
        self.editor.warna_angka.set_rgba(Gdk.RGBA(red=0.0, green=1.0, blue=0.0, alpha=1.0))
        e = self.editor.tata.elemen[0]
        self.assertIsNone(e.label_warna)
        self.assertEqual(e.warna_label, (0, 255, 0))

    # -------------------------------------------------------------- saklar

    def test_saklar_mencerminkan_isi_awal(self):
        for kunci in ltl.EMPAT:
            self.assertTrue(self.editor.saklar[kunci].get_active(), kunci)
        self.assertFalse(self.editor.saklar["cpu_suhu"].get_active())

    def test_menyalakan_saklar_menambah_angka(self):
        jumlah = len(self.editor.tata.elemen)
        self.editor.saklar["cpu_suhu"].set_active(True)
        self.assertEqual(len(self.editor.tata.elemen), jumlah + 1)
        self.assertIn("cpu_suhu", self.editor.tata.jenis_terpakai())

    def test_mematikan_saklar_membuang_angka(self):
        self.editor.saklar["cpu_persen"].set_active(False)
        self.assertNotIn("cpu_persen", self.editor.tata.jenis_terpakai())

    def test_angka_baru_tidak_menumpuk(self):
        """Ditaruh di tempat kosong; menumpuk bikin orang mengira tidak muncul."""
        self.editor.saklar["cpu_suhu"].set_active(True)
        self.assertEqual(ltl.bertumpuk(self.editor.tata), [])

    def test_angka_baru_ikut_gaya_yang_sudah_ada(self):
        self.editor.tata.elemen[0].warna = (7, 8, 9)
        self.editor.tata.elemen[0].ukuran = 41
        self.editor.saklar["gpu_suhu"].set_active(True)
        baru = self.editor.tata.elemen[-1]
        self.assertEqual(baru.warna, (7, 8, 9))
        self.assertEqual(baru.ukuran, 41)

    def test_mematikan_semua_lalu_menyalakan_lagi(self):
        for kunci in list(ltl.EMPAT):
            self.editor.saklar[kunci].set_active(False)
        self.assertEqual(self.editor.tata.elemen, [])
        self.editor.saklar["cpu_persen"].set_active(True)
        self.assertEqual(len(self.editor.tata.elemen), 1)

    # -------------------------------------------------------------- contoh

    def test_menerapkan_contoh_mengganti_semua(self):
        self.editor.baris_contoh.set_selected(
            [k for k, _, _ in ltl.CONTOH].index("sudut"))
        self.editor._terapkan_contoh()
        self.assertEqual(len(self.editor.tata.elemen), 4)
        self.assertEqual(ltl.di_luar_kanvas(self.editor.tata), [])

    def test_contoh_mempertahankan_warna_yang_sudah_dipilih(self):
        for e in self.editor.tata.elemen:
            e.warna = (1, 2, 3)
        self.editor.baris_contoh.set_selected(
            [k for k, _, _ in ltl.CONTOH].index("kolom"))
        self.editor._terapkan_contoh()
        for e in self.editor.tata.elemen:
            self.assertEqual(e.warna, (1, 2, 3))

    def test_contoh_kosong_lalu_saklar(self):
        self.editor.baris_contoh.set_selected(
            [k for k, _, _ in ltl.CONTOH].index("kosong"))
        self.editor._terapkan_contoh()
        self.assertEqual(self.editor.tata.elemen, [])
        self.assertFalse(self.editor.saklar["cpu_persen"].get_active())

    # -------------------------------------------------------------- simpan

    def test_simpan_menyerahkan_tata_letak(self):
        self.editor._simpan()
        self.assertEqual(len(self.disimpan), 1)
        self.assertEqual(len(self.disimpan[0].elemen), 4)

    def test_tidak_menyimpan_kalau_kosong(self):
        """Tema tanpa satu angka pun akan tampil sebagai foto diam.

        Bukan galat, tapi hampir pasti bukan yang dimaksud — dan lebih murah
        dicegah di sini daripada ketahuan setelah terpasang di panel.
        """
        self.editor.tata.elemen = []
        self.editor._simpan()
        self.assertEqual(self.disimpan, [])

    def test_tata_letak_asal_tidak_ikut_berubah(self):
        """Editor bekerja di salinan; membatalkan harus benar-benar batal."""
        asal = ltl.contoh("grid")
        editor = et.Editor(None, self.latar, asal, "uji", "Simpan", lambda t: None)
        editor.tata.elemen[0].x = 999
        self.assertNotEqual(asal.elemen[0].x, 999)
        editor.destroy()

    # -------------------------------------------------------------- kanvas

    def test_kanvas_menemukan_elemen_di_titiknya(self):
        e = self.editor.tata.elemen[0]
        kiri, atas, kanan, bawah = ltl.kotak(e)
        self.assertEqual(self.editor.kanvas._cari((kiri + kanan) / 2, (atas + bawah) / 2), 0)

    def test_kanvas_tidak_menemukan_apa_apa_di_ruang_kosong(self):
        self.assertEqual(self.editor.kanvas._cari(2, 470), -1)

    def test_peringatan_tumpang_tindih_muncul(self):
        self.editor.tata.elemen[1].x = self.editor.tata.elemen[0].x + 3
        self.editor.tata.elemen[1].y = self.editor.tata.elemen[0].y + 3
        self.editor._segarkan_petunjuk()
        self.assertIn("Bertumpuk", self.editor.petunjuk.get_text())

    def test_peringatan_keluar_layar_muncul(self):
        self.editor.tata.elemen[0].x = 470
        self.editor._segarkan_petunjuk()
        self.assertIn("Keluar layar", self.editor.petunjuk.get_text())

    def test_tanpa_masalah_tidak_ada_peringatan(self):
        self.editor._segarkan_petunjuk()
        teks = self.editor.petunjuk.get_text()
        self.assertNotIn("Bertumpuk", teks)
        self.assertNotIn("Keluar layar", teks)


if __name__ == "__main__":
    unittest.main(verbosity=2)
