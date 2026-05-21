import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

import anthropic
import subprocess
import base64
import json
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from openai import OpenAI
import uuid

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "../uploads"
OUTPUT_FOLDER = "../outputs"
ALLOWED_EXTENSIONS = {"mp4", "mov", "webm", "avi"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB max

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def get_tts_provider():
    if ELEVENLABS_API_KEY:
        return "elevenlabs"
    elif OPENAI_API_KEY:
        return "openai"
    else:
        raise EnvironmentError(
            "No TTS API key found. Set ELEVENLABS_API_KEY (recommended) "
            "or OPENAI_API_KEY in your .env file. Audio is required."
        )


TTS_PROVIDER = None


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_frames(video_path, output_dir, fps=1):
    """Extract 1 frame per second from the video using ffmpeg."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        f"{output_dir}/frame_%04d.jpg",
        "-y"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"ffmpeg error: {result.stderr}")
    frames = sorted([f for f in os.listdir(output_dir) if f.endswith(".jpg")])
    return [os.path.join(output_dir, f) for f in frames]


def get_video_duration(video_path):
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def get_video_dimensions(video_path):
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-select_streams", "v:0",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def encode_image_base64(image_path):
    """Encode image to base64 for Claude API."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def generate_script_from_frames(frames, product_name=None, tone="professional"):
    """Send sampled frames to Claude and generate a voiceover script."""
    if len(frames) > 10:
        step = len(frames) // 10
        sampled = frames[::step][:10]
    else:
        sampled = frames

    content = []
    for i, frame_path in enumerate(sampled):
        content.append({"type": "text", "text": f"Frame {i + 1} of {len(sampled)}:"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": encode_image_base64(frame_path)
            }
        })

    product_hint = f"The product is called '{product_name}'." if product_name else ""
    tone_instruction = {
        "professional": "Clear, confident, and professional — like a SaaS product demo.",
        "friendly": "Warm, approachable, and conversational — like a friend showing you something cool.",
        "energetic": "Enthusiastic and punchy — like a startup pitch video."
    }.get(tone, "professional")

    content.append({
        "type": "text",
        "text": f"""You are a professional product demo scriptwriter.

{product_hint}
Tone: {tone_instruction}

These frames are from a screencast recording of a product demo.
Analyze what's happening in each frame and write a natural, engaging voiceover script.

Rules:
- Write a continuous narration, not frame-by-frame descriptions
- Focus on what the USER benefits from, not just what's on screen
- Keep it under 200 words — this should feel like a tight, polished demo
- Write it to be spoken aloud — short sentences, natural rhythm
- Start strong — hook the viewer in the first sentence

Return ONLY the script text, nothing else."""
    })

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": content}]
    )
    return message.content[0].text.strip()


