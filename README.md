# 🎬 Microdrama Promo Clip Studio

An enterprise-grade, highly interactive Streamlit application and high-performance pipeline that ingests timestamped microdrama screenplays (`.txt`) and discovers the best **20–60 second promo clips** — featuring a gripping hook within the first 3 seconds, high emotional intensity, a cliffhanger ending, standalone narrative understandability, and semantic deduplication.

---

## 🌟 Key Features

- **Cinematic Dark-Themed Web Studio**:
  - Custom dark aesthetic (`.streamlit/config.toml` + injected CSS) with rounded glassmorphism cards, glowing score badges, and smooth hover states.
  - Interactive multi-tab layout: **🏆 Promo Clip Cards**, **📊 Visual Analytics**, **🎛️ Clip Trimmer & Compare**, **💬 AI Screenplay Assistant**, and **📋 Raw Data & Exports**.
- **Visual Analytics (Plotly)**:
  - **Drama Flow Timeline**: Interactive chart mapping dialogue tension across the entire episode with highlighted promo windows.
  - **Multi-Attribute Radar**: Comparative radar chart measuring Hook, Cliffhanger, Emotion, and Standalone comprehension.
  - **Score Distribution**: Grouped bar charts visualizing sub-scores across candidates.
- **Interactive Timeline Trimmer & Fine-Tuning**:
  - Live start/end boundary sliders allowing editors to fine-tune trailer cuts with instant duration and cut preview.
  - Side-by-side clip comparison view to evaluate competing promo moments.
- **Persistent History & Sessions (SQLite)**:
  - Stores all sessions, uploaded scripts, evaluated clips, user favorites, feedback ratings (thumbs up/down), and Q&A chat messages in SQLite.
  - Sidebar history drawer allowing users to switch, reload, rename, or delete past runs.
- **AI Social Promo Generator (Reels, TikTok, Shorts)**:
  - Generates viral platform presets (TikTok 9:16, Instagram Reels 9:16, YouTube Shorts) with custom hooks, curiosity gap captions, and trending hashtags with 1-click copy buttons.
- **Comprehensive Multi-Format Exports**:
  - Download full **ZIP Bundle** (containing `promos.csv`, `promos.json`, `report.md`, video editor cut list, and social caption files per clip).
  - Standalone CSV, JSON, and Markdown downloads.
- **Dual Engine Execution**:
  - **Full LLM Mode**: Powered by `nvidia/nemotron-3-ultra-550b-a55b` (or Gemini) with strict Pydantic JSON schemas, validation assertions, and a **Blind Standalone Test**.
  - **Zero-Cost Fallback Mode**: Automatically activates if no API key is configured (or when explicitly toggled), ranking candidates using a 4-factor heuristic prefilter (tones, punctuation, shock words, pace) + local **Sentence-Transformers (`all-MiniLM-L6-v2`)** embeddings.

---

## 📁 Modular Project Structure

```
├── .streamlit/
│   └── config.toml             # Custom dark theme (indigo/cyan accent, dark background)
├── db/
│   ├── __init__.py
│   └── database.py             # SQLite persistence for runs, clips, feedback & chat
├── services/
│   ├── __init__.py
│   ├── pipeline_service.py     # Pipeline execution service with progress callbacks
│   ├── ai_caption_service.py   # TikTok, Reels, and Shorts caption & hashtag generator
│   └── export_service.py       # Multi-format exports (CSV, JSON, MD, and ZIP bundle)
├── ui/
│   ├── __init__.py
│   ├── styles.py               # Injected modern CSS, glassmorphism cards & glowing badges
│   ├── components.py           # Hero banner, metric cards, responsive clip cards, empty states
│   ├── charts.py               # Plotly interactive drama timeline, radar, and distribution
│   ├── editor.py               # Interactive clip trimmer and side-by-side comparison
│   ├── history_sidebar.py      # SQLite-backed history drawer (load, rename, delete)
│   └── chat.py                 # Interactive AI screenplay Q&A chat
├── utils/
│   ├── __init__.py
│   └── formatting.py           # Timestamp formatting, score color scales, HTML badges
├── src/                        # Core pipeline modules (preserved 100%)
│   ├── parse.py                # Stage 1: Parse dialogue lines, tones, and timestamps
│   ├── candidates.py           # Stage 2: Enumerate 20–60s dialogue-bounded windows
│   ├── prefilter.py            # Stage 3: Heuristic scoring (tones, '?'/'...', shock words, pace) + NMS
│   ├── llm.py                  # Central LLM entry-point with fallback detection & disk cache
│   ├── score.py                # Stage 4: LLM Pydantic evaluation & Blind Standalone Test
│   ├── validate.py             # Stage-boundary validation assertions & rejection logging
│   ├── rank.py                 # Stage 5: Config weighted ranking + sentence-transformers dedup
│   └── report.py               # Stage 6: Multi-format report export & raw LLM response logging
├── app.py                      # Streamlit Web UI & CLI dual-mode orchestrator
├── config.yaml                 # Configurable weights, window constraints, model settings
└── requirements.txt            # Python dependencies (Streamlit, Plotly, PyTorch, Pydantic, etc.)
```

