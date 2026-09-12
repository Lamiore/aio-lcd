"""Uji untuk lcd_konfig — jalankan: python3 uji_lcd_konfig.py

Yang diuji cuma logika murni (baca/tulis config, pendataan tema). Bagian
systemd tidak diuji di sini: dia butuh service sungguhan dan layar sungguhan,
jadi buktinya datang dari menjalankannya, bukan dari uji.
"""

import tempfile
import unittest
from pathlib import Path

import lcd_konfig as lk

# Cuplikan yang meniru bentuk asli config.yaml upstream: bersarang, penuh
# komentar, dan punya baris yang sengaja dikomentari.
CONTOH = """\
config:
  # Set your COM port e.g. COM3 for Windows, /dev/ttyACM0 for Linux...
  # COM_PORT: "/dev/ttyACM0"
  # COM_PORT: "COM3"
  COM_PORT: "AUTO"

  # Theme to use (located in res/themes)
  THEME: "26"

display:
  # Display revision
  REVISION: C

  # Display reverse: true/false
  DISPLAY_REVERSE: true

  BRIGHTNESS: 20
"""


class UjiBacaNilai(unittest.TestCase):
    def test_baca_nilai_biasa(self):
        self.assertEqual(lk.baca_nilai(CONTOH, "THEME"), '"26"')
        self.assertEqual(lk.baca_nilai(CONTOH, "REVISION"), "C")
        self.assertEqual(lk.baca_nilai(CONTOH, "BRIGHTNESS"), "20")

    def test_baris_komentar_tidak_dihitung(self):
        # COM_PORT muncul 3x, tapi dua di antaranya komentar. Kalau penyaringan
        # komentar rusak, ini melempar "muncul 3x" — itulah gunanya uji ini.
        self.assertEqual(lk.baca_nilai(CONTOH, "COM_PORT"), '"AUTO"')

    def test_kunci_tidak_ada(self):
        with self.assertRaises(lk.GalatKonfig):
            lk.baca_nilai(CONTOH, "TIDAK_ADA")

    def test_kunci_ganda_ditolak(self):
        ganda = CONTOH + "\n  THEME: \"43\"\n"
        with self.assertRaises(lk.GalatKonfig):
            lk.baca_nilai(ganda, "THEME")


class UjiGantiNilai(unittest.TestCase):
    def test_mengganti_hanya_baris_itu(self):
        hasil = lk.ganti_nilai(CONTOH, "THEME", lk.kutip("43"))
        self.assertIn('THEME: "43"', hasil)
        self.assertNotIn('THEME: "26"', hasil)
        # Semua baris lain harus utuh: panjang berkas hanya boleh beda di satu baris.
        self.assertEqual(len(CONTOH.splitlines()), len(hasil.splitlines()))

    def test_komentar_dan_indentasi_terjaga(self):
        hasil = lk.ganti_nilai(CONTOH, "THEME", lk.kutip("43"))
        for baris in ("  # Theme to use (located in res/themes)",
                      '  # COM_PORT: "/dev/ttyACM0"',
                      "  # Display reverse: true/false"):
            self.assertIn(baris, hasil)
        self.assertIn('\n  THEME: "43"\n', hasil)

    def test_baris_komentar_tidak_ikut_diganti(self):
        hasil = lk.ganti_nilai(CONTOH, "COM_PORT", lk.kutip("/dev/ttyACM0"))
        self.assertIn('  # COM_PORT: "/dev/ttyACM0"', hasil)
        self.assertIn('  # COM_PORT: "COM3"', hasil)
        self.assertIn('  COM_PORT: "/dev/ttyACM0"', hasil)

    def test_boolean_ditulis_tanpa_kutip(self):
        hasil = lk.ganti_nilai(CONTOH, "DISPLAY_REVERSE", "false")
        self.assertIn("  DISPLAY_REVERSE: false", hasil)

    def test_kunci_ganda_membatalkan_penulisan(self):
        ganda = CONTOH + "\n  THEME: \"43\"\n"
        with self.assertRaises(lk.GalatKonfig):
            lk.ganti_nilai(ganda, "THEME", lk.kutip("44"))


