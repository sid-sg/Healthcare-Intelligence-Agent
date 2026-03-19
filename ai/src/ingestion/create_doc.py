import pandas as pd
from pathlib import Path
import json
from langchain_core.documents import Document

# Locate the project root dynamically
ROOT = Path(__file__).resolve().parents[3]

data_path = ROOT / "data" /"geocoded_dataset.csv"

data_frame = pd.read_csv(data_path)

documents = []

# Helper functions to clean data
def clean(value):
    if pd.isna(value):
        return ""
    return value

def clean_or_unknown(value): # for address, no. of doctors, bed capacity
    if pd.isna(value) or str(value).strip() == "":
        return "unknown"
    return str(value).strip()

def clean_list(value):
    if pd.isna(value):
        return ""

    # If it's a string like '["something"]'
    if isinstance(value, str):
        value = value.strip()

        if value == "[]" or value == "":
            return ""

        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return "\n".join(f"- {item}" for item in parsed if item)

        except:
            return value

    # If it's already a list
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value if item)


    return str(value)


# Iterate through each row in the DataFrame and create a Document for each healthcare facility
for _, row in data_frame.iterrows():

    # Clean and extract relevant information from each row

    # Basic info
    name = clean(row.get('name', ''))
    facilityTypeId = clean(row.get('facilityTypeId', ''))
    organization_type = clean(row.get('organization_type', '')) 

    # Location info
    city = clean_or_unknown(row.get('address_city', ''))
    region = clean_or_unknown(row.get('address_stateOrRegion', ''))
    country = clean_or_unknown(row.get('address_country', ''))
    lat = row.get("lat")
    lon = row.get("lon")
    osm_location = clean(row.get("osm_display_name"))

    # Medical info
    description = clean(row.get('description', ''))
    specialties = clean_list(row.get('specialties', ''))
    capability = clean_list(row.get('capability', ''))
    procedure = clean_list(row.get('procedure', ''))
    equipment = clean_list(row.get('equipment', ''))

    number_doctors = clean_or_unknown(row.get('numberDoctors', ''))
    capacity = clean_or_unknown(row.get('capacity', ''))

    text = f"""
[FACILITY]
Organization Type: {organization_type} 
Name: {name}
Facility Type: {facilityTypeId}

[LOCATION]
Location: {osm_location}

[RESOURCES]
Number of Doctors: {number_doctors}
Patient Bed Capacity: {capacity}
"""
    if description or specialties or capability or procedure or equipment:
        text += "\n\n[ADDITIONAL INFORMATION]"

    if description:
        text += f"\nDescription:\n{description}\n"

    if specialties:
        text += f"\nSpecialties:\n{specialties}\n"

    if capability:
        text += f"\nCapabilities:\n{capability}\n"

    if procedure:
        text += f"\nProcedures Offered:\n{procedure}\n"

    if equipment:
        text += f"\nMedical Equipment:\n{equipment}\n"

    # Metadata

    metadata = {
    "facility_id": clean(row.get("unique_id")),
    "name": name,
    "organization_type": organization_type,
    "facility_type": facilityTypeId,

    "city": city,
    "region": region,
    "country": country,
    "lat": lat,
    "lon": lon,
    "location": osm_location,

    "number_doctors": number_doctors,
    "capacity": capacity
    }

    documents.append(
        Document(
            page_content=text,
            metadata=metadata
        )
    )

print(documents[1].page_content)
print(f"Number of documents created: {len(documents)}")
