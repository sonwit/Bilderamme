# kamera/ — fuglekameraet på Raspberry Pi (parkert)

Den første utgaven av fuglekameraet: en Raspberry Pi 3 B med Camera Module 3
Wide, senere HQ-kamera med manuell fokus, i vinduet rettet mot materen.
Erstattet av Android-appen i [../kamera-app/](../kamera-app/README.md) i
september 2026, etter at modellkallene fra kameraet viste seg å være
80–90 % av Gemini-regningen. Beholdt som referanse; konfignavnene lever
videre i appen.

| Fil | Hva |
|---|---|
| `kamera.py` | Tjenesten. Liten gråtonestrøm leses hele tiden; over en bevegelsesterskel i et felt tas et stort bilde, beskjæres og POST-es til serverens `/bilde`. Natt hoppes over. |
| `fokus.py` | Fokushjelper for HQ-kameraet: et skarphetstall per sekund, målt i feltene rundt materne. Vri ringen til tallet er høyest. |
| `titt.sh` | Ta ett bilde av hele rammen, hent det ned og åpne det på Macen. Til retning og fokus. |
| `kamera.example.json` | Innstillingene: server, felter, terskler, pause. |

Tjenestefilen `deploy/fugleramme-kamera.service` hører til her og installeres
på Pi-en. Ingenting analyseres på Pi-en; den er for svak, og serveren har alt
den trenger.
