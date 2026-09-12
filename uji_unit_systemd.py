"""Uji berkas unit systemd — jalankan: python3 uji_unit_systemd.py

Bukan menjalankan systemd, cuma membaca templat unitnya. Gunanya menjaga satu
kombinasi yang sudah terbukti merusak supaya tidak diam-diam kembali.
"""

import re
import unittest
from pathlib import Path

DIR = Path(__file__).resolve().parent / "systemd"


def baca(nama: str) -> str:
    return (DIR / nama).read_text(encoding="utf-8")


def nilai(teks: str, kunci: str) -> list[str]:
    """Nilai sebuah kunci, baris komentar diabaikan."""
    hasil = []
    for baris in teks.splitlines():
        b = baris.strip()
        if b.startswith("#"):
            continue
        m = re.match(rf"^{re.escape(kunci)}=(.*)$", b)
        if m:
            hasil.append(m.group(1).strip())
    return hasil


class UjiSalingKunci(unittest.TestCase):
    """Dua unit ini menulis ke port serial yang sama; hanya satu boleh hidup."""

    def test_keduanya_saling_menyatakan_conflicts(self):
        self.assertIn("aio-lcd-gif.service", nilai(baca("aio-lcd.service.in"), "Conflicts"))
        self.assertIn("aio-lcd.service", nilai(baca("aio-lcd-gif.service.in"), "Conflicts"))

    def test_keduanya_ikut_sesi_grafis(self):
        for unit in ("aio-lcd.service.in", "aio-lcd-gif.service.in"):
            self.assertIn("graphical-session.target", nilai(baca(unit), "WantedBy"), unit)


class UjiTanpaLoopFlapping(unittest.TestCase):
    """Regresi yang pernah terjadi: 45 kali monitor start/stop dalam ~7 menit.

    Dengan Conflicts= + OnFailure= + Restart=on-failure sekaligus, ketiganya
    saling memicu: pemutar gagal -> OnFailure menyalakan monitor -> pemutar
    dicoba ulang -> Conflicts mematikan monitor -> gagal lagi. Batas percobaan
    tidak pernah tercapai karena penghentian oleh Conflicts mereset hitungannya.
    """

    def test_unit_gif_tidak_mencoba_ulang(self):
        teks = baca("aio-lcd-gif.service.in")
        self.assertTrue(nilai(teks, "OnFailure"), "OnFailure hilang — panel bisa tanpa pemilik")
        self.assertEqual(
            nilai(teks, "Restart"), ["no"],
            "Restart selain 'no' berpasangan dengan OnFailure+Conflicts bikin flapping",
        )

    def test_unit_monitor_boleh_mencoba_ulang(self):
        # Monitor tidak punya OnFailure, jadi aman mencoba ulang — dan memang
        # perlu: izin ACL port serial kadang belum siap saat sesi baru menyala.
        teks = baca("aio-lcd.service.in")
        self.assertEqual(nilai(teks, "Restart"), ["always"])
        self.assertFalse(nilai(teks, "OnFailure"))


class UjiJalurTemplat(unittest.TestCase):
    def test_penanda_jalur_diganti_pemasang(self):
        for unit in ("aio-lcd.service.in", "aio-lcd-gif.service.in"):
            teks = baca(unit)
            self.assertIn("@DIR_UPSTREAM@", teks, unit)
        self.assertIn("@DIR_APP@", baca("aio-lcd-gif.service.in"))

    def test_pemutar_dijalankan_tanpa_argumen(self):
        # Argumennya sengaja dibaca dari tampilan.json, bukan ditulis di unit:
        # ganti GIF tidak boleh berarti menulis ulang unit systemd.
        exec_start = nilai(baca("aio-lcd-gif.service.in"), "ExecStart")[0]
        self.assertTrue(exec_start.endswith("gif_pemutar.py"), exec_start)


if __name__ == "__main__":
    unittest.main(verbosity=2)
