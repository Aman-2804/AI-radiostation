AI Radiostation

Simple FastAPI app that exposes an endpoint to generate TTS audio using Google's Gemini (google-genai). This project provides a tiny frontend at `/` to submit prompts and play the generated WAV.

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

Notes
- The app saves generated WAV files to `generated/`.
- This is minimal and intended for local experimentation. Don't expose GEMINI_API_KEY publicly.
