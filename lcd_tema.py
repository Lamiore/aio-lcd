"""Pembuatan dan pengelolaan tema buatan sendiri.

Tema buatan sendiri **tidak** disimpan di dalam klon upstream. Dia tinggal di
`~/.local/share/aio-lcd/themes/` lalu di-symlink ke `res/themes/` milik
upstream. Alasannya: `pasang.sh` mengklon ulang upstream kalau belum ada, dan
tema yang ditaruh langsung di sana akan ikut lenyap. Upstream mendata tema
dengan `is_dir()` dan memuatnya lewat jalur berkas, dua-duanya mengikuti
symlink — sudah diuji, bukan diandaikan.

Efek sampingnya berguna: entri `res/themes/` yang berupa symlink pasti tema
buatan sendiri, jadi tidak perlu penanda apa pun untuk tahu mana yang aman
dihapus atau disunting.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml
from PIL import Image

import lcd_konfig as lk

DIR_DATA = Path(os.environ.get("AIO_LCD_DATA", Path.home() / ".local/share/aio-lcd")).expanduser()

# Nama tema jadi nama folder sekaligus nilai di config.yaml. Dibatasi ketat
# supaya tidak bisa keluar dari direktori tema atau bikin YAML ambigu.
POLA_NAMA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")

BERKAS_WAJIB = "theme.yaml"
UKURAN_BAKU = (480, 480)


class GalatTema(Exception):
    """Dilempar untuk semua kegagalan yang bisa diperkirakan (nama bentrok,
    berkas bukan tema, mau menghapus tema bawaan, dsb)."""


def periksa_nama(nama: str) -> str:
    nama = nama.strip()
    if not POLA_NAMA.match(nama):
        raise GalatTema(
            "Nama cuma boleh huruf/angka/spasi/titik/garis, diawali huruf atau angka, maksimal 40 karakter"
        )
    if nama.lower() in {"default", "."}:
        raise GalatTema(f"{nama!r} nama yang dipakai upstream, pilih yang lain")
    return nama


class PustakaTema:
    """Semua operasi tema, dengan jalur yang bisa ditukar supaya bisa diuji."""

    def __init__(self, akar_tema: Path | None = None, dir_pengguna: Path | None = None):
        self.akar = Path(akar_tema) if akar_tema else lk.DIR_UPSTREAM / "res/themes"
        self.dir_pengguna = Path(dir_pengguna) if dir_pengguna else DIR_DATA / "themes"

    # ------------------------------------------------------------ dasar

    def jalur(self, nama: str) -> Path:
        return self.akar / nama

    def ada(self, nama: str) -> bool:
        return (self.akar / nama).is_dir()

    def milik_pengguna(self, nama: str) -> bool:
        """Tema buatan sendiri selalu berupa symlink di res/themes."""
        return (self.akar / nama).is_symlink()

    def daftar_pengguna(self) -> list[str]:
        if not self.akar.is_dir():
            return []
        return sorted(p.name for p in self.akar.iterdir() if p.is_symlink() and p.is_dir())

    def _tautkan(self, nama: str) -> Path:
        """Pasang symlink dari res/themes ke direktori data."""
        self.akar.mkdir(parents=True, exist_ok=True)
        tautan = self.akar / nama
        if tautan.is_symlink() or tautan.exists():
            tautan.unlink()
        tautan.symlink_to(self.dir_pengguna / nama, target_is_directory=True)
        return tautan

    def segarkan_tautan(self) -> list[str]:
        """Pasang ulang semua symlink yang hilang.

        Dipakai setelah upstream diklon ulang: direktori datanya masih utuh,
        yang lenyap cuma symlink-nya.
        """
        if not self.dir_pengguna.is_dir():
            return []
        dipasang = []
        for asal in sorted(self.dir_pengguna.iterdir()):
            if asal.is_dir() and (asal / BERKAS_WAJIB).is_file():
                self._tautkan(asal.name)
                dipasang.append(asal.name)
        return dipasang

    # --------------------------------------------------------- pembuatan

    def _siapkan_tujuan(self, nama: str) -> Path:
        nama = periksa_nama(nama)
        if self.ada(nama):
            raise GalatTema(f"Tema {nama!r} sudah ada")
        tujuan = self.dir_pengguna / nama
        if tujuan.exists():
            raise GalatTema(f"Folder {tujuan} sudah ada tapi tidak tertaut — beresin dulu")
        return tujuan

    def _pasang_dari(self, bahan: Path, nama: str) -> Path:
        """Pindahkan direktori yang sudah jadi ke tempatnya lalu tautkan.

        Isinya dibangun dulu di direktori sementara, jadi kegagalan di tengah
        tidak meninggalkan tema setengah jadi yang tetap kelihatan di app.
        """
        tujuan = self.dir_pengguna / nama
        tujuan.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(bahan), str(tujuan))
        self._tautkan(nama)
        return tujuan

    def duplikat(self, sumber: str, nama_baru: str) -> Path:
        """Salin tema yang ada jadi tema baru milik sendiri."""
        self._siapkan_tujuan(nama_baru)
        asal = self.akar / sumber
        if not (asal / BERKAS_WAJIB).is_file():
            raise GalatTema(f"{sumber!r} bukan tema yang sah")
        with tempfile.TemporaryDirectory() as tmp:
            bahan = Path(tmp) / nama_baru
            # copy_function=copy2 + follow symlink: tema sumber boleh saja
            # sendirinya symlink (menduplikat tema buatan sendiri).
            shutil.copytree(asal, bahan, symlinks=False)
            self._tulis_penulis(bahan, f"disalin dari {sumber}")
            return self._pasang_dari(bahan, periksa_nama(nama_baru))

    def buat_dari_gambar(self, gambar: Path, nama_baru: str, donor: str) -> Path:
        """Bikin tema baru: tata letak diambil dari `donor`, latarnya gambarmu.

        Tata letak sengaja tidak dibuat dari nol. Menaruh angka di koordinat
        yang pas itu pekerjaan penyunting visual tersendiri; meminjam tata
        letak tema yang sudah terbukti muat di layar ini jauh lebih murah dan
        hasilnya dijamin tidak melenceng.
        """
        self._siapkan_tujuan(nama_baru)
        asal = self.akar / donor
        if not (asal / BERKAS_WAJIB).is_file():
            raise GalatTema(f"Tema contoh {donor!r} tidak ada")
        gambar = Path(gambar)
        if not gambar.is_file():
            raise GalatTema(f"Gambar {gambar} tidak ada")

        with tempfile.TemporaryDirectory() as tmp:
            bahan = Path(tmp) / nama_baru
            shutil.copytree(asal, bahan, symlinks=False)
            ukuran = self._ukuran_kanvas(bahan)
            latar = muat_dan_pas(gambar, ukuran)
            latar.save(bahan / "background.png")
            latar.save(bahan / "preview.png")
            self._tulis_penulis(bahan, f"gambar sendiri, tata letak dari {donor}")
            return self._pasang_dari(bahan, periksa_nama(nama_baru))

    def impor(self, sumber: Path, nama_baru: str | None = None) -> Path:
        """Ambil tema buatan orang dari folder atau berkas .zip."""
        sumber = Path(sumber)
        if not sumber.exists():
            raise GalatTema(f"{sumber} tidak ada")

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            if sumber.is_file() and sumber.suffix.lower() == ".zip":
                isi = self._bongkar_zip(sumber, tmp)
            elif sumber.is_dir():
                isi = sumber
            else:
                raise GalatTema("Yang bisa diimpor cuma folder tema atau berkas .zip")

            if not (isi / BERKAS_WAJIB).is_file():
                raise GalatTema(f"Tidak ketemu {BERKAS_WAJIB} di dalamnya — ini bukan tema")

            nama = periksa_nama(nama_baru or isi.name)
            self._siapkan_tujuan(nama)
            bahan = tmp / f"__siap__{nama}"
            shutil.copytree(isi, bahan, symlinks=False)
            return self._pasang_dari(bahan, nama)

    @staticmethod
    def _bongkar_zip(berkas: Path, tujuan: Path) -> Path:
        keluar = tujuan / "__zip__"
        keluar.mkdir()
        with zipfile.ZipFile(berkas) as z:
            for anggota in z.namelist():
                # Tolak jalur yang keluar dari direktori tujuan (Zip Slip).
                calon = (keluar / anggota).resolve()
                if not str(calon).startswith(str(keluar.resolve())):
                    raise GalatTema(f"Zip memuat jalur berbahaya: {anggota}")
            z.extractall(keluar)

        if (keluar / BERKAS_WAJIB).is_file():
            return keluar
        # Zip yang dibungkus satu folder — bentuk paling umum.
        anak = [p for p in keluar.iterdir() if p.is_dir()]
        if len(anak) == 1 and (anak[0] / BERKAS_WAJIB).is_file():
            return anak[0]
        raise GalatTema(f"Tidak ketemu {BERKAS_WAJIB} di dalam zip")

    # ---------------------------------------------------------- penghapusan

    def hapus(self, nama: str) -> None:
        if not self.ada(nama):
            raise GalatTema(f"Tema {nama!r} tidak ada")
        if not self.milik_pengguna(nama):
            raise GalatTema(f"{nama!r} tema bawaan upstream, tidak dihapus dari sini")
        (self.akar / nama).unlink()
        shutil.rmtree(self.dir_pengguna / nama, ignore_errors=True)

    # ------------------------------------------------------------- bantuan

    @staticmethod
    def _ukuran_kanvas(dir_tema: Path) -> tuple[int, int]:
        """Ukuran kanvas diambil dari latar tema contoh, bukan tabel hafalan.

        Dengan begitu tema contoh ukuran berapa pun ikut benar tanpa perlu
        memetakan DISPLAY_SIZE ke piksel di sini.
        """
        latar = dir_tema / "background.png"
        if latar.is_file():
            try:
                with Image.open(latar) as im:
                    return im.size
            except OSError:
                pass
        return UKURAN_BAKU

    @staticmethod
    def _tulis_penulis(dir_tema: Path, keterangan: str) -> None:
        """Tandai asal-usulnya di theme.yaml, supaya kelihatan di app."""
        berkas = dir_tema / BERKAS_WAJIB
        try:
            teks = berkas.read_text(encoding="utf-8")
        except OSError:
            return
        baris = [b for b in teks.splitlines() if not b.startswith("author:")]
        berkas.write_text(
            "\n".join(baris[:1] + [f'author: "{keterangan}"'] + baris[1:]) + "\n",
            encoding="utf-8",
        )


def muat_dan_pas(gambar: Path, ukuran: tuple[int, int]) -> Image.Image:
    """Muat gambar lalu potong-tengah supaya persis mengisi kanvas.

    Dipilih 'isi lalu potong', bukan 'muat seluruhnya', karena layar ini bujur
    sangkar dan gambar yang dimuat utuh akan menyisakan pita hitam di dua sisi.
    """
    with Image.open(gambar) as im:
        im = im.convert("RGB")
        lebar_t, tinggi_t = ukuran
        skala = max(lebar_t / im.width, tinggi_t / im.height)
        baru = (max(1, round(im.width * skala)), max(1, round(im.height * skala)))
        im = im.resize(baru, Image.LANCZOS)
        kiri = (im.width - lebar_t) // 2
        atas = (im.height - tinggi_t) // 2
        return im.crop((kiri, atas, kiri + lebar_t, atas + tinggi_t))


def ukuran_tema(dir_tema: Path) -> str:
    """Baca DISPLAY_SIZE sebuah tema; dipakai memperingatkan ukuran tak cocok."""
    try:
        with (dir_tema / BERKAS_WAJIB).open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return ""
    return str((data.get("display") or {}).get("DISPLAY_SIZE", '3.5"'))
