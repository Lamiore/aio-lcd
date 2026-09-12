"""Tata letak angka pemantauan: modelnya, berkas temanya, dan pratinjaunya.

Berkas ini yang membuat tema buatan sendiri bisa disetel — warna, ukuran, dan
letak tiap angka — tanpa perlu meminjam tata letak tema lain. Isinya murni
logika: tidak ada GTK, jadi bisa diuji tanpa layar.

Tiga hal yang ditemukan dari membaca kode upstream dan wajib dipegang di sini:

1. **Nama daunnya tidak seragam.** CPU dan GPU memakai `TEXT`, tetapi RAM dan
   disk memakai `PERCENT_TEXT` (`library/stats.py` memanggil
   `display_themed_percent_value` pada `MEMORY.VIRTUAL.PERCENT_TEXT` dan
   `DISK.USED.PERCENT_TEXT`). Menyusun jalur dengan menempelkan `"TEXT"` akan
   menghasilkan tema yang CPU/GPU-nya muncul dan RAM/disk-nya diam saja, tanpa
   pesan galat. Karena itu jalur lengkapnya disimpan sebagai data.

2. **`INTERVAL` letaknya berbeda-beda.** Di CPU dia ada di dalam tiap metrik
   (`CPU.PERCENTAGE.INTERVAL`), sedangkan di GPU, RAM, disk, dan tanggal dia
   ada di tingkat perangkat (`GPU.INTERVAL`). Ini juga disimpan sebagai data.

3. **`BACKGROUND_IMAGE` bukan hiasan, itu mekanisme penghapusnya.**
   `lcd_comm.DisplayText` menggambar teks di atas salinan berkas itu lalu
   memotongnya sebesar teks. Tanpa kunci itu, yang dikirim ke panel adalah
   kotak warna solid — angkanya jadi bertumpuk kotak di atas foto.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

import lcd_konfig as lk

KANVAS_BAKU = (480, 480)
UKURAN_LAYAR = '2.1"'

# Tema yang dibuat lewat editor ini ditandai di baris `author:`. Penandanya
# dipakai untuk memutuskan tema mana yang aman dibuka lagi di editor: hanya
# tema yang kita tulis sendiri yang bentuk YAML-nya kita ketahui persis, jadi
# hanya itu yang bisa dibaca balik tanpa menghilangkan apa pun. Tema bawaan
# dan tema impor punya grafik, radial, dan bagian lain yang tidak dimodelkan
# di sini — membukanya di editor akan membuang bagian-bagian itu.
PENANDA = "aio-lcd"

FONT_BAKU = "jetbrains-mono/JetBrainsMono-Bold.ttf"

FONT_PILIHAN = (
    ("JetBrains Mono Tebal", "jetbrains-mono/JetBrainsMono-Bold.ttf"),
    ("JetBrains Mono", "jetbrains-mono/JetBrainsMono-Regular.ttf"),
    ("Roboto Mono Tebal", "roboto-mono/RobotoMono-Bold.ttf"),
    ("Roboto Mono", "roboto-mono/RobotoMono-Regular.ttf"),
    ("Roboto Tebal", "roboto/Roboto-Bold.ttf"),
    ("GeForce", "geforce/GeForce-Bold.ttf"),
    ("Generale Mono", "generale-mono/GeneraleMonoA.ttf"),
    ("Cubic 11 (piksel)", "Cubic_11/Cubic_11.ttf"),
)


class GalatTataLetak(Exception):
    """Dilempar kalau tema tidak bisa dibaca sebagai tata letak buatan sendiri."""


@dataclass(frozen=True)
class Jenis:
    """Satu macam angka yang bisa dipasang di layar.

    `jalur` dan `jalur_interval` ditulis lengkap sampai nama daunnya karena
    upstream tidak konsisten — lihat catatan di kepala berkas.
    """

    kunci: str
    label: str                      # label bawaan yang ikut tergambar
    nama: str                       # nama yang dipakai di antarmuka
    jalur: tuple[str, ...]          # jalur di bawah STATS, termasuk nama daun
    jalur_interval: tuple[str, ...]  # jalur kunci INTERVAL, juga di bawah STATS
    contoh: str                     # nilai contoh, persis sebagaimana upstream memformatnya
    interval: int = 1


# Nilai contoh ditulis persis seperti yang dihasilkan `display_themed_value`:
# `"{:>min_size}".format(nilai)` lalu satuannya ditempel. Persen memakai
# min_size 3, jadi selalu selebar empat karakter termasuk "%" — itulah sebabnya
# angka yang turun dari 100% ke 9% tidak menyisakan sisa glif.
# Urutannya bukan selera: ini urutan upstream menggambar. `library/stats.py`
# memanggil CPU persen → frekuensi → suhu, lalu GPU persen → memori → suhu,
# lalu RAM, disk, tanggal, jam. Berkas tema **tidak punya** cara menyatakan
# urutan gambar — yang berlaku urutan kode upstream — jadi dua angka yang
# bertindihan akan tersusun menurut daftar ini, bukan menurut urutan orang
# menambahkannya. Pratinjau ikut urutan ini supaya hasilnya sama.
JENIS: tuple[Jenis, ...] = (
    Jenis("cpu_persen", "CPU", "CPU — pemakaian",
          ("CPU", "PERCENTAGE", "TEXT"), ("CPU", "PERCENTAGE", "INTERVAL"), " 45%"),
    Jenis("cpu_frekuensi", "CPU", "CPU — frekuensi",
          ("CPU", "FREQUENCY", "TEXT"), ("CPU", "FREQUENCY", "INTERVAL"), "4.20 GHz"),
    Jenis("cpu_suhu", "CPU", "CPU — suhu",
          ("CPU", "TEMPERATURE", "TEXT"), ("CPU", "TEMPERATURE", "INTERVAL"), " 52°C"),
    Jenis("gpu_persen", "GPU", "GPU — pemakaian",
          ("GPU", "PERCENTAGE", "TEXT"), ("GPU", "INTERVAL"), " 78%"),
    Jenis("gpu_memori", "VRAM", "GPU — memori terpakai",
          ("GPU", "MEMORY_PERCENT", "TEXT"), ("GPU", "INTERVAL"), " 62%"),
    Jenis("gpu_suhu", "GPU", "GPU — suhu",
          ("GPU", "TEMPERATURE", "TEXT"), ("GPU", "INTERVAL"), " 61°C"),
    Jenis("ram_persen", "RAM", "RAM — pemakaian",
          ("MEMORY", "VIRTUAL", "PERCENT_TEXT"), ("MEMORY", "INTERVAL"), " 38%"),
    Jenis("disk_persen", "DISK", "Disk — terpakai",
          ("DISK", "USED", "PERCENT_TEXT"), ("DISK", "INTERVAL"), " 71%"),
    Jenis("tanggal", "", "Tanggal",
          ("DATE", "DAY", "TEXT"), ("DATE", "INTERVAL"), "12/09/2026"),
    Jenis("jam", "", "Jam",
          ("DATE", "HOUR", "TEXT"), ("DATE", "INTERVAL"), "21:04"),
)

PETA_JENIS = {j.kunci: j for j in JENIS}
URUTAN = {j.kunci: i for i, j in enumerate(JENIS)}
# Jalur dipakai sebagai kunci balik ketika membaca theme.yaml jadi tata letak.
PETA_JALUR = {j.jalur: j for j in JENIS}


@dataclass
class Elemen:
    """Satu angka beserta labelnya di atas kanvas.

    Label disimpan sebagai geseran terhadap angkanya, bukan koordinat sendiri.
    Dengan begitu menyeret angkanya membawa labelnya ikut serta — kalau
    keduanya berdiri sendiri, tiap pemindahan jadi dua pekerjaan dan labelnya
    gampang ketinggalan.
    """

    jenis: str
    x: int
    y: int
    ukuran: int = 54
    warna: tuple[int, int, int] = (235, 235, 235)
    font: str = FONT_BAKU
    label: str = ""
    label_ukuran: int = 20
    label_warna: tuple[int, int, int] | None = None   # None = ikut warna angka
    label_geser: tuple[int, int] = (0, -24)

    @property
    def info(self) -> Jenis:
        return PETA_JENIS[self.jenis]

    @property
    def warna_label(self) -> tuple[int, int, int]:
        return self.label_warna if self.label_warna is not None else self.warna

    @property
    def posisi_label(self) -> tuple[int, int]:
        return (self.x + self.label_geser[0], self.y + self.label_geser[1])


@dataclass
class TataLetak:
    elemen: list[Elemen] = field(default_factory=list)
    kanvas: tuple[int, int] = KANVAS_BAKU
    ukuran_layar: str = UKURAN_LAYAR
    orientasi: str = "portrait"
    led: tuple[int, int, int] = (40, 215, 252)

    def salin(self) -> "TataLetak":
        return replace(self, elemen=[replace(e) for e in self.elemen])

    def jenis_terpakai(self) -> set[str]:
        return {e.jenis for e in self.elemen}


# --------------------------------------------------------------------- font

def dir_font() -> Path:
    return lk.DIR_UPSTREAM / "res/fonts"


@lru_cache(maxsize=64)
def muat_font(nama: str, ukuran: int) -> ImageFont.FreeTypeFont:
    """Muat font dari klon upstream; kembali ke font bawaan PIL kalau tidak ada.

    Jatuh ke font bawaan penting untuk pengujian: uji berjalan tanpa klon
    upstream, dan pratinjau yang gagal tidak boleh menjatuhkan aplikasinya.

    Hasilnya disimpan karena pratinjau digambar ulang tiap kali angka digeser:
    tanpa singgahan, tiap bingkai seretan membuka berkas TTF sekali per elemen.
    """
    try:
        return ImageFont.truetype(str(dir_font() / nama), ukuran)
    except (OSError, ValueError):
        try:
            return ImageFont.load_default(size=ukuran)
        except TypeError:      # Pillow lama tidak menerima `size`
            return ImageFont.load_default()


# ---------------------------------------------------------------- pratinjau

def kotak(elemen: Elemen, gambar: Image.Image | None = None) -> tuple[int, int, int, int]:
    """Kotak batas angka, dihitung dengan font dan jangkar yang sama dengan panel.

    Upstream menggambar dengan anchor `lt` (`library/stats.py` meneruskan
    `theme_data.get("ANCHOR", "lt")`), jadi X/Y adalah sudut kiri-atas teks.
    """
    font = muat_font(elemen.font, elemen.ukuran)
    dasar = gambar if gambar is not None else Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dasar)
    kiri, atas, kanan, bawah = d.textbbox((elemen.x, elemen.y), elemen.info.contoh,
                                          font=font, anchor="lt")
    return (int(kiri), int(atas), int(kanan) + 1, int(bawah) + 1)


def kotak_label(elemen: Elemen) -> tuple[int, int, int, int] | None:
    if not elemen.label:
        return None
    font = muat_font(elemen.font, elemen.label_ukuran)
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    x, y = elemen.posisi_label
    kiri, atas, kanan, bawah = d.textbbox((x, y), elemen.label, font=font, anchor="lt")
    return (int(kiri), int(atas), int(kanan) + 1, int(bawah) + 1)


def _beririsan(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def bertumpuk(tata: TataLetak) -> list[tuple[int, int]]:
    """Pasangan indeks elemen yang kotaknya bersinggungan.

    Perlu diperingatkan, bukan dilarang: tiap angka menghapus kotaknya sendiri
    dari latar sebelum menggambar, jadi dua kotak yang beririsan akan saling
    menimpa tiap kali disegarkan dan yang terlihat berkedip.
    """
    kotak_semua = [kotak(e) for e in tata.elemen]
    hasil = []
    for i in range(len(kotak_semua)):
        for j in range(i + 1, len(kotak_semua)):
            if _beririsan(kotak_semua[i], kotak_semua[j]):
                hasil.append((i, j))
    return hasil


def di_luar_kanvas(tata: TataLetak) -> list[int]:
    """Indeks elemen yang kotaknya keluar dari layar.

    Upstream menegaskan X/Y <= ukuran layar lalu memotong kotaknya, jadi angka
    yang melewati tepi tidak menjatuhkan program — dia cuma terpotong. Tetap
    perlu diberitahukan karena di jendela pratinjau hal itu mudah terlewat.
    """
    lebar, tinggi = tata.kanvas
    keluar = []
    for i, e in enumerate(tata.elemen):
        kiri, atas, kanan, bawah = kotak(e)
        kotak_l = kotak_label(e)
        if kotak_l:
            kiri, atas = min(kiri, kotak_l[0]), min(atas, kotak_l[1])
            kanan, bawah = max(kanan, kotak_l[2]), max(bawah, kotak_l[3])
        if kiri < 0 or atas < 0 or kanan > lebar or bawah > tinggi:
            keluar.append(i)
    return keluar


def urut(elemen: list[Elemen]) -> list[Elemen]:
    """Susun elemen menurut urutan upstream menggambarnya.

    Perlu karena urutan di dalam `TataLetak.elemen` mengikuti urutan orang
    menyalakannya di editor, sedangkan panel menggambar menurut urutan kode
    upstream. Untuk angka yang tidak bertindihan dua-duanya sama saja; begitu
    ada yang bertumpuk, yang tampak di atas ditentukan urutan ini.
    """
    return sorted(elemen, key=lambda e: URUTAN.get(e.jenis, len(URUTAN)))


def render(tata: TataLetak, latar: Image.Image) -> Image.Image:
    """Gambar pratinjau yang sepadan dengan yang akan tampil di panel.

    Dipakai dua kali: di jendela editor, dan sebagai `preview.png` tema — jadi
    kartu tema di aplikasi memperlihatkan tata letaknya, bukan cuma fotonya.
    """
    kanvas = latar.convert("RGB").copy()
    d = ImageDraw.Draw(kanvas)
    for e in urut(tata.elemen):
        if e.label:
            d.text(e.posisi_label, e.label, font=muat_font(e.font, e.label_ukuran),
                   fill=e.warna_label, anchor="lt")
        d.text((e.x, e.y), e.info.contoh, font=muat_font(e.font, e.ukuran),
               fill=e.warna, anchor="lt")
    return kanvas


# ------------------------------------------------------------------- berkas

def _sisip(pohon: dict, jalur: tuple[str, ...], nilai) -> None:
    simpul = pohon
    for bagian in jalur[:-1]:
        simpul = simpul.setdefault(bagian, {})
    simpul[jalur[-1]] = nilai


class _Mentah(str):
    """Skalar yang ditulis apa adanya, tanpa tanda kutip.

    Dipakai untuk `FONT_COLOR: 205, 205, 205` — bentuk yang dipakai semua tema
    bawaan. `parse_color` upstream menerimanya sebagai teks lalu memecahnya di
    koma, jadi menuliskannya sebagai senarai YAML juga sah; yang ditulis di
    sini bentuk yang sama dengan tema bawaan supaya berkasnya tidak terlihat
    asing kalau dibuka orang.
    """


def _tulis(nilai, jenjang: int = 0) -> str:
    sela = "  " * jenjang
    if isinstance(nilai, dict):
        potongan = []
        for kunci, isi in nilai.items():
            if isinstance(isi, dict):
                potongan.append(f"{sela}{kunci}:\n{_tulis(isi, jenjang + 1)}")
            else:
                potongan.append(f"{sela}{kunci}: {_skalar(isi)}")
        return "\n".join(potongan)
    return f"{sela}{_skalar(nilai)}"


def _skalar(nilai) -> str:
    if isinstance(nilai, _Mentah):
        return str(nilai)
    if isinstance(nilai, bool):
        return "True" if nilai else "False"
    if isinstance(nilai, (int, float)):
        return str(nilai)
    teks = str(nilai)
    return '"' + teks.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _warna(rgb) -> _Mentah:
    r, g, b = (int(v) for v in rgb)
    return _Mentah(f"{r}, {g}, {b}")


def ke_yaml(tata: TataLetak, keterangan: str = "tata letak sendiri",
            latar: str = "background.png") -> str:
    """Susun isi theme.yaml dari sebuah tata letak.

    Ditulis lewat penyusun sendiri, bukan `yaml.safe_dump`, karena dua nilai
    harus berbentuk khusus: warna ditulis `205, 205, 205` tanpa kutip, dan
    `DISPLAY_SIZE` harus berkutip karena nilainya mengandung tanda petik
    (`2.1"`). Penyusun bawaan akan mengubah warna jadi senarai dan mengutip
    ukuran dengan petik tunggal — dua-duanya masih sah, tapi berkasnya jadi
    tidak seperti tema lain.
    """
    lebar, tinggi = tata.kanvas
    pohon: dict = {
        "author": f"{PENANDA} · {keterangan}",
        "display": {
            "DISPLAY_SIZE": tata.ukuran_layar,
            "DISPLAY_ORIENTATION": _Mentah(tata.orientasi),
            "DISPLAY_RGB_LED": _warna(tata.led),
        },
        "static_images": {
            "BACKGROUND": {"PATH": _Mentah(latar), "X": 0, "Y": 0,
                           "WIDTH": lebar, "HEIGHT": tinggi},
        },
    }

    label = {}
    for i, e in enumerate(tata.elemen):
        if not e.label:
            continue
        x, y = e.posisi_label
        label[f"LABEL_{e.jenis.upper()}_{i}"] = {
            "TEXT": e.label,
            "X": x,
            "Y": y,
            "FONT": _Mentah(e.font),
            "FONT_SIZE": e.label_ukuran,
            "FONT_COLOR": _warna(e.warna_label),
            "BACKGROUND_IMAGE": _Mentah(latar),
        }
    if label:
        pohon["static_text"] = label

    stats: dict = {}
    for e in tata.elemen:
        info = e.info
        _sisip(stats, info.jalur_interval, info.interval)
        _sisip(stats, info.jalur, {
            "SHOW": True,
            "SHOW_UNIT": True,
            "X": e.x,
            "Y": e.y,
            "FONT": _Mentah(e.font),
            "FONT_SIZE": e.ukuran,
            "FONT_COLOR": _warna(e.warna),
            # Tanpa baris ini panel menerima kotak warna solid, bukan angka
            # di atas foto. Lihat catatan di kepala berkas.
            "BACKGROUND_IMAGE": _Mentah(latar),
        })
    pohon["STATS"] = stats

    return "---\n" + _tulis(pohon) + "\n"


def milik_editor(data: dict | None) -> bool:
    """Tema ini ditulis editor kita atau bukan — dibaca dari baris `author:`."""
    if not isinstance(data, dict):
        return False
    return str(data.get("author", "")).strip().startswith(PENANDA)


def unsur_hilang(data: dict) -> list[str]:
    """Bagian tema yang tidak dimodelkan editor, dalam bahasa manusia.

    Dipakai sebagai syarat masuk, bukan sebagai peringatan setelah menyimpan.
    Editor ini cuma tahu angka berupa teks; grafik batang, radial, grafik garis,
    jaringan, dan teks tetap buatan sendiri tidak punya wakilnya di sini, jadi
    menulis ulang theme.yaml akan membuangnya.

    Hasil kosong berarti seluruh isi tema muat di model ini — maka temanya aman
    dibuka walaupun bukan tulisan editor. Itu yang membuat tema lama, yang tata
    letaknya dulu dipinjam dari tema contoh, tetap bisa disetel tanpa harus
    dibuat ulang dari awal.
    """
    hilang: list[str] = []

    def telusuri(simpul, jalur=()):
        if not isinstance(simpul, dict):
            return
        if simpul.get("SHOW") is True and jalur and jalur not in PETA_JALUR:
            hilang.append(".".join(jalur))
        for kunci, isi in simpul.items():
            if isinstance(isi, dict):
                telusuri(isi, jalur + (kunci,))

    telusuri(data.get("STATS") or {})

    # Teks tetap yang bukan label bikinan kita akan ikut hilang: penulisnya
    # cuma menulis ulang label yang cocok pola LABEL_<jenis>_<nomor>.
    for kunci in (data.get("static_text") or {}):
        bagian = str(kunci).split("_")
        if not (len(bagian) >= 3 and bagian[0] == "LABEL"
                and "_".join(bagian[1:-1]).lower() in PETA_JENIS):
            hilang.append(f"teks tetap {kunci}")

    # Gambar statis selain latar tidak ditulis ulang.
    for kunci in (data.get("static_images") or {}):
        if kunci != "BACKGROUND":
            hilang.append(f"gambar {kunci}")

    return hilang


def dapat_disunting(data: dict | None) -> bool:
    """Tema ini boleh dibuka editor atau tidak.

    Dua jalan masuk: ditulis editor ini (bentuknya sudah pasti), atau seluruh
    isinya kebetulan muat di model ini.
    """
    if not isinstance(data, dict):
        return False
    return milik_editor(data) or not unsur_hilang(data)


def _ambil(pohon: dict, jalur: tuple[str, ...]):
    simpul = pohon
    for bagian in jalur:
        if not isinstance(simpul, dict) or bagian not in simpul:
            return None
        simpul = simpul[bagian]
    return simpul


def _ke_rgb(nilai, baku=(235, 235, 235)) -> tuple[int, int, int]:
    if isinstance(nilai, (list, tuple)) and len(nilai) == 3:
        return tuple(int(v) for v in nilai)      # type: ignore[return-value]
    if isinstance(nilai, str):
        bagian = [b.strip() for b in nilai.split(",")]
        if len(bagian) == 3:
            try:
                return tuple(int(b) for b in bagian)   # type: ignore[return-value]
            except ValueError:
                pass
    return baku


def dari_yaml(data: dict) -> TataLetak:
    """Baca theme.yaml jadi tata letak.

    Ditolak kalau temanya memuat bagian yang tidak dimodelkan — grafik, radial,
    jaringan, dan sejenisnya — karena menulis ulang berkasnya akan membuang
    bagian itu diam-diam. Yang diterima: tema tulisan editor ini, atau tema mana
    pun yang seluruh isinya kebetulan muat. Lihat `unsur_hilang`.
    """
    if not dapat_disunting(data):
        raise GalatTataLetak(
            "Tema ini memuat bagian yang tidak dikenali editor: "
            + ", ".join(unsur_hilang(data)[:4])
        )

    tampilan = data.get("display") or {}
    gambar = (data.get("static_images") or {}).get("BACKGROUND") or {}
    kanvas = (int(gambar.get("WIDTH", KANVAS_BAKU[0])), int(gambar.get("HEIGHT", KANVAS_BAKU[1])))

    # Label dicocokkan balik ke angkanya lewat nama kuncinya, LABEL_<jenis>_<i>.
    label_per_jenis: dict[str, dict] = {}
    for kunci, isi in (data.get("static_text") or {}).items():
        bagian = str(kunci).split("_")
        if len(bagian) >= 3 and bagian[0] == "LABEL" and isinstance(isi, dict):
            label_per_jenis["_".join(bagian[1:-1]).lower()] = isi

    stats = data.get("STATS") or {}
    elemen: list[Elemen] = []
    for jenis in JENIS:
        simpul = _ambil(stats, jenis.jalur)
        if not isinstance(simpul, dict) or not simpul.get("SHOW"):
            continue
        e = Elemen(
            jenis=jenis.kunci,
            x=int(simpul.get("X", 0)),
            y=int(simpul.get("Y", 0)),
            ukuran=int(simpul.get("FONT_SIZE", 54)),
            warna=_ke_rgb(simpul.get("FONT_COLOR")),
            font=str(simpul.get("FONT", FONT_BAKU)),
        )
        isi_label = label_per_jenis.get(jenis.kunci)
        if isi_label:
            e.label = str(isi_label.get("TEXT", ""))
            e.label_ukuran = int(isi_label.get("FONT_SIZE", 20))
            e.label_warna = _ke_rgb(isi_label.get("FONT_COLOR"), e.warna)
            e.label_geser = (int(isi_label.get("X", e.x)) - e.x,
                             int(isi_label.get("Y", e.y)) - e.y)
        elemen.append(e)

    return TataLetak(
        elemen=elemen,
        kanvas=kanvas,
        ukuran_layar=str(tampilan.get("DISPLAY_SIZE", UKURAN_LAYAR)),
        orientasi=str(tampilan.get("DISPLAY_ORIENTATION", "portrait")),
        led=_ke_rgb(tampilan.get("DISPLAY_RGB_LED"), (40, 215, 252)),
    )


def baca_tema(dir_tema: Path) -> TataLetak:
    """Muat tata letak sebuah folder tema."""
    berkas = Path(dir_tema) / "theme.yaml"
    try:
        with berkas.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as galat:
        raise GalatTataLetak(f"Tidak bisa membaca {berkas}: {galat}") from galat
    if not isinstance(data, dict):
        raise GalatTataLetak(f"{berkas} tidak berisi tema")
    return dari_yaml(data)


def tulis_tema(dir_tema: Path, tata: TataLetak, keterangan: str = "tata letak sendiri") -> None:
    """Tulis ulang theme.yaml dan preview.png sebuah tema.

    Latarnya tidak ikut disentuh: background.png sudah ada sejak temanya dibuat,
    dan pratinjaunya digambar ulang dari latar itu supaya kartu tema di
    aplikasi selalu memperlihatkan tata letak yang berlaku.
    """
    dir_tema = Path(dir_tema)
    isi = ke_yaml(tata, keterangan=keterangan)

    sementara = dir_tema / "theme.yaml.baru"
    sementara.write_text(isi, encoding="utf-8")
    os.replace(sementara, dir_tema / "theme.yaml")

    latar = dir_tema / "background.png"
    if latar.is_file():
        try:
            with Image.open(latar) as im:
                render(tata, im).save(dir_tema / "preview.png")
        except OSError:
            pass       # pratinjau cuma hiasan; kegagalannya tidak boleh membatalkan penyimpanan


# ------------------------------------------------------------------ contoh

def _grid(jenis: list[str], kanvas=KANVAS_BAKU, ukuran=54, label_ukuran=20) -> list[Elemen]:
    """Susun elemen dalam petak 2 kolom yang terpusat di kanvas."""
    lebar, tinggi = kanvas
    baris = (len(jenis) + 1) // 2
    tinggi_sel = tinggi / (baris + 1)
    hasil = []
    for i, kunci in enumerate(jenis):
        kolom, brs = i % 2, i // 2
        x = int(lebar * (0.17 if kolom == 0 else 0.55))
        y = int(tinggi_sel * (brs + 1) - ukuran * 0.35)
        hasil.append(Elemen(jenis=kunci, x=x, y=y, ukuran=ukuran,
                            label=PETA_JENIS[kunci].label, label_ukuran=label_ukuran,
                            label_geser=(2, -(label_ukuran + 6))))
    return hasil


def _kolom(jenis: list[str], kanvas=KANVAS_BAKU, ukuran=48) -> list[Elemen]:
    lebar, tinggi = kanvas
    langkah = tinggi / (len(jenis) + 1)
    return [
        Elemen(jenis=k, x=int(lebar * 0.42), y=int(langkah * (i + 1) - ukuran * 0.5),
               ukuran=ukuran, label=PETA_JENIS[k].label, label_ukuran=22,
               label_geser=(-int(lebar * 0.28), int(ukuran * 0.28)))
        for i, k in enumerate(jenis)
    ]


def _baris_bawah(jenis: list[str], kanvas=KANVAS_BAKU, ukuran=38) -> list[Elemen]:
    lebar, tinggi = kanvas
    langkah = lebar / len(jenis)
    return [
        Elemen(jenis=k, x=int(langkah * i + langkah * 0.5 - ukuran * 1.1),
               y=int(tinggi * 0.86), ukuran=ukuran,
               label=PETA_JENIS[k].label, label_ukuran=18, label_geser=(6, -22))
        for i, k in enumerate(jenis)
    ]


def _sudut(jenis: list[str], kanvas=KANVAS_BAKU, ukuran=44) -> list[Elemen]:
    lebar, tinggi = kanvas
    tepi = int(min(lebar, tinggi) * 0.07)
    pojok = [
        (tepi, tepi, (2, -0)),
        (lebar - tepi - int(ukuran * 2.6), tepi, (2, 0)),
        (tepi, tinggi - tepi - ukuran, (2, 0)),
        (lebar - tepi - int(ukuran * 2.6), tinggi - tepi - ukuran, (2, 0)),
    ]
    hasil = []
    for i, k in enumerate(jenis[:4]):
        x, y, _ = pojok[i]
        atas = i < 2
        hasil.append(Elemen(jenis=k, x=x, y=y, ukuran=ukuran,
                            label=PETA_JENIS[k].label, label_ukuran=18,
                            label_geser=(2, -24 if not atas else int(ukuran * 1.05))))
    return hasil


EMPAT = ["cpu_persen", "gpu_persen", "ram_persen", "disk_persen"]

CONTOH: tuple[tuple[str, str, "callable"], ...] = (
    ("grid", "Petak 2×2", lambda kanvas: _grid(EMPAT, kanvas)),
    ("kolom", "Satu kolom", lambda kanvas: _kolom(EMPAT, kanvas)),
    ("bawah", "Baris bawah", lambda kanvas: _baris_bawah(EMPAT, kanvas)),
    ("sudut", "Empat sudut", lambda kanvas: _sudut(EMPAT, kanvas)),
    ("suhu", "Pemakaian + suhu", lambda kanvas: _grid(
        ["cpu_persen", "gpu_persen", "cpu_suhu", "gpu_suhu"], kanvas)),
    ("jam", "Jam besar + empat angka", lambda kanvas: (
        [Elemen(jenis="jam", x=int(kanvas[0] * 0.13), y=int(kanvas[1] * 0.16),
                ukuran=96, label="", label_ukuran=20)]
        + _baris_bawah(EMPAT, kanvas))),
    ("kosong", "Kosong (atur sendiri)", lambda kanvas: []),
)

PETA_CONTOH = {kunci: (nama, buat) for kunci, nama, buat in CONTOH}


def contoh(kunci: str, kanvas=KANVAS_BAKU, warna=(235, 235, 235),
           font: str = FONT_BAKU) -> TataLetak:
    """Bangun tata letak siap pakai.

    Ada supaya orang tidak perlu mulai dari kanvas kosong: menempatkan angka
    dari nol itu pekerjaan yang membosankan, dan hasil pertama yang langsung
    kelihatan benar jauh lebih mudah disetel daripada layar kosong.
    """
    if kunci not in PETA_CONTOH:
        raise GalatTataLetak(f"Tata letak contoh {kunci!r} tidak ada")
    elemen = PETA_CONTOH[kunci][1](kanvas)
    for e in elemen:
        e.warna = warna
        e.font = font
        if e.label_warna is not None:
            e.label_warna = warna
    return TataLetak(elemen=elemen, kanvas=kanvas)


# ------------------------------------------------- warna yang enak dibaca

def warna_kontras(latar: Image.Image) -> tuple[int, int, int]:
    """Pilih putih atau hitam menurut terang-gelapnya latar.

    Nilai bawaan yang buta warna latar bikin angka putih di atas foto pantai
    ikut hilang. Ini bukan pemilihan warna yang canggih — cuma menghindarkan
    hasil pertama yang tidak terbaca sama sekali.
    """
    kecil = latar.convert("RGB").resize((32, 32))
    piksel = list(kecil.getdata())
    terang = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in piksel) / len(piksel)
    return (25, 25, 25) if terang > 140 else (240, 240, 240)
