# LCD pendingin AIO ID-Cooling di Linux — driver, autostart, dan pengelola tema

Pendingin AIO **ID-COOLING SL360 PRO SE** punya layar LCD 2,1 inci, tapi aplikasi
resminya (**ID-COOLING Space Control**) cuma jalan di Windows. Repo ini bikin
layar itu hidup di Linux: menampilkan CPU/GPU/RAM/suhu, nyala sendiri saat login,
dan punya aplikasi GTK untuk ganti tema, bikin tema dari gambar sendiri, dan
impor tema orang lain.

> **Kuncinya: layar itu bukan buatan ID-Cooling.** Itu panel **Turing Smart
> Screen 2,1"** yang di-rebrand, dan panel itu sudah didukung proyek sumber
> terbuka [turing-smart-screen-python][upstream]. Begitu tahu itu, sisanya cuma
> soal menyambungkan. Kalau kamu sampai di sini lewat pencarian "ID-Cooling LCD
> Linux" — mulai dari bagian [Apakah punyamu sama?](#apakah-punyamu-sama).

Repo ini **bukan** salinan proyek itu. Isinya perekat di sekelilingnya:
konfigurasi, izin perangkat, autostart, dan aplikasi temanya.

![status](https://img.shields.io/badge/diuji-Fedora%2044%20·%20GNOME%2050%20Wayland-blue)

---

## Apakah punyamu sama?

Colok layarnya, lalu:

```bash
lsusb | grep -i -E "1a86:ca21|UsbMonitor"
```

Kalau muncul `1a86:ca21 QinHeng Electronics UsbMonitor`, kemungkinan besar iya.
Pastikan lagi:

```bash
for d in /sys/bus/usb/devices/*/; do
  [ "$(cat $d/idVendor 2>/dev/null)" = "1a86" ] && cat $d/manufacturer $d/product $d/serial 2>/dev/null
done
```

Yang dicari: `Turing` / `UsbMonitor` / `CT21INCH`.

Panel ini berganti identitas USB saat dibangunkan — penting untuk izin
perangkat nanti:

| keadaan | VID:PID | serial |
|---|---|---|
| tidur | `1a86:ca21` | `CT21INCH` |
| bangun | `1d6b:0121` | `20080411` |

Firmware melapor `chs_5inch.dev1_rom1.89`, sub-revisi `REV_2INCH`. Di upstream
ini berarti **`REVISION: C`**.

Bukan tebakan dari nama produk: `CT21INCH` dan `1a86:ca21` tertulis harfiah di
[`library/lcd/lcd_comm_rev_c.py`][revc] baris 142–158 milik upstream.

**Kalau angkamu beda,** repo ini tetap berguna sebagai contoh — tapi cek dulu
[daftar revisi hardware][revisi] upstream, lalu ganti `REVISION:` di
`config/config.yaml` sesuai model layarmu. Panel 2,8"/5"/8,8" juga rev C.

---

## Pasang

Butuh: Python 3.9+, `git`, dan akses `sudo` sekali (untuk aturan udev).

```bash
git clone https://github.com/Lamiore/aio-lcd.git ~/workspace/projects/aio-lcd
cd ~/workspace/projects/aio-lcd
./pasang.sh
```

Skripnya aman dijalankan berulang — langkah yang sudah beres dilewati, bukan
diulang. Yang dikerjakan:

1. klon [turing-smart-screen-python][upstream] (`--depth 1`)
2. bikin venv + pasang dependensinya
3. salin `config.yaml` yang sudah disetel
4. pasang ulang tema buatan sendiri (kalau ada dari pemasangan sebelumnya)
5. pasang aturan udev — **satu-satunya langkah yang minta `sudo`**
6. pasang & nyalakan service autostart
7. pasang peluncur aplikasi

Klon upstream mau ditaruh di tempat lain? Setel `AIO_LCD_UPSTREAM`.

Bukti berhasil bukan dari status systemd, tapi dari log ini:

```bash
journalctl --user -u aio-lcd -f | grep "Starting system monitoring"
```

---

## Aplikasi tema

```bash
./tema-lcd.py          # atau: cari "Tema LCD AIO" di daftar aplikasi
```

GTK4 + libadwaita, jalan dengan **Python sistem** (bukan venv upstream), karena
`gi` cuma ada di sana. Yang bisa dilakukan:

- **Ganti tema** — petak pratinjau, klik, Terapkan.
- **Balik 180°** — kalau blok pompanya terpasang terbalik seperti punya saya.
- **Bikin tema dari gambar sendiri** — pilih foto apa pun, dipotong-tengah ke
  ukuran kanvas, jadi latar tema baru.
- **Impor tema** dari folder atau `.zip`.
- **Duplikat** tema yang ada untuk diutak-atik tanpa merusak aslinya.
- **Hapus** — hanya tema buatan sendiri; tema bawaan dan tema yang sedang
  dipakai layar ditolak.

Defaultnya cuma menampilkan tema berukuran `2.1"`. Dari 79 tema bawaan upstream,
cuma 5 yang pas; tema ukuran lain tetap mau dimuat tapi tata letaknya melenceng.
Ada sakelar untuk menampilkan semuanya.

### Tema buatan sendiri disimpan di luar klon upstream

Di `~/.local/share/aio-lcd/themes/`, lalu di-symlink ke `res/themes/` milik
upstream. Sebabnya `pasang.sh` bisa mengklon ulang upstream, dan apa pun yang
ditaruh langsung di sana akan ikut lenyap. Upstream mendata tema dengan
`is_dir()` dan memuatnya lewat jalur berkas — dua-duanya mengikuti symlink
(diuji, bukan diandaikan).

Efek sampingnya berguna: entri `res/themes/` yang berupa symlink **pasti** tema
buatan sendiri, jadi tidak perlu penanda apa pun untuk tahu mana yang aman
dihapus.

### Tata letak tema baru dipinjam, bukan dibuat dari nol

Saat bikin tema dari gambar, kamu memilih satu tema yang ada sebagai contoh
tata letak; yang diganti cuma latarnya. Menaruh angka di koordinat yang pas itu
pekerjaan penyunting visual tersendiri, dan meminjam tata letak yang sudah
terbukti muat di layar ini jauh lebih murah — hasilnya dijamin tidak melenceng.
Ukuran kanvasnya pun dibaca dari latar tema contoh, bukan dari tabel hafalan,
jadi ukuran layar berapa pun ikut benar.

### Kenapa tidak pakai `configure.py` bawaan upstream

Upstream sebenarnya sudah punya pemilih tema lengkap dengan pratinjau. Tapi
tombol **Save and run**-nya memanggil `subprocess.Popen(main.py)` **tanpa
mematikan instance yang sedang jalan** (`configure.py:616-630`). Dengan service
systemd hidup, itu bikin dua proses berebut port serial.

Untuk setelan lain dia tetap berguna — matikan dulu service-nya:

```bash
systemctl --user stop aio-lcd
~/workspace/projects/turing-smart-screen-python/.venv/bin/python \
  ~/workspace/projects/turing-smart-screen-python/configure.py
systemctl --user start aio-lcd
```

---

## Soal GIF animasi

Panel ini **bisa**, tapi ada batasnya, dan batasnya sudah diukur langsung di
perangkat — bukan diperkirakan:

| ukuran | fps | laju data |
|---|---|---|
| 480×480 (layar penuh) | **2,9** | 1,9 MB/dtk |
| 240×240 | **15,2** | 2,5 MB/dtk |
| 120×120 | **56,5** | 2,3 MB/dtk |

Jalur datanya ~2–2,5 MB/detik dan fps turun sebanding luas area. Jadi GIF layar
penuh itu salindia, bukan animasi; GIF 240×240 di tengah dapat 15 fps yang
sudah terasa mulus.

Ada satu kenyataan keras: **cuma satu proses yang boleh memegang port serial.**
Selama GIF diputar, `main.py` yang menggambar statistik harus mati — jadi GIF
dan angka suhu tidak bisa tampil bersamaan kecuali satu program menggambar
dua-duanya sendiri.

### Cara memutarnya

Lewat aplikasi: tombol `+` › **Putar GIF…**. Setelah memilih berkas, kamu
memilih ukuran tayang, dan dialognya menyebut berapa fps yang diminta GIF-nya
dan berapa yang sanggup dikirim panel — jadi kamu tahu hasilnya bakal mulus
atau tersendat **sebelum** memutar.

Lewat baris perintah:

```bash
systemctl --user stop aio-lcd
<upstream>/.venv/bin/python gif_pemutar.py --gif anu.gif --ukuran 240
```

Pemutarnya **wajib** memakai Python venv upstream — pyserial dan pustaka
panelnya cuma ada di sana, tidak di Python sistem.

Diukur di perangkat dengan GIF 24 bingkai: **15,6 fps** di 240×240 dan
**3,0 fps** di layar penuh — cocok dengan tabel di atas. Perkiraan yang
ditampilkan aplikasi sengaja dibuat lebih rendah dari kenyataan supaya tidak
pernah menjanjikan lebih dari yang bisa ditepati.

Aplikasi menjalankannya sebagai unit sementara (`systemd-run --user`), bukan
subprocess biasa, supaya statusnya tetap terbaca `systemctl` walau aplikasinya
ditutup. `ExecStopPost` pada unit itu menyalakan kembali service monitor —
bukan sekadar bergantung pada blok `finally` pemutar, karena pustaka upstream
memanggil `os._exit(0)` kalau panel gagal dibuka, dan itu **melewati**
`finally`.

Kalau suatu saat GIF berhenti tapi statistiknya tidak kembali:

```bash
systemctl --user start aio-lcd
```

---

## Dua jebakan yang memakan waktu

Dua-duanya gagal **tanpa pesan galat**, jadi ditulis di sini supaya tidak ada
yang mengulang.

### 1. Aturan udev ber-`uaccess` wajib bernomor di bawah 73

Tag `uaccess` dikonsumsi `/usr/lib/udev/rules.d/73-seat-late.rules`:

```
TAG=="uaccess", ENV{MAJOR}!="", RUN{builtin}+="uaccess"
```

Builtin itu hanya berjalan untuk tag yang sudah terpasang **sebelum** nomor 73.
Aturan bernomor `99-` memasang tagnya terlalu telat — **ACL-nya tidak pernah
terbentuk, dan tidak ada galat apa pun**. Aturannya kelihatan "kepakai" (GROUP
berubah jadi `dialout`) tapi izinnya tetap ditolak. Semua aturan uaccess bawaan
systemd bernomor ≤ 71.

Memastikannya bukan dari `ls -l`, tapi dari ACL-nya:

```bash
getfacl -p /dev/ttyACM0 | grep '^user:'    # harus ada user:<nama>:rw-
```

Tanda `+` di ujung mode (`crw-rw----+`) artinya ACL-nya ada.

`uaccess` dipilih ketimbang `usermod -aG dialout` karena berlaku seketika lewat
ACL sesi — grup baru butuh logout-login dulu.

Aturan di repo ini menutup **empat** ID, bukan satu, karena panelnya berganti
identitas saat dibangunkan. Menutup keadaan tidur saja bikin auto-deteksi putus
di tengah jalan.

### 2. `COM_PORT` biarkan `AUTO`

`/dev/ttyACM1` itu keadaan tidur dan **bukan** port yang dipakai bicara — saat
bangun panelnya pindah ke `/dev/ttyACM0`. Mematoknya di config bikin gagal terus.

### Catatan kecil: nama tema yang berupa angka

Tema 2,1" bernama angka semua (26, 30, 43, 44, 45). Nilai `THEME` harus berupa
string, karena YAML membaca `26` polos sebagai integer dan upstream gagal dengan
`Theme not found or contains errors!`. Aplikasi di repo ini selalu menulisnya
berkutip, dan `configure.py` bawaan juga aman. Yang berbahaya cuma menyuntingnya
dengan tangan.

---

## Isi repo

| | |
|---|---|
| `tema-lcd.py` | aplikasi GTK4: pilih, bikin, impor, duplikat, hapus tema; putar GIF |
| `lcd_konfig.py` | baca/tulis `config.yaml`, pendataan tema, kendali service |
| `lcd_tema.py` | pembuatan tema, impor, symlink, penghapusan |
| `lcd_gif.py` | pembacaan bingkai GIF, perkiraan fps |
| `gif_pemutar.py` | pemutar GIF — jalan dengan venv upstream |
| `uji_*.py` | 70 uji — `for f in uji_*.py; do python3 $f; done` |
| `pasang.sh` | pemasang, aman dijalankan berulang |
| `config/config.yaml` | konfigurasi upstream yang sudah disetel |
| `udev/` | aturan izin port serial |
| `systemd/`, `desktop/` | templat unit autostart & peluncur |

`lcd_konfig.py` sengaja tidak memakai `ruamel.yaml` walaupun upstream memakainya:
Python sistem tidak menyediakannya, dan penyuntingan baris bertarget menjaga
komentar `config.yaml` utuh persis tanpa dependensi tambahan.

---

## Yang belum teruji

Ditulis terbuka supaya tidak ada yang mengira ini sudah dicoba:

- **Belum pernah lewat reboot sungguhan.** Rancangannya sudah menanganinya
  (`Restart=always` + `RestartSec=10` + `StartLimitIntervalSec=0`, jadi
  percobaan pertama yang kena izin-belum-siap tinggal diulang), tapi belum
  disaksikan.
- **Suspend/resume belum diuji, dan ini yang paling mungkin patah.** Panelnya
  berganti identitas USB tiap bangun. `Restart=always` hanya menolong kalau
  prosesnya keluar; kalau `main.py` menggantung memegang deskriptor basi,
  systemd tetap melaporkan `active` padahal layarnya beku. Obatnya
  `systemctl --user restart aio-lcd`.
- Diuji cuma di **Fedora 44 / GNOME 50 / Wayland**, Python 3.14.

Kalau kamu mencobanya di distro atau model pendingin lain, silakan buka issue —
terutama kalau angka USB-nya berbeda.

---

## Lisensi

**GPL-3.0**, mengikuti [turing-smart-screen-python][upstream]. `config/config.yaml`
adalah salinan berkas konfigurasi upstream, jadi repo ini memuat karya turunan
proyek GPL — lisensi yang sama dipakai supaya statusnya jelas.

## Terima kasih

Pekerjaan beratnya milik [mathoudebine/turing-smart-screen-python][upstream] —
protokol, driver, dan temanya dari sana. Repo ini cuma menyambungkannya ke satu
pendingin dan satu desktop.

[upstream]: https://github.com/mathoudebine/turing-smart-screen-python
[revc]: https://github.com/mathoudebine/turing-smart-screen-python/blob/main/library/lcd/lcd_comm_rev_c.py
[revisi]: https://github.com/mathoudebine/turing-smart-screen-python/wiki/Hardware-revisions