class UjiKutip(unittest.TestCase):
    def test_nama_tema_angka_selalu_berkutip(self):
        # Inti masalahnya: tanpa kutip, YAML membaca 26 sebagai integer dan
        # upstream gagal dengan "Theme not found or contains errors!".
        self.assertEqual(lk.kutip("26"), '"26"')

    def test_kutip_di_dalam_nilai_dilarikan(self):
        self.assertEqual(lk.kutip('a"b'), '"a\\"b"')


class UjiKonfigBerkas(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.jalur = Path(self.dir.name) / "config.yaml"
        self.jalur.write_text(CONTOH, encoding="utf-8")
        self.konfig = lk.Konfig(self.jalur)

    def tearDown(self):
        self.dir.cleanup()

    def test_baca(self):
        self.assertEqual(self.konfig.tema, "26")
        self.assertTrue(self.konfig.terbalik)
        self.assertEqual(self.konfig.revisi, "C")

    def test_tulis_bolak_balik(self):
        self.konfig.tema = "45"
        self.assertEqual(self.konfig.tema, "45")
        self.konfig.terbalik = False
        self.assertFalse(self.konfig.terbalik)
        self.assertEqual(self.konfig.tema, "45", "menulis DISPLAY_REVERSE merusak THEME")

    def test_tidak_meninggalkan_berkas_sementara(self):
        self.konfig.tema = "30"
        sisa = [p.name for p in Path(self.dir.name).iterdir()]
        self.assertEqual(sisa, ["config.yaml"], f"ada berkas sisa: {sisa}")


class UjiDaftarTema(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.akar = Path(self.dir.name)
        self._buat("26", '2.1"', penulis="@seseorang", preview=True)
        self._buat("45", '2.1"', penulis="@seseorang", preview=False)
        self._buat("besar", '5"', penulis="@lain", preview=True)
        self._buat("tanpa_ukuran", None, penulis="", preview=False)
        (self.akar / "bukan_tema").mkdir()          # tak ada theme.yaml
        (self.akar / "default.yaml").write_text("x: 1")  # berkas, bukan folder

    def tearDown(self):
        self.dir.cleanup()

    def _buat(self, nama, ukuran, penulis, preview):
        d = self.akar / nama
        d.mkdir()
        baris = ["---", f'author: "{penulis}"', "display:"]
        if ukuran:
            baris.append(f'  DISPLAY_SIZE: {ukuran}')
        baris.append("  DISPLAY_ORIENTATION: portrait")
        (d / "theme.yaml").write_text("\n".join(baris) + "\n", encoding="utf-8")
        if preview:
            (d / "preview.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    def test_saring_menurut_ukuran(self):
        nama = [t.nama for t in lk.daftar_tema('2.1"', dir_tema=self.akar)]
        self.assertEqual(nama, ["26", "45"])

    def test_tanpa_display_size_dianggap_35(self):
        nama = [t.nama for t in lk.daftar_tema('3.5"', dir_tema=self.akar)]
        self.assertEqual(nama, ["tanpa_ukuran"])

    def test_folder_tanpa_theme_yaml_dilewati(self):
        semua = [t.nama for t in lk.daftar_tema(None, dir_tema=self.akar)]
        self.assertNotIn("bukan_tema", semua)
        self.assertNotIn("default.yaml", semua)

    def test_preview_hanya_kalau_berkasnya_ada(self):
        tema = {t.nama: t for t in lk.daftar_tema('2.1"', dir_tema=self.akar)}
        self.assertTrue(tema["26"].punya_preview)
        self.assertFalse(tema["45"].punya_preview)

    def test_direktori_tidak_ada_mengembalikan_kosong(self):
        self.assertEqual(lk.daftar_tema(dir_tema=self.akar / "hantu"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
