from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv

try:
    from scripts.classifier import get_classifier
except ModuleNotFoundError:
    from classifier import get_classifier
from pathlib import Path

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

app = FastAPI(title = "Bank Parser API", version = "1.0")



class ClassifyRequest(BaseModel):
    description: str


class ClassifyResponse(BaseModel):
    category_main: str
    category_sub: str | None = None
    classification_method: str | None = None


classifier = get_classifier()

@app.post("/api/classify")
def classify_transaction(request: ClassifyRequest) -> ClassifyResponse:
    result = classifier.classify(request.description)
    return ClassifyResponse(
        category_main = result.category_main,
        category_sub = result.category_sub,
        classification_method = result.classification_method
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host = "0.0.0.0", port = 8000)



