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
[![lisensi](https://img.shields.io/badge/lisensi-GPL--3.0-blue)](LICENSE)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![GTK4](https://img.shields.io/badge/GTK4-libadwaita-4A86CF?logo=gtk&logoColor=white)

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
  ukuran kanvas, lalu **atur sendiri angka pemantauannya** di editor tata letak.
- **Sunting tata letak** tema yang sudah dibuat, kapan saja.
- **Impor tema** dari folder atau `.zip`.
- **Duplikat** tema yang ada untuk diutak-atik tanpa merusak aslinya.
- **Hapus** — hanya tema buatan sendiri; tema bawaan dan tema yang sedang
  dipakai layar ditolak.
- **Bersihkan tema ukuran lain** — buang tema bawaan yang bukan `2.1"`.

Defaultnya cuma menampilkan tema berukuran `2.1"`. Dari 74 tema bawaan upstream,
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

## Editor tata letak

Setelah memilih gambar, angka pemantauannya diatur sendiri: **warna, ukuran,
huruf, dan letak** tiap angka, plus labelnya. Angka diseret langsung di
pratinjau; tombol panah menggeser satu piksel, Shift+panah sepuluh.

Yang bisa dipasang: CPU (pemakaian, frekuensi, suhu), GPU (pemakaian, memori,
suhu), RAM, disk, tanggal, dan jam. Ada tujuh susunan siap pakai sebagai titik
awal — petak 2×2, satu kolom, baris bawah, empat sudut, dan seterusnya — karena
mulai dari kanvas kosong itu pekerjaan yang membosankan.

Tema yang dibuat begini bisa **dibuka lagi** lewat *Sunting tata letak…*.

### Pratinjaunya digambar penggambar yang sama dengan `preview.png`

Bukan digambar ulang dengan Cairo atau Pango. Dua penggambar berarti dua hasil,
dan yang terlihat waktu menyetel harus sama persis dengan yang keluar di panel.
Satu bingkai butuh ~1,2 ms, jadi menggambar ulang seluruh kanvas tiap kali
kursor bergerak masih jauh di bawah anggaran 60 fps — tidak perlu jalur cepat
terpisah, dan itu yang menjaga pratinjaunya jujur.

`preview.png` tema pun digambar dengan tata letaknya, bukan disalin dari latar,
jadi kartu tema di aplikasi memperlihatkan tata letak yang sebenarnya.

### Tiga hal di berkas tema yang gagalnya tidak berisik

Ketiganya ditemukan dengan membaca kode upstream, dan masing-masing punya uji
sendiri di `uji_lcd_tataletak.py`:

1. **Nama daunnya tidak seragam.** CPU dan GPU memakai `TEXT`, tetapi RAM dan
   disk memakai `PERCENT_TEXT` — `library/stats.py` memanggil
   `display_themed_percent_value` pada `MEMORY.VIRTUAL.PERCENT_TEXT` dan
   `DISK.USED.PERCENT_TEXT`. Menyusun jalur dengan menempelkan `"TEXT"`
   menghasilkan tema yang tetap dimuat tanpa keluhan, cuma dua angkanya tidak
   pernah muncul.
2. **`INTERVAL` letaknya berbeda-beda.** Di CPU ada di dalam tiap metrik
   (`CPU.PERCENTAGE.INTERVAL`); di GPU, RAM, disk, dan tanggal ada di tingkat
   perangkat (`GPU.INTERVAL`). Upstream memutuskan menggambar atau tidak dari
   nilai itu, jadi salah tempat berarti angkanya diam.
3. **`BACKGROUND_IMAGE` bukan hiasan, itu mekanisme penghapusnya.**
   `lcd_comm.DisplayText` menggambar teks di atas salinan berkas itu lalu
   memotongnya sebesar teks. Tanpa kunci itu yang dikirim ke panel kotak warna
   solid — angkanya jadi bertumpuk kotak putih di atas foto.

Berkas tema juga **tidak punya cara menyatakan urutan gambar**: yang berlaku
urutan kode upstream (CPU persen → frekuensi → suhu, lalu GPU, RAM, disk,
tanggal, jam). Katalog jenis di `lcd_tataletak.py` disusun mengikuti urutan itu
supaya dua angka yang bertindihan tampil sama seperti di panel.

### Buktinya: digambar ulang lewat kode upstream sendiri

```bash
~/workspace/projects/turing-smart-screen-python/.venv/bin/python \
  periksa_tema.py <nama-tema> -o /tmp/hasil.png --banding <preview.png>
```

`periksa_tema.py` memakai backend layar tiruan upstream (`REVISION: SIMU`) —
backend yang sama dengan `theme-editor.py`, tanpa Tkinter dan tanpa perangkat.
Dengan `--banding` hasilnya dibandingkan dengan pratinjau kita dan selisih
pikselnya dilaporkan, jadi dua penggambar itu tidak bisa melenceng diam-diam.

### Yang bisa dan tidak bisa dibuka editor

Yang menentukan **isi temanya**, bukan siapa penulisnya. Editor ini cuma tahu
angka berupa teks; grafik batang, radial, grafik garis, statistik jaringan, dan
teks tetap buatan sendiri tidak punya wakilnya, jadi menulis ulang
`theme.yaml` akan membuangnya diam-diam.

Maka sebuah tema dibuka kalau **salah satu** benar: ditulis editor ini
(bentuknya sudah pasti), atau seluruh isinya kebetulan muat. Yang kedua itu yang
membuat tema lama — yang tata letaknya dulu dipinjam dari tema contoh — tetap
bisa disetel tanpa dibuat ulang dari awal. Kalau ada yang tidak muat, yang
ditolak menyebutkan bagian mana, bukan sekadar "tidak bisa".

Dari lima tema bawaan 2.1": `26` seluruhnya muat; `30`, `43`, `44` memakai
grafik batang dan `45` memakai statistik jaringan, jadi keempatnya ditolak.
(Tema bawaan tetap tidak disunting dari sini — itu isi klon upstream. Duplikat
dulu.)

### Membuang tema bawaan yang ukurannya lain

*Bersihkan tema ukuran lain…* menghapus tema bawaan yang `DISPLAY_SIZE`-nya
bukan `2.1"`. Yang **tidak pernah** disentuh, masing-masing ada ujinya:

- apa pun yang bukan direktori — `res/themes` juga memuat `default.yaml`, yang
  berisi bagian wajib yang ditempelkan ke **semua** tema (menghapusnya merusak
  semuanya), plus `theme_example.yaml`, `README.md`, `themes.md`,
  `scale_theme.py`;
- symlink, karena itu tema buatan sendiri;
- tema yang sedang terpasang — menghapusnya bikin service gagal memuat;
- direktori tanpa `theme.yaml`, karena itu bukan tema.

Ini menghapus berkas milik klon upstream. Mengembalikannya:

```bash
git -C ~/workspace/projects/turing-smart-screen-python restore res/themes
```

`pasang.sh` **tidak** mengembalikannya — dia cuma mengklon kalau `.git` belum
ada. Pembaruan upstream akan membawanya kembali, dan itu sebabnya ini perintah
yang bisa diulang, bukan `rm` sekali jalan.

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
**3,0 fps** di layar penuh — cocok dengan tabel di atas.

### Kenapa layar penuh sering tetap mulus

Yang dikirim tiap bingkai bukan seluruh layar, tapi **kotak yang isinya
berubah** dari bingkai sebelumnya — panel menahan apa yang sudah digambar.
Untuk GIF berlatar diam bedanya besar: terukur naik dari **3,0 fps ke 16,6 fps**
pada 480×480 (kapasitas kirim 73,7 fps). GIF yang seluruh layarnya berubah tiap
bingkai tetap 3,0 fps — memang tidak ada yang bisa dihemat.

Memecah layar jadi petak-petak (2×2, 4×4, 16×16) sudah dicoba dan **tidak
membantu**: kalau perubahannya tersebar, hampir semua petak ikut terkirim dan
hasilnya lebih boros daripada satu kotak pembatas.

### Hindari jalur layar-penuh upstream — dia memakai 4 byte/piksel

Ini menghemat 25% dan gampang terlewat. Upstream memilih penyandian di
`_generate_update_image`:

```python
if self.sub_revision != SubRevision.REV_2INCH and self.rom_version > 88:
    img_data = image_to_BGRA(image)   # 4 byte/piksel
else:
    img_data = image_to_BGR(image)    # 3 byte/piksel  ← panel 2.1"
```

Tapi `_generate_full_image` — jalur yang dipakai kalau gambarnya tepat di
`(0,0)` dan sebesar layar — **selalu** `image_to_BGRA`, tanpa percabangan itu.
Jadi mengirim satu bingkai selayar penuh lewat jalur "sebagian" justru lebih
murah daripada lewat jalur "penuh".

Terukur di perangkat:

| cara mengirim satu bingkai 480×480 | waktu | fps |
|---|---|---|
| `480×480` di (0,0) — jalur penuh | 339–369 ms | 2,7–3,0 |
| `480×479` di (0,0) — jalur sebagian | 251–277 ms | 3,6–4,0 |
| dua potong `480×240` — jalur sebagian | 279 ms | 3,6 |

Luasnya cuma beda 0,2%, waktunya beda ~25% — persis rasio 4:3 byte. Karena itu
bingkai selayar penuh dipecah jadi dua sebelum dikirim.

Efek sampingnya: ambang "kalau bedanya besar, kirim utuh saja" yang sempat
dipakai ternyata merugikan dua kali — mengirim piksel yang tidak berubah, dan
menjatuhkan pengiriman ke jalur BGRA. Sekarang selalu kotak pembatas.

### Laju mentahnya tidak bisa dipercepat dari perangkat lunak

Sudah ditelusuri sampai habis, supaya tidak ada yang mengulang:

- panel bicara di **480 Mbps** (USB high-speed) saat bangun, jadi busnya bukan
  penghambat
- menyiapkan payload di Python cuma **2,7 ms** dari 347 ms per bingkai — **1%**,
  jadi bukan CPU
- `serial_write` upstream satu panggilan `write()` tunggal, tanpa pemecahan atau
  jeda buatan

Sisanya adalah laju terima firmware panel itu sendiri: **~2,6 MB/detik**.

### Bingkai dilewati kalau panel tidak sanggup mengejar

Pemutarnya mengikuti jam dinding. Kalau laju GIF melebihi kemampuan panel,
bingkai yang sudah lewat waktunya dilewati supaya animasinya tetap berjalan
pada **kecepatan aslinya**, cuma dengan bingkai lebih sedikit. Tanpa ini,
animasi 10 fps yang cuma sanggup 4 fps akan tampil seperti gerak lambat —
semua bingkai tampil, tapi seluruh gerakannya molor.

Terukur pada GIF 10 fps yang berubah 55% tiap bingkai, di 480×480:
**9,0 fps efektif** (19 bingkai digambar, 21 dilewati). Perkiraan yang
ditampilkan aplikasi sengaja dibuat lebih rendah dari kenyataan supaya tidak
pernah menjanjikan lebih dari yang bisa ditepati.

### GIF yang dipilih dimuat lagi setiap login

Pilihannya disimpan di `~/.local/share/aio-lcd/tampilan.json`, dan pemutarnya
punya unit systemd sendiri yang **di-enable** saat kamu memilih GIF. Hanya unit
yang enabled yang menyala saat login — itulah yang bikin GIF-nya kembali
sendiri. Menekan "Hentikan" mengembalikan modenya ke tema, juga permanen.

### Hanya satu dari dua unit yang boleh hidup

`aio-lcd.service` dan `aio-lcd-gif.service` menulis ke port serial yang sama.
Yang menjamin cuma satu yang hidup adalah **`Conflicts=` pada keduanya**, bukan
kesopanan program.

Ini bukan kehati-hatian berlebihan — ini pernah terjadi. `aio-lcd.service` ikut
`graphical-session.target`, jadi dia menyala **setiap kali sesi grafis
kembali**. Menghentikannya saat memulai GIF saja tidak cukup: di login
berikutnya dia hidup lagi sendiri, berdampingan dengan pemutar GIF yang masih
jalan. Dua penulis di satu port, dan gejalanya menyesatkan — panel berhenti
memperbarui angka (suhu dkk. seperti hilang dari tema) sementara jurnalnya
penuh `device reports readiness to read but returned no data`.

Karena itu modenya disimpan sebagai **unit mana yang enabled**, bukan sekadar
unit mana yang sedang jalan.

### Jangan pasangkan `Restart=on-failure` dengan `OnFailure=` di sini

Unit GIF memakai `OnFailure=aio-lcd.service` supaya panel tidak tertinggal
tanpa pemilik kalau GIF-nya gagal dimuat. Kombinasi itu **wajib** berpasangan
dengan `Restart=no`. Dengan `Restart=on-failure`, ketiganya saling memicu tanpa
henti:

```
pemutar gagal → OnFailure menyalakan monitor → pemutar dicoba ulang
              → Conflicts mematikan monitor → pemutar gagal lagi → ...
```

Batas percobaan (`StartLimitBurst`) tidak pernah tercapai karena penghentian
oleh `Conflicts` mereset hitungannya. Terukur saat menguji jalur gagalnya:
**45 kali monitor start/stop dalam ~7 menit** sebelum dihentikan paksa.
`uji_unit_systemd.py` menjaga kombinasi ini supaya tidak kembali.

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
| `lcd_tema.py` | pembuatan tema, impor, symlink, penghapusan, pembersihan ukuran |
| `lcd_tataletak.py` | model tata letak, penulis `theme.yaml`, penggambar pratinjau |
| `editor_tataletak.py` | jendela editor: seret, warnai, atur ukuran angka |
| `periksa_tema.py` | gambar tema lewat kode upstream — jalan dengan venv upstream |
| `lcd_gif.py` | pembacaan bingkai GIF, perkiraan fps |
| `gif_pemutar.py` | pemutar GIF — jalan dengan venv upstream |
| `uji_*.py` | 188 uji — `for f in uji_*.py; do python3 $f; done` |
| `pasang.sh` | pemasang, aman dijalankan berulang |
| `config/config.yaml` | konfigurasi upstream yang sudah disetel |
| `udev/` | aturan izin port serial |
| `systemd/`, `desktop/` | templat dua unit autostart & peluncur |

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
