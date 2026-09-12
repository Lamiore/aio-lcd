"""Logika pemutaran GIF — bagian yang tidak menyentuh perangkat.

Dipisah dari `gif_pemutar.py` supaya bisa diuji tanpa layar, dan supaya
aplikasi GTK (yang jalan dengan Python sistem, tanpa pyserial) tetap bisa
memakai perkiraan fps-nya untuk memberi tahu pengguna sebelum memutar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageSequence

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


def rasio_berubah(jalur: Path) -> float:
    """Rata-rata bagian layar yang berubah antar bingkai berurutan (0..1).

    Dihitung pada resolusi asli GIF, sekali saja: rasionya tidak bergantung
    ukuran tayang, jadi angka yang sama berlaku untuk semua pilihan ukuran —
    dan aplikasinya tidak perlu me-resize ulang tiap kali pilihan digeser.

    Inilah yang sebenarnya menentukan fps, bukan luas layar: yang dikirim ke
    panel cuma kotak yang isinya berubah.
    """
    with Image.open(jalur) as im:
        bingkai = [b.convert("RGB") for b in ImageSequence.Iterator(im)]
    if len(bingkai) < 2:
        return 1.0
    luas = bingkai[0].width * bingkai[0].height
    if not luas:
        return 1.0
    total = 0.0
    for i, b in enumerate(bingkai):
        kotak = ImageChops.difference(bingkai[i - 1], b).getbbox()
        if kotak is None:
            continue
        bagian = ((kotak[2] - kotak[0]) * (kotak[3] - kotak[1])) / luas
        total += 1.0 if bagian >= AMBANG_UTUH else bagian
    return max(0.01, total / len(bingkai))


def ringkasan(jalur: Path, ukuran: int) -> dict:
    """Keterangan singkat untuk ditampilkan sebelum memutar.

    Menyebut 'mulus' atau tidak dengan jujur, dan memperhitungkan bahwa yang
    dikirim tiap bingkai cuma bagian yang berubah — tanpa itu, GIF berlatar
    diam akan dilaporkan jauh lebih lambat daripada kenyataannya (terukur:
    3,0 fps yang diperkirakan vs 16,6 fps yang sebenarnya terjadi).
    """
    durasi = baca_durasi(jalur)
    rasio = rasio_berubah(jalur)
    sanggup_penuh = perkiraan_fps(ukuran, ukuran)
    sanggup = sanggup_penuh / rasio
    total = sum(durasi)
    diminta = len(durasi) / total if total > 0 else 0.0
    return {
        "jumlah_bingkai": len(durasi),
        "rasio_berubah": rasio,
        "fps_sanggup_penuh": sanggup_penuh,
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


# Di atas ambang ini, mengirim potongan tidak lagi menguntungkan: datanya
# hampir sama banyak sementara pembaruan sebagian punya ongkos perintah
# sendiri. Lebih baik sekalian kirim bingkai utuh.
AMBANG_UTUH = 0.75


@dataclass(frozen=True)
class Perintah:
    """Satu langkah pemutaran: gambar apa, di mana, lalu tunggu berapa lama.

    `gambar` boleh None untuk bingkai yang isinya sama persis dengan
    sebelumnya — tidak ada yang perlu dikirim, cukup ditunggu.
    """
    gambar: Image.Image | None
    x: int
    y: int
    durasi: float


def potong_perubahan(
    sebelum: Image.Image, sesudah: Image.Image, x0: int, y0: int
) -> tuple[Image.Image, int, int]:
    """Kembalikan (gambar, x, y) yang cukup dikirim untuk berpindah antar dua bingkai.

    Dipakai saat pemutaran, bukan disiapkan di muka, karena bingkai bisa
    dilewati kalau panel tidak sanggup mengejar — pembandingnya harus bingkai
    yang terakhir benar-benar digambar. Ongkosnya ~1 ms untuk 480x480,
    dibanding ratusan milidetik waktu kirim, jadi tidak terasa.

    Kalau bedanya sudah melebihi AMBANG_UTUH, bingkai utuh yang dikirim:
    datanya hampir sama banyak sementara pembaruan sebagian punya ongkos
    perintah sendiri.
    """
    kotak = ImageChops.difference(sebelum, sesudah).getbbox()
    if kotak is None:
        # Tidak ada yang berubah; kirim satu piksel saja daripada bingkai utuh.
        return sesudah.crop((0, 0, 1, 1)), x0, y0
    lebar, tinggi = kotak[2] - kotak[0], kotak[3] - kotak[1]
    if lebar * tinggi >= sesudah.width * sesudah.height * AMBANG_UTUH:
        return sesudah, x0, y0
    return sesudah.crop(kotak), x0 + kotak[0], y0 + kotak[1]


def susun_perintah(bingkai: list[Bingkai], x0: int, y0: int) -> list[Perintah]:
    """Ubah daftar bingkai jadi langkah-langkah yang hanya mengirim bagian berubah.

    Panel menahan apa yang sudah digambar, jadi bingkai berikutnya cukup
    menimpa kotak yang isinya berbeda. Untuk GIF berlatar diam ini beda jauh:
    kotak berubahnya bisa cuma 5% luas layar, dan yang menentukan fps memang
    jumlah byte yang dikirim.

    Pembandingnya melingkar — bingkai pertama dibandingkan dengan yang
    terakhir — karena pemutarannya berulang, jadi saat kembali ke awal layar
    sedang menampilkan bingkai terakhir.
    """
    if not bingkai:
        return []
    if len(bingkai) == 1:
        b = bingkai[0]
        return [Perintah(b.gambar, x0, y0, b.durasi)]

    luas_penuh = bingkai[0].gambar.width * bingkai[0].gambar.height
    hasil: list[Perintah] = []
    for i, b in enumerate(bingkai):
        sebelum = bingkai[i - 1].gambar  # i=0 → bingkai terakhir, sesuai perulangan
        kotak = ImageChops.difference(sebelum, b.gambar).getbbox()
        if kotak is None:
            hasil.append(Perintah(None, x0, y0, b.durasi))
            continue
        lebar, tinggi = kotak[2] - kotak[0], kotak[3] - kotak[1]
        if lebar * tinggi >= luas_penuh * AMBANG_UTUH:
            hasil.append(Perintah(b.gambar, x0, y0, b.durasi))
        else:
            hasil.append(
                Perintah(b.gambar.crop(kotak), x0 + kotak[0], y0 + kotak[1], b.durasi)
            )
    return hasil


def hemat(perintah: list[Perintah], ukuran: int) -> float:
    """Berapa bagian data yang dihemat dibanding mengirim bingkai utuh terus.

    0 berarti tidak menghemat apa pun (tiap bingkai berubah seluruhnya).
    """
    if not perintah:
        return 0.0
    penuh = ukuran * ukuran * len(perintah)
    dikirim = sum(
        0 if p.gambar is None else p.gambar.width * p.gambar.height for p in perintah
    )
    return 1 - (dikirim / penuh) if penuh else 0.0
