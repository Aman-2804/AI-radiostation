AI Radiostation


Prerequisites
- Python 3.10+
- Install dependencies: pip install -r requirements.txt
- Set environment variable GEMINI_API_KEY with your API key

Run (development)
1. Install deps
   pip install -r requirements.txt
2. Run uvicorn
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
3. Open http://localhost:8000/

