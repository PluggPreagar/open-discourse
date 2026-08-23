from sqlalchemy import create_engine, text, table as sa_table, column as sa_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
import od_lib.definitions.path_definitions as path_definitions
from od_lib.helper_functions.progressbar import progressbar
import pandas as pd
import datetime
import sys

UPLOAD_CHUNK_SIZE = 5000
SCHEMA = "open_discourse"

# Optional CLI args: one or more electoral_term numbers, e.g. `02_upload_data_to_database.py 19 20 21`.
# Only those speeches/contributions are effected (updated = deleted+inserted)
DELTA_TERMS = [int(t) for t in sys.argv[1:]] if len(sys.argv) > 1 else None

def upload_with_progress(df, table_name, engine, schema, chunk_size=UPLOAD_CHUNK_SIZE, label=None):
    """Uploads df to table_name in chunks, showing a progress bar."""
    label = label or f"Upload {table_name}..."
    if len(df) <= chunk_size:
        print(label, end="", flush=True)
        df.to_sql(table_name, engine, if_exists="append", schema=schema, index=False)
        print(" Done.")
        return
    chunk_starts = range(0, len(df), chunk_size)
    for start in progressbar(chunk_starts, label):
        df.iloc[start : start + chunk_size].to_sql(
            table_name, engine, if_exists="append", schema=schema, index=False
        )


def upload_by_period(df, table_name, engine, schema, periods, chunk_size=UPLOAD_CHUNK_SIZE):
    """Chunky version of upload_with_progress - split by term + batch.

    `periods` is a Series aligned with df's rows giving each row's electoral
    term (df itself may not have that column directly, e.g. contributions_*
    only carry a speech_id - the caller maps that to a term beforehand).
    """
    total_rows = len(df)
    rows_done = 0
    unique_periods = sorted(periods.unique())
    for i, period in enumerate(unique_periods, start=1):
        subset = df[(periods == period).values]
        label = (
            f"Upload {table_name} (Wahlperiode {period}, {i}/{len(unique_periods)}, "
            f"Zeile {rows_done + 1}-{rows_done + len(subset)}/{total_rows})..."
        )
        upload_with_progress(subset, table_name, engine, schema, chunk_size=chunk_size, label=label)
        rows_done += len(subset)


def upsert_dataframe(df, table_name, engine, schema, pk_cols=("id",), chunk_size=UPLOAD_CHUNK_SIZE):
    """Insert/Update for the small reference (not period-scoped) tables
    (electoral_terms/politicians/factions). Will keep tables in delta mode
    (untouched periods' speeches will have foreign keys to them).
    """
    if len(df) == 0:
        return
    print(f"Upsert {table_name}...", end="", flush=True)
    # astype(object) first: on a pure-float column (e.g. electoral_terms.end_date,
    # which is NaN for the still-ongoing current term), plain .where(notnull, None)
    # silently casts None back to NaN (float64 can't hold None natively).
    df = df.astype(object).where(pd.notnull(df), None)
    tbl = sa_table(table_name, *[sa_column(c) for c in df.columns], schema=schema)
    records = df.to_dict(orient="records")
    with engine.begin() as conn:
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            stmt = pg_insert(tbl).values(chunk)
            update_cols = {c: stmt.excluded[c] for c in df.columns if c not in pk_cols}
            stmt = stmt.on_conflict_do_update(index_elements=list(pk_cols), set_=update_cols)
            conn.execute(stmt)
    print(" Done.")


def delete_rows(engine, schema, table_name, where_sql=None, params=None):
    sql = f'DELETE FROM "{schema}"."{table_name}"'
    if where_sql:
        sql += f" WHERE {where_sql}"
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def next_id_start(engine, schema, table_name, id_col="id"):
    with engine.connect() as conn:
        max_id = conn.execute(
            text(f'SELECT MAX("{id_col}") FROM "{schema}"."{table_name}"')
        ).scalar()
    return 0 if max_id is None else max_id + 1


engine = create_engine("postgresql://postgres:postgres@localhost:5432/next")

# Load Final Data

CONTRIBUTIONS_EXTENDED = path_definitions.DATA_FINAL / "contributions_extended.pkl"
SPOKEN_CONTENT = path_definitions.DATA_FINAL / "speech_content.pkl"
FACTIONS = path_definitions.DATA_FINAL / "factions.pkl"
PEOPLE = path_definitions.DATA_FINAL / "politicians.csv"
CONTRIBUTIONS_SIMPLIFIED = path_definitions.CONTRIBUTIONS_SIMPLIFIED \
    / "contributions_simplified.pkl"
ELECTORAL_TERMS = path_definitions.ELECTORAL_TERMS / "electoral_terms.csv"

