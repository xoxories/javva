from fastapi import FastAPI

app = FastAPI(
    title="Javva Backend",
    version="0.1.0",
    description="AI customer support for trading platforms",
)


@app.get("/")
def root() -> dict[str, str]:
    """Welcome endpoint with API metadata."""
    return {
        "name": "Javva Backend",
        "version": "0.1.0",
        "description": "AI customer support for trading platforms",
        "docs_url": "/docs",
        "health_url": "/health",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}