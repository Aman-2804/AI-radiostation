AI Radiostation

Simple FastAPI app that exposes an endpoint to generate TTS audio using Google's Gemini (google-genai). This project provides a tiny frontend at `/` to submit prompts and play the generated WAV.

Prerequisites
- Python 3.10+
- Node.js 18+ (for Vite dev server)
- Install Python dependencies: `pip install -r requirements.txt`
- Install Node.js dependencies: `npm install`
- Set environment variable GEMINI_API_KEY with your API key

Run (development with Vite)

Option 1: Local development with Vite (recommended)
1. Install Python deps
   ```bash
   pip install -r requirements.txt
   ```

2. Install Node.js deps
   ```bash
   npm install
   ```

3. Start the FastAPI backend (in one terminal)
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. Start the Vite dev server (in another terminal)
   ```bash
   npm run dev
   ```

5. Open http://localhost:5173/ in your browser

Option 2: FastAPI only (legacy)
1. Install deps
   ```bash
   pip install -r requirements.txt
   ```
2. Run uvicorn
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
3. Open http://localhost:8000/

Notes
- The app saves generated WAV files to `generated/`.
- Vite dev server runs on port 5173 and proxies API requests to FastAPI on port 8000.
- This is minimal and intended for local experimentation. Don't expose GEMINI_API_KEY publicly.
