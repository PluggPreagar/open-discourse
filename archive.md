# Archive

Abgeschlossene Todos aus `todo.md`.

## TODO-002: Wahlperiode 21 (ab 2025) fehlt komplett in der Pipeline

- **Status:** erledigt (2026-08-21)
- **Komponente:** `python/01_preprocessing`, `python/07_database`
- **Prio:** Hoch
- **Risk:** Mittel
- **Impact:** Hoch
- **Dependencies:** keine
- **Beschreibung:**
  [02_download_raw_data_electoral_term_19_20.py:11-20](python/src/od_lib/01_preprocessing/02_download_raw_data_electoral_term_19_20.py:11) hatte die Ziel-Wahlperioden hart codiert (nur 19 und 20, via feste `opendata`-Filterlist-IDs 543410 bzw. 866354). WP 21 (seit 2025) fehlte komplett.
- **Kommentare:**
  Filterlist-ID für WP21 (`1058442`) per Browser-Netzwerkinspektion auf `bundestag.de/services/opendata` gefunden (Nutzer lieferte `21001.xml`-Beispiel-URL als Hinweis). Umsetzung:
  - `02_download_raw_data_electoral_term_19_20.py`: dritten Eintrag für `election_period: 21` ergänzt.
  - `01_concat_everything.py`: WP19/WP20-Duplikatblöcke durch generische Schleife über alle `electoral_term_*`-Ordner unter Stage 03 ersetzt — WP22+ künftig automatisch abgedeckt, keine erneute manuelle Ergänzung nötig.
  - `02_upload_data_to_database.py`: dieselbe Hardcode-Klasse gefunden (`CONTRIBUTIONS_SIMPLIFIED_WP19`/`_WP20`) und ebenso generalisiert.
  - `05_electoral_term_19_20/...`-Skripte waren bereits generisch (`iterdir()`), keine Änderung nötig.
  Ordner-/Modulname `05_electoral_term_19_20` bleibt aus Kompatibilitätsgründen unverändert (rein kosmetisch, keine funktionale Einschränkung mehr).

  **Nachtrag (2026-08-21, beim ersten echten `--term`-Lauf entdeckt):** Dieselbe Hardcode-Bug-Klasse noch an einer weiteren Stelle — `01_07_create_electoral_terms.py` hatte eine hartkodierte Liste mit nur 20 Wahlperioden, WP21 fehlte. Führte zu `ForeignKeyViolation` beim Upload (`speeches.electoral_term=21` nicht in `electoral_terms`-Tabelle vorhanden). Fix: WP21-Eintrag ergänzt (Start 25.03.2025, `end_date=None` da noch laufend, Schema erlaubt `NULL`). Stage zusätzlich in `build.sh` unter `--term` erzwungen (war zuvor nicht in der Force-Liste, da beim ursprünglichen TODO-004-Umbau übersehen).

## TODO-003: Global eindeutige Datei-/Stage-Präfixe (Log- und Marker-Namen)

- **Status:** erledigt (2026-08-21)
- **Komponente:** `python/build.sh`
- **Prio:** Niedrig
- **Risk:** Niedrig
- **Impact:** Niedrig
- **Dependencies:** keine
- **Beschreibung:**
  Pipeline-Skripte sind pro Phasen-Ordner erneut ab `01_` durchnummeriert. `build.sh` verwendete nur den Skript-Basenamen für Log-Dateien und Stage-Marker — fragil bei künftigen Namenskollisionen zwischen Phasen.
- **Kommentare:**
  Alle 21 `run_stage`-Aufrufe in `build.sh` um den numerischen Parent-Ordner-Präfix ergänzt (z. B. `07_01_concat_everything` statt `01_concat_everything`). Bestehende `logs/.status/*.done`-Marker auf die neuen Namen migriert (`mv`), damit kein unnötiger Vollrerun ausgelöst wird. `.py`-Dateien im Repo unverändert.

## TODO-004: Globaler `--term`-Parameter für `build.sh` (inkl. DB-Reset-Frage)

- **Status:** erledigt (2026-08-21)
- **Komponente:** `python/build.sh`, `python/06_contributions`, `python/01_preprocessing`, `python/05_electoral_term_19_20`, `python/07_database`
- **Prio:** Hoch
- **Risk:** Mittel
- **Impact:** Hoch
- **Dependencies:** keine (TODO-001/Upsert bleibt separates, größeres Thema)
- **Beschreibung:**
  7 Skripte hatten einen `sys.argv`-basierten Wahlperioden-Filter, war aber nicht über `build.sh` erreichbar.
