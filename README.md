# revmatch

A data-driven enthusiast decision engine for performance cars.

## Architecture

- MongoDB Atlas (Azure)
- MCP for schema + curation workflow
- Backend API (FastAPI + Motor)
- SwiftUI frontend (planned)

## Database

Database: porsche  
Collections:
- makes
- models
- generations
- trims
- specSheets
- featureCatalog
- trimFeatures
- characterScores
- sourceRefs

## Run

1. Create a virtualenv and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Set the MongoDB connection string (no default; do not commit secrets):
   ```bash
   export MONGODB_URL="mongodb+srv://user:pass@cluster.mongodb.net/"
   ```
3. Start the API:
   ```bash
   uvicorn app.main:app --reload
   ```
   - Health: `GET http://localhost:8000/health`
   - Recommendations: `GET http://localhost:8000/recommendations?year=2024&limit=10`

## Deploy (Docker)

1. Build the image:
   ```bash
   docker build -t revmatch .
   ```
2. Run with env for MongoDB (use secrets manager or `-e`):
   ```bash
   docker run -p 8000:8000 -e MONGODB_URL="mongodb+srv://..." revmatch
   ```
   Do not bake `MONGODB_URL` into the image; always pass it at runtime.

## Tests

From the repo root with the venv activated:
```bash
pytest tests/ -v
```
Health and recommendations endpoints are covered; recommendations tests mock the service so no live DB is required.