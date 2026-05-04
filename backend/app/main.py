from fastapi import FastAPI

app = FastAPI(title="Javva Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
