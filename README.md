# 🎬 DemoForge

**Raw screencast in. Narrated video + social short clip out.**

DemoForge takes any raw screencast and automatically produces two things:

1. **A full narrated video** — AI-generated voiceover merged into your original recording
2. **A social-ready short clip** — a 10–20s highlight formatted in 9:16 for Instagram Reels, TikTok, and YouTube Shorts

No editing. No script writing. No voice recording. Just upload and go.

---

## Why DemoForge

Recording a screencast is easy. Making it look and sound like a real product demo is not. Most screencasts end up silent, unpolished, and never shared publicly.

DemoForge solves the whole pipeline automatically:
- Watches your recording frame by frame using Claude AI
- Writes a natural voiceover script based on what's on screen
- Generates professional audio via ElevenLabs or OpenAI TTS
- Merges everything into a shareable MP4
- Auto-cuts a social short clip with AI-detected highlight moment

**What makes it different from similar tools:**
- Open source — self-host it, own it
- No account needed — upload and go
- Bring your own API keys — you control the cost and the data
- Privacy-first — your screencasts never touch someone else's server
- Social-first — produces a short clip automatically, not just a long narration

---

## Demo

| Input | Output |
|---|---|
| Raw silent screencast | Full narrated MP4 + 9:16 social short clip |

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React + Vite |
| Backend | Python + Flask |
| AI Script Generation | Claude API (Anthropic) |
| Text-to-Speech | ElevenLabs (primary) → OpenAI TTS (fallback) |
| Video Processing | ffmpeg |

---

## Prerequisites

Make sure you have these installed before starting:

- Python 3.10+
- Node.js 18+
- ffmpeg

**On Mac:**
```bash
brew install ffmpeg
```

**On Linux:**
```bash
sudo apt install ffmpeg
```

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/demoforge.git
cd demoforge
```

### 2. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create your `.env` file:
```bash
cp .env.example .env
```

Open `.env` and add your API keys:
```
ANTHROPIC_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

> You need **ANTHROPIC_API_KEY** and at least one of **ELEVENLABS_API_KEY** or **OPENAI_API_KEY**.

Create the required folders:
```bash
mkdir -p ../uploads ../outputs
```

Start the backend:
```bash
python3 app.py
```

You should see:
```
* Running on http://127.0.0.1:5000
* Debug mode: on
```

### 3. Frontend setup

Open a new terminal window:

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
npm run dev
```

### 4. Open the app

Go to your browser and open:
```
http://localhost:5173
```

---

## How to Use

1. **Upload** your screencast — MP4, MOV, WebM, or AVI up to 200MB
2. **Enter** the product name (optional — helps Claude write a better script)
3. **Choose** a voiceover tone — Professional, Friendly, or Energetic
4. **Toggle** social short clip on or off
5. **Choose** highlight mode:
   - **AI picks** — Claude automatically finds the most interesting 10–20s moment
   - **You mark** — enter start and end time in seconds manually
6. **Click** Generate Demo
7. **Download** your full narrated video and social short clip

---

## API Keys

| Key | Required | Get it at |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Yes | [console.anthropic.com](https://console.anthropic.com) |
| `ELEVENLABS_API_KEY` | One of these | [elevenlabs.io](https://elevenlabs.io) |
| `OPENAI_API_KEY` | is required | [platform.openai.com](https://platform.openai.com) |

ElevenLabs free tier gives you 10,000 characters/month — more than enough for testing.

---

## How It Works

```
Upload screencast
      ↓
ffmpeg extracts 1 frame per second
      ↓
Sample up to 10 frames evenly
      ↓
Claude API: analyze frames → write voiceover script
      ↓
ElevenLabs / OpenAI TTS: script → MP3 audio
      ↓
ffmpeg: merge original video + audio → full narrated MP4
      ↓
Claude API: detect best 10–20s highlight moment
      ↓
ffmpeg: cut highlight → reformat to 9:16 → social short MP4
      ↓
Return script + full video + short clip
```

---

## Project Structure

```
demoforge/
├── backend/
│   ├── app.py              # Flask server + full pipeline
│   ├── requirements.txt    # Python dependencies
│   └── .env.example        # Environment variables template
├── frontend/
│   └── src/
│       └── App.jsx         # React UI
├── uploads/                # Temporary uploaded videos
├── outputs/                # Generated videos and audio
└── README.md
```

---

## Voiceover Tones

| Tone | Style |
|---|---|
| 🎯 Professional | Clear and confident — SaaS product demo style |
| 🤝 Friendly | Warm and conversational — like showing a friend |
| ⚡ Energetic | Punchy and enthusiastic — startup pitch energy |

---

## Roadmap

- [ ] Auto-generated captions on the short clip
- [ ] Visual highlight selector — drag on a timeline instead of typing seconds
- [ ] Multiple voice options for ElevenLabs
- [ ] Background job queue for large files
- [ ] One-click share to YouTube / social platforms

---

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request.

---

## License

MIT — do whatever you want with it.

---

*Built in one day by Team Momentum* 🚀
