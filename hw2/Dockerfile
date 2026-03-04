FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app
COPY openapi ./openapi

# Generate models from OpenAPI spec
RUN mkdir -p app/generated && \
    datamodel-codegen \
    --input openapi/openapi.yaml \
    --output app/generated/models.py \
    --output-model-type pydantic_v2.BaseModel \
    --use-standard-collections \
    --use-schema-description \
    --field-constraints \
    --use-default \
    --use-title-as-name || true

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
