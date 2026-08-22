# Logbook

## 2026-08-21 — WP19-21-Lücke: Pagination-Bug + zwei Datenquirks, Vollständigkeits-Check ergänzt
- Ursache der leeren 2019-Suche: `02_download_raw_data_electoral_term_19_20.py` zählte pro AJAX-Seite die `<a href=...xml>`-Tags roh — die Bundestag-Seite listet jedes Dokument aber zweimal (Desktop/Mobil-Markup). `offset += len(current_links)` erhöhte dadurch um 20 statt 10 pro Schritt und übersprang jeden zweiten 10er-Block. Fix: Dedup nach `href` vor der Offset-Berechnung.
- Beim Nachladen der so gefundenen Sitzungen zwei echte Bundestag-XML-Quirks aufgedeckt (Rohabruf bestätigt, kein Artefakt unseres Scripts): `<redner id="11005217 999990074">` (zwei Leerzeichen-getrennte IDs) und doppelter Klartext (`SvenjaSvenja`). Fix in `05_electoral_term_19_20/01_extract_speeches_and_contributions_electoral_term_19_20.py`: erste ID nehmen (`.split()[0]`), robust gegen `IndexError`/leeres Attribut.
- Neu: `python/src/od_lib/check_raw_data_completeness.py` (`just check-raw-data`) — read-only Lückenprüfung über alle 21 Wahlperioden, ohne etwas zu löschen/neu zu laden. Ergebnis nach Fix: keine Lücken mehr, WP1-18 waren nie betroffen (anderer Download-Pfad). Ersetzt die ursprünglich geplante Idee eines kompletten Neu-Crawls (`rm -rf python/data` + 4h Neulauf) — unnötig teuer und verwirft bereits gecrawlte Seiten ohne Not.
- Vollständiger `pipeline-term 19,20,21`-Lauf (unter Wiederverwendung des gecrawlten Webpage-Caches, nur die eine gefundene Lücke nachgeladen) erfolgreich abgeschlossen: WP19 31.089→64.025, WP20 33.431→63.929, WP21 16.914→31.322 Reden, Dump geschrieben, Suche verifiziert.

## 2026-08-21 — Finding: Namensinkonsistenz speeches vs. politicians
- Beim WP19-Vergleich gegen Original-System-CSV zwei Namensabweichungen gefunden: Dehm/Dehm-Desoi, Noll/Tadjadod — jeweils Ehename (`speeches`) vs. Geburtsname (`politicians`), beide real (Web-Recherche bestätigt). Kein Fehler, aber gleiche Person zeigt je Endpunkt anderen Namen. Nur dokumentiert, siehe TODO-007 — keine Umsetzung.

## 2026-08-21 — Proxy-Fix, DB-Reset als Nebenwirkung, gehardened
- Proxy-Crash (TS2769, `app.use(RateLimit(...))`): doppelte `@types/express`-Kopie durch `@types/express-rate-limit`. Fix: `resolutions` in `proxy/package.json` pinnt sie auf eine Version.
- Docker-Rebuild zur Proxy-Reparatur hatte einen schlechten Nebeneffekt: `db:update:local` lief mit und hat `next` komplett gedroppt/neu angelegt — 928k Reden weg, da der Schritt bedingungslos `DROP`/`CREATE DATABASE` macht ([dbUpdate.ts](database/src/model/dbUpdate.ts)).
- Gehardened: `setupDB()` skippt den Rebuild jetzt, wenn `next` existiert (nur `--force` droppt); `build.sh` schreibt nach jedem Upload einen gzipped `pg_dump` nach `database/dumps/` als Restore-Punkt.
- Datenverlust überbrückt: `python src/od_lib/07_database/02_upload_data_to_database.py 19` reimportiert WP19 direkt aus den noch vorhandenen finalen Pickles (`python/data/03_final/*`) ohne vollen Pipeline-Lauf; andere Perioden bleiben bis zum nächsten `build.sh`-Lauf leer.

