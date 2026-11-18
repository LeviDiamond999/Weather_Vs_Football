import io
import os
import sys
from datetime import date

import polars as pl
import psycopg

from build_pbp import build      # same steps as your CSV

# Supabase: project -> Connect -> "Session pooler" connection string.
DB_URL = os.environ.get("SUPABASE_DB_URL",
                        "postgresql://postgres.hcbntggbogfhgryrnbys:PASSWORD@aws-0-us-east-2.pooler.supabase.com:5432/postgres")
TABLE  = "pbp"                  
KEY    = ["game_id", "play_id"]  # one row per play
BATCH  = 20_000                  # rows per upload batch

# Only these columns go to Supabase (all ~400 columns for 2022-2026 is ~700 MB,
KEEP_COLUMNS = [
    # game info
    "season_type", "week", "game_date", "home_team", "away_team",
    "posteam", "defteam", "posteam_type",
    # stadium + weather matching
    "stadium", "stadium_id", "roof", "surface",
    "location_id", "time_of_day_rounded",
    # situation and result
    "play_type", "down", "ydstogo", "yardline_100", "yards_gained",
    "epa", "qb_epa", "wpa", "success", "first_down",
    # play type flags
    "pass_attempt", "rush_attempt", "complete_pass", "qb_dropback", "qb_scramble",
    "qb_kneel", "qb_spike", "two_point_attempt", "kick_distance",
    "sack", "interception", "fumble_lost",
    # scoring
    "touchdown", "td_team", "pass_touchdown", "rush_touchdown",
    # yards
    "passing_yards", "rushing_yards", "receiving_yards", "air_yards",
    # players
    "passer", "passer_player_id", "passer_player_name", "passer_jersey_number",
    "rusher", "rusher_player_id", "rusher_player_name", "rusher_is_qb",
    "receiver_player_id", "receiver_player_name",
    # FTN charting
    "is_play_action", "is_screen_pass", "is_rpo", "n_blitzers", "n_pass_rushers",
    "is_drop", "is_catchable_ball",
]

INT_TYPES = ("smallint", "integer", "bigint")


def q(name):
    return '"' + name.replace('"', '""') + '"'


def current_season(today=None):
    today = today or date.today()
    return today.year if today.month >= 8 else today.year - 1   # season starts in Aug


def pg_type(dtype):
    """Postgres type for a new column, based on the polars type."""
    if dtype.is_integer():
        return "bigint"
    if dtype.is_float():
        return "double precision"
    if dtype == pl.Boolean:
        return "boolean"
    if dtype == pl.Date:
        return "date"
    if isinstance(dtype, pl.Datetime):
        return "timestamp"
    return "text"


# ---------------------------------------------------------------------------
# Make the table and the new data agree on column types
# ---------------------------------------------------------------------------
def table_columns(cur):
    cur.execute("SELECT to_regclass(%s)", (q(TABLE),))
    if cur.fetchone()[0] is None:
        return None
    cur.execute("""
        SELECT attname, format_type(atttypid, atttypmod)
        FROM pg_attribute
        WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped
    """, (q(TABLE),))
    return dict(cur.fetchall())


