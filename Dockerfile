FROM python:3.10-slim

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		pkg-config \
		python3-dev \
		libpoppler-cpp-dev \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements_backend.txt .
RUN pip install --no-cache-dir -r requirements_backend.txt

RUN pip install --no-cache-dir pdftotext

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "scripts.backend_api:app", "--host", "0.0.0.0", "--port", "8000"]