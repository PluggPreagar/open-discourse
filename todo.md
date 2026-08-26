# Todo

## TODO-008: Full-Import abschließen + Längen-Histogramme über alle Perioden

- **Status:** abgeschlossen (2026-08-26) — Full-Import verifiziert (1.005.962 Reden, 21 Wahlperioden, 0 verwaiste Contributions), Statistik-Vergleich als Artifact "Redenlängen-Analyse" geliefert. Ein Finding daraus als eigenständiges TODO-009 ausgelagert.
- **Prio:** Hoch (aktueller Fokus)
- **Schritt 1 — Full-Import verifizieren:**
  - `just reimport-all` läuft (DB-Reset via `db-update --force` + Full-Rebuild-Insert aller 21 Perioden, kein Delta/kein Delete).
  - Nach Abschluss prüfen: `speeches`/`contributions_extended`/`contributions_simplified` für alle 21 Perioden nicht-leer, Zeilenzahlen gegen die Pipeline-Pickles verifizieren (siehe Vorgehen in `logbook.md`, Abschnitt "WP1-18-Import").
  - Falls wieder abgebrochen: NICHT per TaskStop unterbrechen, sobald `delete_rows()` läuft (Teil-Schaden, siehe Logbook); bei Full-Rebuild gibt es aber ohnehin keine Deletes.
  - Bekannte Fallstricke, die bereits gefixt wurden: Postgres-Server-Crash bei Massen-Delete (RUM-Index), Insert-Parallelität (`ThreadPoolExecutor`) verursachte `PendingRollbackError` → wieder sequenziell; Host-Standby killt prozessgebundenen Sleep-Schutz bei jedem Skript-Absturz erneut.
  - Danach `docker-compose up -d proxy` (Pipeline-Neustarts nehmen den Proxy immer wieder raus).
- **Schritt 2 — Statistischer Vergleich über alle Perioden (Histogramme):**
  - Kriterien: Speech-Länge, Contribution-Länge, **Satzlängen** (Sentence-Length) — ursprünglicher Auslöser: sehr kurzer Redebeitrag ("Frau Kollegin.", Ramelow) → Verdacht auf Schnittfehler bei der Extraktion.
  - Bereits geklärt (siehe Logbook "Speech-Length-Check"): kurze Präsidiums-Wortmeldungen sind strukturell normal (Median 76 Zeichen bei `Presidium of Parliament` vs. 2850 bei MPs), kein Parsing-Fehler. 9 echte 0-Zeichen-Speeches gefunden (Ryglewski-Fall noch nicht tief geprüft).
  - Satzlängen-Verteilung: SQL-seitig via `regexp_split_to_table(speech_content, '[.!?]+')` + Bucket-Aggregation pro `electoral_term`, nicht Volltext nach Python ziehen (Datenvolumen).
  - Vergleich WP1-18 (alt) vs. WP19-21 (neu) — sind die Muster konsistent?
  - Visualisierung: dataviz-Skill bereits geladen (Palette/Validator beachten), small multiples pro Periode, als Artifact publizieren.

## TODO-009: Kurztext-Duplikate in WP20/21 (speeches)

