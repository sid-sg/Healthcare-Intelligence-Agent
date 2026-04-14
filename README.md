# 🏥 Healthcare Intelligence Agent

> **An AI-powered healthcare facility intelligence platform for Ghana** — built on Databricks, powered by Llama 3.3 70B, and designed to help NGO planners, healthcare coordinators, and researchers improve healthcare access across the country.

Built for the **Databricks × Accenture Hackathon**.

---

## 🎯 Problem Statement

Ghana has approximately **750+ healthcare facilities** spread across 16 regions, but there's no easy way to query, analyze, and visualize this data meaningfully. Healthcare coordinators need answers to questions like:

- *"Which hospitals within 100km of Accra have cardiology?"*
- *"Which facilities have an unusually high breadth of claimed procedures relative to their stated/observed infrastructure signals?"*
- *"Where are the largest geographic "cold spots" where radiology is absent within 50 km?"*

We built an **AI agent** that understands natural language, queries structured data via SQL, performs semantic search across facility descriptions, runs geospatial analysis, and renders results on an interactive map — all in one conversational interface.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🤖 **Multi-tool AI Agent** | Llama 3.3 70B agent with 7 specialized tools (SQL, Vector Search, Geospatial, etc.) |
| 🗺️ **Interactive Facility Map** | MapLibre GL-powered dark map with clickable markers, auto-fit bounds, and jittered overlapping pins |
| 📊 **Tabular SQL Results** | Query results rendered in scrollable data tables directly in the chat |
| 🔍 **RAG + Text-to-SQL** | Hybrid retrieval — semantic search for capability questions, SQL for structured queries |
| 🌍 **Geospatial Analysis** | Find nearby facilities, detect healthcare cold spots, proximity-based filtering |
| 📈 **WHO Benchmarks** | Built-in population data and WHO standards for per-capita healthcare analysis |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         User (Browser)                           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  React + Vite + TailwindCSS v4  (apps/frontend)             │ │
│  │  • Chat UI with markdown rendering                          │ │
│  │  • Interactive MapLibre GL map panel                        │ │
│  │  • Collapsible tool-call steps & citations                  │ │
│  └───────────────────────┬─────────────────────────────────────┘ │
└──────────────────────────┼───────────────────────────────────────┘
                           │ HTTP (REST)
┌──────────────────────────┼───────────────────────────────────────┐
│  ┌───────────────────────▼─────────────────────────────────────┐ │
│  │  FastAPI Backend  (apps/backend)                            │ │
│  │  • Proxies requests to Databricks Agent endpoint            │ │
│  │  • Parses structured response (steps, citations, map data)  │ │
│  │  • Extracts Citations & Mappable facilities                 │ │
│  └───────────────────────┬─────────────────────────────────────┘ │
└──────────────────────────┼───────────────────────────────────────┘
                           │ HTTPS (Databricks Serving)