## 2026-08-21 — Wahlperiode 21 ergänzt
- Filterlist-ID für WP21 (`1058442`) per Browser-Netzwerkinspektion gefunden (Hardcode-Muster identisch zu WP19/`543410`, WP20/`866354`).
- `02_download_raw_data_electoral_term_19_20.py`, `01_concat_everything.py`, `02_upload_data_to_database.py` generalisiert — WP22+ künftig ohne Codeänderung abgedeckt. Details siehe `archive.md` (TODO-002).

## 2026-08-21 — build.sh: Stage-Präfixe + `--term`-Parameter
- `run_stage`-Namen um Phasen-ID präfigiert (`07_01_concat_everything` statt `01_concat_everything`), bestehende `.done`-Marker migriert.
- `./build.sh --term 21` filtert nur `02_clean_contributions_extended`/`03_match_contributions_extended` (zusammen ~2h von ~4h Gesamtlaufzeit, einzige Stages die sicher periodenübergreifend + pro-Term-Output filterbar sind). Andere vermeintlich filterbare Skripte sind WP1-18-exklusiv (Filterung wirkungslos/riskant) oder müssen immer voll laufen (`01_concat_everything`).
- DB-Reset/Upload bleibt bei `--term` unverändert vollständig (bewusste Design-Entscheidung gegen periodenscoped Reset, siehe `archive.md` TODO-004).
- Nachträglich korrigiert: `07_01_concat_everything`/`07_02_upload_data_to_database` sowie die drei WP19-21-relevanten Vorstufen (`01_02_download...`, `01_05_split_xml...`, `05_01_extract_speeches_and_contributions...`) müssen bei `--term` ebenfalls erzwungen neu laufen (hätten sonst ihren `.done`-Marker aus der Migration behalten und die frisch reprozessierten Daten nie erreicht/hochgeladen). `02_download_raw_data_electoral_term_19_20.py` lud bislang jede Sitzung bei jedem Lauf neu herunter — jetzt Skip-Existing-Check ergänzt.

## 2026-08-21 — Root Cause gefunden: Fraktions-Zuordnung WP19/20
- `05_electoral_term_19_20/01_extract_speeches_and_contributions_electoral_term_19_20.py:224` setzte `position_raw` bei gefundenem `<fraktion>`-Element fälschlich auf `""` statt dessen Text — Fraktionsangabe ging für normale Abgeordnete komplett verloren, bevor das Pattern-Matching überhaupt lief. Fix: `find_with_default(name, "fraktion", "")`.
- "Presidium of Parliament" (52,6 % der Unmatched-Fälle) war kein Bug — identisch zu WP1-18 (100 % ohne Fraktion), Sitzungsleitung hat strukturell keine Fraktion.
- **Verifiziert** durch Neu-Ausführung der Stage: `faction_id`-Unbekannt-Quote 86,5 % → WP19 52,2 %/WP20 51,4 % (unter Baseline-Niveau).
- Zwei weitere Ursachen für Rest-"Not found"-Fälle gefunden: case-sensitives Pattern-Matching (`"Die Linke"` vs. `"DIE LINKE"` → `regex.IGNORECASE` ergänzt) und fehlendes `"BSW"`-Pattern (neue Partei seit 2023) — beide in allen vier `get_faction_abbrev()`-Kopien gefixt. "Not found"-Fälle WP20: 22.364 → 13 (99,94 % Reduktion). Details siehe `ideas.md`.

## 2026-08-21 — ForeignKeyViolation beim ersten `--term 19,20,21`-Lauf
- `electoral_terms`-Tabelle hatte keinen WP21-Eintrag (`01_07_create_electoral_terms.py`: hartkodierte Liste mit nur 20 Perioden) → Upload von `speeches` (electoral_term=21) scheiterte an FK-Constraint.
- Fix: WP21 ergänzt (Start 25.03.2025, `end_date=None`), Stage zusätzlich unter `--term` erzwungen (war beim TODO-004-Umbau übersehen worden).
- `--term` unterstützt jetzt kommagetrennte Liste (`--term 19,20,21`), um mehrere Perioden nach einem gemeinsamen Bugfix konsistent neu zu verarbeiten.

