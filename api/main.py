"""
FastAPI service layer - the actual separation between the retrieval/
data layer and the presentation layer (frontend/streamlit_app.py talks
to this over HTTP, it does not import MicroRAG). This is what makes
the two independently deployable and independently testable: you can
`curl` this API and get a real answer with zero UI involved, which is
exactly what "real live queries you personally ran" should mean.

Run with:
    uvicorn api.main:app --reload --port 8000

Then either hit it directly:
    curl -X POST localhost:8000/query -H "Content-Type: application/json" \
         -d '{"question": "Which family offices are active in AI investing?"}'

or point the Streamlit frontend at it via API_BASE_URL.
"""
import json
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from retrieval.rag import MicroRAG
from config import DATA_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fo-intel-api")

app = FastAPI(title="Family Office Intelligence API", version="1.0")

# Wide open for the assessment demo - there is no auth layer and no
# real user base to scope this to. Known limitation, not an oversight:
# a real deployment would restrict this to the frontend's origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

rag = MicroRAG()


class QueryRequest(BaseModel):
    question: str
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    firm_type: str | None = None
    n_results: int = Field(default=8, ge=1, le=50)


@app.on_event("startup")
def load_dataset() -> None:
    try:
        with open(DATA_PATH) as f:
            records = json.load(f)
    except FileNotFoundError:
        logger.warning("No dataset found at %s - starting with an empty index.", DATA_PATH)
        records = []

    n_chunks = rag.index_records(records)
    logger.info("Indexed %d chunks from %d records (%s).", n_chunks, len(records), DATA_PATH)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "chunks_indexed": rag.record_count_indexed(),
        "generation_available": rag.generator.available,
    }


@app.post("/reindex")
def reindex() -> dict:
    """Re-reads DATA_PATH and rebuilds the vector store. Call this after updating data/records.json."""
    with open(DATA_PATH) as f:
        records = json.load(f)
    n_chunks = rag.index_records(records)
    return {"status": "ok", "records": len(records), "chunks_indexed": n_chunks}


@app.post("/query")
def query(req: QueryRequest) -> dict:
    response = rag.grounded_answer(
        req.question,
        min_confidence=req.min_confidence,
        firm_type=req.firm_type,
        n_results=req.n_results,
    )
    return response.to_dict()
