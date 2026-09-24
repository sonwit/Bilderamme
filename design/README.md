# design/ — artboards for fuglesiden

Tre layoutretninger for siden, som statiske artboards på 1200×1600:

| Fil | Retning |
|---|---|
| `Main.dc.html` | A, spalte: infoboks og liste til venstre, illustrasjonen fyller høyre side. Den som ble valgt. |
| `Kolofon.dc.html` | B, kolofon: illustrasjonen øverst, tekst i kolofonstil under. |
| `Kapittel.dc.html` | C, kapittel: sentrert tittel, illustrasjon midt på, listen i to spalter. |

`canvas.json` plasserer dem på et designcanvas med kommentarer. Det seedede
canvaset (`fugleramme-layoutretninger.html`) bygges av disse og er ikke i
git. Siden som faktisk rendres lages av `tools/render_daily_panel.py`.
