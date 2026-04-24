# Tradera Wantlist Searcher

GUI-applikation för Ubuntu (Linux) som läser en Discogs wantlist (CSV) och söker efter skivorna på [Tradera](https://www.tradera.com) – Sveriges största auktionsplats.

## Funktioner

- 📁 **Ladda Discogs wantlist** – Importera din CSV-export från Discogs
- 🔍 **Sök på Tradera** – Automatisk sökning efter varje skiva
- 🎯 **Hittade skivor** – Egen flik med alla träffar (pris, titel, antal)
- ❌ **Saknade skivor** – Egen flik med skivor som inte hittades
- 🎵 **YouTube Music** – Klickbar länk till varje skiva i detaljvyn
- 🟢 **Spotify** – Klickbar länk till sökning i Spotify
- 💾 **Sparar session** – Programmet kommer ihåg wantlist och resultat mellan körningar
- 📀 **Format-matchning** – Filtrerar Tradera-träffar efter format (LP, CD, etc.)

## Installation

1. Klona eller ladda ned repot
2. Installera beroenden:

```bash
pip install requests
```

> `tkinter` och `csv` ingår i Python-standardbiblioteket.

## Så här kör du

```bash
python3 tradera_wantlist_searcher.py
```

## Användning

1. Klicka **"Välj fil…"** och välj din Discogs wantlist (CSV)
2. Klicka **"Ladda"** för att importera skivorna
3. Klicka **"🔍 Sök på Tradera"** för att starta sökningen
4. Resultatet visas i två flikar:
   - **🎯 Hittade skivor** – skivor med träffar på Tradera
   - **❌ Saknade skivor** – skivor utan träffar
5. Klicka på en rad för att se detaljer (länkar, priser, format, bud)
6. Dubbelklicka på en rad för att öppna bästa träffen i webbläsaren

### Exportera wantlist från Discogs

1. Gå till din Discogs-profil → Collection → Wantlist
2. Klicka på **Export** (CSV)
3. Spara filen och välj den i programmet

## GUI – översikt

```
┌─────────────────────────────────────────────────────────┐
│  Discogs Wantlist (CSV): [filväg...] [Välj fil] [Ladda] │
│  Laddade 81 skivor                                      │
├─────────────────────────────────────────────────────────┤
│  [🔍 Sök på Tradera] [⏹ Stoppa] [======>    ] Klar      │
│                    🎯 Hittade: 45 | ❌ Saknade: 36      │
├─────────────────────────────────────────────────────────┤
│  ┌🎯 Hittade skivor (45)─┐ ┌❌ Saknade skivor (36)──┐  │
│  │ Artist – Title        │ │ Artist – Title         │  │
│  │ Träffar │ Bästa träff │ │                        │  │
│  │ Pris    │             │ │                        │  │
│  └────────────────────────┘ └────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│  Detaljer                                               │
│  🎵 Pink Floyd – The Dark Side of the Moon              │
│  🎧 Lyssna på YouTube Music  |  🟢 Öppna i Spotify      │
│  ─────────────────────────────────────────────────────  │
│  #1 Pink Floyd - The Dark Side Of The Moon [LP]         │
│     💰 1 240 kr                                         │
│     🏷️ 27 bud                                            │
│     🔗 https://www.tradera.com/item/...                 │
└─────────────────────────────────────────────────────────┘
```

## Filstruktur

| Fil | Beskrivning |
|-----|-------------|
| `tradera_wantlist_searcher.py` | Huvudprogrammet |
| `wantlist_cache.json` | Autosparad session (skapas vid stängning) |
| `phermansson-wantlist-*.csv` | Exempel på Discogs wantlist |

## Tekniska detaljer

- **GUI**: tkinter med ttk Notebook (två flikar)
- **Web scraping**: BeautifulSoup-liknande parsing av Traderas `__NEXT_DATA__`-JSON
- **Format-matchning**: Läser `Format`-kolumnen från Discogs CSV och matchar mot Traderas `music_format`
- **Trådning**: Sökningar körs i bakgrundstråd för att GUI inte ska låsa sig
- **Cache**: Sparas till JSON vid `WM_DELETE_WINDOW`

## Beroenden

- Python 3.8+
- `requests`
- `tkinter` (följer med Python)

## Licens

MIT – använd, ändra och dela fritt!
