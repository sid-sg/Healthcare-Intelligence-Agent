import pandas as pd

def clean(value):
    if value is None:
        return None

    # Handle pandas NaN
    if isinstance(value, float) and pd.isna(value):
        return None

    value = str(value).strip()

    if value == "" or value.lower() in ["unknown", "none", "nan"]:
        return None

    return value

def extract_locality(line):
    line = clean(line)
    if not line:
        return None

    parts = [p.strip() for p in line.split(",") if p.strip()]

    if parts:
        return parts[-1]

    return None


def build_query(row):
    # name = clean(row.get("name"))
    city = clean(row.get("address_city"))
    region = clean(row.get("address_stateOrRegion"))
    country = clean(row.get("address_country"))

    line1 = clean(row.get("address_line1"))
    line2 = clean(row.get("address_line2"))
    line3 = clean(row.get("address_line3"))

    locality = (
        extract_locality(line3) or
        extract_locality(line2) or
        extract_locality(line1)
    )

    # Priority logic
    if locality and region and country:
        return f"{locality}, {region}, {country}", "locality_region"

    elif locality and country:
        return f"{locality}, {country}", "locality"

    elif city and region and country:
        return f"{city}, {region}, {country}", "city_region"

    elif city and country:
        return f"{city}, {country}", "city"

    else:
        return None, None