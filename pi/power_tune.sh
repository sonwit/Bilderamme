#!/usr/bin/env bash
#
# power_tune.sh — skru ned stroemforbruket paa utedelens Pi.
# Kjoeres én gang med sudo:   sudo /home/bruker/power_tune.sh
# Installerer ogsaa fugleramme-power.service som setter det samme ved hver boot.
#
# VIKTIG designvalg: dette scriptet endrer BEVISST ikke /boot/firmware/config.txt.
# Pi-en henger ute paa en solcelle-rigg — en feil i boot-configen ville betydd
# fysisk nedhenting. Alt her er kjoeretids-innstillinger som ikke kan hindre
# oppstart. De virkelig store gevinstene (dtoverlay=disable-bt, disable-wifi-
# pow-management i firmware, mindre kort) tas naar kassa uansett er nede.
#
# Forventet effekt paa en Pi 3 B: ca. 100-150 mA mindre av ~450 mA i tomgang
# (20-30 %). Den STORE gevinsten er aa bytte til Pi Zero 2W (~3x lavere).

set -uo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Kjoer med sudo."; exit 1; }

# Finnes denne systemd-enheten? NB: IKKE `... | grep -q` her -- med
# `set -o pipefail` gir grep -q SIGPIPE til systemctl, pipelinen returnerer
# 141, og testen feiler alltid (det skjedde: bluetooth ble aldri slaatt av).
has_unit() {
  [ -n "$(systemctl list-unit-files --no-legend --no-pager "$1.service" 2>/dev/null)" ]
}

echo "== 1. HDMI/skjerm av =="
# Merk: med KMS-driveren (vc4-kms-v3d) gjoer ikke `vcgencmd display_power` noe
# paa Pi 3 -- den rapporterer bare 1 tilbake. Uten skjerm tilkoblet trekker
# HDMI-utgangen lite uansett, saa vi lar det ligge fremfor aa rote i
# boot-configen paa en enhet som henger ute.
vcgencmd display_power 0 >/dev/null 2>&1 || true
echo "  (KMS: ingen effekt paa Pi 3 — hoppet over, se kommentar i scriptet)"

echo "== 2. Statuslysdioder av (~5-15 mA) =="
for led in /sys/class/leds/ACT /sys/class/leds/PWR; do
  [ -d "$led" ] || continue
  echo none > "$led/trigger" 2>/dev/null
  echo 0 > "$led/brightness" 2>/dev/null
  echo "  $(basename "$led") av"
done

echo "== 3. CPU-guvernoer: powersave (lavere topplast under opplasting) =="
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  [ -w "$g" ] && echo powersave > "$g"
done
echo "  naa: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"

echo "== 4. Bluetooth-tjenester av (~10-20 mA) =="
for svc in bluetooth hciuart; do
  if has_unit "$svc"; then
    systemctl disable --now "$svc" >/dev/null 2>&1
    echo "  $svc: $(systemctl is-active "$svc" 2>/dev/null), $(systemctl is-enabled "$svc" 2>/dev/null)"
  fi
done

echo "== 5. Wifi power-save PAA (stoerste programvare-gevinsten, 50-100 mA) =="
# Global NetworkManager-standard. Viktig: profilen her heter
# «netplan-wlan0-...», dvs. den GENERERES av netplan -- en endring gjort med
# `nmcli c modify` kan bli overskrevet neste gang netplan kjoerer. En drop-in i
# conf.d gjelder alle profiler og overlever det.
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/wifi-powersave.conf <<'EOF'
# Fugleramme: wifi power-save paa (3 = enable) for aa spare batteri ute.
[connection]
wifi.powersave = 3
EOF
echo "  /etc/NetworkManager/conf.d/wifi-powersave.conf skrevet"

CON="$(nmcli -t -f NAME,DEVICE c show --active 2>/dev/null | sed -n 's/:wlan0$//p' | head -1)"
if [ -n "$CON" ]; then
  nmcli c modify "$CON" 802-11-wireless.powersave 3 2>/dev/null \
    && echo "  satt ogsaa paa profilen «$CON»"
fi
# `iw` lar oss baade sette og VERIFISERE tilstanden; uten den flyr vi blindt.
if ! command -v iw >/dev/null 2>&1; then
  echo "  installerer iw (liten pakke, for aa kunne verifisere power-save) ..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends iw >/dev/null 2>&1 \
    && echo "  iw installert" || echo "  (kunne ikke installere iw — hopper over)"
fi
command -v iw >/dev/null 2>&1 && iw dev wlan0 set power_save on 2>/dev/null
command -v iw >/dev/null 2>&1 && echo "  tilstand naa: $(iw dev wlan0 get power_save 2>/dev/null)"

echo "== 6. Mindre SD-skriving (brownout-sikring, ikke stroem) =="
# Undervoltage under skriving er den klassiske maaten aa oedelegge et SD-kort.
# Logg i RAM + ingen swap = langt faerre skrivinger, og lite aa oedelegge.
if ! grep -q '^Storage=volatile' /etc/systemd/journald.conf; then
  sed -i 's/^#\?Storage=.*/Storage=volatile/' /etc/systemd/journald.conf
  systemctl restart systemd-journald 2>/dev/null
  echo "  journald logger naa i RAM"
fi
if has_unit dphys-swapfile; then
  systemctl disable --now dphys-swapfile >/dev/null 2>&1
  echo "  swap: $(systemctl is-active dphys-swapfile 2>/dev/null)"
fi

echo "== 7. Installer boot-tjeneste saa dette settes ved hver oppstart =="
cat > /etc/systemd/system/fugleramme-power.service <<'EOF'
[Unit]
Description=Fugleramme: stroemsparing for utedelen
After=multi-user.target NetworkManager.service

[Service]
Type=oneshot
RemainAfterExit=yes
# Kun kjoeretids-innstillinger som maa settes paa nytt etter boot.
ExecStart=/bin/sh -c 'vcgencmd display_power 0 || true'
ExecStart=/bin/sh -c 'for l in /sys/class/leds/ACT /sys/class/leds/PWR; do [ -d "$l" ] && { echo none > "$l/trigger"; echo 0 > "$l/brightness"; }; done; true'
ExecStart=/bin/sh -c 'for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do [ -w "$g" ] && echo powersave > "$g"; done; true'
ExecStart=/bin/sh -c 'iw dev wlan0 set power_save on 2>/dev/null || true'

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable fugleramme-power.service >/dev/null 2>&1
echo "  fugleramme-power.service installert og aktivert"

echo
echo "Ferdig. Status naa:"
echo "  throttled: $(vcgencmd get_throttled)   temp: $(vcgencmd measure_temp)"
echo "  guvernoer: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
echo "  undervoltage-hendelser siden boot: $(dmesg | grep -ci 'undervoltage detected')"