def detect_enhancements(frames, duration):
    """Analyze frames to detect highlight window, interaction points, and scene changes."""
    if len(frames) > 12:
        step = len(frames) // 12
        sampled = frames[::step][:12]
    else:
        sampled = frames

    content = []
    for i, frame_path in enumerate(sampled):
        timestamp = round((i / len(sampled)) * duration)
        content.append({"type": "text", "text": f"Frame at ~{timestamp}s:"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": encode_image_base64(frame_path)
            }
        })

    content.append({
        "type": "text",
        "text": f"""You are analyzing a product screencast that is {duration:.0f} seconds long.

Do four things:

1. HIGHLIGHT: Find the single most interesting 10–20 second window for a social clip.

2. INTERACTIONS: Identify moments where the user clicks a button, types in a field, or
   performs a key action. For each, estimate where on screen it happens using percentage
   coordinates (0.0 to 1.0, where 0,0 is top-left). Return up to 5 interactions.

3. SCENE CHANGES: List timestamps (seconds) where the screen content changes significantly
   (new page, modal opens, navigation, etc).

4. SHORT TITLE: Write a catchy, short title (max 6 words) for the social reel clip that
   describes the key feature being shown. Think Instagram/TikTok hook style.

Return ONLY a JSON object (no markdown, no extra text):
{{
  "highlight": {{
    "start_time": <integer seconds>,
    "end_time": <integer seconds>,
    "reason": "<one sentence>"
  }},
  "interactions": [
    {{
      "timestamp": <integer seconds>,
      "x_pct": <float 0.0-1.0>,
      "y_pct": <float 0.0-1.0>,
      "description": "<what happens>"
    }}
  ],
  "scene_changes": [<integer seconds>, ...],
  "short_title": "<catchy 6 word max title>"
}}

Rules:
- Highlight clip must be 10–20 seconds, start_time >= 0, end_time <= {duration:.0f}
- Interaction coordinates are percentages of frame dimensions (0.0 = left/top, 1.0 = right/bottom)
- Only include clear, visible interactions — don't guess
- scene_changes should have at least 1 entry if the screen changes at all
- short_title should be punchy and social-media friendly"""
    })

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": content}]
    )

    raw = message.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)

    hl = data.get("highlight", {})
    start = max(0, int(hl.get("start_time", 0)))
    end = min(int(duration), int(hl.get("end_time", min(int(duration), start + 15))))
    if end - start < 5:
        end = min(int(duration), start + 15)

    highlight = {
        "start_time": start,
        "end_time": end,
        "reason": hl.get("reason", "Key feature moment"),
        "source": "ai"
    }

    interactions = []
    for ix in data.get("interactions", []):
        interactions.append({
            "timestamp": int(ix.get("timestamp", 0)),
            "x_pct": max(0.05, min(0.95, float(ix.get("x_pct", 0.5)))),
            "y_pct": max(0.05, min(0.95, float(ix.get("y_pct", 0.5)))),
            "description": ix.get("description", ""),
        })

    scene_changes = [int(t) for t in data.get("scene_changes", []) if 0 < int(t) < duration]

    short_title = data.get("short_title", "")

    return {
        "highlight": highlight,
        "interactions": interactions,
        "scene_changes": sorted(scene_changes),
        "short_title": short_title,
    }


