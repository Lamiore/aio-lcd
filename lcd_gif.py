"""Logika pemutaran GIF — bagian yang tidak menyentuh perangkat.

Dipisah dari `gif_pemutar.py` supaya bisa diuji tanpa layar, dan supaya
aplikasi GTK (yang jalan dengan Python sistem, tanpa pyserial) tetap bisa
memakai perkiraan fps-nya untuk memberi tahu pengguna sebelum memutar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence

from lcd_tema import pas_ke

# Laju data panel, diukur langsung 12 September 2026 dengan menimpa bingkai
# berulang: 1948 KB/dtk pada 480x480, 2564 KB/dtk pada 240x240, 2382 KB/dtk
# pada 120x120. Dipakai angka paling pesimistis supaya perkiraan fps tidak
# pernah menjanjikan lebih dari yang bisa ditepati.
LAJU_BYTE_PER_DETIK = 1948 * 1024

# Sisi kanvas panel 2.1" dalam piksel.
KANVAS_BAKU = 480

# Ukuran yang ditawarkan aplikasi. KANVAS_BAKU berarti layar penuh.
UKURAN_PILIHAN = (KANVAS_BAKU, 360, 240, 160)

DURASI_BAKU = 0.1  # dipakai kalau GIF-nya tidak menyebut durasi bingkai
DURASI_MINIMUM = 0.01


@dataclass(frozen=True)
class Bingkai:
    gambar: Image.Image
    durasi: float  # detik, sesuai maunya GIF — belum tentu tercapai


def perkiraan_fps(lebar: int, tinggi: int) -> float:
    """Berapa bingkai per detik yang sanggup dikirim untuk area sebesar itu.

    Satu piksel = 3 byte. Angkanya turun sebanding luas, bukan sisi, jadi
    mengecilkan sisi setengah bikin fps-nya empat kali lipat.
    """
    byte = max(1, lebar * tinggi * 3)
    return LAJU_BYTE_PER_DETIK / byte


def fps_diminta(bingkai: list[Bingkai]) -> float:
    """Rata-rata fps yang diminta GIF-nya sendiri."""
    if not bingkai:
        return 0.0
    total = sum(b.durasi for b in bingkai)
    return len(bingkai) / total if total > 0 else 0.0


def baca_durasi(jalur: Path) -> list[float]:
    """Durasi tiap bingkai, tanpa me-resize apa pun.

    Dipisah dari muat_bingkai supaya aplikasi bisa menampilkan perkiraan fps
    seketika saat pengguna menggeser pilihan ukuran — me-resize ratusan bingkai
    cuma untuk sebuah angka bikin antarmukanya tersendat.
    """
    hasil: list[float] = []
    with Image.open(jalur) as im:
        baku = im.info.get("duration") or 0
        for bingkai in ImageSequence.Iterator(im):
            milidetik = bingkai.info.get("duration") or baku
            hasil.append(max(DURASI_MINIMUM, milidetik / 1000) if milidetik else DURASI_BAKU)
    return hasil


def ringkasan(jalur: Path, ukuran: int) -> dict:
    """Keterangan singkat untuk ditampilkan sebelum memutar.

    Menyebut 'mulus' atau tidak dengan jujur: panel tidak bisa mengejar GIF
    yang mintanya lebih cepat daripada yang sanggup dikirim.
    """
    durasi = baca_durasi(jalur)
    sanggup = perkiraan_fps(ukuran, ukuran)
    total = sum(durasi)
    diminta = len(durasi) / total if total > 0 else 0.0
    return {
        "jumlah_bingkai": len(durasi),
        "fps_sanggup": sanggup,
        "fps_diminta": diminta,
        "fps_nyata": min(sanggup, diminta) if diminta else sanggup,
        "mulus": diminta <= sanggup + 0.5,
    }


def muat_bingkai(jalur: Path, ukuran: int) -> list[Bingkai]:
    """Baca semua bingkai GIF, sudah dipotong ke ukuran tayang.

    Seluruh bingkai dirender di muka, bukan saat diputar. Layar ini sanggup
    ~15 bingkai/detik di 240x240; kalau tiap bingkai masih harus di-resize saat
    pemutaran, waktu render ikut memakan jatah itu dan hasilnya tersendat.
    """
    hasil: list[Bingkai] = []
    with Image.open(jalur) as im:
        for bingkai in ImageSequence.Iterator(im):
            # Komposit ke hitam: GIF transparan kalau langsung di-convert("RGB")
            # menghasilkan latar hitam pekat yang tidak konsisten antar bingkai.
            rgba = bingkai.convert("RGBA")
            dasar = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
            dasar.alpha_composite(rgba)

            milidetik = bingkai.info.get("duration") or im.info.get("duration") or 0
            durasi = max(DURASI_MINIMUM, milidetik / 1000) if milidetik else DURASI_BAKU
            hasil.append(Bingkai(pas_ke(dasar, (ukuran, ukuran)), durasi))
    return hasil


def posisi_tengah(ukuran: int, kanvas: int = KANVAS_BAKU) -> tuple[int, int]:
    """Koordinat kiri-atas supaya bingkai duduk di tengah layar."""
    sisa = max(0, kanvas - ukuran)
    return sisa // 2, sisa // 2