┌──────────────────────────┼───────────────────────────────────────┐
│  ┌───────────────────────▼─────────────────────────────────────┐ │
│  │  Databricks AI Agent  (databricks/agent)                    │ │
│  │  • Llama 3.3 70B on Model Serving                           │ │
│  │  • MLflow ResponsesAgent with tool-calling loop             │ │
│  │  • Unity Catalog Functions as tools                         │ │
│  │                                                             │ │
│  │  Tools:                                                     │ │
│  │  ├── sql_query        → Text-to-SQL on Delta tables         │ │
│  │  ├── vector_search    → Semantic RAG over facility docs     │ │
│  │  ├── get_facility     → Single facility detail lookup       │ │
│  │  ├── external_data    → Population, WHO standards, regions  │ │
│  │  ├── find_nearby      → Proximity / radius search           │ │
│  │  └── find_cold_spots  → Healthcare desert analysis          │ │
│  │  └── analyze_anomalies  → anomalies & correlation detection │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                        Databricks Workspace                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
├── data/                          # Raw dataset
│   ├── Virtue-Foundation-Ghana-v0.3-Sheet1.csv   # Original facility CSV (988 facilities)
│   ├── geocoded_dataset.csv                       # Geocoded with lat/lon
│
├── dataset_geocoding/             # Geocoding pipeline
│   └── src/
│       ├── pipeline.py            # Main geocoding orchestrator
│       ├── osm.py                 # OpenStreetMap Nominatim geocoder
│       ├── llm_cleaner.py         # LLM-based address cleaning (Gemini)
│       └── normalizer.py          # Address normalization
│
├── databricks/
│   ├── notebooks/                 # Databricks notebooks (run in order)
│   │   ├── 1 csv_to_delta-table.ipynb      # Ingest CSV → Delta table
│   │   ├── 2 data_cleaning.ipynb           # Clean & standardize data
│   │   ├── 3 data_pre-compute.ipynb        # Pre-compute derived metrics
│   │   ├── 4 create_doc_for_RAG.ipynb      # Generate docs for vector search
│   │   ├── 5 create_embeddings.ipynb        # Create vector embeddings
│   │   ├── 6 RAG_model.ipynb               # Build & test RAG pipeline
│   │   └── 7 agent_tools.ipynb             # Define UC functions (tools)
│   └── agent/
│       ├── agent.py               # Agent definition (deployed on Model Serving)
│       └── driver.py              # Agent driver / test harness
│
├── apps/
│   ├── backend/                   # FastAPI proxy server
│   │   ├── main.py                # API routes, response parsing
│   │   ├── requirements.txt
│   │   └── .env.example
│   └── frontend/                  # React + Vite chat UI
│       ├── src/
│       │   ├── App.tsx            # Main app with split-pane layout
│       │   ├── components/
│       │   │   ├── ChatInput.tsx       # Input with send/stop buttons
│       │   │   ├── MessageBubble.tsx   # Message rendering + map trigger
│       │   │   ├── StepsAccordion.tsx  # Collapsible tool-call steps
│       │   │   ├── FacilitiesMap.tsx   # MapLibre GL interactive map
│       │   │   ├── CitationsPanel.tsx  # RAG citation cards
│       │   │   ├── DataAccordion.tsx   # Generic data accordion
│       │   │   └── ResultsTable.tsx    # Scrollable data table
│       │   ├── api.ts             # API client with abort support
│       │   ├── types.ts           # TypeScript interfaces
│       │   └── index.css          # Design system (dark theme)
│       └── package.json
│
├── test/                          # Standalone test UIs (Gradio/Jupyter)
├── genie_space_instructions.md    # Genie SQL space schema docs
└── README.md
```

---

## 🔧 How We Built It (Step-by-Step)

### Step 1 — Data Preparation
Started with the raw Virtue Foundation Ghana healthcare CSV in `/data`. The dataset contains 988 facilities with names, types, specialties, equipment, and location info — but **many facilities lacked GPS coordinates**.

### Step 2 — Geocoding
Built a geocoding pipeline in `/dataset_geocoding` that:
- Cleans and normalizes messy addresses using **Gemini LLM**
- Resolves coordinates via **OpenStreetMap Nominatim**
- Outputs a geocoded CSV with `lat` and `lon` for each facility

### Step 3 — Databricks Data Pipeline
Uploaded the geocoded dataset to Databricks and ran 7 notebooks sequentially:

| # | Notebook | Purpose |
|---|----------|---------|
| 1 | `csv_to_delta-table` | Ingest CSV into a Unity Catalog Delta table, while standardize types, handle nulls, normalize arrays|
| 2 | `data_cleaning` | Clean Noise from procedures column |
| 3 | `data_pre-compute` | Pre-calculate per-facility metrics for anomaly detection |
| 4 | `create_doc_for_RAG` | Generate structured text documents per facility |
| 5 | `create_embeddings` | Embed documents into a Vector Search index |
| 6 | `RAG_model` | Build and validate the RAG retrieval pipeline |
| 7 | `agent_tools` | Register 7 Unity Catalog functions as agent tools |

### Step 4 — Agent Deployment
Defined a **tool-calling ResponsesAgent** in `databricks/agent/agent.py`:
- Uses **Llama 3.3 70B Instruct** via Databricks Model Serving
- Follows a **ReAct reasoning loop** (Think → Act → Observe → Repeat)
- Has access to 7 tools: `sql_query`, `vector_search`, `get_facility`, `external_data`, `find_nearby_facilities`, `find_cold_spots`, `analyze_anomalies`
- Agent is deployed as a **Model Serving endpoint**

### Step 5 — Backend API
Built a **FastAPI** server (`apps/backend`) that:
- Proxies chat requests to the Databricks Agent endpoint
- Parses the agent's raw response into structured sections: **answer**, **steps** (tool calls), **citations** (RAG sources), and **mappable facilities** (for the map)
- Extracts embedded JSON blocks (`CITATIONS_JSON_START/END`, `MAPPABLE_JSON_START/END`) from the agent's text output

### Step 6 — Frontend Chat UI
Built a premium **React + Vite + TailwindCSS v4** chat interface (`apps/frontend`):
- Dark-themed, ChatGPT-like conversational UI
- Markdown rendering with `react-markdown`
- Collapsible steps showing the agent's intermediate tool calls
- SQL results displayed in clean, scrollable tables
- Interactive **MapLibre GL** map panel that slides in from the right
- Markers with popups, overlapping coordinate jittering, facility list
- Stop-response button with `AbortController` support

---

## 🚀 Running Locally

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** and **npm**
- A deployed **Databricks Agent endpoint** with a valid token

### 1. Clone the repo

```bash
git clone https://github.com/your-username/databricks-accenture-hackathon.git
cd databricks-accenture-hackathon
```

### 2. Start the Backend

```bash
cd apps/backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and fill in your Databricks credentials:
#   DATABRICKS_TOKEN=dapi...
#   AGENT_ENDPOINT=https://<workspace>.databricks.com/serving-endpoints/<endpoint>/invocations

# Start the server
uvicorn main:app --reload --port 8000
```

### 3. Start the Frontend

```bash
cd apps/frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## 💬 Example Questions

| Category | Example |
|----------|---------|
| **Counting** | *How many hospitals offer cardiology in Ghana?* |
| **Geospatial** | *Which hospitals for emergency care are within 100km of Accra?* |
| **Capability Search** | *Which facilities have ICU beds and ventilators?* |
| **Comparison** | *Compare healthcare coverage in Upper East vs Greater Accra* |
| **Cold Spots** | *Where are the largest gaps for surgical care within 50km?* |
| **Facility Lookup** | *What services does 2BN Military Hospital offer?* |
| **WHO Analysis** | *Which regions need the most hospitals per WHO standards?* |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **LLM** | Llama 3.3 70B Instruct (Databricks Model Serving) |
| **Agent Framework** | OpenAI Agents SDK |
| **Data Platform** | Databricks Unity Catalog, Delta Lake |
| **Agent Tools** | Unity Catalog Functions |
| **Backend** | FastAPI (Python) |
| **Frontend** | React 19, Vite, TypeScript, TailwindCSS v4 |
| **Map** | MapLibre GL JS + react-map-gl |
| **Geocoding** | OpenStreetMap Nominatim + Gemini LLM |
