"""Uji untuk lcd_tema — jalankan: python3 uji_lcd_tema.py

Semua uji memakai direktori sementara, jadi tidak pernah menyentuh klon
upstream maupun tema sungguhan di ~/.local/share/aio-lcd.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

import lcd_tataletak as ltl
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




class UjiDariTataLetak(Dasar):
    """Tema yang dibuat dari tata letak sendiri, bukan dari tema contoh."""

    def setUp(self):
        super().setUp()
        self.gambar = Path(self.tmp.name) / "foto.png"
        Image.new("RGB", (900, 600), (80, 120, 200)).save(self.gambar)
        self.tata = ltl.contoh("grid")

    def test_berkasnya_lengkap(self):
        d = self.pustaka.buat_dari_tata_letak(self.gambar, "fotoku", self.tata)
        for berkas in ("theme.yaml", "background.png", "preview.png"):
            self.assertTrue((d / berkas).is_file(), berkas)

    def test_latar_dipotong_seukuran_kanvas(self):
        d = self.pustaka.buat_dari_tata_letak(self.gambar, "fotoku", self.tata)
        with Image.open(d / "background.png") as im:
            self.assertEqual(im.size, self.tata.kanvas)

    def test_tertaut_ke_res_themes(self):
        self.pustaka.buat_dari_tata_letak(self.gambar, "fotoku", self.tata)
        self.assertTrue((self.res / "fotoku").is_symlink())
        self.assertIn("fotoku", self.pustaka.daftar_pengguna())

    def test_bisa_dibuka_lagi_di_editor(self):
        """Inti dari cara ini: temanya bisa disunting lagi.

        Tema hasil `buat_dari_gambar` tidak bisa, karena theme.yaml-nya milik
        tema contoh dan memuat bagian yang tidak dimodelkan editor.
        """
        d = self.pustaka.buat_dari_tata_letak(self.gambar, "fotoku", self.tata)
        balik = ltl.baca_tema(d)
        self.assertEqual(len(balik.elemen), len(self.tata.elemen))

    def test_tema_donor_ikut_bisa_dibuka_kalau_isinya_muat(self):
        """Yang menentukan bukan siapa penulisnya, tapi apa isinya.

        Tema yang tata letaknya dulu dipinjam dari tema contoh tetap bisa
        disetel selama seluruh isinya muat di model editor — menolaknya cuma
        karena baris `author:`-nya berbeda berarti temanya harus dibuat ulang
        dari awal tanpa alasan.
        """
        d = self.pustaka.buat_dari_gambar(self.gambar, "lama", donor="26")
        self.assertEqual(ltl.baca_tema(d).elemen, [])   # tema contoh di uji ini tanpa STATS

    def test_tema_donor_bergrafik_ditolak(self):
        """Grafik batang tidak dimodelkan editor, jadi menyimpannya akan
        membuangnya diam-diam — lebih baik ditolak di depan."""
        buat_tema(self.res, "bergrafik")
        (self.res / "bergrafik" / "theme.yaml").write_text(
            '---\nauthor: "@asli"\ndisplay:\n  DISPLAY_SIZE: 2.1"\n'
            'STATS:\n  CPU:\n    PERCENTAGE:\n      GRAPH:\n        SHOW: True\n',
            encoding="utf-8")
        d = self.pustaka.buat_dari_gambar(self.gambar, "lama2", donor="bergrafik")
        with self.assertRaises(ltl.GalatTataLetak):
            ltl.baca_tema(d)

    def test_nama_bentrok_ditolak(self):
        self.pustaka.buat_dari_tata_letak(self.gambar, "fotoku", self.tata)
        with self.assertRaises(lt.GalatTema):
            self.pustaka.buat_dari_tata_letak(self.gambar, "fotoku", self.tata)

    def test_gambar_tidak_ada(self):
        with self.assertRaises(lt.GalatTema):
            self.pustaka.buat_dari_tata_letak(Path("/tidak/ada.png"), "x", self.tata)

    def test_gagal_tidak_meninggalkan_sisa(self):
        with self.assertRaises(lt.GalatTema):
            self.pustaka.buat_dari_tata_letak(Path("/tidak/ada.png"), "x", self.tata)
        self.assertFalse((self.res / "x").exists())
        self.assertFalse((self.data / "x").exists())


class UjiBersihkanUkuran(unittest.TestCase):
    """Penjaga-penjaga `hapus_tema_ukuran_lain`.

    Ini satu-satunya operasi yang menghapus berkas milik upstream, jadi tiap
    hal yang tidak boleh tersentuh punya ujinya sendiri.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        akar = Path(self.tmp.name)
        self.res = akar / "res_themes"
        self.data = akar / "data_themes"
        self.res.mkdir()
        self.data.mkdir()

        buat_tema(self.res, "26", ukuran='2.1"')
        buat_tema(self.res, "45", ukuran='2.1"')
        buat_tema(self.res, "BigClock", ukuran='3.5"')
        buat_tema(self.res, "5inchTheme2", ukuran='5"')
        buat_tema(self.res, "TanpaUkuran")
        # Tema tanpa kunci DISPLAY_SIZE dianggap 3.5" oleh upstream.
        (self.res / "TanpaUkuran" / "theme.yaml").write_text(
            '---\nauthor: "@asli"\ndisplay:\n  DISPLAY_ORIENTATION: portrait\n',
            encoding="utf-8")

        # Berkas-berkas yang memang ada di res/themes dan bukan tema.
        (self.res / "default.yaml").write_text("STATS:\n  CPU:\n", encoding="utf-8")
        (self.res / "theme_example.yaml").write_text("---\n", encoding="utf-8")
        (self.res / "README.md").write_text("# tema\n", encoding="utf-8")
        (self.res / "scale_theme.py").write_text("pass\n", encoding="utf-8")

        # Direktori yang bukan tema (tidak ada theme.yaml).
        (self.res / "bukan-tema").mkdir()
        (self.res / "bukan-tema" / "catatan.txt").write_text("x", encoding="utf-8")

        # Tema buatan sendiri: direktori data + symlink, ukurannya sengaja 5"
        # supaya ketahuan kalau symlink ikut tersapu karena ukurannya.
        buat_tema(self.data, "punyaku", ukuran='5"')
        (self.res / "punyaku").symlink_to(self.data / "punyaku", target_is_directory=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _bersihkan(self, **kw):
        return lt.hapus_tema_ukuran_lain('2.1"', akar=self.res, **kw)

    def test_menghapus_yang_ukurannya_lain(self):
        kena = self._bersihkan()
        self.assertEqual(sorted(kena), ["5inchTheme2", "BigClock", "TanpaUkuran"])
        for nama in kena:
            self.assertFalse((self.res / nama).exists(), nama)

    def test_menyisakan_yang_seukuran(self):
        self._bersihkan()
        self.assertTrue((self.res / "26").is_dir())
        self.assertTrue((self.res / "45").is_dir())

    def test_default_yaml_tidak_tersentuh(self):
        """default.yaml memuat bagian wajib yang ditempelkan ke SEMUA tema.

        Dia berkas, bukan direktori, dan menghapusnya merusak seluruh tema —
        bukan cuma satu.
        """
        self._bersihkan()
        self.assertTrue((self.res / "default.yaml").is_file())

    def test_berkas_lain_tidak_tersentuh(self):
        self._bersihkan()
        for nama in ("theme_example.yaml", "README.md", "scale_theme.py"):
            self.assertTrue((self.res / nama).is_file(), nama)

    def test_tema_buatan_sendiri_tidak_tersentuh(self):
        """Symlink dilewati tanpa melihat ukurannya sama sekali."""
        self._bersihkan()
        self.assertTrue((self.res / "punyaku").is_symlink())
        self.assertTrue((self.data / "punyaku").is_dir())

    def test_direktori_bukan_tema_tidak_tersentuh(self):
        self._bersihkan()
        self.assertTrue((self.res / "bukan-tema").is_dir())

    def test_yang_dilindungi_tidak_tersentuh(self):
        """Tema yang sedang terpasang tidak boleh hilang — service gagal memuat."""
        kena = self._bersihkan(lindungi={"BigClock"})
        self.assertNotIn("BigClock", kena)
        self.assertTrue((self.res / "BigClock").is_dir())

    def test_kering_tidak_menghapus_apa_pun(self):
        kena = self._bersihkan(kering=True)
        self.assertEqual(sorted(kena), ["5inchTheme2", "BigClock", "TanpaUkuran"])
        for nama in kena:
            self.assertTrue((self.res / nama).is_dir(), nama)

    def test_kering_dan_sungguhan_sepakat(self):
        self.assertEqual(self._bersihkan(kering=True), self._bersihkan())

    def test_dijalankan_dua_kali_aman(self):
        self._bersihkan()
        self.assertEqual(self._bersihkan(), [])

    def test_akar_tidak_ada(self):
        with self.assertRaises(lt.GalatTema):
            lt.hapus_tema_ukuran_lain('2.1"', akar=self.res / "tidak-ada")


if __name__ == "__main__":
    unittest.main(verbosity=2)
