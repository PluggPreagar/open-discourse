# Architektur

```mermaid
flowchart LR
  Browser -->|fetch NEXT_PUBLIC_PROXY_ENDPOINT| Proxy
  Proxy -->|pg pool, Port 5432| Database[(Postgres: next)]
  Python[python/build.sh] -->|Reden, Politiker, Fraktionen| Database
  Database -.->|yarn db:update:local\nDROP/CREATE next| Database

  subgraph Frontend[frontend :3000 - Next.js]
    Browser
  end
  subgraph Proxy[proxy :5300 - Express]
  end
  subgraph DB[database :5432 - Postgres+rum]
    Database
  end
```

- **frontend**: Next.js, holt Daten client-seitig direkt vom Proxy (kein SSR-Fetch).
- **proxy**: einzige Komponente mit DB-Zugriff, cached GET-Responses, rate-limited.
- **database**: Docker-Image ist nur der leere Postgres-Server; Schema/Daten kommen erst durch `yarn db:update:local` (legt `next` neu an) + `python/build.sh` (Pipeline-Upload).

## DB-Import-Prozess (`02_upload_data_to_database.py`)

```mermaid
flowchart TD
    A["python/data/03_final/*.pkl\n(Ergebnis der Pipeline-Stages 01-07_01)"] --> B["Upsert Referenztabellen\n(electoral_terms / politicians / factions)\nON CONFLICT DO UPDATE - immer"]
    B --> C{"DELTA_TERMS gesetzt?\n(CLI: Term-Nummern, optional --force)"}

    C -->|"nein - Full Rebuild"| D["Drop speeches-Indizes\nCOPY-Insert aller Perioden (leeres Schema)\nRebuild-Indizes"]

    C -->|"ja - Delta"| E["Drop speeches-Indizes (1x pro Lauf,\nfalls irgendein Term Arbeit braucht)"]
    E --> L["Loop pro Wahlperiode"]
    L --> M["Match-Check je Tabelle:\ndb_matches_pickle() bzw. Row-Count\n(--force erzwingt Mismatch)"]
    M -->|"matcht"| F["Skip: kein Delete,\nIDs bleiben stehen"]
    M -->|"Mismatch"| G["delete_rows(): contributions_ext/simpl zuerst,\ndann speeches (FK-Reihenfolge);\nspeeches per ID-Range partitioniert (PK-Scan),\ncontributions per id % N; parallel, 5000er-Batches"]
    G --> H["ID-Rebase: next_id_start()\nadditiver Offset"]
    H --> I["COPY-Upload (25k-Chunks):\nspeeches zuerst, dann contributions"]
    F --> L
    I --> L
    L --> K["Rebuild speeches-Indizes (1x am Ende)"]
    D --> J[("speeches\ncontributions_extended\ncontributions_simplified")]
    K --> J
```

- **Full Rebuild** (kein CLI-Arg): leeres Schema vorausgesetzt, IDs 1:1 aus der Pipeline.
- **Delta** (Term-Nummern als Args, `--force` überspringt Match-Checks): pro Wahlperiode geloopt; je Tabelle Match-Check, nur bei Abweichung Delete+Reinsert. Ersetzen der speeches erzwingt Ersetzen der contributions (ID-Offset + FK).
- Insert via Postgres `COPY` (copy_expert, `\N`-NULL-Marker), sequenziell; Delete parallel partitioniert.
- speeches-Indizes (inkl. RUM-Volltext) werden für Bulk-Writes gedroppt und einmalig neu gebaut — RUM-Pflege pro Zeile war der Insert-/Delete-Flaschenhals. Zweiter Delete-Flaschenhals war der fehlende Index auf `contributions_*.speech_id` (FK-Check = Seq-Scan pro Zeile), seit 2026-08-26 im Schema.

## Datenmodell

```mermaid
erDiagram
    electoral_terms ||--o{ speeches : electoral_term
    factions ||--o{ speeches : faction_id
    politicians ||--o{ speeches : politician_id
    speeches ||--o{ contributions_extended : speech_id
    speeches ||--o{ contributions_simplified : speech_id
    factions ||--o{ contributions_extended : faction_id
    politicians ||--o{ contributions_extended : politician_id

    electoral_terms {
        int8 id PK
        int8 start_date
        int8 end_date
    }
    factions {
        int8 id PK
        varchar abbreviation
        varchar full_name
    }
    politicians {
        int8 id PK
        varchar first_name
        varchar last_name
        varchar birth_place
        varchar birth_country
        date birth_date
        date death_date
        varchar gender
        varchar profession
        varchar aristocracy
        varchar academic_title
    }
    speeches {
        int8 id PK
        int8 session
        int8 electoral_term FK
        varchar first_name
        varchar last_name
        int8 politician_id FK
        text speech_content
        int8 faction_id FK
        varchar document_url
        varchar position_short
        varchar position_long
        date date
        tsvector search_speech_content
    }
    contributions_extended {
        int8 id PK
        varchar type
        varchar first_name
        varchar last_name
        int8 politician_id FK
        text content
        int8 speech_id FK
        int8 text_position
        int8 faction_id FK
    }
    contributions_simplified {
        int8 id PK
        int8 text_position
        int8 speech_id FK
        varchar content
    }
```

- Schema `open_discourse`, 6 Kerntabellen. `search_speech_content` ist eine generierte `tsvector`-Spalte (German-Volltextsuche), von `search_speeches()` verwendet.
- `speeches.first_name`/`last_name` sind **denormalisiert** (Snapshot des zur Redezeit gebräuchlichen Namens) und können vom `politicians`-Datensatz abweichen — siehe TODO-007.
- `politician_id`/`faction_id` nutzen `-1`/"not found" als Sentinel bei fehlender Zuordnung (in `speeches` NOT NULL, in `contributions_extended` nullable).
- `contributions_*.speech_id` ist indexiert (FK-Spalten werden von Postgres nicht auto-indexiert; ohne Index macht ein speeches-Delete pro Zeile einen Seq-Scan der Kindtabellen).
- Weitere Schemas (nicht im Diagramm): `misc` (`fts_tracking`, `topic_tracking` — Such-Query-Logging), `lda_group`/`lda_person` (Topic-Modelling, separat von der Kernsuche).