- **Kommentare:**
  Vor Umsetzung genauer geprüft, welche der 7 Skripte tatsächlich sicher filterbar sind — Ergebnis wich vom ursprünglichen Plan ab:
  - `03_split_xml.py`, `01_extract_speeches.py`, `02_clean_speeches.py`, `01_extract_contributions.py` (06_contributions) sind **WP1-18-exklusiv** (separater Verarbeitungspfad, WP19+ läuft komplett getrennt über `05_electoral_term_19_20/...`). WP21 kommt dort nie vor — Filterung wäre wirkungslos, bei `01_extract_contributions.py` sogar gefährlich (überschreibt eine globale `contributions_simplified.pkl`-Datei ohne Pro-Term-Trennung; ein `--term 21`-Filter hätte sie mit einem leeren Ergebnis überschrieben).
  - `01_concat_everything.py` muss immer vollständig laufen (finale Aggregation aller Perioden für den DB-Upload) — der ursprünglich vermutete "Fallstrick" (`sys.argv` filtert nur die Metadaten-Schleife) ist für unser Design irrelevant, da dieses Skript nie gefiltert aufgerufen wird.
  - Nur `02_clean_contributions_extended.py` und `03_match_contributions_extended.py` verarbeiten generisch **alle** Perioden (1–21) in einem Durchlauf und schreiben sauber pro Wahlperiode getrennte Output-Dateien — genau diese beiden sind zusammen auch der größte Kostenblock (~2 h von ~4 h Gesamtlaufzeit). Nur sie bekommen `--term` durchgereicht.
  - DB-Reset/Upload-Entscheidung: **Option "ganze DB resetten und alles neu einfügen"** gewählt (nicht periodenscoped) — Upload/Reset ist mit Sekunden bis wenigen Minuten nicht der Kostentreiber; ein periodenscoped Reset hätte ohne echten Zeitgewinn dieselbe Komplexität wie TODO-001 (Upsert/ID-Stabilität) vorgezogen. `--term` beeinflusst daher nur die zwei genannten Verarbeitungsstufen, nicht `db:update:local` oder den Upload.
  - `build.sh` erzwingt bei gesetztem `--term` einen Rerun der zwei betroffenen Stages auch wenn deren `.done`-Marker bereits existiert (sonst würde die Skip-Logik sie übergehen).

  **Nachträgliche Korrekturen (im Chat gefunden, gleicher Tag):**
  - `07_01_concat_everything`/`07_02_upload_data_to_database` hatten ebenfalls schon `.done`-Marker aus der Migration → wären ohne Force übersprungen worden, die frisch reprozessierten WP21-Daten hätten nie den Upload erreicht. Beide bekommen jetzt `force_this=$TERM_FORCE`.
  - `01_02_download_raw_data_electoral_term_19_20`, `01_05_split_xml_electoral_term_19_20`, `05_01_extract_speeches_and_contributions_electoral_term_19_20` sind ebenfalls WP21-relevant (WP1-18-exklusive Stages wie `03_split_xml`/`01_extract_speeches`/`01_extract_contributions` sind es nicht). Alle drei bekommen `force_this=$TERM_FORCE`, da sie für alle drei Perioden zusammen ohnehin schnell sind (Split ~12s, Extract ~5min) — keine gesonderte Pro-Term-Filterung nötig.
  - `02_download_raw_data_electoral_term_19_20.py` hatte keinerlei Skip-Existing-Logik (lud bei jedem Lauf alle Sitzungen aller drei Perioden erneut herunter) — Fix: überspringt jetzt bereits heruntergeladene Sitzungsdateien (`target_path.exists()`-Check), damit wiederholte `--term`-Läufe nur neu veröffentlichte Sitzungen nachladen.
  - `--term` unterstützt jetzt eine kommagetrennte Liste (`--term 19,20,21`) statt nur eines einzelnen Werts — nötig, um nach einem gemeinsamen Bugfix in der geteilten `get_faction_abbrev()`-Logik mehrere Perioden in einem Lauf konsistent neu zu verarbeiten (`build.sh` wandelt Kommas in Leerzeichen um und übergibt sie ungequotet, damit sie als separate argv-Einträge an die Python-Skripte durchgereicht werden).
