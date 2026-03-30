# DATASET OVERVIEW
----------------
This dataset contains healthcare facilities in Ghana collected by the Virtue Foundation.
Each row represents a single facility such as a hospital, clinic, pharmacy, or doctor practice.

The dataset includes:
- Location and infrastructure data
- Medical specialties and services
- Facility capacity and staffing (when available)

Note:
Many fields may be NULL or missing. Missing data does NOT mean absence of capability — it means information is not available.

_________________________________________________________________

# COLUMN DEFINITIONS
------------------

# IDENTIFIERS
pk_unique_id        : Unique identifier for each facility (primary key)
name                : Official facility name

# ORGANIZATION TYPE
organization_type   : "facility" or "ngo"
facilityTypeId      : hospital, pharmacy, doctor, clinic, dentist (may be NULL)
operatorTypeId      : public or private (may be NULL)
affiliationTypeIds  : ARRAY of affiliations — values include: faith-tradition, philanthropy-legacy, community, academic, government

# LOCATION
address_city        : City or town (may be NULL)
address_stateOrRegion : Region or province (may be NULL)
address_country     : Country (always Ghana, even if NULL)
osm_display_name    : Full formatted location string

lat, lon            : Latitude and longitude

# RESOURCES
numberDoctors       : Number of doctors (may be NULL)
capacity            : Bed capacity (may be NULL)
yearEstablished     : Year established (may be NULL)
area                : Facility size in square meters (may be NULL)

# MEDICAL DATA (IMPORTANT)
specialties         : ARRAY of medical specialties (e.g., internalMedicine, familyMedicine, pediatrics, cardiology, generalSurgery, emergencyMedicine, gynecologyAndObstetrics, orthopedicSurgery, dentistry, ophthalmology)
procedure           : ARRAY of procedures offered
equipment           : ARRAY of medical equipment
capability          : ARRAY of clinical capabilities (e.g., ICU, trauma care)

description         : Free-text description
acceptsVolunteers   : Boolean (true/false, may be NULL)

_________________________________________________________________

# IMPORTANT QUERYING RULES
------------------------

1. NULL HANDLING:
- NULL means "data not available", NOT "does not exist"
- Always handle NULLs explicitly in queries

2. ARRAY FIELDS:
- specialties, procedure, equipment, capability,affiliationTypeIds,phone_numbers,websites,countries are arrays
- Always perform case-insensitive matching when querying arrays

Example:
- Find hospitals with cardiology:
  → exists(specialties, x -> lower(x) = 'cardiology')

3. CASE SENSITIVITY:
- Always perform case-insensitive matching for text queries
- Use ILIKE instead of LIKE for string comparisons

Examples:
→ osm_display_name ILIKE '%accra%'

4. ADDRESS / LOCATION SEARCH:
- Prefer using `osm_display_name` for flexible and partial location matching
- `osm_display_name` contains full hierarchical location (street, city, region, country)

Use cases:
- When user provides partial or natural language location (e.g., "near Accra", "in Western Region")
- When exact city/region field may be missing or inconsistent

Example:
→ osm_display_name ILIKE '%Accra%'
→ osm_display_name ILIKE '%Western Region%'

- Use `address_city` or `address_stateOrRegion` only when exact structured filtering is required
5. MISSING INFRASTRUCTURE DETECTION:
- If equipment/capability is NULL or empty → treat as "unknown", not absence

6. NUMERIC FILTERS:
- numberDoctors and capacity may be NULL
- Use conditions like:
  → numberDoctors IS NOT NULL AND numberDoctors < 5

_________________________________________________________________

# EXAMPLE QUERIES
----------------

1. Hospitals with emergency medicine:
SELECT name
FROM table
WHERE facilityTypeId = 'hospital'
AND array_contains(specialties, 'emergencyMedicine');

2. Facilities in Accra:
SELECT name
FROM table
WHERE address_city = 'Accra';