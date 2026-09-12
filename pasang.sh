#!/usr/bin/env bash
# Pasang seluruh rangkaian layar LCD AIO di mesin ini.
#
#   ./pasang.sh
#
# Aman dijalankan berulang. Langkah yang sudah beres dilewati, bukan diulang.
# Bagian yang butuh sudo cuma satu (udev rule) dan ditanyakan di tempatnya.
set -euo pipefail

DIR_APP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR_UPSTREAM="${AIO_LCD_UPSTREAM:-$HOME/workspace/projects/turing-smart-screen-python}"
ASAL_UPSTREAM="https://github.com/mathoudebine/turing-smart-screen-python.git"
SERVICE=aio-lcd.service

info() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
oke()  { printf '    \033[32m✓\033[0m %s\n' "$*"; }
awas() { printf '    \033[33m!\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------- 1. upstream
info "Klon upstream ke $DIR_UPSTREAM"
if [ -d "$DIR_UPSTREAM/.git" ]; then
  oke "sudah ada, dilewati"
else
  # --depth 1 memang disengaja: riwayat penuhnya ±936 MB karena gambar tema
  # bertumpuk, dan tidak ada gunanya di sini.
  git clone --depth 1 "$ASAL_UPSTREAM" "$DIR_UPSTREAM"
  oke "terklon (dangkal)"
fi

# ------------------------------------------------------------------- 2. venv
info "Siapkan venv"
if [ -x "$DIR_UPSTREAM/.venv/bin/python" ]; then
  oke "venv sudah ada, dilewati"
else
  python3 -m venv "$DIR_UPSTREAM/.venv"
  "$DIR_UPSTREAM/.venv/bin/pip" install -q --upgrade pip
  "$DIR_UPSTREAM/.venv/bin/pip" install -q -r "$DIR_UPSTREAM/requirements.txt"
  oke "venv siap"
fi

# ----------------------------------------------------------------- 3. config
info "Pasang config.yaml"
if [ -f "$DIR_UPSTREAM/config.yaml" ] && ! cmp -s "$DIR_APP/config/config.yaml" "$DIR_UPSTREAM/config.yaml"; then
  cp "$DIR_UPSTREAM/config.yaml" "$DIR_UPSTREAM/config.yaml.sebelum-pasang"
  awas "config lama dicadangkan ke config.yaml.sebelum-pasang"
fi
cp "$DIR_APP/config/config.yaml" "$DIR_UPSTREAM/config.yaml"
oke "REVISION C, COM_PORT AUTO, tema berkutip"

# --------------------------------------------------------- 3b. tema sendiri
info "Pasang ulang tema buatan sendiri"
# Tema buatan sendiri disimpan di ~/.local/share/aio-lcd/themes lalu di-symlink
# ke res/themes. Klon upstream yang baru tidak punya symlink itu, jadi
# dipasang ulang di sini — isinya sendiri tidak pernah ikut hilang.
PULIH=$(AIO_LCD_UPSTREAM="$DIR_UPSTREAM" python3 -c "
import sys; sys.path.insert(0, '$DIR_APP')
import lcd_tema
print(len(lcd_tema.PustakaTema().segarkan_tautan()))
" 2>/dev/null || echo 0)
oke "$PULIH tema buatan sendiri tertaut kembali"

# ------------------------------------------------------------------- 4. udev
info "Pasang izin port serial (udev)"
TUJUAN=/etc/udev/rules.d/70-turing-smart-screen.rules
if cmp -s "$DIR_APP/udev/70-turing-smart-screen.rules" "$TUJUAN" 2>/dev/null; then
  oke "rule sudah terpasang, dilewati"
else
  echo "    Perlu sudo untuk menulis $TUJUAN"
  sudo install -m644 "$DIR_APP/udev/70-turing-smart-screen.rules" "$TUJUAN"
  sudo udevadm control --reload
  sudo udevadm trigger --subsystem-match=tty
  oke "rule terpasang + udev dimuat ulang"
fi

# ---------------------------------------------------------------- 5. service
info "Pasang service autostart"
mkdir -p "$HOME/.config/systemd/user"
sed "s|@DIR_UPSTREAM@|$DIR_UPSTREAM|g" \
  "$DIR_APP/systemd/$SERVICE.in" > "$HOME/.config/systemd/user/$SERVICE"
systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE"
oke "$SERVICE aktif & enabled"

# ---------------------------------------------------------------- 6. desktop
info "Pasang peluncur aplikasi"
chmod +x "$DIR_APP/tema-lcd.py" "$DIR_APP/gif_pemutar.py"
mkdir -p "$HOME/.local/share/applications"
sed "s|@DIR_APP@|$DIR_APP|g" \
  "$DIR_APP/desktop/aio-lcd-tema.desktop.in" > "$HOME/.local/share/applications/aio-lcd-tema.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
oke "\"Tema LCD AIO\" muncul di daftar aplikasi"

# ------------------------------------------------------------------ 7. bukti
info "Periksa hasilnya"
echo "    izin  : $(getfacl -p /dev/ttyACM1 2>/dev/null | grep -c '^user:' || echo 0) entri ACL di /dev/ttyACM1"
echo "    service: $(systemctl --user is-active $SERVICE) / $(systemctl --user is-enabled $SERVICE)"
echo
echo "Layar baru benar-benar terbukti jalan kalau log ini muncul:"
echo "  journalctl --user -u $SERVICE -f | grep 'Starting system monitoring'"
