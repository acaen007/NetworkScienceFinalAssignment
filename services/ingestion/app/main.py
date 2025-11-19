from fastapi import FastAPI

app = FastAPI(title="ManyWorlds Ingestion Service")


@app.get("/")
async def root() -> dict:
    """Health check endpoint.

    Returns a simple message indicating that the ingestion service is
    reachable.  Extend this service with additional routes to accept
    ingestion requests and process documents in the background.
    """
    return {"message": "Hello from Ingestion service"}