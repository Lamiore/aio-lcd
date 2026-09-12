#!/usr/bin/env python3
"""Pemutar GIF untuk layar LCD AIO.

Wajib dijalankan dengan Python venv upstream — pyserial dan pustaka panelnya
cuma ada di sana, tidak di Python sistem.

    <upstream>/.venv/bin/python gif_pemutar.py --gif anu.gif --ukuran 240

Selama GIF diputar, service monitor (`aio-lcd.service`) dimatikan: cuma satu
proses yang boleh memegang port serial. Service-nya dinyalakan lagi saat
pemutar berhenti, termasuk kalau dihentikan lewat SIGTERM — yang memang cara
systemd menghentikan unit.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

DIR_APP = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR_APP))

import lcd_gif as lg  # noqa: E402
import lcd_konfig as lk  # noqa: E402

sys.path.insert(0, str(lk.DIR_UPSTREAM))

from PIL import Image  # noqa: E402
from library.lcd.lcd_comm import Orientation  # noqa: E402
from library.lcd.lcd_comm_rev_c import LcdCommRevC  # noqa: E402

KANVAS = 480
JEDA_BANGUN = 3.0
PERCOBAAN_BANGUN = 12

_berhenti = False


def _minta_berhenti(*_):
    global _berhenti
    _berhenti = True


def systemctl(*argumen: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *argumen], capture_output=True, text=True, check=False
    )


def hentikan_monitor(batas: float = 30.0) -> bool:
    """Matikan service monitor dan tunggu sampai benar-benar lepas.

    Menunggu itu penting: `systemctl stop` kembali sebelum prosesnya selesai
    melepas port serial, dan pemutar yang langsung menyambar akan ditolak.
    """
    if not lk.service_terpasang():
        return False
    systemctl("stop", lk.NAMA_SERVICE)
    tenggat = time.monotonic() + batas
    while time.monotonic() < tenggat:
        if not lk.service_aktif():
            time.sleep(1.0)  # beri waktu port serialnya benar-benar tertutup
            return True
        time.sleep(0.5)
    return True


def nyalakan_monitor() -> None:
    if lk.service_terpasang():
        systemctl("start", lk.NAMA_SERVICE)


def sambung_panel() -> LcdCommRevC | None:
    """Bangunkan panel lalu buka sambungannya.

    Panel kembali tidur begitu monitor berhenti, dan sekali panggil
    auto-deteksi tidak cukup untuk membangunkannya — persis seperti yang
    dilakukan main.py upstream dengan WAKE_RETRIES.
    """
    for _ in range(PERCOBAAN_BANGUN):
        if _berhenti:
            return None
        if LcdCommRevC.auto_detect_com_port():
            break
        time.sleep(JEDA_BANGUN)
    else:
        return None

    # 'AUTO', bukan port yang barusan ketemu. Reset() membuat panel
    # re-enumerate dan portnya berpindah (/dev/ttyACM0 lenyap lalu muncul
    # lagi); openSerial() upstream cuma mendeteksi ulang kalau com_port-nya
    # persis 'AUTO' (lcd_comm.py:109). Dengan port konkret dia mentok di port
    # basi lalu memanggil os._exit(0) — yang juga melewati blok finally di
    # bawah, sehingga service monitor tidak pernah dinyalakan kembali.
    lcd = LcdCommRevC(com_port="AUTO", display_width=KANVAS, display_height=KANVAS)
    lcd.Reset()
    lcd.InitializeComm()
    return lcd


def putar(lcd: LcdCommRevC, bingkai: list[lg.Bingkai], ukuran: int, ulang: int) -> None:
    """Gelung pemutaran, berhenti begitu diminta.

    Tidak mengejar ketertinggalan dengan melompati bingkai: layar ini ditulisi
    berurutan, jadi melompat tidak menghemat apa pun — waktu terbesarnya di
    pengiriman, bukan di jeda.
    """
    x, y = lg.posisi_tengah(ukuran, KANVAS)
    putaran = 0
    terkirim = 0
    waktu_kirim = 0.0
    awal = time.monotonic()

    def lapor():
        lama = time.monotonic() - awal
        if terkirim and lama > 0:
            # Dua angka berbeda: laju kirim mentah (batas panel) dan laju
            # tayang (termasuk jeda antar bingkai sesuai maunya GIF).
            print(f"{terkirim} bingkai dalam {lama:.1f} dtk — "
                  f"tayang {terkirim / lama:.1f} fps, "
                  f"kirim {terkirim / waktu_kirim:.1f} fps", flush=True)

    while not _berhenti:
        for b in bingkai:
            if _berhenti:
                lapor()
                return
            mulai = time.monotonic()
            lcd.DisplayPILImage(b.gambar, x, y)
            selesai = time.monotonic()
            terkirim += 1
            waktu_kirim += selesai - mulai
            sisa = b.durasi - (selesai - mulai)
            if sisa > 0:
                # Tidur dipecah supaya permintaan berhenti tidak menunggu
                # bingkai lambat selesai.
                akhir = time.monotonic() + sisa
                while time.monotonic() < akhir and not _berhenti:
                    time.sleep(min(0.05, akhir - time.monotonic()))
        putaran += 1
        if ulang and putaran >= ulang:
            lapor()
            return


def main() -> int:
    p = argparse.ArgumentParser(description="Putar GIF di layar LCD AIO")
    p.add_argument("--gif", required=True, type=Path, help="berkas GIF (atau gambar diam)")
    p.add_argument("--ukuran", type=int, default=240,
                   help=f"sisi area tayang; {KANVAS} berarti layar penuh (baku: 240)")
    p.add_argument("--kecerahan", type=int, default=20, help="0-100 (baku: 20)")
    p.add_argument("--ulang", type=int, default=0, help="jumlah putaran; 0 = terus-menerus")
    a = p.parse_args()

    if not a.gif.is_file():
        print(f"GAGAL: {a.gif} tidak ada", file=sys.stderr)
        return 2
    if not 1 <= a.ukuran <= KANVAS:
        print(f"GAGAL: --ukuran harus 1..{KANVAS}", file=sys.stderr)
        return 2

    signal.signal(signal.SIGTERM, _minta_berhenti)
    signal.signal(signal.SIGINT, _minta_berhenti)

    # Bingkai dirender sebelum monitor dimatikan, supaya layar tidak kosong
    # lama-lama kalau GIF-nya besar.
    try:
        bingkai = lg.muat_bingkai(a.gif, a.ukuran)
    except (OSError, ValueError) as galat:
        print(f"GAGAL membaca GIF: {galat}", file=sys.stderr)
        return 1
    if not bingkai:
        print("GAGAL: GIF tidak punya bingkai", file=sys.stderr)
        return 1

    sanggup = lg.perkiraan_fps(a.ukuran, a.ukuran)
    diminta = lg.fps_diminta(bingkai)
    print(f"{len(bingkai)} bingkai @ {a.ukuran}x{a.ukuran} — "
          f"diminta {diminta:.1f} fps, sanggup {sanggup:.1f} fps", flush=True)

    monitor_dimatikan = hentikan_monitor()
    lcd = None
    try:
        lcd = sambung_panel()
        if lcd is None:
            print("GAGAL: panel tidak terdeteksi", file=sys.stderr)
            return 1
        lcd.SetBrightness(max(0, min(100, a.kecerahan)))

        # Ikuti DISPLAY_REVERSE dari config, kalau tidak GIF-nya tampil
        # terbalik di pemasangan yang blok pompanya diputar. Pustakanya yang
        # memutar gambar sekaligus menggeser koordinatnya — pembaruan sebagian
        # pun ikut diperhitungkan (lcd_comm_rev_c.py: _generate_update_image).
        try:
            terbalik = lk.Konfig().terbalik
        except (lk.GalatKonfig, OSError):
            terbalik = False
        lcd.SetOrientation(Orientation.REVERSE_PORTRAIT if terbalik else Orientation.PORTRAIT)

        # Bersihkan sisa tampilan monitor di luar area GIF sekali saja.
        lcd.DisplayPILImage(Image.new("RGB", (KANVAS, KANVAS), (0, 0, 0)), 0, 0)
        print("mulai memutar", flush=True)
        putar(lcd, bingkai, a.ukuran, a.ulang)
        print("berhenti", flush=True)
        return 0
    finally:
        if lcd is not None:
            try:
                lcd.closeSerial()
            except Exception:
                pass
        if monitor_dimatikan:
            nyalakan_monitor()


if __name__ == "__main__":
    sys.exit(main())
