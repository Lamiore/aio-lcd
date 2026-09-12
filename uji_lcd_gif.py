"""Uji untuk lcd_gif — jalankan: python3 uji_lcd_gif.py

Tidak menyentuh perangkat sama sekali; GIF-nya dibuat di direktori sementara.
"""

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import lcd_gif as lg


def buat_gif(jalur: Path, n=4, ukuran=(320, 240), durasi_ms=100, mode="RGB"):
    bingkai = []
    for i in range(n):
        im = Image.new(mode, ukuran, (i * 40 % 256, 80, 160))
        bingkai.append(im)
    bingkai[0].save(
        jalur, save_all=True, append_images=bingkai[1:], duration=durasi_ms, loop=0
    )
    return jalur


class UjiPerkiraanFps(unittest.TestCase):
    def test_cocok_dengan_angka_terukur(self):
        # Yang diuji: rumusnya menghasilkan kembali angka yang diukur di
        # perangkat, bukan sekadar mengembalikan sesuatu.
        self.assertAlmostEqual(lg.perkiraan_fps(480, 480), 2.89, delta=0.15)
        self.assertAlmostEqual(lg.perkiraan_fps(240, 240), 11.6, delta=0.6)

    def test_sisi_setengah_bikin_fps_empat_kali(self):
        self.assertAlmostEqual(
            lg.perkiraan_fps(240, 240) / lg.perkiraan_fps(480, 480), 4.0, delta=0.01
        )

    def test_tidak_pernah_bagi_nol(self):
        self.assertGreater(lg.perkiraan_fps(0, 0), 0)


