"""
Join several CSVs that share the same structure.

For each CSV:
  - drop the first 41 rows (the location metadata block + blank line)
  - use row 42 as the column names
Then stack them all into one CSV and download it.

Works in Google Colab (asks you to upload files, then downloads the result)
or on your own computer (reads every .csv in a folder you choose).
"""

import glob
import os
import pandas as pd

OUTPUT_FILE = "joined.csv"
INPUT_FOLDER = "."          # used only when NOT running in Colab


def load_one(path):
    # skiprows=41 drops rows 1-41, so row 42 becomes the header
    df = pd.read_csv(path, skiprows=41)
    df["source_file"] = os.path.basename(path)   # remember where each row came from
    return df


def main():
    try:
        from google.colab import files          # running in Colab
        in_colab = True
        uploaded = files.upload()               # pick all your CSVs at once
        paths = list(uploaded.keys())
    except ImportError:                         # running locally
        in_colab = False
        paths = sorted(glob.glob(os.path.join(INPUT_FOLDER, "*.csv")))
        paths = [p for p in paths if os.path.basename(p) != OUTPUT_FILE]

    if not paths:
        raise SystemExit("No CSV files found.")

    # --- clean and join ---
    frames = []
    for p in paths:
        df = load_one(p)
        print(f"{os.path.basename(p)}: {len(df):,} rows")
        frames.append(df)

    joined = pd.concat(frames, ignore_index=True)

    # warn if any file had different columns than the first one
    first_cols = list(frames[0].columns)
    for p, df in zip(paths, frames):
        if list(df.columns) != first_cols:
            print(f"Warning: {os.path.basename(p)} has different columns")

    joined.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved {OUTPUT_FILE}: {len(joined):,} rows, {len(joined.columns)} columns")

    if in_colab:
        files.download(OUTPUT_FILE)
    else:
        print(f"File is at: {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    main()