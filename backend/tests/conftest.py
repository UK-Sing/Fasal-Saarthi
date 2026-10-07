import os
import tempfile

# Isolated, offline, deterministic settings for every test (set before the app is imported).
_db = os.path.join(tempfile.mkdtemp(prefix="fasal-test-"), "test.db")
os.environ.update(DATABASE_URL=f"sqlite:///{_db}", USE_LIVE_DATA="false", API_KEY="", LLM_BASE_URL="", LLM_MODEL="")
os.environ.setdefault("DATABASE_BACKEND", "memory")  # overridable: DATABASE_BACKEND=sqlite exercises the SQL path
