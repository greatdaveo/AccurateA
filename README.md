# AccurateA Server

AccurateA is an AI-powered accounting automation platform built for UK small businesses and accounting practices. The server provides a RESTful API for financial data management, AI-driven transaction classification, bank reconciliation, VAT compliance, and HMRC MTD integration.

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Tesseract OCR (for document processing)
- An OpenAI API key (for AI classification features)

## Project Structure

## Setup

### 1. Clone and create virtual environment

```bash
git clone <repository-url>
cd server
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and configure the required variables (see Environment Variables section below).

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the development server

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SECRET_KEY` | Yes | JWT signing secret |
| `ALGORITHM` | No | JWT algorithm (default: HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Token expiry in minutes (default: 60) |
| `APP_ENV` | No | `development` or `production` (default: development) |
| `DEBUG` | No | Enable debug mode (default: True) |
| `OPENAI_API_KEY` | No | Required for AI classification and agents |
| `PINECONE_API_KEY` | No | Required for vector-based pattern matching |
| `PLAID_CLIENT_ID` | Yes | Plaid API credentials |
| `PLAID_SECRET` | Yes | Plaid API credentials |
| `TRUELAYER_CLIENT_ID` | No | TrueLayer Open Banking credentials |
| `TRUELAYER_CLIENT_SECRET` | No | TrueLayer Open Banking credentials |
| `FRONTEND_URL` | No | Frontend origin for CORS (default: http://localhost:5173) |
| `SENTRY_DSN` | No | Sentry error monitoring DSN |
| `SENTRY_TRACES_SAMPLE_RATE` | No | Sentry performance sampling rate (default: 0.2) |

## API Documentation

When running in development mode, interactive API documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

These endpoints are disabled in production for security.

## Docker

Build and run with Docker:

```bash
docker build -t accuratea-server .
docker run -p 8000:8000 --env-file .env accuratea-server
```

## Testing

Run the test suite:

```bash
python -m pytest tests/
```

Run individual test files:

```bash
python test_security.py
python test_db.py
```