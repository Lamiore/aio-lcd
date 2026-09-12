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
import os
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


def dijalankan_systemd() -> bool:
    """Apakah proses ini memang unit pemutar yang sedang aktif.

    Pembandingnya PID, bukan variabel INVOCATION_ID: variabel itu diwariskan
    dari unit systemd yang menaungi terminal atau aplikasi pemanggil, jadi
    hampir selalu terisi dan tidak membuktikan apa pun.
    """
    return lk.gif_aktif() and lk.pid_pemutar_gif() == os.getpid()


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
        # Harus 'inactive', bukan sekadar 'bukan active': selama 'deactivating'
        # prosesnya masih hidup dan port serialnya masih dipegang. Menyambar di
        # situ bikin galat "device reports readiness to read but returned no
        # data (multiple access on port?)".
        if lk.service_selesai_berhenti():
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

    Mengikuti jam dinding, bukan sekadar menggambar berurutan. Kalau panel
    tidak sanggup mengejar laju GIF-nya, bingkai yang sudah lewat waktunya
    dilewati supaya animasinya tetap berjalan pada **kecepatan aslinya**,
    cuma dengan bingkai lebih sedikit. Tanpa ini animasi 10 fps yang cuma
    sanggup 3,6 fps akan tampil melambat — semua bingkai tampil, tapi
    seluruh gerakannya jadi seperti gerak lambat.

    Karena bingkai bisa dilewati, potongan yang dikirim dihitung terhadap
    bingkai yang **terakhir benar-benar digambar**, bukan terhadap bingkai
    sebelumnya di daftar.
    """
    x, y = lg.posisi_tengah(ukuran, KANVAS)

    # Bingkai pertama dikirim penuh: isi layar saat ini tidak diketahui.
    for gbr, gx, gy in lg.perintah_gambar(None, bingkai[0].gambar, x, y, KANVAS):
        lcd.DisplayPILImage(gbr, gx, gy)
    terakhir = bingkai[0].gambar

    putaran = 0
    terkirim = 1
    dilewati = 0
    waktu_kirim = 0.0
    awal = time.monotonic()
    jadwal = awal  # kapan bingkai berikutnya seharusnya tampil

    def lapor():
        lama = time.monotonic() - awal
        if terkirim and lama > 0 and waktu_kirim > 0:
            print(f"{terkirim} bingkai digambar, {dilewati} dilewati, dalam {lama:.1f} dtk — "
                  f"tayang {(terkirim + dilewati) / lama:.1f} fps efektif, "
                  f"kirim {terkirim / waktu_kirim:.1f} fps", flush=True)

    while not _berhenti:
        for indeks, b in enumerate(bingkai):
            if _berhenti:
                lapor()
                return
            if putaran == 0 and indeks == 0:
                jadwal += b.durasi
                continue  # sudah digambar di atas

            jadwal += b.durasi
            sekarang = time.monotonic()

            # Sudah lewat jadwalnya lebih dari satu bingkai penuh: lewati,
            # jangan digambar. Bingkai terakhir satu putaran tidak pernah
            # dilewati supaya gambar akhirnya tidak nyangkut di tengah gerakan.
            if sekarang > jadwal + b.durasi and indeks != len(bingkai) - 1:
                dilewati += 1
                continue

            mulai = time.monotonic()
            for gbr, gx, gy in lg.perintah_gambar(terakhir, b.gambar, x, y, KANVAS):
                lcd.DisplayPILImage(gbr, gx, gy)
            waktu_kirim += time.monotonic() - mulai
            terakhir = b.gambar
            terkirim += 1

            # Tidur dipecah supaya permintaan berhenti tidak menunggu lama.
            while time.monotonic() < jadwal and not _berhenti:
                time.sleep(min(0.05, jadwal - time.monotonic()))

        putaran += 1
        if ulang and putaran >= ulang:
            lapor()
            return


def main() -> int:
    tersimpan = lk.baca_tampilan()
    p = argparse.ArgumentParser(description="Putar GIF di layar LCD AIO")
    # Semua argumen opsional: kalau tidak diberikan, dipakai pilihan tersimpan
    # di ~/.local/share/aio-lcd/tampilan.json. Itulah cara unit systemd-nya
    # tahu GIF mana yang harus dimuat saat login tanpa perlu ditulis ulang.
    p.add_argument("--gif", type=Path, default=None,
                   help="berkas GIF (baku: yang terakhir dipilih)")
    p.add_argument("--ukuran", type=int, default=None,
                   help=f"sisi area tayang; {KANVAS} berarti layar penuh")
    p.add_argument("--kecerahan", type=int, default=None, help="0-100")
    p.add_argument("--ulang", type=int, default=0, help="jumlah putaran; 0 = terus-menerus")
    p.add_argument("--latar", choices=("buram", "hitam"), default=None,
                   help="isi sisi kosong saat GIF lebih kecil dari layar")
    a = p.parse_args()

    if a.gif is None:
        a.gif = Path(tersimpan["gif"]) if tersimpan["gif"] else None
    if a.ukuran is None:
        a.ukuran = int(tersimpan["ukuran"])
    if a.kecerahan is None:
        a.kecerahan = int(tersimpan["kecerahan"])
    if a.latar is None:
        a.latar = tersimpan["latar"]

    if a.gif is None:
        print("GAGAL: belum ada GIF tersimpan, dan --gif tidak diberikan.\n"
              f"       Pilih GIF lewat aplikasi, atau setel di {lk.BERKAS_TAMPILAN}",
              file=sys.stderr)
        return 2
    if not a.gif.is_file():
        print(f"GAGAL: {a.gif} tidak ada", file=sys.stderr)
        return 2
    if not 1 <= a.ukuran <= KANVAS:
        print(f"GAGAL: --ukuran harus 1..{KANVAS}", file=sys.stderr)
        return 2

    # Cuma satu proses yang boleh memegang port serial. Kalau unit pemutar
    # sudah jalan (dinyalakan dari aplikasi) lalu skrip ini dijalankan lagi
    # dari terminal, keduanya berebut dan galatnya menyesatkan:
    # "device reports readiness to read but returned no data".
    #
    # Pembandingnya PID, bukan variabel INVOCATION_ID: variabel itu diwariskan
    # dari unit systemd yang menaungi terminal/aplikasi pemanggil, jadi hampir
    # selalu terisi dan tidak membuktikan apa pun soal unit pemutar.
    sebagai_unit = dijalankan_systemd()
    if lk.gif_aktif() and not sebagai_unit:
        print(f"GAGAL: {lk.NAMA_SERVICE_GIF} sedang memutar GIF lain.\n"
              f"       Hentikan dulu: systemctl --user stop {lk.NAMA_SERVICE_GIF}",
              file=sys.stderr)
        return 3

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
    hemat = lg.hemat(bingkai)
    print(f"{len(bingkai)} bingkai @ {a.ukuran}x{a.ukuran} — "
          f"diminta {diminta:.1f} fps, sanggup {sanggup:.1f} fps"
          + (f", hemat data {hemat*100:.0f}% (cuma bagian yang berubah)" if hemat > 0.02 else ""),
          flush=True)

    # Kalau kita dijalankan sebagai unit, systemd sudah menghentikan monitor
    # lewat Conflicts= dan akan mengurus giliran berikutnya sendiri. Mematikan
    # atau menyalakannya lagi dari sini justru melawan systemd. Yang perlu
    # mengurusnya sendiri cuma pemanggilan langsung dari terminal.
    monitor_dimatikan = False if sebagai_unit else hentikan_monitor()
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

        # Bersihkan sisa tampilan monitor di luar area GIF — sekali saja, jadi
        # tidak ikut membebani pemutaran. Latar buram mengisi sisi yang kosong
        # tanpa menaikkan biaya tiap bingkai: yang ditimpa berulang cuma area
        # GIF di tengah.
        if a.latar == "buram" and a.ukuran < KANVAS:
            latar = lg.latar_buram(bingkai[0].gambar, KANVAS)
        else:
            latar = Image.new("RGB", (KANVAS, KANVAS), (0, 0, 0))
        lcd.DisplayPILImage(latar, 0, 0)

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
