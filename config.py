"""
Central config. Reads API keys from environment variables so nothing
secret gets committed to git. Copy .env.example to .env and fill in
your own free-tier keys.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Free tier: https://newsapi.org/register (100 req/day, no card required)
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

# Free, no key needed: https://www.propublica.org/datastore/api/nonprofit-explorer-api
PROPUBLICA_BASE = "https://projects.propublica.org/nonprofits/api/v2"

# SEC EDGAR requires a real identifying User-Agent (name + email), no key.
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "YourName your_email@example.com")

# Groq (for the RAG generation step) - free tier available:
# https://console.groq.com
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Minimum confidence a record needs to count toward the final 50.
# Tune this once you see how your scoring distributes across real data.
MIN_CONFIDENCE_FOR_INCLUSION = 0.4

# --- Retrieval layer ---

# Local, free, no API key - sentence-transformers model used for both
# indexing and query embedding. Kept as a single named constant so the
# model can be swapped in one place without hunting through rag.py.
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "family_offices")

# Default breadth of retrieval. Records are chunked into ~3 pieces
# each (profile / signals / principal - see retrieval/chunking.py),
# so this is expressed in chunks, not records.
DEFAULT_N_RESULTS = int(os.getenv("DEFAULT_N_RESULTS", "8"))

# --- API / frontend wiring ---

# Streamlit talks to the FastAPI service over HTTP instead of importing
# MicroRAG in-process. This is a deliberate separation between the
# retrieval/data layer (api/main.py) and the presentation layer
# (frontend/streamlit_app.py), each independently deployable and
# independently testable (curl the API without touching a browser).
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://localhost:{API_PORT}")

DATA_PATH = os.getenv("DATA_PATH", "data/records.json")
