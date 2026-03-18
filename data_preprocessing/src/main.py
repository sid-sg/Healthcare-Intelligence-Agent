import pandas as pd
from pathlib import Path
from .pipeline import geocode_row

ROOT = Path(__file__).resolve().parents[2]
data_path = ROOT / "data" / "Virtue-Foundation-Ghana-v0.3-Sheet1.csv"
output_path = ROOT / "data" / "geocoded_dataset.csv"

df = pd.read_csv(data_path)

# df = df.head(5).copy()

geo_results = df.apply(lambda row: geocode_row(row), axis=1)

df_geo = pd.concat([df, pd.DataFrame(list(geo_results))], axis=1)

df_geo.to_csv(output_path, index=False)

print(f"Success! Geocoded data saved to: {output_path}")