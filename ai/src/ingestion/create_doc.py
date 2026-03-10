import pandas as pd
from pathlib import Path
from langchain_core.documents import Document

ROOT = Path(__file__).resolve().parents[3]

data_path = ROOT / "data" /"../data/Virtue-Foundation-Ghana-v0.3-Sheet1.csv"

df = pd.read_csv(data_path)

documents = []

for _, row in df.iterrows():

    text = f"""
Facility: {row.get('name', '')}

Description:
{row.get('description', '')}

Procedures:
{row.get('procedure', '')}

Equipment:
{row.get('equipment', '')}

Capabilities:
{row.get('capability', '')}
"""

    documents.append(
        Document(
            page_content=text,
            metadata={"facility": row.get("name", "")}
        )
    )

print(documents[0].page_content)