def generate_voiceover_elevenlabs(script, output_path, voice_id="JBFqnCBsd6RMkjVDRZzb"):
    """Generate voiceover using ElevenLabs TTS."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "text": script,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise Exception(f"ElevenLabs error: {response.text}")
    with open(output_path, "wb") as f:
        f.write(response.content)
    return output_path


def generate_voiceover_openai(script, output_path, voice="alloy"):
    """Generate voiceover using OpenAI TTS as fallback.

    Voices: alloy (neutral), echo (warm), fable (British),
            onyx (deep), nova (friendly female), shimmer (optimistic)
    """
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    response = openai_client.audio.speech.create(model="tts-1", voice=voice, input=script)
    response.stream_to_file(output_path)
    return output_path


def generate_voiceover(script, output_path):
    """Generate voiceover — ElevenLabs first, OpenAI TTS fallback. Audio is mandatory."""
    global TTS_PROVIDER
    if TTS_PROVIDER is None:
        TTS_PROVIDER = get_tts_provider()

    if TTS_PROVIDER == "elevenlabs":
        try:
            return generate_voiceover_elevenlabs(script, output_path)
        except Exception as e:
            if OPENAI_API_KEY:
                print(f"ElevenLabs failed ({e}), falling back to OpenAI TTS...")
                TTS_PROVIDER = "openai"
                return generate_voiceover_openai(script, output_path)
            raise
    elif TTS_PROVIDER == "openai":
        return generate_voiceover_openai(script, output_path)

    raise Exception("No TTS provider available.")


def build_zoom_filter(interactions, width, height, duration, zoom_level=1.5):
    """Build FFmpeg filter expressions for zooming into interaction points.

    Uses scale+crop approach: scales the video up at specific moments, then crops
    back to original size centered on the interaction point.
    """
    if not interactions:
        return []

    picked = interactions[:3]
    if len(interactions) > 3:
        picked = sorted(interactions, key=lambda x: x["timestamp"])
        step = len(picked) // 3
        picked = [picked[i * step] for i in range(3)]

    filters = []
    z = zoom_level
    for ix in picked:
        t = ix["timestamp"]
        cx_pct = ix["x_pct"]
        cy_pct = ix["y_pct"]

        zoom_start = max(0, t - 0.5)
        zoom_end = min(duration, t + 1.5)

        cx = int(cx_pct * width * z) - width // 2
        cy = int(cy_pct * height * z) - height // 2
        cx = max(0, min(int(width * z - width), cx))
        cy = max(0, min(int(height * z - height), cy))

        filters.append(
            f"scale={int(width * z)}:{int(height * z)}:flags=lanczos,"
            f"crop={width}:{height}:{cx}:{cy},"
            f"scale={width}:{height}:flags=lanczos,"
            f"enable='between(t,{zoom_start:.2f},{zoom_end:.2f})'"
        )

    return filters


def build_transition_filter(scene_changes, duration, style="fade"):
    """Build FFmpeg fade filter expressions for transitions."""
    filters = []

    if duration < 3:
        return filters

    filters.append(f"fade=t=in:st=0:d=0.5")
    filters.append(f"fade=t=out:st={duration - 0.5:.2f}:d=0.5")

    if duration < 10 or not scene_changes:
        return filters

    min_gap = 2.0
    filtered_changes = []
    for t in scene_changes:
        if t < 1 or t > duration - 1:
            continue
        if not filtered_changes or (t - filtered_changes[-1]) >= min_gap:
            filtered_changes.append(t)

    for t in filtered_changes:
        filters.append(f"fade=t=out:st={t - 0.25:.2f}:d=0.25:enable='between(t,{t - 0.25:.2f},{t:.2f})'")
        filters.append(f"fade=t=in:st={t:.2f}:d=0.25:enable='between(t,{t:.2f},{t + 0.25:.2f})'")

    return filters


def build_enhancement_filter(interactions, scene_changes, width, height, duration,
                              zoom_level=1.5, transition_style="fade",
                              enable_zoom=True, enable_transitions=True):
    """Combine zoom and transition filters into a single filter chain."""
    parts = []

    if enable_transitions:
        parts.extend(build_transition_filter(scene_changes, duration, transition_style))

    if enable_zoom and interactions:
        zoom_filters = build_zoom_filter(interactions, width, height, duration, zoom_level)
        parts.extend(zoom_filters)

    return ",".join(parts) if parts else ""


def merge_audio_with_video(video_path, audio_path, output_path, video_filter=None):
    """Merge voiceover into the full video, optionally applying enhancement filters."""
    cmd = ["ffmpeg", "-i", video_path, "-i", audio_path]

    if video_filter:
        cmd += ["-vf", video_filter, "-c:v", "libx264", "-preset", "fast", "-crf", "18"]
    else:
        cmd += ["-c:v", "copy"]

    cmd += [
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:a", "aac", "-shortest",
        output_path, "-y"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"ffmpeg merge error: {result.stderr}")
    return output_path


def _has_drawtext():
    result = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
    return "drawtext" in result.stdout


HAS_DRAWTEXT = _has_drawtext()


def generate_short_clip(video_path, audio_path, start_time, end_time, output_path,
                        title="", product_name=""):
    """Cut a social-ready vertical clip (9:16) with optional title overlay."""
    duration = end_time - start_time

    vf_parts = [
        "scale=1080:1920:force_original_aspect_ratio=decrease",
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        "fade=t=in:st=0:d=0.4",
        f"fade=t=out:st={max(0, duration - 0.4):.2f}:d=0.4",
    ]

    if HAS_DRAWTEXT:
        font_path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if not os.path.exists(font_path):
            font_path = "/System/Library/Fonts/Helvetica.ttc"

        escaped_title = title.replace("'", "'\\''").replace(":", "\\:") if title else ""
        escaped_product = product_name.replace("'", "'\\''").replace(":", "\\:") if product_name else ""

        if escaped_title:
            vf_parts.append(
                f"drawtext=fontfile='{font_path}'"
                f":text='{escaped_title}'"
                f":fontsize=52:fontcolor=white"
                f":borderw=3:bordercolor=black@0.6"
                f":x=(w-text_w)/2:y=140"
                f":enable='between(t,0.3,{min(duration, 4)})'"
                f":alpha='if(lt(t,0.6),(t-0.3)/0.3,if(gt(t,{min(duration, 4) - 0.5}),({min(duration, 4)}-t)/0.5,1))'"
            )

        if escaped_product:
            vf_parts.append(
                f"drawtext=fontfile='{font_path}'"
                f":text='{escaped_product}'"
                f":fontsize=32:fontcolor=white@0.7"
                f":borderw=2:bordercolor=black@0.4"
                f":x=(w-text_w)/2:y=1820"
                f":enable='between(t,0,{duration})'"
            )

    vf_string = ",".join(vf_parts)

    cmd = [
        "ffmpeg",
        "-ss", str(start_time), "-i", video_path,
        "-ss", str(start_time), "-i", audio_path,
        "-t", str(duration),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", vf_string,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        output_path, "-y"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"ffmpeg short clip error: {result.stderr}")
    return output_path


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/api/process", methods=["POST"])
def process_screencast():
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    product_name = request.form.get("product_name", "")
    tone = request.form.get("tone", "professional")
    generate_short = request.form.get("generate_short", "true") == "true"
    manual_start = request.form.get("manual_start", None)
    manual_end = request.form.get("manual_end", None)

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Use mp4, mov, webm, or avi"}), 400

    try:
        get_tts_provider()
    except EnvironmentError as e:
        return jsonify({"error": str(e)}), 500

    job_id = str(uuid.uuid4())[:8]
    filename = secure_filename(file.filename)
    video_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{filename}")
    file.save(video_path)

    try:
        # Step 1: Extract frames + duration + dimensions
        frames_dir = os.path.join(UPLOAD_FOLDER, f"{job_id}_frames")
        frames = extract_frames(video_path, frames_dir, fps=1)
        if not frames:
            return jsonify({"error": "Could not extract frames from video"}), 500
        duration = get_video_duration(video_path)
        vid_w, vid_h = get_video_dimensions(video_path)

        # Step 2: Generate voiceover script
        script = generate_script_from_frames(frames, product_name, tone)

        # Step 3: Generate voiceover audio
        audio_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_voiceover.mp3")
        generate_voiceover(script, audio_path)
        audio_url = f"/outputs/{job_id}_voiceover.mp3"

        # Step 4: Detect enhancements (highlight + interactions + scene changes + title)
        highlight = None
        interactions = []
        scene_changes = []
        short_title = ""

        if manual_start is not None and manual_end is not None:
            highlight = {
                "start_time": int(float(manual_start)),
                "end_time": int(float(manual_end)),
                "reason": "Manually selected by user",
                "source": "manual"
            }
            try:
                enhancements = detect_enhancements(frames, duration)
                interactions = enhancements.get("interactions", [])
                scene_changes = enhancements.get("scene_changes", [])
                short_title = enhancements.get("short_title", "")
            except Exception as e:
                app.logger.error(f"Enhancement detection failed: {e}")
        else:
            try:
                enhancements = detect_enhancements(frames, duration)
                highlight = enhancements["highlight"]
                interactions = enhancements.get("interactions", [])
                scene_changes = enhancements.get("scene_changes", [])
                short_title = enhancements.get("short_title", "")
                app.logger.info(f"Enhancements detected: highlight={highlight}, interactions={len(interactions)}, title={short_title}")
            except Exception as e:
                app.logger.error(f"Enhancement detection failed: {e}", exc_info=True)

        # Step 5: Full narrated video (always enhanced with zoom + transitions)
        video_filter = None
        enhancements_applied = False

        try:
            video_filter = build_enhancement_filter(
                interactions, scene_changes, vid_w, vid_h, duration,
            )
            if not video_filter:
                video_filter = None
        except Exception as e:
            print(f"Filter build failed, proceeding without enhancements: {e}")
            video_filter = None

        full_video_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_demo.mp4")
        try:
            merge_audio_with_video(video_path, audio_path, full_video_path, video_filter=video_filter)
            enhancements_applied = video_filter is not None
        except Exception:
            if video_filter:
                print("Enhanced merge failed, retrying without filters...")
                merge_audio_with_video(video_path, audio_path, full_video_path)
            else:
                raise
        full_video_url = f"/outputs/{job_id}_demo.mp4"

        # Step 6: Social short clip with title overlay
        short_url = None
        app.logger.info(f"Short clip check: generate_short={generate_short}, highlight={highlight is not None}")
        if generate_short and highlight:
            short_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_short.mp4")
            generate_short_clip(
                video_path, audio_path,
                highlight["start_time"], highlight["end_time"],
                short_path,
                title=short_title,
                product_name=product_name,
            )
            short_url = f"/outputs/{job_id}_short.mp4"

        provider = TTS_PROVIDER or get_tts_provider()

        return jsonify({
            "job_id": job_id,
            "script": script,
            "audio_url": audio_url,
            "full_video_url": full_video_url,
            "short_clip_url": short_url,
            "highlight": highlight,
            "short_title": short_title,
            "duration": duration,
            "frame_count": len(frames),
            "tts_provider": provider,
            "enhancements_applied": enhancements_applied,
            "interactions_detected": len(interactions),
            "scene_changes_detected": len(scene_changes),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/regenerate", methods=["POST"])
def regenerate_from_script():
    data = request.get_json()
    job_id = data.get("job_id")
    script = data.get("script")

    if not job_id or not script:
        return jsonify({"error": "job_id and script are required"}), 400

    upload_dir = UPLOAD_FOLDER
    video_files = [f for f in os.listdir(upload_dir) if f.startswith(job_id) and not f.endswith("_frames")]
    if not video_files:
        return jsonify({"error": "Original video not found for this job"}), 404

    video_path = os.path.join(upload_dir, video_files[0])

    try:
        audio_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_voiceover.mp3")
        generate_voiceover(script, audio_path)
        audio_url = f"/outputs/{job_id}_voiceover.mp3"

        duration = get_video_duration(video_path)
        vid_w, vid_h = get_video_dimensions(video_path)

        frames_dir = os.path.join(upload_dir, f"{job_id}_frames")
        frames = sorted([os.path.join(frames_dir, f) for f in os.listdir(frames_dir) if f.endswith(".jpg")])

        video_filter = None
        try:
            enhancements = detect_enhancements(frames, duration)
            interactions = enhancements.get("interactions", [])
            scene_changes = enhancements.get("scene_changes", [])
            video_filter = build_enhancement_filter(
                interactions, scene_changes, vid_w, vid_h, duration,
            ) or None
        except Exception:
            pass

        full_video_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_demo.mp4")
        try:
            merge_audio_with_video(video_path, audio_path, full_video_path, video_filter=video_filter)
        except Exception:
            if video_filter:
                merge_audio_with_video(video_path, audio_path, full_video_path)
            else:
                raise

        provider = TTS_PROVIDER or get_tts_provider()

        return jsonify({
            "audio_url": audio_url,
            "full_video_url": f"/outputs/{job_id}_demo.mp4",
            "tts_provider": provider,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/outputs/<filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "tts_provider": TTS_PROVIDER or "not yet resolved"})


if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    app.run(debug=True, port=5001)
