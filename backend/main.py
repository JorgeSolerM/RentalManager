from fastapi import FastAPI

app = FastAPI(
    title="RentalManager",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "application": "RentalManager",
        "status": "running",
        "version": "1.0.0"
    }