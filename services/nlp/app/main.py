from fastapi import FastAPI

app = FastAPI(title="ManyWorlds NLP Service")


@app.get("/")
async def root() -> dict:
    """Health check endpoint.

    Returns a simple message indicating that the NLP service is
    reachable.  Extend this service with endpoints for embeddings,
    retrieval‑augmented generation (RAG), classification, and other
    machine‑learning tasks.
    """
    return {"message": "Hello from NLP service"}