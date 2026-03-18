from geopy.geocoders import Nominatim
import time

geolocator = Nominatim(user_agent="healthcare_mapper")

cache = {}

def is_good_match(query, location):
    if not location:
        return False

    address = location.raw.get("display_name", "").lower()
    query = query.lower()

    tokens = [t.strip() for t in query.split(",")]
    match_count = sum(1 for t in tokens if t in address)

    return match_count >= 1


def geocode(query):
    if not query:
        return None

    if query in cache:
        return cache[query]

    try:
        location = geolocator.geocode(query, addressdetails=True)
        time.sleep(1)

        if location and is_good_match(query, location):
            result = {
                "lat": location.latitude,
                "lon": location.longitude,
                "location_query": query,
                "osm_display_name": location.raw.get("display_name"),
            }
        else:
            result = None

        cache[query] = result
        return result

    except Exception as e:
        print(f"OSM Error: {e}")
        return None