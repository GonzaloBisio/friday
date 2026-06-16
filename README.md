# FRIDAY

Asistente personal estilo JARVIS con cerebro Google Gemini.

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con tus API keys
```

## Correr

```bash
python -m friday.main
```

## Tests

```bash
pytest -q
```

## Dashboard

```bash
streamlit run friday/dashboard/app.py
```