- **Status:** offen (nur Finding, keine Umsetzung)
- **Prio:** Niedrig
- **Beschreibung:** Beim TODO-008-Statistikvergleich gefunden: 3.242 `speeches`-Zeilen mit identischem `(politician_id, date, speech_content)` — WP20: 901 Duplikat-Gruppen / 3.180 betroffene Zeilen / 2.279 überzählig; WP21: 488 Gruppen / 1.451 Zeilen / 963 überzählig. Alle betroffenen Texte sind kurz (max. 84 Zeichen WP20, 105 Zeichen WP21) und formelhaft (z. B. „Ja.", „Danke schön.", Vereidigungsformeln wie „Ich schwöre es, so wahr mir Gott helfe."). Keine Duplikate mit substanziellem Redetext (>200 Zeichen) gefunden. Anteil verschwindend gering (0,34 % von 1.005.962 Reden), daher nicht priorisiert.
- **Offene Frage:** Echte Mehrfach-Wortmeldung derselben Person am selben Sitzungstag (z. B. bei aufeinanderfolgenden Abstimmungen/Kurzantworten in der Fragestunde) oder ein XML-Extraktionsartefakt bei sehr kurzen Redner-Einträgen in `05_electoral_term_19_20/01_extract_speeches_and_contributions_electoral_term_19_20.py`? Nicht untersucht.
- **Nächster Schritt (falls aufgegriffen):** Root Cause in der WP19-21-Extraktion prüfen — z. B. ob derselbe kurze `<rede>`/`<p>`-Block bei bestimmten XML-Strukturen mehrfach als eigene Rede statt korrekt zusammengeführt erfasst wird. Vergleich, ob dasselbe Muster auch in WP19 oder älteren Perioden auftritt (bisher nur für WP20/21 geprüft).
- **Kommentare:** Aus Chat-Analyse entstanden (Statistik-Vergleich, siehe Artifact "Redenlängen-Analyse", Abschnitt 05, 2026-08-26).

## TODO-007: Namensinkonsistenz speeches vs. politicians

- **Status:** offen (nur Finding, keine Umsetzung)
- **Prio:** Niedrig
- **Beschreibung:** `speeches.first_name`/`last_name` (gebräuchlicher Name zur Redezeit) kann von `politicians.first_name`/`last_name` (Stammdaten) abweichen — bestätigt bei Diether Dehm/Dehm-Desoi und Michaela Noll/Tadjadod (Ehename vs. Geburtsname, beide real). Effekt: gleiche Person erscheint je nach Endpunkt (`/` vs. `/politician`) unter unterschiedlichem Namen. Entscheidung (welcher Name kanonisch ist) steht noch aus — bewusst nicht umgesetzt.

## TODO-001: Upsert statt Truncate+Insert (inkrementelle Verarbeitung)

- **Status:** offen
- **Komponente:** `python/07_database` (`02_upload_data_to_database.py`), `database` (`dbUpdate.ts`)
- **Prio:** Niedrig
- **Risk:** Mittel
- **Impact:** Hoch
- **Dependencies:** keine
- **Beschreibung:**
  Ziel: künftige Läufe sollen nur die aktuelle(n) Wahlperiode(n)/jüngere Jahre neu verarbeiten, ältere Daten unverändert lassen, statt bei jedem Lauf die komplette Historie neu zu prozessieren und die DB komplett neu aufzubauen (`db:update:local` macht aktuell `DROP DATABASE`/`CREATE DATABASE`).

  Voraussetzung geprüft: Alle sechs Zieltabellen (`electoral_terms`, `factions`, `politicians`, `speeches`, `contributions_extended`, `contributions_simplified`) haben bereits einen expliziten Primärschlüssel (`id int8 NOT NULL`, keine Sequence) — Grundlage für `INSERT ... ON CONFLICT (id) DO UPDATE` ist also vorhanden.

  Zwei offene Hürden:
  1. Pandas `to_sql()` unterstützt kein natives Upsert → eigener `method=`-Callback nötig (SQLAlchemy Core `insert().on_conflict_do_update()`, Postgres-Dialekt) statt einfacher Chunk-Inserts.
  2. `contributions_simplified["id"]` ist keine fachliche ID, sondern `range(len(...))` — rein positionsbasiert vergeben ([02_upload_data_to_database.py:209](python/src/od_lib/07_database/02_upload_data_to_database.py:209)). Ändert sich Reihenfolge/Anzahl der Zeilen zwischen Läufen, verschieben sich alle IDs → Upsert würde falsche Zeilen überschreiben. Für echtes Upsert braucht diese Tabelle einen stabilen fachlichen Schlüssel (z. B. `speech_id` + `text_position`).

  Weitere Konsequenz: `db:update:local`'s `resetDB()` (DROP/CREATE DATABASE) müsste entfallen bzw. nur bei echten Schema-Änderungen laufen, nicht bei jedem Datenlauf.

  **Update 2026-08-21:** Dieser Teilaspekt ist gelöst — `db:update:local` überspringt den Rebuild jetzt, wenn `next` bereits existiert (`--force` für den bewussten Drop+Rebuild nötig), siehe [dbUpdate.ts:108](database/src/model/dbUpdate.ts:108). Der Rest von TODO-001 (echtes Upsert statt Truncate+Insert im Python-Upload) bleibt offen.

  Für "nur jüngere Jahre neu verarbeiten" zusätzlich nötig:
  - Pipeline-Stages müssten nach Wahlperiode/Jahr parametrisierbar werden (teils schon vorbereitet, z. B. `01_concat_everything.py` akzeptiert `sys.argv`-Filter nach Wahlperiode).
  - Scraping-Stages (`02_scrape_mgs.py`, Politiker-Stammdaten) liefern immer den Gesamtbestand — müssten ggf. auch nur inkrementell abgeglichen werden.
  - Matching-Schritte (`match_names.py`) arbeiten gegen den kompletten Politiker-/Fraktionsbestand — sollte unkritisch sein, da Referenzdaten ohnehin komplett geladen werden müssen.
- **Kommentare:** Nicht priorisiert. Zurückgestellt zugunsten von TODO-006 (pragmatischere Alternative) — Nutzerentscheidung 2026-08-21: "simplifying by reset-by-period is acceptable". Aus `ideas.md` übernommen (2026-08-21).

## TODO-006: Delta-Loading per Reset-by-Period (statt vollem DB-Rebuild)

- **Status:** implementiert (2026-08-21), Verifikation gegen echte DB läuft
- **Komponente:** `python/07_database` (`02_upload_data_to_database.py`), `build.sh`, `python/05_electoral_term_19_20`
- **Prio:** Hoch
- **Risk:** Mittel
- **Impact:** Hoch
- **Dependencies:** keine
- **Beschreibung:**
  Vereinfachte Alternative zu TODO-001 (echtes Upsert): Statt jede Zeile per `ON CONFLICT DO UPDATE` abzugleichen, wird pro betroffener Wahlperiode einfach **gelöscht + neu eingefügt** ("reset-by-period"). Kein Pandas-`method=`-Callback, kein Zeilenabgleich nötig — nur ein `DELETE ... WHERE electoral_term = ...` vor dem bestehenden `to_sql(append)`.

  **Kritische Voraussetzung, zuerst zu lösen — ID-Instabilität:**
  Aktuell ist `speeches.id` ein **laufabhängiger, fortlaufender Zähler** (`speech_content_id = 1000000` in [05_electoral_term_19_20/01_extract_speeches_and_contributions_electoral_term_19_20.py:125](python/src/od_lib/05_electoral_term_19_20/01_extract_speeches_and_contributions_electoral_term_19_20.py:125), zählt über alle im selben Lauf verarbeiteten Perioden hinweg fortlaufend hoch). Ein isolierter Lauf für nur WP21 würde bei 1.000.000 neu beginnen und exakt den ID-Bereich treffen, den WP19/20 bereits in der DB belegen → Kollision/falsches Löschen fremder Zeilen.

  Kein Constraint verlangt Lückenlosigkeit/Aufsteigend — `id int8 NOT NULL PRIMARY KEY` fordert nur Eindeutigkeit. Gewählter Ansatz: **Finale ID erst beim Upload vergeben, per additivem Offset statt Mapping-Tabelle.**

  Grundlage: `speech_content_id` ist ein lückenloser Zähler, der die Perioden-Ordner sortiert durchläuft (`electoral_term_19`, `_20`, `_21`, ...) — jede Periode bildet dadurch einen zusammenhängenden Block in der Pipeline-internen ID-Folge. Eine Contribution referenziert per `extract(..., speech_content_id, ...)` immer exakt die Rede, in der sie *gerade gefunden wird* ([Zeile 358-373](python/src/od_lib/05_electoral_term_19_20/01_extract_speeches_and_contributions_electoral_term_19_20.py:358)) — nie eine Rede aus einer anderen Periode. Damit reicht ein einziger konstanter Offset statt einer 1:1-Mapping-Tabelle:
  1. Betroffene Periode(n) zuerst aus `speeches` löschen (siehe DELETE-Reihenfolge unten).
  2. `SELECT MAX(id) FROM speeches` — spiegelt danach exakt die verbleibenden, unberührten Perioden.
  3. `offset = (MAX(id)+1) − MIN(pipeline_id der reprozessierten Periode(n))`.
  4. Vektorisierte Addition auf alle drei betroffenen ID-Spalten: `speeches["id"] += offset`, `contributions_extended["speech_id"] += offset`, `contributions_simplified["speech_id"] += offset`.

  Vorteil ggü. Mapping-Tabelle: keine Dictionary-Lookups, nur eine Konstante pro Delta-Lauf. Vorteil ggü. Offset-Schema mit festem Perioden-Slot: kein verschwendeter ID-Raum, keine willkürliche Slot-Größen-Annahme, funktioniert unverändert egal wie viele Perioden im selben Lauf reprozessiert werden.
  WP1-18-Route (`speech_content_01_18["id"] = list(range(len(...)))`, [01_concat_everything.py:57](python/src/od_lib/07_database/01_concat_everything.py:57)) bleibt unangetastet — diese Perioden werden nie neu prozessiert.

  **DELETE-Reihenfolge (FK-Constraints beachten):**
  `contributions_extended`/`contributions_simplified` referenzieren `speeches.id` per Fremdschlüssel, haben aber **kein eigenes `electoral_term`-Feld** — Scope muss über `speech_id IN (SELECT id FROM speeches WHERE electoral_term = ANY(...))` abgeleitet werden. Löschreihenfolge: 1) `contributions_extended`, 2) `contributions_simplified`, 3) `speeches`. Insert-Reihenfolge danach umgekehrt (`speeches` zuerst, da die anderen beiden `speech_id` referenzieren — und der Offset erst nach der `speeches`-ID-Vergabe feststeht).

  **DB-Reset entfällt für Delta-Läufe:**
  `yarn db:update:local` (`DROP DATABASE`/`CREATE DATABASE`) nur noch bei echten Schema-Änderungen oder beim allerersten Setup nötig, nicht mehr bei jedem `--term`-Lauf. `build.sh` müsste diesen Schritt für Delta-Läufe überspringen (z. B. an `--term` gekoppelt, analog zur bestehenden `TERM_FORCE`-Logik).

  **Referenztabellen (`electoral_terms`, `politicians`, `factions`):** bleiben beim einfachen Voll-Replace (klein, Sekunden, kein Delta nötig).

  **Bekannter Trade-off:** Zwischen `DELETE` und erneutem `INSERT` sind die betroffenen Perioden kurzzeitig nicht in der DB — für die aktuelle lokale/Entwickler-Nutzung unkritisch. Bei Bedarf per einzelner DB-Transaktion um DELETE+INSERT atomar machen (Postgres unterstützt das nativ).
