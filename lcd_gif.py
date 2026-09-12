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

# Laju data panel, diukur langsung 12 September 2026 lewat jalur pembaruan
# sebagian: 480x479 selesai dalam 251-277 ms, jadi 2,5-2,75 MB/dtk pada
# 3 byte/piksel. Dipakai angka pesimistis supaya perkiraan fps tidak pernah
# menjanjikan lebih dari yang bisa ditepati.
LAJU_BYTE_PER_DETIK = 2400 * 1024

# Panel 2.1" menerima 3 byte/piksel (BGR) pada jalur pembaruan sebagian.
BYTE_PER_PIKSEL = 3

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
    byte = max(1, lebar * tinggi * BYTE_PER_PIKSEL)
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
        total += bagian
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


def latar_buram(
    bingkai: Image.Image, kanvas: int = KANVAS_BAKU, kabur: int = 18, terang: float = 1.0
) -> Image.Image:
    """Latar sekanvas penuh dari bingkai GIF, dibesarkan lalu dikaburkan.

    Gunanya mengisi sisi yang kosong saat GIF diputar lebih kecil dari layar.
    Ini **tidak** menambah beban pemutaran: latarnya digambar sekali di awal,
    lalu tiap bingkai cuma menimpa area GIF di tengah — jadi fps-nya tetap
    fps ukuran kecil, bukan fps layar penuh.

    Membesarkan GIF-nya sendiri ke layar penuh tidak bisa jadi jalan pintas:
    yang menentukan waktu kirim adalah jumlah piksel yang ditulis ke panel,
    bukan resolusi sumbernya.
    """
    from PIL import ImageEnhance, ImageFilter

    besar = pas_ke(bingkai, (kanvas, kanvas)).filter(ImageFilter.GaussianBlur(kabur))
    if terang == 1.0:
        return besar
    # Penggelapan sengaja tidak dipakai secara baku. Untuk GIF berlatar terang
    # hasilnya justru buruk: latar putih jadi bingkai abu-abu datar dan
    # sambungannya malah kelihatan. Tanpa digelapkan, latar sewarna menyambung
    # nyaris tanpa batas.
    return ImageEnhance.Brightness(besar).enhance(terang)


def _hindari_jalur_penuh(
    gambar: Image.Image, x: int, y: int, kanvas: int
) -> list[tuple[Image.Image, int, int]]:
    """Pecah dua kalau pengiriman ini akan memakai jalur layar-penuh upstream.

    Upstream memilih jalur berdasarkan posisi dan ukuran: tepat di (0,0) dan
    sebesar layar akan lewat `_generate_full_image`, yang **selalu** menyandi
    BGRA 4 byte/piksel. Jalur pembaruan sebagian menyandi BGR 3 byte untuk
    panel 2.1" ini — seperempat lebih sedikit.

    Terukur: 480x480 di (0,0) butuh 339-369 ms, sedangkan 480x479 di (0,0)
    butuh 251-277 ms. Luasnya cuma beda 0,2%, waktunya beda ~25% — persis
    rasio 4:3 byte. Memecahnya jadi dua bagian membuat keduanya lewat jalur
    sebagian, dan ongkos satu perintah tambahan jauh lebih murah daripada
    seperempat data.
    """
    if not (x == 0 and y == 0 and gambar.width == kanvas and gambar.height == kanvas):
        return [(gambar, x, y)]
    tengah = gambar.height // 2
    return [
        (gambar.crop((0, 0, gambar.width, tengah)), 0, 0),
        (gambar.crop((0, tengah, gambar.width, gambar.height)), 0, tengah),
    ]


def perintah_gambar(
    sebelum: Image.Image | None,
    sesudah: Image.Image,
    x0: int,
    y0: int,
    kanvas: int = KANVAS_BAKU,
) -> list[tuple[Image.Image, int, int]]:
    """Langkah menggambar untuk berpindah dari satu bingkai ke bingkai berikutnya.

    `sebelum=None` berarti isi layar tidak diketahui, jadi bingkai penuh yang
    dikirim. Kalau tidak, cukup kotak pembatas dari piksel yang berubah.

    Dihitung saat pemutaran, bukan disiapkan di muka, karena bingkai bisa
    dilewati kalau panel tidak sanggup mengejar — pembandingnya harus bingkai
    yang terakhir benar-benar digambar. Ongkos diff ~1 ms untuk 480x480,
    dibanding ratusan milidetik waktu kirim.

    Selalu kotak pembatas, tidak pernah sengaja mengirim lebih: kotak itu
    menurut definisi lebih kecil atau sama dengan bingkai penuh, dan ongkos
    perintahnya sama saja. Ambang "kalau bedanya besar kirim utuh saja" yang
    sempat dipakai di sini justru merugikan — selain mengirim piksel yang tidak
    berubah, pengiriman sebesar layar penuh malah jatuh ke jalur BGRA yang
    lebih boros.
    """
    if sebelum is None:
        return _hindari_jalur_penuh(sesudah, x0, y0, kanvas)
    kotak = ImageChops.difference(sebelum, sesudah).getbbox()
    if kotak is None:
        return []
    if kotak == (0, 0, sesudah.width, sesudah.height):
        return _hindari_jalur_penuh(sesudah, x0, y0, kanvas)
    return [(sesudah.crop(kotak), x0 + kotak[0], y0 + kotak[1])]


def hemat(bingkai: list[Bingkai]) -> float:
    """Bagian data yang dihemat dibanding mengirim bingkai penuh terus-menerus.

    0 berarti tidak menghemat apa pun (tiap bingkai berubah seluruhnya).
    """
    if len(bingkai) < 2:
        return 0.0
    luas = bingkai[0].gambar.width * bingkai[0].gambar.height
    if not luas:
        return 0.0
    terkirim = 0
    for i, b in enumerate(bingkai):
        kotak = ImageChops.difference(bingkai[i - 1].gambar, b.gambar).getbbox()
        if kotak is not None:
            terkirim += (kotak[2] - kotak[0]) * (kotak[3] - kotak[1])
    return 1 - terkirim / (luas * len(bingkai))
