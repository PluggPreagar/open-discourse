# Ideas

## Untersuchung: Fraktions-Zuordnung bricht ab WP 19/20 ein — GELÖST

**Befund (2026-08-21), Analyse von `data/03_final/speech_content.pkl`:**
- `politician_id`-Unbekannt-Quote: WP 1–18 = 2–11 %, WP 19–20 = 0,2–0,3 % (besser als Baseline).
- `faction_id`-Unbekannt-Quote: WP 1–18 = 53–65 %, WP 19–20 = 86,5 % (deutlich schlechter).

**Aufschlüsselung der 55.805 unmatched WP19/20-Fälle nach `position_short`:**
- "Presidium of Parliament" (29.342, 52,6 %) — **kein Bug**: in WP1-18 identisch zu 100 % ohne Fraktion (356.700/356.700), Sitzungsleitung hat strukturell keine Fraktionszuordnung, in beiden Pfaden konsistent.
- "Not found" (22.364, 40,1 %) — **echter Bug**: Stichprobe zeigte ganz normale Abgeordnete mit bekannter Partei (Kerstin Andreae/Grüne, Tino Chrupalla/AfD, ...) mit `position_long = None`.

**Root Cause gefunden und gefixt:** [05_electoral_term_19_20/01_extract_speeches_and_contributions_electoral_term_19_20.py:216-224](python/src/od_lib/05_electoral_term_19_20/01_extract_speeches_and_contributions_electoral_term_19_20.py:216) — im Speeches-Extraktionszweig wurde `position_raw`, wenn das `<fraktion>`-XML-Element gefunden wurde, fälschlich auf einen **leeren String** statt auf dessen Textinhalt gesetzt:
```python
position_raw = name.find("fraktion")
if position_raw is None:
    ...
else:
    position_raw = ""   # Bug: sollte find_with_default(name, "fraktion", "") sein
```
Der parallele Contributions-Extraktionszweig in derselben Datei (Zeile 327) hatte die korrekte Logik (`name.find("fraktion").text` mit try/except) — die Speeches-Logik war isoliert falsch. Fix: `position_raw = find_with_default(name, "fraktion", "")`.

**Verifiziert (2026-08-21) durch Neu-Ausführung der Stage:**

| | Vorher | Nachher |
|---|---|---|
| `faction_id`-Unbekannt-Quote | 86,5 % | WP19: 52,4 %, WP20: 53,3 % |
| „Not found"-Fälle (der eigentliche Bug) | 22.364 | WP19: 10, WP20: 534 |

Jetzt auf/unter WP1-18-Baseline (53–65 %) zurückgeführt — verbleibende Unbekannt-Fälle sind strukturell korrekt (Präsidium, Minister, Kanzler:in).

**Zwei weitere, unabhängige Ursachen für die restlichen "Not found"-Fälle gefunden und gefixt:**
1. `<fraktion>`-Elementtext teils case-unterschiedlich (`"Die Linke"` statt `"DIE LINKE"`) — Pattern-Matching war case-sensitiv → `regex.IGNORECASE` in allen vier `get_faction_abbrev()`-Kopien ergänzt.
2. `"BSW"` (Bündnis Sahra Wagenknecht, neue Partei seit Ende 2023) fehlte komplett in allen vier `faction_patterns`-Dicts → Pattern `r"BSW|Bündnis\s*Sahra\s*Wagenknecht"` ergänzt.

**Finales Ergebnis nach allen drei Fixes:** WP20 "Not found" 22.364 → 534 → 465 → **13** (99,94 % Reduktion). WP19 blieb bei 10 (war schon niedrig). Gesamtquote: WP19 52,2 %, WP20 51,4 % — sogar unter WP1-18-Baseline.

**Verbleibende ~23 Einzelfälle sind eine andere Kategorie** (keine Fraktions-Bugs mehr): Amtsträger ohne Fraktionsbezug (Wehrbeauftragte, Behindertenbeauftragter, Bürgermeister als Bundesratsmitglied, diverse Regierungsbeauftragte) plus 2 Parsing-Artefakte (Regieanweisung fälschlich als Redner erkannt, abgeschnittener Namenspräfix). Nicht weiter vertieft — verschwindend klein (0,036 % aller Reden), bräuchte neue Rollen-Kategorien statt Fraktions-Fixes.

**Vier separate Kopien von `faction_patterns`/`get_faction_abbrev`** existieren weiterhin im Projekt (`03_politicians/03_merge_politicians.py`, `04_speech_content/02_clean_speeches.py`, `05_electoral_term_19_20/...`, `06_contributions/02_clean_contributions_extended.py`) — bei einer künftigen Bereinigung auf eine gemeinsame Quelle konsolidieren (hätte diesen Bug allerdings nicht verhindert, da er vor dem Pattern-Matching lag).

