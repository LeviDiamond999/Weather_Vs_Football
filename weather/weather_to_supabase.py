import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import polars as pl
import psycopg
import requests

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
# Supabase: project -> Connect -> "Session pooler" connection string.
DB_URL = os.environ.get("SUPABASE_DB_URL",
                        "postgresql://postgres.hcbntggbogfhgryrnbys:PASSWORD@aws-0-us-east-2.pooler.supabase.com:5432/postgres")
TABLE  = "weather"           

API_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

VARIABLES = {
    "temperature_2m":       "temperature_2m (°F)",
    "rain":                 "rain (mm)",
    "precipitation":        "precipitation (mm)",
    "apparent_temperature": "apparent_temperature (°F)",
    "relative_humidity_2m": "relative_humidity_2m (%)",
    "snowfall":             "snowfall (cm)",
    "showers":              "showers (mm)",
    "snow_depth":           "snow_depth (m)",
    "visibility":           "visibility (m)",
    "surface_pressure":     "surface_pressure (hPa)",
    "wind_speed_10m":       "wind_speed_10m (mp/h)",
}

# Every column and its Postgres type. Decimals are double precision.
COLUMNS = {
    "location_id":         "integer",
    "latitude":            "double precision",
    "longitude":           "double precision",
    "elevation":           "double precision",
    "time_of_day_rounded": "text",
    **{col: "double precision" for col in VARIABLES.values()},
    "source_file":         "text",
}

# location_id -> (name, latitude, longitude). Add new stadiums here.
STADIUMS = {
    0:  ("Acrisure Stadium (PIT)",           40.445118,  -80.005745),
    1:  ("Allegiant Stadium (LV)",           36.10117,  -115.1967),
    2:  ("Arrowhead Stadium (KC)",           39.052387,  -94.483864),
    3:  ("AT&T Stadium (DAL)",               32.75946,   -97.09115),
    4:  ("Bank of America Stadium (CAR)",    35.221813,  -80.86432),
    5:  ("Caesars Superdome (NO)",           29.95653,   -90.07374),
    6:  ("Empower Field (DEN)",              39.74471,  -105.02203),
    7:  ("EverBank Stadium (JAX)",           30.322327,  -81.644424),
    8:  ("Ford Field (DET)",                 42.351395,  -83.06135),
    9:  ("Gillette Stadium (NE)",            42.09629,   -71.24448),
    10: ("Hard Rock Stadium (MIA)",          25.968954,  -80.24638),
    11: ("Highmark Stadium (BUF)",           42.764954,  -78.79994),
    12: ("Huntington Bank Field (CLE)",      41.502296,  -81.709496),
    13: ("Lambeau Field (GB)",               44.50524,   -88.049416),
    14: ("Levi's Stadium (SF)",              37.411503, -121.973076),
    15: ("Lincoln Financial Field (PHI)",    39.909508,  -75.17229),
    16: ("Lucas Oil Stadium (IND)",          39.770077,  -86.17878),
    17: ("Lumen Field (SEA)",                47.595562, -122.32443),
    18: ("M&T Bank Stadium (BAL)",           39.289543,  -76.624466),
    19: ("Mercedes-Benz Stadium (ATL)",      33.759865,  -84.39586),
    20: ("MetLife Stadium (NYG/NYJ)",        40.80899,   -74.06947),
    21: ("Nissan Stadium (TEN)",             36.158024,  -86.76494),
    22: ("Northwest Stadium (WAS)",          38.919254,  -76.87658),
    23: ("Paycor Stadium (CIN)",             39.084545,  -84.53511),
    24: ("Raymond James Stadium (TB)",       27.964216,  -82.50329),
    25: ("NRG Stadium (HOU)",                29.688457,  -95.417984),
    26: ("SoFi Stadium (LAR/LAC)",           33.957516, -118.33903),
    27: ("Soldier Field (CHI)",              41.879498,  -87.64974),
    28: ("State Farm Stadium (ARI)",         33.52082,  -112.27156),
    29: ("U.S. Bank Stadium (MIN)",          44.96949,   -93.26296),
    30: ("Tottenham Hotspur Stadium",        51.62056,    -0.1829834),
    31: ("Wembley Stadium",                  51.550354,   -0.27337646),
    32: ("Allianz Arena (Munich)",           48.23242,    11.629531),
    33: ("Estadio Azteca (Mexico City)",     19.29701,   -99.08911),
    34: ("Arena Corinthians (Sao Paulo)",   -23.585238,  -46.46997),
    35: ("Croke Park (Dublin)",              53.365837,   -6.2392273),
    36: ("Olympic Stadium (Berlin)",         52.520737,   13.251395),
    37: ("Bernabeu (Madrid)",                40.476448,   -3.7423131),
    38: ("Melbourne Cricket Ground",        -37.85589,   145.0134),
    39: ("Frankfurt Stadium",                50.075577,    8.636711),
    40: ("Maracana (Rio de Janeiro)",       -22.952549,  -43.215027),
    41: ("Stade de France (Paris)",          48.921276,    2.3591201),
}