## 2026-08-21 — kosmetischer Progressbar-Glitch bei Ein-Chunk-Uploads
- `upload_with_progress()` zeigte bei Tabellen mit nur einem Chunk (z. B. `electoral_terms`, `factions`) einen sichtbaren Zeichenrest ("0]") am Ende der Fortschrittsanzeige — Carriage-Return-Überschreibung ohne Zeilenlöschung in der bestehenden `progressbar`-Utility, sichtbar erst durch den neuen Ein-Chunk-Fall. Kein Fehler, nur Optik. Fix: bei ≤1 Chunk direkter Upload ohne Progressbar.

## 2026-08-21 — Plan für Delta-Loading (TODO-006) statt Volluploads
- Nutzerentscheidung: einfacheres "Reset-by-Period" (DELETE+INSERT pro Wahlperiode) statt vollem Upsert (TODO-001) — reicht für den aktuellen Bedarf.
- Kritische Voraussetzung im Plan verankert: `speeches.id`-Vergabe ist aktuell ein laufabhängiger globaler Zähler, nicht stabil pro Periode — muss zuerst auf ein deterministisches Schema (`electoral_term`-basiert) umgestellt werden, sonst würde ein isolierter Periodenlauf mit bestehenden IDs anderer Perioden kollidieren.
- `contributions_extended`/`contributions_simplified` haben kein eigenes `electoral_term`-Feld, Scope muss über `speech_id`-Subquery auf `speeches` abgeleitet werden; FK-Reihenfolge beim Löschen beachten.
- Plan weiter vereinfacht: Statt Mapping-Tabelle reicht ein additiver Offset (`MAX(id)+1 − MIN(pipeline_id)`), da jede Wahlperiode einen zusammenhängenden, lückenlosen ID-Block bildet und Contributions nie periodenübergreifend referenzieren — vektorisierte Addition auf `speeches["id"]` + beide `speech_id`-Spalten statt Dictionary-Lookup. Details siehe `todo.md` TODO-006.

## 2026-08-21 — TODO-006 (Delta-Loading) implementiert
- `02_upload_data_to_database.py`: `upsert_dataframe()` (ON CONFLICT DO UPDATE für electoral_terms/politicians/factions — nötig, da diese bei Delta-Läufen nicht mehr komplett geleert werden dürfen, andere Perioden referenzieren sie per FK) + Delta-Zweig für speeches/contributions_* (DELETE per Periode, dann Offset-Rebase + Insert). `build.sh`: `--term` überspringt jetzt den vollen DB-Reset und reicht die Perioden an den Upload durch.
- Beim ersten Testlauf gegen die echte DB gefunden: DB war in einem Teil-Zustand von einem abgebrochenen Lauf (WP1-16 vollständig, WP17 nur zur Hälfte, WP18-21 komplett fehlend, Contributions leer) — genau der Fall, für den Delta-Loading gebaut wurde.
- Bug beim ersten Testlauf gefunden: `df.where(pd.notnull(df), None)` castet `None` auf reinen `float64`-Spalten (z. B. `electoral_terms.end_date`, NaN für die noch laufende WP21) automatisch wieder zu `NaN` zurück → `NumericValueOutOfRange` beim Insert in eine `int8`-Spalte. Fix: vorher `astype(object)`.

