# Tri9t AI Backend — Blood Pressure Monitor Technical Manual Parser & QA Test Generator

A production-ready backend designed with Clean Architecture principles (SOLID, Repository Pattern, Service Layer) that parses markdown manuals, tracks document changes across versions, allows node selection, generates structured QA test cases using Groq LLM, and manages output staleness when manual versions change.

---

## 🛠️ Technology Stack

* **Language**: Python 3.12+
* **Framework**: FastAPI
* **Relational DB**: SQLite (Async via SQLAlchemy ORM & aiosqlite)
* **Migrations**: Alembic
* **NoSQL DB**: MongoDB Local (Async via Motor driver)
* **LLM Integration**: Groq SDK (`llama-3.3-70b-versatile` with fallbacks)
* **Validation**: Pydantic v2
* **Logging**: Loguru

---

## 🚀 Installation & Setup

### 1. Clone & Set Up Directory
Navigate to the backend directory:
```bash
cd backend
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
# Activate on Windows:
.venv\Scripts\activate
# Activate on Unix/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configuration (`.env`)
Copy the template `.env.example` into a new `.env` file:
```bash
cp .env.example .env
```
Open `.env` and fill in your details:
```ini
LOG_LEVEL=INFO
DATABASE_URL=sqlite+aiosqlite:///./tri9t_ai.db
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=tri9t_ai
MONGO_COLLECTION=generated_testcases
GROQ_API_KEY=your-actual-groq-api-key
```

### 5. Start MongoDB
Make sure MongoDB is running and accessible. You can connect to a local MongoDB instance (installed directly on your machine) or a remote MongoDB Atlas database by updating the `MONGO_URI` variable in your `.env` file.

---

## 🗄️ Database Migrations

SQLite tables are automatically initialized by the application lifecycle manager on startup, making migrations optional for first boot. 

However, you can manage schemas using Alembic:
```bash
# Generate a new migration
alembic revision --autogenerate -m "Initial schema"

# Apply migrations
alembic upgrade head
```

---

## 🚦 Running the Application

Start the FastAPI development server:
```bash
uvicorn app.main:app --reload
```
Once started, you can access:
* **Interactive API Documentation (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **Alternative Documentation (Redoc)**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🧪 Running Tests

The application comes with a comprehensive test suite covering the parser, hybrid matcher, selection service, LLM wrapper, and staleness engine.

Run all tests in isolation using in-memory SQLite:
```bash
pytest -v
```

To check coverage:
```bash
pytest --cov=app tests/
```

---

## 🔄 Core End-to-End Workflow & API Examples

Here are the curl commands to demonstrate the complete workflow step-by-step.

### 1. Ingest Version 1 Manual
Uploads the original manual, parses it into hierarchical nodes, and sets it as Version 1.
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/upload" \
  -F "title=CardioTrack CT-200 Technical Manual" \
  -F "file=@../ct200_manual.md"
```
**Response Output**:
```json
{
  "document_id": "8c4ab17a-5b12-4fb2-9e8c-85a22d51dcfb",
  "version_id": "18f95c47-66a9-4678-bde1-90a6e3ee41a1",
  "node_count": 27
}
```

---

### 2. Browse Ingested Node Tree
Retrieve the nodes for Version 1 to find IDs to select.
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/versions/18f95c47-66a9-4678-bde1-90a6e3ee41a1"
```

---

### 3. Search Manual for Specific Sections
Search for keywords across headings and body text:
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/search?query=battery"
```

---

### 4. Create a Version-Pinned Selection
Create a selection of node IDs (e.g. Battery Life section) pinned to Version 1:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/selections" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Power & Battery Specs",
    "version_id": "18f95c47-66a9-4678-bde1-90a6e3ee41a1",
    "node_ids": ["c0a8010b-8e9a-41f2-bf23-8cbe4d0fb24a"]
  }'
```
**Response Output**:
```json
{
  "id": "sel-1002-3004",
  "name": "Power & Battery Specs",
  "version_id": "18f95c47-66a9-4678-bde1-90a6e3ee41a1",
  "nodes": [...]
}
```

---

### 5. Generate QA Test Cases
Trigger LLM test case generation for the selection:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/generated" \
  -H "Content-Type: application/json" \
  -d '{
    "selection_id": "sel-1002-3004"
  }'
```
This reconstructs the text, queries Groq, saves results into MongoDB, and returns:
```json
{
  "id": "65f8a2f8c85c2c525f000001",
  "selection_id": "sel-1002-3004",
  "version_id": "18f95c47-66a9-4678-bde1-90a6e3ee41a1",
  "llm_model": "llama-3.3-70b-versatile",
  "status": "CURRENT",
  "test_cases": [
    {
      "test_case_id": "TC-001",
      "title": "Verify battery life criteria under typical use",
      ...
    }
  ]
}
```

---

### 6. Upload Version 2 Manual (Re-ingestion)
Uploads the revised manual, compares V1 nodes with V2 nodes, and updates database records.
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/reingest" \
  -F "document_id=8c4ab17a-5b12-4fb2-9e8c-85a22d51dcfb" \
  -F "file=@../ct200_manual_v2.md"
```
**Response Output**:
```json
{
  "document_id": "8c4ab17a-5b12-4fb2-9e8c-85a22d51dcfb",
  "new_version_id": "99f848ac-ef14-4a27-a083-ef58a2d1fdf2",
  "new_version_num": 2,
  "node_count": 30,
  "comparison_summary": {
    "added_count": 4,
    "deleted_count": 0,
    "modified_count": 12,
    "unchanged_count": 15
  },
  "stale_generations_marked": 1
}
```

---

### 7. Retrieve Generated Test Cases (Showing Staleness Status)
Retrieve the generated test cases again. The API automatically runs a comparison against the new manual and flags changes:
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/generated/sel-1002-3004"
```
**Response Output**:
```json
{
  "selection_id": "sel-1002-3004",
  "version_id": "18f95c47-66a9-4678-bde1-90a6e3ee41a1",
  "status": "STALE",
  "stale_reason": "The following sections changed since generation: '[MODIFIED] Battery Life Under Typical Use'",
  "staleness_info": {
    "is_stale": true,
    "changed_headings": ["[MODIFIED] 'Battery Life Under Typical Use'"],
    "diff_summaries": [
      "Section 'Battery Life Under Typical Use' content changed (prev_hash=abcd1234..., curr_hash=xyz89012...)."
    ]
  },
  "test_cases": [...]
}
```

---

## 🔍 Health Diagnostics
Verify system health and active integrations (SQLite connection, MongoDB connection, Groq API access):
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/health"
```
