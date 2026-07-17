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
cp .env.example .env     # On Unix/macOS
copy .env.example .env   # On Windows
```
Open `.env` and fill in your details:
```ini
# Application Settings
LOG_LEVEL=INFO                    # Logging verbosity: DEBUG, INFO, WARNING, ERROR

# SQLite Database Settings
DATABASE_URL=sqlite+aiosqlite:///./tri9t_ai.db    # Database file location

# MongoDB Settings
MONGO_URI=mongodb://localhost:27017              # MongoDB connection string
MONGO_DB_NAME=tri9t_ai                           # Database name
MONGO_COLLECTION=generated_testcases             # Collection for test case generations

# Groq LLM API Settings
GROQ_API_KEY=your-actual-groq-api-key            # Get from https://console.groq.com/keys
```

**Environment Variable Details:**
- **LOG_LEVEL**: Controls application logging verbosity. Use `DEBUG` for development, `INFO` for production.
- **DATABASE_URL**: SQLite database file path. The `aiosqlite` driver enables async operations.
- **MONGO_URI**: MongoDB connection string. For local MongoDB, use `mongodb://localhost:27017`. For MongoDB Atlas, use your connection string.
- **MONGO_DB_NAME**: Database name in MongoDB for storing generated test cases.
- **MONGO_COLLECTION**: Collection name within the database for test case documents.
- **GROQ_API_KEY**: Required for LLM test case generation. Obtain from Groq console.

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

### Running All Tests
Run all tests in isolation using in-memory SQLite:
```bash
pytest -v
```

### Running Specific Test Suites
```bash
# Parser tests (markdown parsing edge cases)
pytest tests/test_parser.py -v

# Versioning tests (matching algorithm and diff generation)
pytest tests/test_versioning.py -v

# Selection service tests (CRUD and text reconstruction)
pytest tests/test_selection_service.py -v

# Staleness detection tests
pytest tests/test_staleness.py -v

# LLM integration tests (requires valid GROQ_API_KEY)
pytest tests/test_llm.py -v

# Document service tests (upload and re-ingestion workflows)
pytest tests/test_document_service.py -v
```

### Coverage Report
Generate a detailed coverage report:
```bash
pytest --cov=app tests/ --cov-report=html
```
This creates an `htmlcov/` directory with an interactive HTML report showing line-by-line coverage.

### Test Configuration
Tests use pytest-asyncio for async database operations and automatically use in-memory SQLite for isolation. No test database setup is required.

### LLM Testing Notes
- LLM tests require a valid `GROQ_API_KEY` in your `.env` file
- These tests make actual API calls to Groq and may incur costs
- To skip LLM tests: `pytest tests/ -v -k "not llm"`

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

## � Triggering V1 → V2 Re-ingestion Flow

The re-ingestion flow is specifically designed to handle document version updates while maintaining traceability of test case staleness. Here's the step-by-step process:

### Prerequisites
1. **Version 1 must already exist**: You must have previously uploaded a document using the `/documents/upload` endpoint
2. **Have the Document ID**: Keep track of the `document_id` from the initial upload response
3. **Prepare Version 2**: Have the revised markdown file ready (e.g., `ct200_manual_v2.md`)

### Re-ingestion Steps

#### Step 1: Upload Version 2
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/reingest" \
  -F "document_id=8c4ab17a-5b12-4fb2-9e8c-85a22d51dcfb" \
  -F "file=@../ct200_manual_v2.md"
```

**What happens internally:**
- System fetches all V1 nodes from SQLite
- Parses V2 markdown into new node tree
- Runs hybrid matching algorithm to compare V1 vs V2 nodes
- Creates Version 2 record with new nodes
- Stores comparison results and node mappings
- **Automatically marks stale** any test case generations that reference modified nodes

#### Step 2: Review Comparison Results
The response includes:
- `new_version_id`: UUID for the newly created Version 2
- `comparison_summary`: Counts of added/modified/unchanged/deleted nodes
- `stale_generations_marked`: Number of test case generations marked as stale

#### Step 3: Check Stale Generations
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/generated"
```

This lists all generations with their staleness status. Generations marked as `STALE` will include:
- `stale_reason`: Which sections changed since generation
- `staleness_info`: Detailed diff summaries and changed headings

#### Step 4: Regenerate Test Cases (Optional)
For stale generations, you can trigger regeneration:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/generated" \
  -H "Content-Type: application/json" \
  -d '{
    "selection_id": "sel-1002-3004"
  }'
```

This will create a new generation based on the latest document version, automatically updating the version reference.

### Key Behaviors
- **Version Lineage**: Each re-ingestion creates a sequential version (V1 → V2 → V3)
- **Node Mapping**: The system tracks how each node changed between versions
- **Automatic Staleness**: Test cases are marked stale without manual intervention
- **Comparison Persistence**: All version comparisons are stored for audit trails
- **Selection Version Pinning**: Original selections remain pinned to their creation version

---

## 🔍 Health Diagnostics
Verify system health and active integrations (SQLite connection, MongoDB connection, Groq API access):
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/health"
```
