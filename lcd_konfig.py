"""Logika pengaturan layar LCD AIO — tanpa sangkut paut antarmuka.

Berkas ini sengaja tidak memakai ruamel.yaml. Alasannya dua: `config.yaml`
milik upstream penuh komentar penjelas yang berguna, dan Python sistem Fedora
(yang punya GTK4) tidak menyediakan ruamel. Penyuntingan baris bertarget
menjaga berkas utuh persis di luar baris yang memang diubah, sekaligus bikin
aplikasinya jalan tanpa dependensi di luar bawaan sistem.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

# Lokasi klon upstream. Bisa ditimpa lewat variabel lingkungan supaya
# pemasangan di mesin lain tidak perlu menyunting kode.
DIR_UPSTREAM = Path(
    os.environ.get(
        "AIO_LCD_UPSTREAM",
        Path.home() / "workspace/projects/turing-smart-screen-python",
    )
).expanduser()

NAMA_SERVICE = os.environ.get("AIO_LCD_SERVICE", "aio-lcd.service")

# Penanda di log yang berarti layar sudah benar-benar digambar ulang, bukan
# sekadar prosesnya hidup. systemd melaporkan "active" jauh sebelum ini.
PENANDA_SIAP = "Starting system monitoring"


class GalatKonfig(Exception):
    """Dilempar kalau config.yaml tidak berbentuk seperti yang diharapkan."""


@dataclass(frozen=True)
class Tema:
    nama: str
    ukuran: str
    orientasi: str
    penulis: str
    preview: Path | None

    @property
    def punya_preview(self) -> bool:
        return self.preview is not None and self.preview.is_file()


# ---------------------------------------------------------------- config.yaml

def _pola(kunci: str) -> re.Pattern[str]:
    """Cocokkan baris `  KUNCI: nilai`.

    Antara awal baris dan kunci hanya boleh ada spasi/tab, jadi baris yang
    sudah dijadikan komentar tidak ikut tercocok dengan sendirinya — di config
    bawaan ada beberapa (`# COM_PORT: "/dev/ttyACM0"`), dan kalau ikut
    tercocok, penggantian bisa mendarat di baris yang salah.
    """
    return re.compile(rf"^(?P<awal>[ \t]*){re.escape(kunci)}:[ \t]*(?P<nilai>.*)$", re.MULTILINE)


def _baris_aktif(teks: str, kunci: str) -> list[re.Match[str]]:
    return list(_pola(kunci).finditer(teks))


def baca_nilai(teks: str, kunci: str) -> str:
    """Ambil nilai mentah sebuah kunci (masih termasuk tanda kutip kalau ada)."""
    cocok = _baris_aktif(teks, kunci)
    if not cocok:
        raise GalatKonfig(f"kunci {kunci!r} tidak ada di config")
    if len(cocok) > 1:
        raise GalatKonfig(f"kunci {kunci!r} muncul {len(cocok)}x, tidak jelas mana yang dipakai")
    return cocok[0].group("nilai").split("#")[0].strip()


def ganti_nilai(teks: str, kunci: str, nilai_literal: str) -> str:
    """Ganti nilai satu kunci, sisanya dibiarkan utuh apa adanya.

    `nilai_literal` ditulis mentah — pemanggil yang bertanggung jawab mengutip.
    Nama tema untuk layar 2.1" berupa angka semua (26, 30, 43, 44, 45); tanpa
    kutip, YAML membacanya sebagai integer dan upstream gagal dengan
    "Theme not found or contains errors!".
    """
    cocok = _baris_aktif(teks, kunci)
    if not cocok:
        raise GalatKonfig(f"kunci {kunci!r} tidak ada di config")
    if len(cocok) > 1:
        raise GalatKonfig(f"kunci {kunci!r} muncul {len(cocok)}x, penggantian dibatalkan")
    m = cocok[0]
    # Komentar di ujung baris (kalau ada) dipertahankan.
    ekor = m.group("nilai")
    komentar = ""
    if "#" in ekor:
        komentar = "  " + ekor[ekor.index("#"):].strip()
    return teks[:m.start()] + f"{m.group('awal')}{kunci}: {nilai_literal}{komentar}" + teks[m.end():]


def kutip(nilai: str) -> str:
    """Bungkus nilai sebagai skalar YAML berkutip ganda."""
    aman = nilai.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{aman}"'


class Konfig:
    """Pembungkus tipis di atas berkas config.yaml upstream."""

    def __init__(self, jalur: Path | None = None):
        self.jalur = Path(jalur) if jalur else DIR_UPSTREAM / "config.yaml"

    def _baca(self) -> str:
        return self.jalur.read_text(encoding="utf-8")

    def _tulis(self, teks: str) -> None:
        # Tulis lewat berkas sementara di direktori yang sama lalu ganti nama,
        # supaya config tidak pernah setengah tertulis kalau proses mati.
        sementara = self.jalur.with_suffix(self.jalur.suffix + ".baru")
        sementara.write_text(teks, encoding="utf-8")
        os.replace(sementara, self.jalur)

    @property
    def tema(self) -> str:
        return baca_nilai(self._baca(), "THEME").strip("\"'")

    @tema.setter
    def tema(self, nama: str) -> None:
        self._tulis(ganti_nilai(self._baca(), "THEME", kutip(nama)))

    @property
    def terbalik(self) -> bool:
        return baca_nilai(self._baca(), "DISPLAY_REVERSE").lower() == "true"

    @terbalik.setter
    def terbalik(self, nyala: bool) -> None:
        self._tulis(ganti_nilai(self._baca(), "DISPLAY_REVERSE", "true" if nyala else "false"))

    @property
    def revisi(self) -> str:
        return baca_nilai(self._baca(), "REVISION").strip("\"'")


# --------------------------------------------------------------------- tema

def _data_tema(dir_tema: Path) -> dict | None:
    berkas = dir_tema / "theme.yaml"
    if not berkas.is_file():
        return None
    try:
        with berkas.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None
    return data if isinstance(data, dict) else None


def daftar_tema(ukuran: str | None = None, dir_tema: Path | None = None) -> list[Tema]:
    """Kumpulkan tema yang tersedia, disaring menurut ukuran layar.

    Ukuran diambil dari `DISPLAY_SIZE` di theme.yaml; upstream menganggap
    tema tanpa kunci itu sebagai 3.5". Menyaringnya penting: dari 79 tema,
    cuma 5 yang muat di layar 2.1", dan tema salah ukuran bikin tata letaknya
    melenceng, bukan menolak jalan.
    """
    akar = Path(dir_tema) if dir_tema else DIR_UPSTREAM / "res/themes"
    hasil: list[Tema] = []
    if not akar.is_dir():
        return hasil
    for anak in sorted(akar.iterdir(), key=lambda p: p.name.casefold()):
        if not anak.is_dir():
            continue
        data = _data_tema(anak)
        if not data:
            continue
        tampilan = data.get("display") or {}
        uk = str(tampilan.get("DISPLAY_SIZE", '3.5"'))
        if ukuran is not None and uk != ukuran:
            continue
        preview = anak / "preview.png"
        hasil.append(
            Tema(
                nama=anak.name,
                ukuran=uk,
                orientasi=str(tampilan.get("DISPLAY_ORIENTATION", "portrait")),
                penulis=str(data.get("author", "")).strip(),
                preview=preview if preview.is_file() else None,
            )
        )
    return hasil


# ------------------------------------------------------------------ service

def _systemctl(*argumen: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *argumen],
        capture_output=True, text=True, check=False,
    )


def service_terpasang() -> bool:
    return _systemctl("cat", NAMA_SERVICE).returncode == 0


def service_aktif() -> bool:
    return _systemctl("is-active", NAMA_SERVICE).stdout.strip() == "active"


def _invocation_id() -> str:
    return _systemctl("show", NAMA_SERVICE, "-p", "InvocationID", "--value").stdout.strip()


def restart_service(batas_detik: float = 90.0) -> tuple[bool, str]:
    """Restart service lalu tunggu sampai layar benar-benar digambar ulang.

    Mengembalikan (berhasil, keterangan). Yang ditunggu bukan status systemd —
    systemd bilang "active" dalam hitungan milidetik, sementara layarnya baru
    tergambar belasan detik kemudian setelah panel dibangunkan dan port
    serialnya pindah. Yang dipakai sebagai bukti adalah PENANDA_SIAP di jurnal
    milik invocation yang baru, bukan invocation sebelumnya.
    """
    if not service_terpasang():
        return False, f"{NAMA_SERVICE} belum terpasang"

    hasil = _systemctl("restart", NAMA_SERVICE)
    if hasil.returncode != 0:
        return False, (hasil.stderr or hasil.stdout).strip() or "gagal restart"

    inv = _invocation_id()
    if not inv:
        return False, "tidak dapat membaca InvocationID service"

    tenggat = time.monotonic() + batas_detik
    while time.monotonic() < tenggat:
        log = subprocess.run(
            ["journalctl", "--user", f"_SYSTEMD_INVOCATION_ID={inv}", "--no-pager", "-o", "cat"],
            capture_output=True, text=True, check=False,
        ).stdout
        if PENANDA_SIAP in log:
            return True, "layar sudah digambar ulang"
        if not service_aktif():
            return False, "service berhenti sebelum layar sempat digambar"
        time.sleep(1.0)

    return False, f"lewat {batas_detik:.0f} detik layar belum melapor siap"
