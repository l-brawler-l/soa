.PHONY: help install generate-models migrate up down clean test

help:
	@echo "Available commands:"
	@echo "  make install         - Install dependencies"
	@echo "  make generate-models - Generate Pydantic models from OpenAPI spec"
	@echo "  make migrate         - Run database migrations"
	@echo "  make up              - Start services with docker-compose"
	@echo "  make down            - Stop services"
	@echo "  make clean           - Clean generated files"
	@echo "  make test            - Run tests"

install:
	pip install -r requirements.txt

generate-models:
	mkdir -p app/generated
	datamodel-codegen \
		--input openapi/openapi.yaml \
		--output app/generated/models.py \
		--output-model-type pydantic_v2.BaseModel \
		--use-standard-collections \
		--use-schema-description \
		--field-constraints \
		--use-default \
		--use-title-as-name

migrate:
	alembic upgrade head

up:
	docker-compose up --build

down:
	docker-compose down

clean:
	rm -rf app/generated/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

test:
	pytest tests/ -v