- **Kommentare:** Nutzerentscheidung 2026-08-21, während eines besonders langen `speeches`-Upload-Laufs entstanden: volles Upsert (TODO-001) ist für den aktuellen Bedarf überdimensioniert, Reset-by-Period reicht.

## TODO-005: MP-Stammdaten-Download von historischen ZIPs trennen (für `--term`)

- **Status:** offen
- **Komponente:** `python/01_preprocessing` (`01_download_raw_data.py`), `build.sh`
- **Prio:** Mittel
- **Risk:** Niedrig
- **Impact:** Mittel
- **Dependencies:** keine
- **Beschreibung:**
  `01_preprocessing/01_download_raw_data.py` lädt in einem Rutsch sowohl die historischen, unveränderlichen WP1-18-Session-ZIPs (mehrere hundert MB) als auch die "MdB-Stammdaten"-ZIP (`MDB_STAMMDATEN.XML`) — letztere wird vom Bundestag laufend aktuell gehalten (aktuelle lokale Kopie trägt eingebetteten Zeitstempel "29.04.2026" und enthält bereits 635 WP21-Einträge), Erstere ändert sich nie.

  Aktuell ist `01_01_download_raw_data` unter `./build.sh --term N` **nicht** geforct (bewusst, siehe TODO-004-Historie in `archive.md`), weil ein Force sonst bei jedem `--term`-Lauf unnötig die kompletten historischen ZIPs erneut herunterladen würde. Das bedeutet aber: neue Politiker in Wahlperiode 21 (Nachrücker, Mandatsverzicht) werden **nicht automatisch** nachgezogen, solange dieser Download nicht separat aktualisiert wird — aktuell nur Zufall, dass der letzte Download (19.08.2026) bereits WP21-Stand hatte.

  Fix: Stammdaten-Download in ein eigenes Skript/eine eigene Stage auslagern, damit sie unabhängig von den historischen ZIPs unter `--term` geforct werden kann. Downstream-Stufen `01_06_extract_mps_from_mp_base_data`, `03_01_add_faction_id_to_mps`, `03_03_merge_politicians` sind bereits im Sekundenbereich — können anschließend risikolos mitgeforct werden.
- **Kommentare:** Aus Chat-Frage entstanden ("enthalten die übersprungenen Referenz-Daten-Steps auch Politiker die in #21 neu sind?").
