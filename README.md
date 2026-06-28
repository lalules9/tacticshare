# TacticShare

Strategic intelligence for campaigners. Learn from movements that came before yours.

## Setup

1. Clone the repo
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux)
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and add your Anthropic API key
6. Run: `streamlit run app.py`

## Configuration

- **Model:** Set in `app.py` at the top — `claude-haiku-4-5` for development, `claude-sonnet-4-6` for production
- **Prompts:** All LLM instructions are in `prompt.py` — tune here without touching app logic
- **Database:** `data/campaign_database_v1.csv` — add campaigns by adding rows

## Project Structure

```
tacticshare/
├── app.py                  # Streamlit app
├── prompt.py               # LLM prompts
├── data/
│   └── campaign_database_v1.csv
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Evidence Policy

TacticShare distinguishes between evidence drawn from the campaign database and strategic inferences. 
All inferences are marked with ⚡ in both the app and exported HTML reports.
