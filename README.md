# Energie backtest

Minimale projectstructuur om Fluvius-data te uploaden en een dynamische
energieprijs-backtest te draaien.

## Projectstructuur

```
.
├── docs/
│   └── fluvius_voorbeeld.csv
├── energie_backtest/
├── app.py
├── src/
└── README.md
```

## Lokale app starten

Installeer de dependencies en start de Flask-app:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open daarna `http://localhost:8000` om het uploadscherm te gebruiken.

## Verwachte data (Fluvius-export)

Dit project verwacht een CSV-export van Fluvius met kwartierwaarden (of uurwaarden) per meetpunt.

### Bestandsformaat

- **CSV** met puntkomma (`;`) of komma (`,`) als scheidingsteken.
- **UTF-8** encoding.
- **Headerregel verplicht**.

### Kolomnamen (verplicht)

Gebruik onderstaande kolomnamen (exacte schrijfwijze):

- `timestamp` — datum/tijd van het interval.
- `afname_kwh` — afname (kWh) in het interval.
- `injectie_kwh` — injectie (kWh) in het interval.
- `meter_id` — optioneel maar aanbevolen, ID van het meetpunt.

### Tijdzone

- **Europe/Brussels** (CET/CEST).
- Timestamps moeten **lokaal** zijn, zonder expliciete offset.
- Tijdens de overgang naar zomertijd/wintertijd moet de dubbele of ontbrekende uurcorrect worden weergegeven (bijv. 02:00 komt twee keer voor bij wintertijd; bij zomertijd ontbreekt 02:00).

### Voorbeelddata

Zie `docs/fluvius_voorbeeld.csv` voor een minimale CSV met de verwachte kolommen en een paar rijen voorbeelddata.

## Tarieven inladen

Tarieven worden verwacht in een aparte CSV (of JSON) met een vaste structuur, zodat de backtest de kostprijs per interval kan berekenen.

### Aanbevolen CSV-structuur

- `tarief_type` — bijv. `afname` of `injectie`.
- `start` — startdatum van het tarief (YYYY-MM-DD).
- `einde` — einddatum van het tarief (YYYY-MM-DD, optioneel).
- `prijs_eur_per_kwh` — prijs per kWh (decimaal met punt).

Voorbeeld (CSV):

```
tarief_type,start,einde,prijs_eur_per_kwh
afname,2024-01-01,2024-06-30,0.32
injectie,2024-01-01,2024-06-30,0.06
```

De huidige app gebruikt een eenvoudig dynamisch tariefmodel op basis van
piekuur (07:00-22:00) versus daluur. Voor realistische berekeningen kan je
de tariefmodule aanpassen en marktprijzen koppelen.

## Beperkingen

- Alleen **kWh**-waarden worden ondersteund.
- Geen automatische conversie van tijdzones of offsets.
- Geen automatische aggregatie: de intervalgrootte in de CSV moet overeenkomen met het gewenste backtest-interval.
- Onvolledige of dubbele rijen moeten vooraf opgeschoond worden.