## 2026-08-21 — Upload nach Wahlperiode quantisiert, Progressbar-Fix
- `02_upload_data_to_database.py`: neuer `upload_by_period()`-Helper — `speeches`/`contributions_*` werden jetzt periodenweise hochgeladen (Voll- und Delta-Modus), Label zeigt Perioden- und Gesamtfortschritt gleichzeitig. Nebeneffekt: bei Absturz bleibt sichtbar, welche Periode zuletzt lief, bereits erfolgreiche Perioden bleiben in der DB stehen.
- "gesamt 0/..." beim ersten Chunk vermieden — Label zeigt jetzt den Zeilenbereich der aktuellen Periode statt eines Zählers, der bei 0 startet.
- `helper_functions/progressbar.py`: `\x1b[K` (ANSI clear-to-end-of-line) vor jedem `\r` ergänzt — behebt das Zeilenrest-Artefakt ("...0]") generell, nicht nur für den Einzel-Chunk-Fall. Betrifft alle Aufrufer dieser gemeinsam genutzten Utility.

## 2026-08-21 — Upload erfolgreich verifiziert
- Vollständiger, sauberer Lauf durch: 928.120 Reden (alle 21 Perioden, lückenlos), 0 verwaiste Contributions, `faction_id`-Unbekannt-Quote überall im erwarteten 51-65%-Band. WP21 vollständig integriert. Damit ist der komplette WP21-Onboarding- und Fraktions-Bugfix-Zyklus abgeschlossen.

## Aktueller Stand (2026-08-20)
- **Pipeline noch NICHT vollständig durchgelaufen.** Alle bekannten Bugs sind gefixt, aber kein bestätigter Ende-zu-Ende-Lauf seitdem.
- Offen:
  - `01_concat_everything` (mktime-Fix) & neuer DB-Healthcheck-Wait in `build.sh` wurden seit dem Fix nicht erneut getestet.
  - `03_match_contributions_extended`-Log (7,2 MB) nie ausgewertet — evtl. weiterer Bug unentdeckt.
- Nächster Schritt: `./build.sh` erneut laufen lassen (Windows nativ oder WSL, egal). Stage-Marker (`logs/.status/*.done`) sorgen dafür, dass bereits erfolgreiche Stages übersprungen werden — Lauf setzt direkt bei der ersten offenen Stage fort.
- Fixes sitzen im Code/`build.sh` selbst → plattformunabhängig, Windows-nativ oder WSL macht hier keinen Unterschied.

## WSL/Arch-Setup
- Arch-Erstinstallation ging verloren: Move nach `D:` fehlgeschlagen, weil `D:\wsl` beim `--export` noch nicht existierte → `--unregister` lief trotzdem durch. Kein echter Verlust, da Arch noch pure/leer war. Lehre: erst Zielordner anlegen, dann Export/Unregister/Import.
- `prep-wsl-arch.sh` (Repo-Root) bootstrapt frisches Arch: `base-devel`, `python`, `nodejs`+`yarn`, `postgresql-libs`. Docker selbst nicht nötig — kommt über Docker-Desktop-WSL-Integration (Settings → Resources → WSL Integration).
- Projekt bleibt bei WSL-Nutzung unter `D:\_project\...` — via `/mnt/d/...` direkt erreichbar, kein Kopieren nötig.
- **Performance-Hinweis:** Zugriff auf `/mnt/d` aus WSL2 ist spürbar langsamer als natives ext4 (9P-Protokoll) — relevant, da die Pipeline viele kleine Dateien erzeugt (XML-Split pro Sitzung).
- **mktime-Klarstellung:** Der `OverflowError`-Bug war spezifisch für natives Windows-Python (MSVCRT), nicht für WSL/glibc — unter WSL hätte der alte Code vermutlich funktioniert. Code-Fix ist trotzdem plattformunabhängig drin.
- `archlinux` ist nicht Default-WSL-Distro (`docker-desktop` ist es) → explizit `wsl -d archlinux` nutzen.

## 2026-08-20 — Windows/Python 3.13 Migration

