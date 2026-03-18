import pandas as pd
from .normalizer import build_query
from .osm import geocode
from .llm_cleaner import clean_with_llm

def is_valid(text):
    if text is None:
        return False

    # Handle NaN
    if isinstance(text, float) and pd.isna(text):
        return False

    text = str(text).strip().lower()

    return text not in ["", "unknown", "none", "nan"]


def safe_join(*parts):
    cleaned = []

    for p in parts:
        if is_valid(p):
            cleaned.append(str(p).strip())

    return ", ".join(cleaned) if cleaned else None


def geocode_row(row):
    row_id = row.get("unique_id", "unknown_id")
    print(f"\n🔍 Processing row: {row_id}")

    # ---------------------------
    # Step 1: Rule-based
    # ---------------------------
    query, level = build_query(row)

    if query:
        print(f"➡️ Rule query: {query}")
        result = geocode(query)

        if result:
            return {
                **result,
                "method_used_for_geocoding": "rule_based",
                "resolved_location_query": query
            }

    # ---------------------------
    # Step 2: LLM fallback
    # ---------------------------
    print(f"⚠️ Rule-based failed → trying LLM ({row_id})")

    try:
        llm_query = clean_with_llm(row)

        if is_valid(llm_query):
            print(f"🤖 LLM query: {llm_query}")

            result = geocode(llm_query)

            if result:
                return {
                    **result,
                    "method_used_for_geocoding": "llm",
                    "resolved_location_query": llm_query
                }

    except Exception as e:
        print("❌ LLM failed:", e)

    # ---------------------------
    # Step 3: Fallback hierarchy
    # ---------------------------
    print(f"⚠️ LLM failed → trying fallback ({row_id})")

    fallbacks = [
        ("city", safe_join(row.get("address_city"), row.get("address_country"))),
        ("region", safe_join(row.get("address_stateOrRegion"), row.get("address_country"))),
        ("country", safe_join(row.get("address_country")))
    ]

    for level, fb in fallbacks:
        if not is_valid(fb):
            continue

        print(f"🔁 Fallback ({level}): {fb}")

        result = geocode(fb)

        if result:
            return {
                **result,
                "method_used_for_geocoding": "fallback",
                "resolved_location_query": fb
            }

    # ---------------------------
    # Step 4: Failure
    # ---------------------------
    print(f"❌ Failed to geocode row: {row_id}")

    return {
        "lat": None,
        "lon": None,
        "method_used_for_geocoding": "failed",
        "resolved_location_query": None
    }