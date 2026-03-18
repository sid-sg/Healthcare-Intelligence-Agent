import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def is_rate_limit_error(exception):
    return "429" in str(exception)

@retry(
    retry=retry_if_exception_type(Exception), # In production, use specific Gemini errors
    wait=wait_exponential(multiplier=1, min=4, max=60), # Wait 4s, 8s, 16s...
    stop=stop_after_attempt(5), # Give up after 5 tries
    reraise=True # Crucial: ensures the final error is raised if all 5 tries fail
)

def clean_with_llm(row):
    prompt = f"""
You are a geolocation normalization system.

Your task is to convert noisy, unstructured address data into a clean, hierarchical location string that is valid and resolvable by OpenStreetMap (Nominatim).

OUTPUT FORMAT (STRICT):
<locality>, <region>, <country>

GOAL:
Produce a location string that OpenStreetMap can successfully geocode with high accuracy.

RULES:
- Use ONLY the information provided in the input
- DO NOT hallucinate or invent new locations
- Prefer real geographic entities (towns, cities, districts, regions)
- IGNORE landmarks, buildings, directions (e.g., "behind", "opposite", "near")
- Extract the most specific valid locality (e.g., town, suburb, district)
- Ensure correct hierarchical order: locality → region → country
- If region is missing, return: <locality>, <country>
- If only region is known, return: <region>, <country>
- Always include country if available
- Do NOT include extra text, explanations, or formatting
- Output ONLY the final location string

---
EXAMPLE 1:
Input:
address_line1: Behind Cuzi Soap Training Centre, Krofrom Light Industrial Area  
address_line2: Acherensua, Asutifi South  
address_line3: Acherensua, Ghana  
city: Acherensua  
region: Asutifi South  
country: Ghana  

Output:
Acherensua, Asutifi South, Ghana
---
EXAMPLE 2:
Input:
address_line1: Accra-Airport Residential Area; Accra-Lapaz (St Michael’s Specialist Hospital); Kumasi-Ahodwo  
address_line2: null  
address_line3: null  
city: Acherensua  
region: Asutifi South  
country: Ghana  

Output:
Kumasi-Ahodwo, Ghana
---
NOW PROCESS THE FOLLOWING INPUT:
name: {row.get("name")}
address_line1: {row.get("address_line1")}
address_line2: {row.get("address_line2")}
address_line3: {row.get("address_line3")}
city: {row.get("address_city")}
region: {row.get("address_stateOrRegion")}
country: {row.get("address_country")}
"""
    try:
        # 2. Use the new 'models.generate_content' method
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a precise geolocation normalizer. Output only clean location strings.",
                temperature=0,
            ),
        )

        output = response.text.strip()

        # Validation logic
        if "," not in output:
            return None
        
        return output

    except Exception as e:
        if "429" in str(e):
            print("⚠️ Rate limit hit. Retrying...")
            raise e  # This will trigger the retry
        else:
            print(f"❌ Gemini SDK Error (Non-rate limit): {e}")
        return None