def prepare(conn, df):
    """Create/fix the table so df fits, and adjust df to the table's types."""
    with conn.cursor() as cur:
        cols = table_columns(cur)

        if cols is None:                                    # brand-new table
            col_sql = ", ".join(f"{q(c)} {pg_type(t)}" for c, t in df.schema.items())
            cur.execute(f"CREATE TABLE {q(TABLE)} ({col_sql})")
            print(f"Created table {TABLE} with {df.width} columns")
            cols = table_columns(cur)

        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
              AND (is_identity = 'YES' OR column_default LIKE 'nextval%%')
        """, (TABLE,))
        auto_cols = {row[0] for row in cur.fetchall()}
        clashes = {c: f"{c}_nflverse" for c in df.columns if c in auto_cols}
        if clashes:
            df = df.rename(clashes)
            for old, new in clashes.items():
                print(f"Your table's {old} column is filled in by Supabase, "
                      f"so nflfastR's {old} is stored as {new}")

        fixes = []
        for c, dtype in df.schema.items():
            have = cols.get(c)
            if have is None:                                # new column
                cur.execute(f"ALTER TABLE {q(TABLE)} ADD COLUMN {q(c)} {pg_type(dtype)}")
                print(f"Added column {c} ({pg_type(dtype)})")
            elif have in INT_TYPES and dtype.is_float():
                whole = df.select((pl.col(c).drop_nulls().drop_nans() % 1 == 0).all()).item()
                if whole:                                   # 3.0 -> 3 to fit the column
                    fixes.append(pl.col(c).fill_nan(None).cast(pl.Int64))
                else:                                       # real decimals: widen the column
                    cur.execute(f"ALTER TABLE {q(TABLE)} ALTER COLUMN {q(c)} "
                                f"TYPE double precision")
                    print(f"Fixed column type: {c} {have} -> double precision")
            elif have in INT_TYPES and dtype == pl.Boolean:
                fixes.append(pl.col(c).cast(pl.Int64))      # true/false -> 1/0
            elif have == "boolean" and dtype.is_numeric():
                fixes.append(pl.col(c) != 0)                # 1/0 -> true/false
            elif have == "text" and dtype != pl.Utf8:
                fixes.append(pl.col(c).cast(pl.Utf8))
            elif dtype.is_float():
                fixes.append(pl.col(c).fill_nan(None))      # NaN -> empty

        # one row per play: remove duplicates, then enforce it
        key_sql = ", ".join(q(k) for k in KEY)
        cur.execute(f"""
            DELETE FROM {q(TABLE)} a USING {q(TABLE)} b
            WHERE a.ctid > b.ctid AND a.game_id = b.game_id AND a.play_id = b.play_id
        """)
        if cur.rowcount:
            print(f"Removed {cur.rowcount:,} duplicate plays already in the table")
        cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {q(TABLE + '_play')} "
                    f"ON {q(TABLE)} ({key_sql})")
    conn.commit()
    return df.with_columns(fixes) if fixes else df


def upsert(conn, df):
    """Add plays; plays already in the table are replaced with the new version."""
    with conn.cursor() as cur:
        types = table_columns(cur)
        cols = df.columns
        col_list = ", ".join(q(c) for c in cols)
        temp_cols = ", ".join(f"{q(c)} {types[c]}" for c in cols)
        updates = ", ".join(f"{q(c)} = EXCLUDED.{q(c)}" for c in cols if c not in KEY)
        key_sql = ", ".join(q(k) for k in KEY)

        for start in range(0, df.height, BATCH):
            part = df.slice(start, BATCH)
            buf = io.BytesIO()
            part.write_csv(buf, include_header=False, null_value="")
            cur.execute(f"CREATE TEMP TABLE pbp_incoming ({temp_cols}) ON COMMIT DROP")
            with cur.copy(f"COPY pbp_incoming ({col_list}) FROM STDIN "
                          f"WITH (FORMAT csv, NULL '')") as copy:
                copy.write(buf.getvalue())
            cur.execute(f"""
                INSERT INTO {q(TABLE)} ({col_list})
                SELECT {col_list} FROM pbp_incoming
                ON CONFLICT ({key_sql}) DO UPDATE SET {updates}
            """)
            conn.commit()
            print(f"    uploaded {min(start + BATCH, df.height):,} / {df.height:,} plays")


def games_to_update(conn, season):
    """Game IDs in Supabase that are complete (have FTN data) for this season."""
    with conn.cursor() as cur:
        cols = table_columns(cur)
        # table missing, empty, or made before these columns existed:
        if cols is None or not {"game_id", "season", "is_qb_sneak"} <= set(cols):
            print(f"Table {TABLE} doesn't have play data with all columns yet - "
                  f"loading every game this season.")
            return set()
        cur.execute(f"""
            SELECT game_id FROM {q(TABLE)}
            WHERE season = %s
            GROUP BY game_id
            HAVING COUNT(is_qb_sneak) > 0
        """, (season,))
        return {row[0] for row in cur.fetchall()}


def main():
    if "USER:PASSWORD" in DB_URL:
        raise SystemExit("Set DB_URL at the top of the script (or SUPABASE_DB_URL) first.")

    full_reload = len(sys.argv) >= 3 and sys.argv[1] == "--seasons"
    seasons = [int(s) for s in sys.argv[2:]] if full_reload else [current_season()]

    df = build(seasons)
    if KEEP_COLUMNS:
        # these are always needed: the play ID, and the columns the update check uses
        needed = KEY + ["season", "is_qb_sneak"]
        keep = list(dict.fromkeys(needed + list(KEEP_COLUMNS)))
        missing = [c for c in keep if c not in df.columns]
        if missing:
            raise SystemExit(f"These KEEP_COLUMNS don't exist in the data: {missing}")
        df = df.select(keep)

    with psycopg.connect(DB_URL) as conn:
        if not full_reload:
            done = games_to_update(conn, seasons[0])
            df = df.filter(~pl.col("game_id").is_in(list(done)))
            n_games = df["game_id"].n_unique()
            if n_games == 0:
                print("Already up to date - no new games.")
                return
            print(f"{n_games} games to add or refresh ({df.height:,} plays)")

        df = prepare(conn, df)
        upsert(conn, df)

        with conn.cursor() as cur:
            cur.execute(f"SELECT season, COUNT(DISTINCT game_id), COUNT(*) FROM {q(TABLE)} "
                        f"GROUP BY season ORDER BY season")
            print(f"\n{TABLE} now holds:")
            for season, games, plays in cur.fetchall():
                print(f"  {season}: {games} games, {plays:,} plays")


if __name__ == "__main__":
    main()