# Seasons (preseason through the Super Bowl). Only these dates are downloaded.
def season_windows(today):
    windows = [(date(2022, 1, 1), date(2022, 2, 20))]
    for year in range(2022, today.year + 1):
        windows.append((date(year, 8, 1), date(year + 1, 2, 20)))
    return windows

CHUNK_DAYS = 60                 # days per Open-Meteo request
MAX_WEIGHT_PER_MINUTE = 450     


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def q(name):
    """Quote a column/table name for SQL (names here contain spaces and °)."""
    return '"' + name.replace('"', '""') + '"'


def prepare_table(conn):
    """Create the table with the right types, or fix the types of an existing one."""
    with conn.cursor() as cur:
        cols_sql = ",\n  ".join(f"{q(c)} {t}" for c, t in COLUMNS.items())
        cur.execute(f"CREATE TABLE IF NOT EXISTS {q(TABLE)} (\n  {cols_sql}\n)")

        cur.execute("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
        """, (TABLE,))
        existing = dict(cur.fetchall())

        for col, want in COLUMNS.items():
            have = existing.get(col)
            if have is None:
                print(f"Adding missing column {col}")
                cur.execute(f"ALTER TABLE {q(TABLE)} ADD COLUMN {q(col)} {want}")
            elif want == "double precision" and have in ("bigint", "integer", "smallint"):
                print(f"Fixing column type: {col} {have} -> double precision")
                cur.execute(f"ALTER TABLE {q(TABLE)} ALTER COLUMN {q(col)} "
                            f"TYPE double precision")

        # one row per stadium per hour
        cur.execute(f"""
            DELETE FROM {q(TABLE)} a USING {q(TABLE)} b
            WHERE a.ctid > b.ctid
              AND a.location_id = b.location_id
              AND a.time_of_day_rounded = b.time_of_day_rounded
        """)
        if cur.rowcount:
            print(f"Removed {cur.rowcount:,} duplicate rows already in the table")
        cur.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {q(TABLE + "_location_hour")}
            ON {q(TABLE)} (location_id, time_of_day_rounded)
        """)
    conn.commit()


def upsert(conn, df):
    """Add rows; if a stadium + hour already exists, replace it with the new values."""
    if df.height == 0:
        return
    cols = list(COLUMNS)
    df = df.select(cols)
    col_list = ", ".join(q(c) for c in cols)
    updates = ", ".join(f"{q(c)} = EXCLUDED.{q(c)}" for c in cols
                        if c not in ("location_id", "time_of_day_rounded"))

    with conn.cursor() as cur:
        cur.execute("""
            SELECT attname, format_type(atttypid, atttypmod)
            FROM pg_attribute
            WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped
        """, (q(TABLE),))
        types = dict(cur.fetchall())
        temp_cols = ", ".join(f"{q(c)} {types.get(c, COLUMNS[c])}" for c in cols)
        cur.execute(f"CREATE TEMP TABLE weather_incoming ({temp_cols}) ON COMMIT DROP")
        with cur.copy(f"COPY weather_incoming ({col_list}) FROM STDIN") as copy:
            for row in df.iter_rows():
                copy.write_row(row)
        cur.execute(f"""
            INSERT INTO {q(TABLE)} ({col_list})
            SELECT {col_list} FROM weather_incoming
            ON CONFLICT (location_id, time_of_day_rounded) DO UPDATE SET {updates}
        """)
    conn.commit()


def latest_hour_per_stadium(conn):
    with conn.cursor() as cur:
        cur.execute(f"SELECT location_id, MAX(time_of_day_rounded::text) "
                    f"FROM {q(TABLE)} GROUP BY location_id")
        return {loc: last for loc, last in cur.fetchall()}


# ---------------------------------------------------------------------------
# Open-Meteo
# ---------------------------------------------------------------------------
def request_weight(start, end):
    return max(1.0, ((end - start).days + 1) / 14) * max(1.0, len(VARIABLES) / 10)


