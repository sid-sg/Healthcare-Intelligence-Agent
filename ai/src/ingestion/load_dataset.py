from pathlib import Path
from langchain_community.document_loaders.csv_loader import CSVLoader

# Locate the project root dynamically
ROOT = Path(__file__).resolve().parents[3]

data_path = ROOT / "data" /"../data/Virtue-Foundation-Ghana-v0.3-Sheet1.csv"

loader = CSVLoader(file_path=str(data_path))

data = loader.load()

for i, doc in enumerate(loader.lazy_load()):
    if i >= 2: # Stop after 2 rows
        break
    print(f"Row {i}: {doc.page_content}")