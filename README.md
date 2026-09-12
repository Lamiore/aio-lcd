# aio-lcd

Bikin layar LCD pendingin **ID-Cooling SL360 PRO SE** jalan di Linux, plus
aplikasi kecil buat ganti-ganti temanya.

App resmi bawaan pendinginnya (**Space Control**) cuma ada di Windows. Tapi
layarnya sendiri bukan bikinan ID-Cooling — itu panel **Turing Smart Screen
2.1"** yang di-rebrand, dan panel itu punya dukungan sumber terbuka lewat
[turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python).

Repo ini **bukan** salinan proyek itu. Isinya cuma perekat yang bikin dia jalan
di mesin ini: konfigurasi, izin perangkat, autostart, dan pemilih temanya.

## Panelnya ngaku apa

Diperiksa lewat USB, bukan ditebak dari nama produk:

| keadaan | id | serial |
|---|---|---|
| tidur | `1a86:ca21` | `CT21INCH` |
| bangun | `1d6b:0121` | `20080411` |

Firmware melapor `chs_5inch.dev1_rom1.89`, sub-revisi `REV_2INCH`. Di
`config.yaml` ini berarti `REVISION: C`.

Yang bikin yakin bukan tebakan: `CT21INCH` dan `1a86:ca21` **tertulis harfiah**
di `library/lcd/lcd_comm_rev_c.py:142-158` milik upstream.

## Pasang

```bash
git clone <repo-ini> ~/workspace/projects/aio-lcd
cd ~/workspace/projects/aio-lcd
./pasang.sh
```

Skripnya aman dijalankan berulang — langkah yang sudah beres dilewati. Yang
butuh `sudo` cuma satu: menulis udev rule.

Kalau klon upstream mau ditaruh di tempat lain, setel `AIO_LCD_UPSTREAM`.

## Aplikasi tema

```bash
./tema-lcd.py
```

Atau lewat daftar aplikasi GNOME: **Tema LCD AIO**.

GTK4 + libadwaita, jalan dengan **Python sistem** (bukan venv upstream) karena
`gi` cuma ada di sana. Isinya: petak preview tema, sakelar balik 180°, dan
tombol Terapkan yang menulis config lalu me-restart service.

Defaultnya cuma menampilkan tema yang ukurannya `2.1"` — dari 79 tema bawaan
upstream, cuma 5 yang pas. Tema ukuran lain tetap mau dimuat, tapi tata
letaknya melenceng, bukan menolak jalan. Ada sakelar buat menampilkan semuanya.

`Terapkan` menunggu sampai log service memuat `Starting system monitoring`
sebelum melapor berhasil. Ini disengaja: systemd bilang `active` dalam
milidetik, sementara layarnya baru tergambar belasan detik kemudian setelah
panel dibangunkan dan port serialnya pindah.

### Kenapa tidak pakai `configure.py` bawaan upstream

Dia sebenarnya sudah punya pemilih tema lengkap dengan preview. Tapi tombol
**Save and run**-nya memanggil `subprocess.Popen(main.py)` **tanpa mematikan
instance yang sedang jalan** (`configure.py:616-630`). Dengan service systemd
hidup, itu bikin dua proses berebut port serial.

Buat setelan lain dia tetap berguna — matikan dulu service-nya:

```bash
systemctl --user stop aio-lcd
~/workspace/projects/turing-smart-screen-python/.venv/bin/python \
  ~/workspace/projects/turing-smart-screen-python/configure.py
systemctl --user start aio-lcd
```

## Dua jebakan yang memakan waktu

**1. Udev rule ber-`uaccess` wajib bernomor < 73.** Tag `uaccess` dikonsumsi
`/usr/lib/udev/rules.d/73-seat-late.rules`, jadi rule bernomor `99-` memasang
tagnya terlalu telat — ACL-nya tidak pernah terbentuk, **tanpa pesan galat apa
pun**. Rule-nya kelihatan "kepakai" (GROUP berubah jadi `dialout`) tapi izinnya
tetap ditolak. Semua rule uaccess bawaan systemd bernomor ≤ 71.

Memastikannya bukan dari `ls -l`, tapi dari ACL-nya:

```bash
getfacl -p /dev/ttyACM1 | grep '^user:'   # harus ada user:<nama>:rw-
```

`uaccess` dipilih ketimbang `usermod -aG dialout` karena berlaku seketika lewat
ACL sesi — grup baru perlu logout-login dulu.

Rule di sini menutup **empat** id, bukan satu, karena panelnya ganti identitas
saat dibangunkan. Menutup keadaan tidur saja bikin auto-deteksi putus di tengah.

**2. `COM_PORT` biarkan `AUTO`.** `/dev/ttyACM1` itu keadaan tidur dan bukan
port yang dipakai bicara — saat bangun dia pindah ke `/dev/ttyACM0`.
Mematoknya di config bikin gagal terus.

Soal `THEME` yang nama temanya angka semua (26, 30, ...): nilainya harus berupa
string, karena YAML membaca `26` polos sebagai integer dan upstream gagal dengan
`Theme not found or contains errors!`. `tema-lcd.py` selalu menulisnya berkutip,
dan `configure.py` bawaan juga aman (ruamel mengutip sendiri). Yang berbahaya
cuma menyuntingnya dengan tangan.

## Isi repo

| | |
|---|---|
| `tema-lcd.py` | aplikasi GTK4 pemilih tema |
| `lcd_konfig.py` | logika: baca/tulis config, pendataan tema, kendali service |
| `uji_lcd_konfig.py` | uji buat logika di atas — `python3 uji_lcd_konfig.py` |
| `pasang.sh` | pemasang, aman diulang |
| `config/config.yaml` | konfigurasi upstream yang sudah disetel |
| `udev/` | rule izin port serial |
| `systemd/` | templat unit autostart |
| `desktop/` | templat peluncur aplikasi |

`lcd_konfig.py` sengaja tidak memakai ruamel.yaml walaupun upstream memakainya:
Python sistem tidak menyediakannya, dan penyuntingan baris bertarget menjaga
komentar `config.yaml` utuh persis tanpa perlu dependensi tambahan.

## Yang belum teruji

- **Belum pernah lewat reboot sungguhan.** Rancangannya sudah menanganinya
  (`Restart=always` + `RestartSec=10` + `StartLimitIntervalSec=0`, jadi
  percobaan pertama yang kena izin-belum-siap tinggal diulang), tapi belum
  disaksikan.
- **Suspend/resume belum diuji, dan ini yang paling mungkin patah.** Panelnya
  ganti identitas USB tiap bangun. `Restart=always` cuma menolong kalau
  prosesnya keluar; kalau `main.py` menggantung memegang fd basi, systemd tetap
  melaporkan `active` padahal layarnya beku. Obatnya
  `systemctl --user restart aio-lcd`.