# Load data
electoral_terms = pd.read_csv(ELECTORAL_TERMS)

politicians = pd.read_csv(PEOPLE)
politicians = politicians.drop_duplicates(subset=["ui"], keep="first")
politicians = politicians.drop(
    [
        "electoral_term",
        "faction_id",
        "institution_type",
        "institution_name",
        "constituency",
    ],
    axis=1,
)

politicians.columns = [
    "id",
    "first_name",
    "last_name",
    "birth_place",
    "birth_country",
    "birth_date",
    "death_date",
    "gender",
    "profession",
    "aristocracy",
    "academic_title",
]

series = {
    "id": -1,
    "first_name": "Not found",
    "last_name": "",
    "birth_place": None,
    "birth_country": None,
    "birth_date": None,
    "death_date": None,
    "gender": None,
    "profession": None,
    "aristocracy": None,
    "academic_title": None,
}

politicians = pd.concat([politicians, pd.DataFrame([series])], ignore_index=True)


def convert_date_politicians(date):
    try:
        date = datetime.datetime.strptime(date, "%d.%m.%Y")
        date = date.strftime("%Y-%m-%d %H:%M:%S")
        return date
    except (ValueError, TypeError):
        return None


def convert_date_speeches(date):
    try:
        date = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=date)
        date = date.strftime("%Y-%m-%d %H:%M:%S")
        return date
    except (ValueError, TypeError) as e:
        print(e)
        return None


def check_politicians(row):
    speaker_id = row["politician_id"]

    politician_ids = politicians["id"].tolist()
    if speaker_id not in politician_ids:
        speaker_id = -1
    return speaker_id


# Upsert - non-period-scoped tables with referenced keys
upsert_dataframe(electoral_terms, "electoral_terms", engine, SCHEMA)

politicians["birth_date"] = politicians["birth_date"].apply(convert_date_politicians)
politicians["death_date"] = politicians["death_date"].apply(convert_date_politicians)

upsert_dataframe(politicians, "politicians", engine, SCHEMA)

# list of all factions in the form ["abbreviation", "full_name"]
factions = [
    ["not found", "not found"],
    ["AfD", "Alternative für Deutschland"],
    ["BHE", "Block der Heimatvertriebenen und Entrechteten"],
    ["BP", "Bayernpartei"],
    ["BSW", "Bündnis Sahra Wagenknecht"],
    ["Grüne", "Bündnis 90/Die Grünen"],
    ["CDU/CSU", "Christlich Demokratische Union Deutschlands/Christlich-Soziale Union in Bayern"],
    ["DA", "Demokratische Arbeitsgemeinschaft"],
    ["DIE LINKE.", "DIE LINKE."],
    ["DP", "Deutsche Partei"],
    ["DP/DPB", "Deutsche Partei/Deutsche Partei Bayern"],
    ["DP/FVP", "Deutsche Partei/Freie Volkspartei"],
    ["DPB", "Deutsche Partei Bayern"],
    ["DRP", "Deutsche Reformpartei"],
    ["DRP/NR", "Deutsche Reichspartei/Nationale Rechte"],
    ["DSU", "Deutsche Soziale Union"],
    ["FDP", "Freie Demokratische Partei"],
    ["FU", "Föderalistische Union"],
    ["FVP", "Freie Volkspartei"],
    ["Fraktionslos", "Fraktionslos"],
    ["GB/BHE", "Gesamtdeutscher Block/Bund der Heimatvertriebenen und Entrechteten"],
    ["Gast", "Gast"],
    ["KO", "Kraft/Oberländer-Gruppe"],
    ["KPD", "Kommunistische Partei Deutschlands"],
    ["NR", "Nationale Rechte"],
    ["PDS", "Partei des Demokratischen Sozialismus"],
    ["SPD", "Sozialdemokratische Partei Deutschlands"],
    ["SSW", "Südschleswigscher Wählerverband"],
    ["WAV", "Wirtschaftliche Aufbau-Vereinigung"],
    ["Z", "Deutsche Zentrumspartei"],
]

# convert to dataframe and add id-field
factions = pd.DataFrame(
    [[idx-1, *entry] for idx, entry in enumerate(factions)],
    columns=["id", "abbreviation", "full_name"],
)
factions["id"] = factions["id"].astype(int)

upsert_dataframe(factions, "factions", engine, SCHEMA)

speeches = pd.read_pickle(SPOKEN_CONTENT)

speeches["date"] = speeches["date"].apply(convert_date_speeches)

speeches = speeches.where((pd.notnull(speeches)), None)
speeches["position_long"] = speeches["position_long"].replace(
    [r"^\s*$"], [None], regex=True
)
speeches["politician_id"] = speeches.apply(check_politicians, axis=1)