class UjiMuatBingkai(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_semua_bingkai_terbaca(self):
        g = buat_gif(self.dir / "a.gif", n=5)
        self.assertEqual(len(lg.muat_bingkai(g, 240)), 5)

    def test_bingkai_sudah_dipotong_ke_ukuran_tayang(self):
        g = buat_gif(self.dir / "b.gif", ukuran=(640, 200))
        for b in lg.muat_bingkai(g, 240):
            self.assertEqual(b.gambar.size, (240, 240))
            self.assertEqual(b.gambar.mode, "RGB")

    def test_durasi_dibaca_dari_gif(self):
        g = buat_gif(self.dir / "c.gif", durasi_ms=250)
        for b in lg.muat_bingkai(g, 160):
            self.assertAlmostEqual(b.durasi, 0.25, places=3)

    def test_durasi_nol_jatuh_ke_baku(self):
        g = buat_gif(self.dir / "d.gif", durasi_ms=0)
        self.assertAlmostEqual(lg.muat_bingkai(g, 160)[0].durasi, lg.DURASI_BAKU, places=3)

    def test_gif_transparan_tidak_bikin_galat(self):
        # GIF mode P dengan transparansi: jalur yang paling gampang patah.
        # Tiap bingkai harus beda WARNA, bukan cuma beda indeks palet: encoder
        # GIF membuang bingkai yang tampilannya sama persis dengan sebelumnya,
        # dan Image.new("P", color=n) memetakan semua indeks ke hitam di palet
        # baku — bingkainya kembar, lalu uji ini cuma mengukur perilaku encoder.
        b = [
            Image.new("RGB", (100, 100), (i * 80 + 20, 40, 200)).convert(
                "P", palette=Image.ADAPTIVE
            )
            for i in range(3)
        ]
        g = self.dir / "e.gif"
        b[0].save(g, save_all=True, append_images=b[1:], duration=80, transparency=0)
        bingkai = lg.muat_bingkai(g, 120)
        self.assertEqual(len(bingkai), 3)
        self.assertEqual(bingkai[0].gambar.mode, "RGB")

    def test_gambar_diam_dianggap_satu_bingkai(self):
        p = self.dir / "diam.png"
        Image.new("RGB", (200, 200)).save(p)
        self.assertEqual(len(lg.muat_bingkai(p, 240)), 1)


class UjiFpsDiminta(unittest.TestCase):
    def test_rata_rata_dari_durasi(self):
        b = [lg.Bingkai(Image.new("RGB", (1, 1)), 0.1) for _ in range(10)]
        self.assertAlmostEqual(lg.fps_diminta(b), 10.0, places=3)

    def test_kosong_mengembalikan_nol(self):
        self.assertEqual(lg.fps_diminta([]), 0.0)


class UjiRingkasan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gif_pelan_di_area_kecil_disebut_mulus(self):
        g = buat_gif(self.dir / "pelan.gif", durasi_ms=200)  # 5 fps
        r = lg.ringkasan(g, 240)
        self.assertTrue(r["mulus"])
        self.assertAlmostEqual(r["fps_nyata"], 5.0, delta=0.1)

    def test_gif_cepat_layar_penuh_disebut_tidak_mulus(self):
        g = buat_gif(self.dir / "cepat.gif", durasi_ms=40)  # 25 fps
        r = lg.ringkasan(g, 480)
        self.assertFalse(r["mulus"], "25 fps di layar penuh tidak mungkin mulus")
        # Yang dilaporkan harus kemampuan panel, bukan maunya GIF.
        self.assertLess(r["fps_nyata"], 4.0)

    def test_jumlah_bingkai_dilaporkan(self):
        g = buat_gif(self.dir / "x.gif", n=7)
        self.assertEqual(lg.ringkasan(g, 240)["jumlah_bingkai"], 7)

    def test_ringkasan_tidak_ikut_meresize(self):
        # Ringkasan dipakai saat pengguna mengganti pilihan ukuran, jadi harus
        # murah: durasinya saja, tanpa menyentuh piksel.
        g = buat_gif(self.dir / "besar.gif", n=6, ukuran=(1280, 720))
        self.assertEqual(lg.ringkasan(g, 240)["jumlah_bingkai"], 6)

    def test_durasi_sama_dengan_yang_dipakai_muat_bingkai(self):
        g = buat_gif(self.dir / "sama.gif", n=4, durasi_ms=120)
        dari_durasi = lg.baca_durasi(g)
        dari_bingkai = [b.durasi for b in lg.muat_bingkai(g, 120)]
        self.assertEqual(dari_durasi, dari_bingkai)


class UjiDelta(unittest.TestCase):
    """Pengiriman hanya bagian yang berubah — inti dari fps di layar penuh."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _latar_diam(self, n=8, S=240):
        """Latar tetap, satu kotak kecil berpindah — watak GIF yang umum."""
        b = []
        for i in range(n):
            im = Image.new("RGB", (S, S), (10, 12, 30))
            d = ImageDraw.Draw(im)
            x = 10 + i * 12
            d.rectangle([x, 10, x + 20, 30], fill=(200, 80, 60))
            b.append(im)
        g = self.dir / "diam.gif"
        b[0].save(g, save_all=True, append_images=b[1:], duration=100, loop=0)
        return g

    def _berubah_total(self, n=8, S=240):
        b = [Image.new("RGB", (S, S), (i * 30 % 256, 60, 200)) for i in range(n)]
        g = self.dir / "penuh.gif"
        b[0].save(g, save_all=True, append_images=b[1:], duration=100, loop=0)
        return g

    def test_latar_diam_menghemat_banyak(self):
        bingkai = lg.muat_bingkai(self._latar_diam(), 240)
        p = lg.susun_perintah(bingkai, 0, 0)
        self.assertGreater(lg.hemat(p, 240), 0.5, "latar diam seharusnya hemat besar")

    def test_berubah_total_tidak_menghemat(self):
        bingkai = lg.muat_bingkai(self._berubah_total(), 240)
        p = lg.susun_perintah(bingkai, 0, 0)
        self.assertLess(lg.hemat(p, 240), 0.05)

    def test_potongan_digeser_sesuai_offsetnya(self):
        bingkai = lg.muat_bingkai(self._latar_diam(), 240)
        p = lg.susun_perintah(bingkai, 120, 120)
        kecil = [q for q in p if q.gambar is not None and q.gambar.width < 240]
        self.assertTrue(kecil, "tidak ada potongan sama sekali")
        for q in kecil:
            # Potongan harus ditempatkan relatif terhadap posisi bingkai,
            # kalau tidak gambarnya mendarat di tempat yang salah.
            self.assertGreaterEqual(q.x, 120)
            self.assertGreaterEqual(q.y, 120)

    def test_bingkai_kembar_tidak_dikirim(self):
        im = Image.new("RGB", (120, 120), (5, 5, 5))
        b = [lg.Bingkai(im, 0.1), lg.Bingkai(im, 0.1)]
        p = lg.susun_perintah(b, 0, 0)
        self.assertTrue(all(q.gambar is None for q in p), "bingkai identik tidak perlu dikirim")

    def test_satu_bingkai_dikirim_utuh(self):
        im = Image.new("RGB", (120, 120), (5, 5, 5))
        p = lg.susun_perintah([lg.Bingkai(im, 0.1)], 7, 9)
        self.assertEqual(len(p), 1)
        self.assertIsNotNone(p[0].gambar)
        self.assertEqual((p[0].x, p[0].y), (7, 9))

    def test_rasio_berubah_membedakan_dua_watak(self):
        self.assertLess(lg.rasio_berubah(self._latar_diam()), 0.3)
        self.assertGreater(lg.rasio_berubah(self._berubah_total()), 0.9)

    def test_ringkasan_ikut_memperhitungkan_delta(self):
        # Tanpa ini, GIF berlatar diam dilaporkan jauh lebih lambat daripada
        # kenyataannya dan orang memilih ukuran kecil tanpa perlu.
        r = lg.ringkasan(self._latar_diam(), 480)
        self.assertGreater(r["fps_sanggup"], r["fps_sanggup_penuh"] * 2)


class UjiPosisi(unittest.TestCase):
    def test_layar_penuh_di_pojok(self):
        self.assertEqual(lg.posisi_tengah(480), (0, 0))

    def test_lebih_kecil_ditengahkan(self):
        self.assertEqual(lg.posisi_tengah(240), (120, 120))

    def test_lebih_besar_dari_kanvas_tidak_negatif(self):
        self.assertEqual(lg.posisi_tengah(600), (0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
