#!/usr/bin/env python3
"""Uji tata letak angka pemantauan dan pembersihan tema bawaan.

Yang paling banyak diuji di sini dua hal yang kegagalannya tidak berisik:

* **nama daun yang tidak seragam** — RAM dan disk memakai `PERCENT_TEXT`,
  sedangkan CPU dan GPU memakai `TEXT`. Menyusun jalur dengan menempelkan
  `"TEXT"` menghasilkan tema yang tetap dimuat upstream tanpa keluhan, cuma
  dua angkanya tidak pernah muncul;
* **pembersihan tema bawaan** — satu-satunya operasi yang menghapus berkas
  orang lain, jadi tiap penjaganya punya uji sendiri.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lcd_tataletak as ltl  # noqa: E402


def latar_uji(ukuran=(480, 480), warna=(30, 30, 40)) -> Image.Image:
    return Image.new("RGB", ukuran, warna)


class UjiJalur(unittest.TestCase):
    """Jalur tiap jenis harus cocok dengan yang dibaca upstream."""

    def test_daun_tidak_seragam(self):
        peta = {j.kunci: j.jalur for j in ltl.JENIS}
        self.assertEqual(peta["cpu_persen"], ("CPU", "PERCENTAGE", "TEXT"))
        self.assertEqual(peta["gpu_persen"], ("GPU", "PERCENTAGE", "TEXT"))
        # Dua ini yang gampang salah: daunnya PERCENT_TEXT, bukan TEXT.
        self.assertEqual(peta["ram_persen"], ("MEMORY", "VIRTUAL", "PERCENT_TEXT"))
        self.assertEqual(peta["disk_persen"], ("DISK", "USED", "PERCENT_TEXT"))

    def test_letak_interval_berbeda_per_perangkat(self):
        peta = {j.kunci: j.jalur_interval for j in ltl.JENIS}
        # CPU menyimpan INTERVAL di dalam tiap metrik…
        self.assertEqual(peta["cpu_persen"], ("CPU", "PERCENTAGE", "INTERVAL"))
        self.assertEqual(peta["cpu_suhu"], ("CPU", "TEMPERATURE", "INTERVAL"))
        # …sedangkan sisanya di tingkat perangkat.
        self.assertEqual(peta["gpu_persen"], ("GPU", "INTERVAL"))
        self.assertEqual(peta["gpu_suhu"], ("GPU", "INTERVAL"))
        self.assertEqual(peta["ram_persen"], ("MEMORY", "INTERVAL"))
        self.assertEqual(peta["disk_persen"], ("DISK", "INTERVAL"))
        self.assertEqual(peta["jam"], ("DATE", "INTERVAL"))

    def test_kunci_jenis_tidak_kembar(self):
        kunci = [j.kunci for j in ltl.JENIS]
        self.assertEqual(len(kunci), len(set(kunci)))
        jalur = [j.jalur for j in ltl.JENIS]
        self.assertEqual(len(jalur), len(set(jalur)))


class UjiBerkas(unittest.TestCase):
    """Isi theme.yaml yang dihasilkan."""

    def setUp(self):
        self.tata = ltl.contoh("grid")
        self.teks = ltl.ke_yaml(self.tata)
        self.data = yaml.safe_load(self.teks)

    def test_bisa_dibaca_yaml(self):
        self.assertIsInstance(self.data, dict)
        self.assertIn("STATS", self.data)

    def test_ukuran_layar_terbawa(self):
        # Nilainya mengandung tanda petik (2.1"), jadi gampang rusak waktu ditulis.
        self.assertEqual(self.data["display"]["DISPLAY_SIZE"], '2.1"')
        self.assertEqual(self.data["display"]["DISPLAY_ORIENTATION"], "portrait")

    def test_warna_berbentuk_r_g_b(self):
        """Upstream `parse_color` menerima teks "r, g, b" maupun senarai.

        Yang ditulis di sini bentuk teks, sama dengan semua tema bawaan.
        """
        simpul = self.data["STATS"]["CPU"]["PERCENTAGE"]["TEXT"]
        self.assertEqual(simpul["FONT_COLOR"], "235, 235, 235")
        self.assertEqual(len(simpul["FONT_COLOR"].split(",")), 3)

    def test_tiap_angka_punya_latar(self):
        """Tanpa BACKGROUND_IMAGE, panel menerima kotak warna solid.

        `lcd_comm.DisplayText` menggambar teks di atas salinan berkas itu lalu
        memotongnya; kalau tidak ada, yang dipakai BACKGROUND_COLOR yang putih.
        """
        for jenis in ltl.JENIS:
            simpul = self.data["STATS"]
            for bagian in jenis.jalur:
                if bagian not in simpul:
                    simpul = None
                    break
                simpul = simpul[bagian]
            if simpul is None:
                continue
            self.assertEqual(simpul.get("BACKGROUND_IMAGE"), "background.png",
                             f"{jenis.kunci} tidak memuat BACKGROUND_IMAGE")

    def test_label_juga_punya_latar(self):
        for nama, isi in (self.data.get("static_text") or {}).items():
            self.assertEqual(isi.get("BACKGROUND_IMAGE"), "background.png", nama)

    def test_interval_ditulis_di_tempat_yang_dibaca(self):
        """theme-editor upstream memutuskan menggambar dari INTERVAL > 0."""
        self.assertGreater(self.data["STATS"]["CPU"]["PERCENTAGE"]["INTERVAL"], 0)
        self.assertGreater(self.data["STATS"]["GPU"]["INTERVAL"], 0)
        self.assertGreater(self.data["STATS"]["MEMORY"]["INTERVAL"], 0)
        self.assertGreater(self.data["STATS"]["DISK"]["INTERVAL"], 0)

    def test_ram_dan_disk_benar_benar_muncul(self):
        ram = self.data["STATS"]["MEMORY"]["VIRTUAL"]["PERCENT_TEXT"]
        disk = self.data["STATS"]["DISK"]["USED"]["PERCENT_TEXT"]
        self.assertTrue(ram["SHOW"])
        self.assertTrue(disk["SHOW"])

    def test_latar_terdaftar_sebagai_gambar_statis(self):
        gambar = self.data["static_images"]["BACKGROUND"]
        self.assertEqual(gambar["PATH"], "background.png")
        self.assertEqual((gambar["WIDTH"], gambar["HEIGHT"]), (480, 480))


class UjiBolakBalik(unittest.TestCase):
    """Tata letak → theme.yaml → tata letak harus utuh."""

    def _bolak_balik(self, tata: ltl.TataLetak) -> ltl.TataLetak:
        return ltl.dari_yaml(yaml.safe_load(ltl.ke_yaml(tata)))

    def test_semua_contoh_utuh(self):
        for kunci, nama, _ in ltl.CONTOH:
            if kunci == "kosong":
                continue
            with self.subTest(contoh=kunci):
                asal = ltl.contoh(kunci)
                balik = self._bolak_balik(asal)
                self.assertEqual(len(balik.elemen), len(asal.elemen))
                # Dibandingkan menurut urutan gambar: berkas tema tidak
                # menyimpan urutan, jadi yang kembali selalu urutan katalog.
                for a, b in zip(ltl.urut(asal.elemen), ltl.urut(balik.elemen)):
                    self.assertEqual((a.jenis, a.x, a.y, a.ukuran, a.warna, a.font),
                                     (b.jenis, b.x, b.y, b.ukuran, b.warna, b.font))

    def test_label_dan_geserannya_utuh(self):
        tata = ltl.contoh("grid")
        tata.elemen[0].label = "PROSESOR"
        tata.elemen[0].label_geser = (-17, 41)
        tata.elemen[0].label_ukuran = 27
        balik = self._bolak_balik(tata)
        self.assertEqual(balik.elemen[0].label, "PROSESOR")
        self.assertEqual(balik.elemen[0].label_geser, (-17, 41))
        self.assertEqual(balik.elemen[0].label_ukuran, 27)

    def test_warna_label_sendiri_utuh(self):
        tata = ltl.contoh("grid")
        tata.elemen[0].label_warna = (200, 40, 40)
        balik = self._bolak_balik(tata)
        self.assertEqual(balik.elemen[0].label_warna, (200, 40, 40))

    def test_semua_jenis_bolak_balik(self):
        """Tiap jenis diuji sendiri — satu jalur salah cuma menghilangkan satu angka."""
        for jenis in ltl.JENIS:
            with self.subTest(jenis=jenis.kunci):
                tata = ltl.TataLetak(elemen=[ltl.Elemen(jenis=jenis.kunci, x=11, y=22)])
                balik = self._bolak_balik(tata)
                self.assertEqual(len(balik.elemen), 1, f"{jenis.kunci} hilang")
                self.assertEqual(balik.elemen[0].jenis, jenis.kunci)
                self.assertEqual((balik.elemen[0].x, balik.elemen[0].y), (11, 22))

    def test_tema_orang_lain_ditolak(self):
        """Tema tanpa penanda penulis tidak boleh dibuka editor.

        Tema bawaan memuat grafik, radial, dan jaringan yang tidak dimodelkan;
        membacanya lalu menyimpannya akan membuangnya diam-diam.
        """
        data = yaml.safe_load(ltl.ke_yaml(ltl.contoh("grid")))
        data["author"] = "@mathoudebine"
        data["STATS"]["NET"] = {"INTERVAL": 1,
                                "ETH": {"UPLOAD": {"TEXT": {"SHOW": True, "X": 0, "Y": 0}}}}
        self.assertFalse(ltl.milik_editor(data))
        self.assertFalse(ltl.dapat_disunting(data))
        with self.assertRaises(ltl.GalatTataLetak):
            ltl.dari_yaml(data)

    def test_tema_lama_yang_muat_tetap_bisa_dibuka(self):
        """Tema yang tata letaknya dulu dipinjam dari tema contoh.

        Kalau seluruh isinya kebetulan muat di model ini, tidak ada alasan
        menolaknya — menolak berarti temanya harus dibuat ulang dari awal cuma
        karena baris `author:`-nya berbeda.
        """
        data = yaml.safe_load(ltl.ke_yaml(ltl.contoh("grid")))
        data["author"] = "gambar sendiri, tata letak dari 26"
        self.assertFalse(ltl.milik_editor(data))
        self.assertEqual(ltl.unsur_hilang(data), [])
        self.assertTrue(ltl.dapat_disunting(data))
        self.assertEqual(len(ltl.dari_yaml(data).elemen), 4)

    def test_grafik_bikin_tema_ditolak(self):
        data = yaml.safe_load(ltl.ke_yaml(ltl.contoh("grid")))
        data["author"] = "@orang-lain"
        data["STATS"]["CPU"]["PERCENTAGE"]["GRAPH"] = {"SHOW": True, "X": 0, "Y": 0}
        self.assertIn("CPU.PERCENTAGE.GRAPH", ltl.unsur_hilang(data))
        self.assertFalse(ltl.dapat_disunting(data))
        with self.assertRaises(ltl.GalatTataLetak):
            ltl.dari_yaml(data)

    def test_unsur_yang_mati_tidak_dihitung_hilang(self):
        """`SHOW: False` memang tidak digambar, jadi tidak ada yang hilang."""
        data = yaml.safe_load(ltl.ke_yaml(ltl.contoh("grid")))
        data["author"] = "@orang-lain"
        data["STATS"]["CPU"]["PERCENTAGE"]["GRAPH"] = {"SHOW": False}
        self.assertEqual(ltl.unsur_hilang(data), [])

    def test_teks_tetap_asing_dihitung_hilang(self):
        data = yaml.safe_load(ltl.ke_yaml(ltl.contoh("grid")))
        data["author"] = "@orang-lain"
        data.setdefault("static_text", {})["JUDUL"] = {"TEXT": "halo", "X": 1, "Y": 1}
        self.assertIn("teks tetap JUDUL", ltl.unsur_hilang(data))

    def test_gambar_tambahan_dihitung_hilang(self):
        data = yaml.safe_load(ltl.ke_yaml(ltl.contoh("grid")))
        data["author"] = "@orang-lain"
        data["static_images"]["HIASAN"] = {"PATH": "x.png", "X": 0, "Y": 0}
        self.assertIn("gambar HIASAN", ltl.unsur_hilang(data))

    def test_label_bikinan_sendiri_tidak_dihitung_hilang(self):
        data = yaml.safe_load(ltl.ke_yaml(ltl.contoh("grid")))
        data["author"] = "@orang-lain"
        self.assertEqual(ltl.unsur_hilang(data), [])

    def test_penanda_penulis_terpasang(self):
        data = yaml.safe_load(ltl.ke_yaml(ltl.contoh("grid")))
        self.assertTrue(ltl.milik_editor(data))
        self.assertTrue(str(data["author"]).startswith(ltl.PENANDA))


class UjiTataLetak(unittest.TestCase):
    def test_contoh_muat_di_kanvas(self):
        for kunci, nama, _ in ltl.CONTOH:
            with self.subTest(contoh=kunci):
                self.assertEqual(ltl.di_luar_kanvas(ltl.contoh(kunci)), [],
                                 f"{nama} keluar layar")

    def test_contoh_tidak_bertumpuk(self):
        for kunci, nama, _ in ltl.CONTOH:
            with self.subTest(contoh=kunci):
                self.assertEqual(ltl.bertumpuk(ltl.contoh(kunci)), [],
                                 f"{nama} bertumpuk")

    def test_tumpang_tindih_terdeteksi(self):
        tata = ltl.TataLetak(elemen=[
            ltl.Elemen(jenis="cpu_persen", x=100, y=100),
            ltl.Elemen(jenis="gpu_persen", x=105, y=104),
        ])
        self.assertEqual(ltl.bertumpuk(tata), [(0, 1)])

    def test_keluar_kanvas_terdeteksi(self):
        tata = ltl.TataLetak(elemen=[ltl.Elemen(jenis="cpu_persen", x=470, y=100)])
        self.assertEqual(ltl.di_luar_kanvas(tata), [0])

    def test_contoh_tak_dikenal_ditolak(self):
        with self.assertRaises(ltl.GalatTataLetak):
            ltl.contoh("tidak-ada")

    def test_salin_tidak_berbagi_elemen(self):
        asal = ltl.contoh("grid")
        salinan = asal.salin()
        salinan.elemen[0].x = 999
        self.assertNotEqual(asal.elemen[0].x, 999)

    def test_warna_kontras_ikut_terang_latar(self):
        self.assertEqual(ltl.warna_kontras(latar_uji(warna=(250, 250, 250))), (25, 25, 25))
        self.assertEqual(ltl.warna_kontras(latar_uji(warna=(10, 10, 20))), (240, 240, 240))

    def test_render_menghasilkan_kanvas_seukuran(self):
        hasil = ltl.render(ltl.contoh("grid"), latar_uji())
        self.assertEqual(hasil.size, (480, 480))

    def test_render_benar_benar_menggambar(self):
        latar = latar_uji(warna=(0, 0, 0))
        hasil = ltl.render(ltl.contoh("grid"), latar)
        self.assertGreater(len(set(hasil.getdata())), 1, "tidak ada yang tergambar")


class UjiTulisTema(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        latar_uji().save(self.tmp / "background.png")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_menulis_yaml_dan_pratinjau(self):
        ltl.tulis_tema(self.tmp, ltl.contoh("grid"))
        self.assertTrue((self.tmp / "theme.yaml").is_file())
        self.assertTrue((self.tmp / "preview.png").is_file())

    def test_pratinjau_memuat_tata_letaknya(self):
        """Pratinjau digambar ulang dengan angkanya, bukan disalin dari latar.

        Kalau cuma disalin, kartu tema di aplikasi memperlihatkan foto polos
        dan tata letak yang salah baru ketahuan setelah terpasang di panel.
        """
        ltl.tulis_tema(self.tmp, ltl.contoh("grid"))
        with Image.open(self.tmp / "background.png") as latar, \
             Image.open(self.tmp / "preview.png") as pratinjau:
            self.assertNotEqual(list(latar.convert("RGB").getdata()),
                                list(pratinjau.convert("RGB").getdata()))

    def test_tidak_meninggalkan_berkas_sementara(self):
        ltl.tulis_tema(self.tmp, ltl.contoh("grid"))
        self.assertFalse((self.tmp / "theme.yaml.baru").exists())

    def test_bisa_dibaca_balik(self):
        asal = ltl.contoh("sudut")
        ltl.tulis_tema(self.tmp, asal)
        balik = ltl.baca_tema(self.tmp)
        self.assertEqual([e.jenis for e in balik.elemen], [e.jenis for e in asal.elemen])

    def test_baca_tema_tanpa_berkas(self):
        with self.assertRaises(ltl.GalatTataLetak):
            ltl.baca_tema(self.tmp / "tidak-ada")

    def test_menimpa_tema_yang_sudah_ada(self):
        ltl.tulis_tema(self.tmp, ltl.contoh("grid"))
        ltl.tulis_tema(self.tmp, ltl.contoh("kolom"))
        balik = ltl.baca_tema(self.tmp)
        self.assertEqual([e.jenis for e in balik.elemen], ltl.EMPAT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
