#!/usr/bin/env python3
"""Gambar sebuah tema lewat kode upstream sendiri, tanpa panel dan tanpa jendela.

Kenapa ada: tata letak yang kita tulis diperiksa dua kali — sekali oleh
pratinjau kita (`lcd_tataletak.render`, dipakai di editor) dan sekali oleh
upstream waktu benar-benar menggambar. Dua penggambar yang terpisah pasti akan
melenceng cepat atau lambat kalau tidak pernah dibandingkan. Berkas ini
pembandingnya.

Upstream punya backend layar tiruan (`REVISION: SIMU`) yang menyimpan hasil
gambarnya di sebuah objek PIL, jadi seluruh jalurnya bisa dijalankan tanpa
perangkat. `theme-editor.py` memakai backend yang sama, cuma membungkusnya
dengan Tkinter — yang di sini tidak diperlukan dan malah bikin tidak bisa
dijalankan dari terminal.

Wajib memakai Python venv upstream (psutil, pyserial, dan kawan-kawan tidak
ada di Python sistem):

    ~/workspace/projects/turing-smart-screen-python/.venv/bin/python \
        periksa_tema.py <nama-tema> -o /tmp/hasil.png

Dengan `--banding <berkas>` hasilnya dibandingkan dengan pratinjau kita dan
selisih pikselnya dilaporkan.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

DIR_UPSTREAM = Path(
    os.environ.get("AIO_LCD_UPSTREAM", Path.home() / "workspace/projects/turing-smart-screen-python")
).expanduser()


def gambar(nama_tema: str):
    """Kembalikan citra PIL hasil gambar upstream untuk satu tema.

    Urutan impornya penting dan menyalin `theme-editor.py`: config disetel
    dulu, `library.display` diimpor belakangan. Modul display membangun
    objek LCD-nya saat diimpor, jadi REVISION yang dibaca adalah yang berlaku
    pada saat itu — mengimpornya lebih awal akan membuatnya mencari panel
    sungguhan lewat port serial.
    """
    os.chdir(DIR_UPSTREAM)
    sys.path.insert(0, str(DIR_UPSTREAM))

    import library.log
    library.log.logger.setLevel(logging.ERROR)

    from library import config

    config.CONFIG_DATA["config"]["HW_SENSORS"] = "STATIC"   # data contoh, bukan sensor asli
    config.CONFIG_DATA["config"]["THEME"] = nama_tema
    config.load_theme()
    config.CONFIG_DATA["display"]["REVISION"] = "SIMU"

    from library.display import display
    import library.stats as stats

    display.initialize_display()
    display.display_static_images()
    display.display_static_text()

    data = config.THEME_DATA["STATS"]
    # Cerminan `refresh_theme()` milik theme-editor: tiap kelompok digambar
    # hanya kalau INTERVAL-nya > 0, dan letak kunci INTERVAL itu berbeda-beda
    # antar perangkat — CPU menyimpannya per metrik, sisanya di tingkat
    # perangkat. Justru ketidakseragaman itu yang ingin diuji di sini.
    if data["CPU"]["PERCENTAGE"].get("INTERVAL", 0) > 0:
        stats.CPU.percentage()
    if data["CPU"]["FREQUENCY"].get("INTERVAL", 0) > 0:
        stats.CPU.frequency()
    if data["CPU"]["TEMPERATURE"].get("INTERVAL", 0) > 0:
        stats.CPU.temperature()
    if data["GPU"].get("INTERVAL", 0) > 0:
        stats.Gpu.stats()
    if data["MEMORY"].get("INTERVAL", 0) > 0:
        stats.Memory.stats()
    if data["DISK"].get("INTERVAL", 0) > 0:
        stats.Disk.stats()
    if data["DATE"].get("INTERVAL", 0) > 0:
        stats.Date.stats()

    return display.lcd.screen_image


def banding(a, b) -> tuple[float, int]:
    """(selisih rata-rata per kanal, jumlah piksel yang berbeda jauh)."""
    from PIL import Image, ImageChops

    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    beda = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    # Lewat histogram, bukan daftar piksel: hasilnya sama tapi tidak memuat
    # seperempat juta tuple ke memori, dan `getdata()` sudah ditandai usang.
    sebaran = beda.histogram()
    jumlah = sum(sebaran)
    rata = sum(i * n for i, n in enumerate(sebaran)) / jumlah
    jauh = sum(sebaran[61:])
    return rata, jauh


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tema", help="nama folder tema di res/themes")
    p.add_argument("-o", "--keluaran", default="/tmp/tema.png", help="tempat menyimpan hasilnya")
    p.add_argument("--banding", help="berkas pratinjau kita, untuk dibandingkan")
    arg = p.parse_args()

    try:
        citra = gambar(arg.tema)
    except Exception as galat:                       # noqa: BLE001 — apa pun yang gagal harus terbaca
        print(f"gagal menggambar {arg.tema!r}: {type(galat).__name__}: {galat}", file=sys.stderr)
        return 1

    keluaran = Path(arg.keluaran).expanduser()
    citra.save(keluaran)
    print(f"tergambar {citra.size[0]}×{citra.size[1]} → {keluaran}")

    if arg.banding:
        from PIL import Image
        with Image.open(arg.banding) as kita:
            rata, jauh = banding(citra, kita)
        print(f"selisih rata-rata {rata:.2f}/255 · {jauh} piksel meleset jauh")
        # Ambang longgar dengan sengaja: penghalusan tepi huruf dan nilai
        # sensor contoh yang berbeda angka membuat selisih kecil selalu ada.
        # Yang dicari letak yang meleset, bukan piksel yang persis sama.
        if jauh > citra.size[0] * citra.size[1] * 0.02:
            print("pratinjau kita melenceng dari gambar upstream", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    kode = main()
    # Keluar paksa: backend layar tiruan upstream menyalakan peladen web di
    # utas yang bukan daemon, jadi proses ini tidak pernah berakhir sendiri
    # walaupun pekerjaannya sudah selesai. Semua berkas sudah ditulis dan
    # ditutup di atas, jadi tidak ada yang hilang karena melewati pembersihan.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(kode)