def fetch(loc_id, start, end):
    """Download one stadium for one date range. Returns a polars DataFrame."""
    _, lat, lon = STADIUMS[loc_id]
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": ",".join(VARIABLES),
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "precipitation_unit": "mm", "timezone": "GMT",
    }

    data, problem = None, ""
    for attempt in range(1, 6):
        wait = 30 * attempt
        try:
            r = requests.get(API_URL, params=params, timeout=180)
        except requests.exceptions.RequestException as e:
            problem = f"connection problem: {e}"
        else:
            if r.status_code == 429:
                problem, wait = "rate limit (429)", wait * 2
            elif r.status_code >= 500:
                problem = f"server error {r.status_code}"
            elif r.status_code != 200:
                raise SystemExit(f"Open-Meteo rejected the request: {r.text[:300]}")
            else:
                try:
                    data = r.json()
                    break
                except ValueError:
                    problem = (f"reply was not weather data ({len(r.content)} bytes, "
                               f"{r.headers.get('Content-Type')}): {r.text[:150]!r}")
        print(f"    {problem} - retrying in {wait}s ({attempt}/5)")
        time.sleep(wait)

    if data is None:
        raise SystemExit(f"Gave up on location {loc_id} ({start} to {end}). "
                         f"Last problem: {problem}\nEverything added so far is saved - "
                         f"run the script again later to continue.")

    hourly = data["hourly"]
    df = pl.DataFrame(
        {"time_of_day_rounded": hourly["time"],
         **{col: hourly[var] for var, col in VARIABLES.items()}},
        schema_overrides={col: pl.Float64 for col in VARIABLES.values()},
        strict=False,
    )
    return df.with_columns(
        pl.lit(loc_id, dtype=pl.Int64).alias("location_id"),
        pl.lit(float(data["latitude"])).alias("latitude"),
        pl.lit(float(data["longitude"])).alias("longitude"),
        pl.lit(float(data["elevation"])).alias("elevation"),
        pl.lit("open-meteo api").alias("source_file"),
    )


def ranges_to_download(last_hour, today):
    """Date ranges still missing for one stadium, limited to football seasons."""
    yesterday = today - timedelta(days=1)
    start_from = (date.fromisoformat(last_hour[:10]) if last_hour else date(2022, 1, 1))
    ranges = []
    for ws, we in season_windows(today):
        s, e = max(ws, start_from), min(we, yesterday)
        while s <= e:                              # split into CHUNK_DAYS pieces
            piece_end = min(s + timedelta(days=CHUNK_DAYS - 1), e)
            ranges.append((s, piece_end))
            s = piece_end + timedelta(days=1)
    return ranges


def update_from_open_meteo(conn):
    today = datetime.now(timezone.utc).date()
    latest = latest_hour_per_stadium(conn)

    jobs = [(loc, s, e) for loc in STADIUMS
            for (s, e) in ranges_to_download(latest.get(loc), today)]
    if not jobs:
        print("Already up to date.")
        return
    print(f"{len(jobs)} pieces to download "
          f"(about {sum(request_weight(s, e) for _, s, e in jobs):,.0f} Open-Meteo calls)")

    used, minute_start, added = 0.0, time.time(), 0
    for i, (loc, start, end) in enumerate(jobs, 1):
        w = request_weight(start, end)
        if used + w > MAX_WEIGHT_PER_MINUTE:
            pause = max(0, 61 - (time.time() - minute_start))
            print(f"    pausing {pause:.0f}s to stay under Open-Meteo's limit...")
            time.sleep(pause)
            used, minute_start = 0.0, time.time()

        print(f"[{i}/{len(jobs)}] {STADIUMS[loc][0]}: {start} to {end}")
        df = fetch(loc, start, end)
        used += w
        upsert(conn, df)                       # saved right away
        added += df.height
    print(f"\nAdded or refreshed {added:,} hourly rows.")


def upload_csv(conn, path):
    df = pl.read_csv(
        path,
        schema_overrides={c: (pl.Int64 if t == "integer" else
                              pl.Float64 if t == "double precision" else pl.Utf8)
                          for c, t in COLUMNS.items()},
    )
    if "source_file" not in df.columns:
        df = df.with_columns(pl.lit(os.path.basename(path)).alias("source_file"))
    df = df.unique(subset=["location_id", "time_of_day_rounded"], keep="first")
    print(f"Uploading {df.height:,} rows from {path}...")
    for start in range(0, df.height, 50_000):           # in batches
        upsert(conn, df.slice(start, 50_000))
        print(f"    {min(start + 50_000, df.height):,} / {df.height:,}")


# ---------------------------------------------------------------------------
def main():
    if "USER:PASSWORD" in DB_URL:
        raise SystemExit("Set DB_URL at the top of the script (or SUPABASE_DB_URL) first.")

    with psycopg.connect(DB_URL) as conn:
        prepare_table(conn)
        if len(sys.argv) >= 3 and sys.argv[1] == "--csv":
            upload_csv(conn, sys.argv[2])
        else:
            update_from_open_meteo(conn)

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT location_id), "
                        f"MAX(time_of_day_rounded::text) FROM {q(TABLE)}")
            rows, stadiums, last = cur.fetchone()
        print(f"\n{TABLE}: {rows:,} rows, {stadiums} stadiums, newest hour {last}")


if __name__ == "__main__":
    main()
