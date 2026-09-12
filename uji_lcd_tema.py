"""Uji untuk lcd_tema — jalankan: python3 uji_lcd_tema.py

Semua uji memakai direktori sementara, jadi tidak pernah menyentuh klon
upstream maupun tema sungguhan di ~/.local/share/aio-lcd.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

import lcd_tema as lt


def buat_tema(akar: Path, nama: str, ukuran='2.1"', latar=(480, 480)):
    d = akar / nama
    d.mkdir(parents=True)
    (d / "theme.yaml").write_text(
        f'---\nauthor: "@asli"\ndisplay:\n  DISPLAY_SIZE: {ukuran}\n'
        f'  DISPLAY_ORIENTATION: portrait\n',
        encoding="utf-8",
    )
    if latar:
        Image.new("RGB", latar, (10, 20, 30)).save(d / "background.png")
        Image.new("RGB", latar, (10, 20, 30)).save(d / "preview.png")
    return d


class Dasar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        akar = Path(self.tmp.name)
        self.res = akar / "res_themes"
        self.data = akar / "data_themes"
        self.res.mkdir()
        self.data.mkdir()
        buat_tema(self.res, "26")
        self.pustaka = lt.PustakaTema(akar_tema=self.res, dir_pengguna=self.data)

    def tearDown(self):
        self.tmp.cleanup()


class UjiNama(unittest.TestCase):
    def test_nama_wajar_lolos(self):
        for n in ("punyaku", "Tema 1", "a.b-c_d", "26b"):
            self.assertEqual(lt.periksa_nama(n), n)

    def test_nama_berbahaya_ditolak(self):
        for n in ("../lolos", "a/b", "", " ", "-awal", "x" * 41, "a\nb"):
            with self.assertRaises(lt.GalatTema, msg=f"{n!r} seharusnya ditolak"):
                lt.periksa_nama(n)

    def test_nama_milik_upstream_ditolak(self):
        with self.assertRaises(lt.GalatTema):
            lt.periksa_nama("default")


class UjiDuplikat(Dasar):
    def test_hasilnya_symlink_dan_terdata(self):
        self.pustaka.duplikat("26", "punyaku")
        self.assertTrue(self.pustaka.ada("punyaku"))
        self.assertTrue(self.pustaka.milik_pengguna("punyaku"))
        self.assertTrue((self.data / "punyaku" / "theme.yaml").is_file())
        self.assertEqual(self.pustaka.daftar_pengguna(), ["punyaku"])

    def test_asli_tidak_jadi_milik_pengguna(self):
        self.pustaka.duplikat("26", "punyaku")
        self.assertFalse(self.pustaka.milik_pengguna("26"))

    def test_isinya_ikut_tersalin(self):
        self.pustaka.duplikat("26", "punyaku")
        self.assertTrue((self.res / "punyaku" / "background.png").is_file())

    def test_nama_bentrok_ditolak(self):
        self.pustaka.duplikat("26", "punyaku")
        with self.assertRaises(lt.GalatTema):
            self.pustaka.duplikat("26", "punyaku")

    def test_sumber_bukan_tema_ditolak(self):
        (self.res / "kosong").mkdir()
        with self.assertRaises(lt.GalatTema):
            self.pustaka.duplikat("kosong", "punyaku")

    def test_menduplikat_tema_buatan_sendiri(self):
        self.pustaka.duplikat("26", "satu")
        self.pustaka.duplikat("satu", "dua")
        self.assertTrue(self.pustaka.milik_pengguna("dua"))
        # Hasilnya harus direktori sungguhan, bukan symlink berantai.
        self.assertTrue((self.data / "dua").is_dir())
        self.assertFalse((self.data / "dua").is_symlink())


class UjiDariGambar(Dasar):
    def setUp(self):
        super().setUp()
        self.gambar = Path(self.tmp.name) / "foto.jpg"
        Image.new("RGB", (1920, 1080), (200, 100, 50)).save(self.gambar)

    def test_latar_dipotong_ke_ukuran_kanvas(self):
        self.pustaka.buat_dari_gambar(self.gambar, "fotoku", donor="26")
        with Image.open(self.res / "fotoku" / "background.png") as im:
            self.assertEqual(im.size, (480, 480))

    def test_preview_ikut_dibuat(self):
        self.pustaka.buat_dari_gambar(self.gambar, "fotoku", donor="26")
        self.assertTrue((self.res / "fotoku" / "preview.png").is_file())

    def test_ukuran_kanvas_ikut_donor_bukan_tebakan(self):
        buat_tema(self.res, "besar", ukuran='5"', latar=(800, 480))
        self.pustaka.buat_dari_gambar(self.gambar, "fotobesar", donor="besar")
        with Image.open(self.res / "fotobesar" / "background.png") as im:
            self.assertEqual(im.size, (800, 480))

    def test_tata_letak_donor_terbawa(self):
        self.pustaka.buat_dari_gambar(self.gambar, "fotoku", donor="26")
        teks = (self.res / "fotoku" / "theme.yaml").read_text()
        self.assertIn('DISPLAY_SIZE: 2.1"', teks)
        self.assertIn("DISPLAY_ORIENTATION: portrait", teks)

    def test_penulis_ditandai(self):
        self.pustaka.buat_dari_gambar(self.gambar, "fotoku", donor="26")
        teks = (self.res / "fotoku" / "theme.yaml").read_text()
        self.assertIn("gambar sendiri", teks)
        self.assertNotIn("@asli", teks)

    def test_gambar_tidak_ada_ditolak(self):
        with self.assertRaises(lt.GalatTema):
            self.pustaka.buat_dari_gambar(Path("/tidak/ada.png"), "x", donor="26")

    def test_gagal_tidak_meninggalkan_sisa(self):
        with self.assertRaises(lt.GalatTema):
            self.pustaka.buat_dari_gambar(Path("/tidak/ada.png"), "x", donor="26")
        self.assertFalse(self.pustaka.ada("x"))
        self.assertFalse((self.data / "x").exists())


class UjiPotongGambar(unittest.TestCase):
    def test_gambar_lebar_dipotong_kiri_kanan(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = Path(tmp) / "l.png"
            Image.new("RGB", (1000, 500)).save(g)
            hasil = lt.muat_dan_pas(g, (480, 480))
            self.assertEqual(hasil.size, (480, 480))

    def test_gambar_tinggi_dipotong_atas_bawah(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = Path(tmp) / "t.png"
            Image.new("RGB", (500, 1000)).save(g)
            self.assertEqual(lt.muat_dan_pas(g, (480, 480)).size, (480, 480))

    def test_gambar_lebih_kecil_diperbesar(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = Path(tmp) / "k.png"
            Image.new("RGB", (64, 64)).save(g)
            self.assertEqual(lt.muat_dan_pas(g, (480, 480)).size, (480, 480))


class UjiImpor(Dasar):
    def test_impor_folder(self):
        luar = Path(self.tmp.name) / "luar"
        buat_tema(luar.parent, "luar")
        self.pustaka.impor(luar)
        self.assertTrue(self.pustaka.milik_pengguna("luar"))

    def test_impor_zip_datar(self):
        luar = buat_tema(Path(self.tmp.name) / "bahan", "ztema")
        z = Path(self.tmp.name) / "datar.zip"
        with zipfile.ZipFile(z, "w") as f:
            for p in luar.iterdir():
                f.write(p, p.name)
        self.pustaka.impor(z, nama_baru="daridatar")
        self.assertTrue(self.pustaka.milik_pengguna("daridatar"))

    def test_impor_zip_berbungkus_folder(self):
        luar = buat_tema(Path(self.tmp.name) / "bahan2", "ztema")
        z = Path(self.tmp.name) / "bungkus.zip"
        with zipfile.ZipFile(z, "w") as f:
            for p in luar.iterdir():
                f.write(p, f"ztema/{p.name}")
        self.pustaka.impor(z)
        self.assertTrue(self.pustaka.milik_pengguna("ztema"))

    def test_zip_tanpa_theme_yaml_ditolak(self):
        z = Path(self.tmp.name) / "bukan.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("catatan.txt", "halo")
        with self.assertRaises(lt.GalatTema):
            self.pustaka.impor(z)

    def test_zip_slip_ditolak(self):
        # Zip yang berisi jalur ../ akan menulis di luar direktori tujuan
        # kalau diekstrak mentah-mentah.
        z = Path(self.tmp.name) / "jahat.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("../../kena.txt", "x")
            f.writestr("theme.yaml", "display: {}")
        with self.assertRaises(lt.GalatTema) as k:
            self.pustaka.impor(z)
        self.assertIn("berbahaya", str(k.exception))

    def test_sumber_tidak_ada_ditolak(self):
        with self.assertRaises(lt.GalatTema):
            self.pustaka.impor(Path("/tidak/ada"))


class UjiHapus(Dasar):
    def test_hapus_tema_sendiri(self):
        self.pustaka.duplikat("26", "punyaku")
        self.pustaka.hapus("punyaku")
        self.assertFalse(self.pustaka.ada("punyaku"))
        self.assertFalse((self.data / "punyaku").exists())

    def test_tema_bawaan_tidak_bisa_dihapus(self):
        with self.assertRaises(lt.GalatTema):
            self.pustaka.hapus("26")
        self.assertTrue(self.pustaka.ada("26"), "tema bawaan malah hilang")

    def test_hapus_yang_tidak_ada(self):
        with self.assertRaises(lt.GalatTema):
            self.pustaka.hapus("hantu")


class UjiSegarkanTautan(Dasar):
    def test_symlink_dipasang_ulang_setelah_upstream_diklon_ulang(self):
        self.pustaka.duplikat("26", "punyaku")
        # Tiru klon ulang upstream: res/themes baru, isinya cuma tema bawaan.
        (self.res / "punyaku").unlink()
        self.assertFalse(self.pustaka.ada("punyaku"))

        dipasang = self.pustaka.segarkan_tautan()
        self.assertEqual(dipasang, ["punyaku"])
        self.assertTrue(self.pustaka.milik_pengguna("punyaku"))

    def test_folder_data_tanpa_theme_yaml_dilewati(self):
        (self.data / "sampah").mkdir()
        self.assertEqual(self.pustaka.segarkan_tautan(), [])


class UjiUkuranTema(Dasar):
    def test_membaca_display_size(self):
        self.assertEqual(lt.ukuran_tema(self.res / "26"), '2.1"')

    def test_tanpa_berkas_mengembalikan_kosong(self):
        self.assertEqual(lt.ukuran_tema(self.res / "hantu"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