contributions_extended = pd.read_pickle(CONTRIBUTIONS_EXTENDED)

contributions_extended = contributions_extended.where(
    (pd.notnull(contributions_extended)), None
)

contributions_simplified_parts = [pd.read_pickle(CONTRIBUTIONS_SIMPLIFIED)]
for folder_path in sorted(path_definitions.CONTRIBUTIONS_SIMPLIFIED.iterdir()):
    if not folder_path.is_dir() or not folder_path.name.startswith("electoral_term_"):
        continue
    contributions_simplified_parts.append(
        pd.read_pickle(folder_path / "contributions_simplified.pkl")
    )

contributions_simplified = pd.concat(contributions_simplified_parts, sort=False)

contributions_simplified = contributions_simplified.where(
    (pd.notnull(contributions_simplified)), None
)

# for per-period progress only: derive electoral_term from speech
# (contributions_* don't carry it)
speech_term_by_id = speeches.set_index("id")["electoral_term"]

if DELTA_TERMS is None:
    # FULL REBUILD
    # init id from pipeline 1:1 (0-based for WP1-18, incr 1_000_000 for WP19+)
    contributions_simplified["id"] = range(len(contributions_simplified.content))

    upload_by_period(speeches, "speeches", engine, SCHEMA, speeches["electoral_term"])
    upload_by_period(
        contributions_extended,
        "contributions_extended",
        engine,
        SCHEMA,
        contributions_extended["speech_id"].map(speech_term_by_id),
    )
    upload_by_period(
        contributions_simplified,
        "contributions_simplified",
        engine,
        SCHEMA,
        contributions_simplified["speech_id"].map(speech_term_by_id),
    )
else:
    # DELTA - keep terms as self-contained block, use global id offset
    print(f"Delta load for electoral term(s): {DELTA_TERMS}")

    delta_speeches = speeches[speeches["electoral_term"].isin(DELTA_TERMS)].copy()
    working_speech_ids = set(delta_speeches["id"])
    delta_contributions_extended = contributions_extended[
        contributions_extended["speech_id"].isin(working_speech_ids)
    ].copy()
    delta_contributions_simplified = contributions_simplified[
        contributions_simplified["speech_id"].isin(working_speech_ids)
    ].copy()
    # Capture periods before speech_id gets rebased below - the mapping is
    # keyed on the original (pre-offset) working IDs.
    ext_periods = delta_contributions_extended["speech_id"].map(speech_term_by_id)
    simplified_periods = delta_contributions_simplified["speech_id"].map(speech_term_by_id)

    if len(delta_speeches) == 0:
        print(f"No speeches found for term(s) {DELTA_TERMS} - nothing to do.")
    else:
        term_filter_sql = "electoral_term = ANY(:terms)"
        speech_scope_sql = (
            f"speech_id IN (SELECT id FROM {SCHEMA}.speeches WHERE {term_filter_sql})"
        )
        # FK-safe delete order: contributions reference speeches, so they go first.
        delete_rows(engine, SCHEMA, "contributions_extended", speech_scope_sql, {"terms": DELTA_TERMS})
        delete_rows(engine, SCHEMA, "contributions_simplified", speech_scope_sql, {"terms": DELTA_TERMS})
        delete_rows(engine, SCHEMA, "speeches", term_filter_sql, {"terms": DELTA_TERMS})

        # Rebase speeches.id (and every speech_id reference to it) onto free IDs.
        speeches_offset = next_id_start(engine, SCHEMA, "speeches") - delta_speeches["id"].min()
        delta_speeches["id"] += speeches_offset
        delta_contributions_extended["speech_id"] += speeches_offset
        delta_contributions_simplified["speech_id"] += speeches_offset

        # contributions_extended.id and contributions_simplified.id are independent
        # PK spaces (nothing else references them) - rebase each on its own.
        if len(delta_contributions_extended) > 0:
            ext_offset = (
                next_id_start(engine, SCHEMA, "contributions_extended")
                - delta_contributions_extended["id"].min()
            )
            delta_contributions_extended["id"] += ext_offset

        simplified_next_id = next_id_start(engine, SCHEMA, "contributions_simplified")
        delta_contributions_simplified = delta_contributions_simplified.reset_index(drop=True)
        delta_contributions_simplified["id"] = range(
            simplified_next_id, simplified_next_id + len(delta_contributions_simplified)
        )

        # Insert order: speeches first, the other two reference it.
        upload_by_period(delta_speeches, "speeches", engine, SCHEMA, delta_speeches["electoral_term"])
        upload_by_period(
            delta_contributions_extended, "contributions_extended", engine, SCHEMA, ext_periods
        )
        upload_by_period(
            delta_contributions_simplified, "contributions_simplified", engine, SCHEMA, simplified_periods
        )