---

## 🚀 Quick Start & Setup

### 1. Clone & Set Up Environment

```bash
# Clone the repository and navigate into the project directory
git clone https://github.com/amankumar5345/Microdrama-Promo-Clip-Finder.git
cd Microdrama-Promo-Clip-Finder

# Create a virtual environment (Python 3.10+ recommended)
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Key (Optional for Fallback Mode)

Copy `.env.example` to `.env`:
```bash
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux
```

Open `.env` and enter your OpenRouter, NVIDIA, or Gemini API key:
```env
OPENROUTER_API_KEY="sk-or-v1-..."
# Or direct NVIDIA API key:
# NVIDIA_API_KEY="nvapi-..."
# Or for Gemini:
# GEMINI_API_KEY="..."
```

> **Note on Fallback Mode**: If no API key is provided, the application will **automatically run in Fallback Mode** at zero cost, ranking candidates using heuristic prefilter metrics and local sentence embedding deduplication.

---

## 💻 Running the Application

### Option A: Interactive Streamlit Web Studio (Recommended)

Launch the Streamlit app:
```bash
streamlit run app.py
```

This will automatically open your browser to `http://localhost:8501`.

#### Studio Features & Walkthrough:
1. **Sidebar Configuration**:
   - Check API Key Status (or enter an override key for the session).
   - Choose Execution Mode (`Automatic LLM` or `Fallback Mode Only`).
   - Adjust duration sliders (e.g. 20–60s) and max clips per episode (1–5).
   - Select Social Aspect Ratio (`9:16 Vertical`, `1:1 Square`, `16:9 Landscape`).
   - Click **📂 Load Sample Episode 1** to test with the bundled screenplay.
2. **Execution**:
   - Click **🚀 Run Promo Finder** and watch live stage-by-stage progress.
3. **Interactive Tabs**:
   - **🏆 Promo Clip Cards**: Review ranked clips with Hook quotes, Cliffhanger quotes, Why It Works explanation, and copyable social captions.
   - **📊 Visual Analytics**: Inspect the interactive Plotly Drama Flow timeline and score radar.
   - **🎛️ Clip Trimmer & Compare**: Fine-tune start and end seconds with instant cut updates, or compare two clips side-by-side.
   - **💬 AI Screenplay Assistant**: Ask contextual questions about characters, plot twists, and why clips were selected.
   - **📋 Raw Data & Exports**: Download a single consolidated **ZIP Bundle**, CSV, JSON, or Markdown report.

---

### Option B: Command-Line Interface (CLI)

Run the full pipeline headlessly on a screenplay file:

```bash
python app.py "path/to/episode.txt"
```

#### Run in Fallback Mode (No API Key Required)
```bash
python app.py "path/to/episode.txt" --fallback
```

#### Run Individual Pipeline Stages for Debugging
```bash
python app.py "path/to/episode.txt" --stage parse
python app.py "path/to/episode.txt" --stage candidates
python app.py "path/to/episode.txt" --stage prefilter
python app.py "path/to/episode.txt" --stage score
python app.py "path/to/episode.txt" --stage rank
```

---

## 🌐 Free 1-Click Deployment on Streamlit Cloud

Deploy this studio for free forever in 30 seconds using **Streamlit Community Cloud**:

1. Go to **[share.streamlit.io](https://share.streamlit.io/)** and log in with your GitHub account.
2. Click **"New app"** (or **"Create app"**).
3. Set:
   - **Repository:** `amankumar5345/Microdrama-Promo-Clip-Finder`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. *(Optional)* Click **Advanced settings** and paste your API key in Secrets:
   ```toml
   OPENROUTER_API_KEY = "your-key-here"
   ```
   *(If omitted, the app runs in **Fallback Mode** for free with zero token cost).*
5. Click **Deploy!** Your live web app will be accessible worldwide on your custom `.streamlit.app` URL.