**Pipeline-Bugs (build.sh)**
- `02_download_raw_data_electoral_term_19_20.py`: bundestag.de liefert jetzt absolute `href`-URLs, String-Concat erzeugte kaputten Host → `urljoin`.
- Custom Progressbar nutzt Unicode-Blockzeichen → Crash unter Windows-Konsolen-Codepage → `PYTHONUTF8=1` in `build.sh`/`setup.sh`.
- `02_scrape_mgs.py`: Wikipedia blockt Requests ohne Browser-User-Agent (403) → Header ergänzt.
- `02_add_abbreviations_and_ids.py`: `KeyError 'Fraktion Die Linke'` — Mapping fehlte im Dict → ergänzt.
- `01_concat_everything.py`: `time.mktime()` wirft `OverflowError` für Daten vor 1970 unter nativem Windows-Python → durch reine Epoch-Berechnung (`datetime`-Differenz) ersetzt.
- `02_upload_data_to_database.py`: gleicher Windows-CRT-Bug in Gegenrichtung — `datetime.fromtimestamp()` wirft `OSError [Errno 22]` → durch `datetime(1970,1,1) + timedelta(seconds=...)` ersetzt.
- `helper_functions/match_names.py`: 3× Chained Assignment (`df[col].at[index] = ...`) → `FutureWarning`, bricht mit pandas 3.0 (Copy-on-Write) endgültig → auf `df.loc[index, col] = ...` umgestellt.
- `02_upload_data_to_database.py:170`: Chained Assignment via `df[col].replace(..., inplace=True)` → auf `df[col] = df[col].replace(...)` umgestellt.
- `02_upload_data_to_database.py`: `to_sql()` lief ohne jede Rückmeldung (Prozess bei `speeches` optisch "hängend", real nur unsichtbar) → `upload_with_progress()`-Helper mit 5000er-Chunks + vorhandener `progressbar`-Utility ergänzt. Hinweis: `db:update:local` macht `DROP DATABASE`/`CREATE DATABASE` — Neustart nur über `build.sh` bzw. nach erneutem `yarn db:update:local`, sonst Duplikate bei erneutem `to_sql(append)`.
- DB-Upload-Fehler war Race Condition (`sleep 20` reichte nicht) → `build.sh` wartet jetzt auf Docker-Healthcheck.

**build.sh überarbeitet**
- `| tee` maskierte bisher den echten Exit-Code jeder Stage → jetzt Prüfung via `PIPESTATUS`.
- Pro Stage `.done`-Marker in `logs/.status/` → abgeschlossene Stages werden bei erneutem Lauf übersprungen.
- Bricht beim ersten echten Fehler sofort ab, statt in Folgefehlern zu kaskadieren.
- `--force`-Flag löscht alle Marker für kompletten Neu-Lauf.

**Python-Dependencies**
- Nur Python 3.13 installiert, aber `pandas==1.4.2`/`numpy==1.22.3` haben keine cp313-Wheels.
- Entscheidung: Dependencies hochziehen statt Python downgraden. Code-Scan zeigte keine pandas-2.0-Breaking-APIs (`.append`/`.iteritems`/`.applymap`/`.ix`) im Projekt.
- `requirements.txt` aktualisiert: `pandas==2.3.3` (bewusst nicht 3.0, wegen Copy-on-Write/PyArrow-Defaults), `numpy==2.5.2`, restliche 2022er-Pins auf aktuelle Versionen.

**Proxy (Node/TS)**
- `package.json` `dev`-Script: einfache Anführungszeichen im `--exec`-Arg brechen unter `cmd.exe` (nur bash entfernt sie) → doppelte Anführungszeichen.
- TS-Fehler durch doppelte `@types/express-serve-static-core` (v5 vs. v4) wegen ungepinntem `@types/express@4.17.8` (`*`-Dependency) → `@types/express` auf `^4.17.21` gehoben.
- Frontend-`NetworkError`: Proxy lief schlicht nicht auf Port 5300.

**Environment**
- `bash` löste auf WSL-Stub (`docker-desktop`-Distro ohne `/bin/bash`) statt Git Bash auf → Arch-WSL installiert, Git-Bash-Pfad in PATH nach oben verschoben.
- `.venv/bin/activate` existiert auf nativem Windows-venv nicht (nur `Scripts/activate`) → Fallback in `setup.sh`/`build.sh`.
