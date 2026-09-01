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
import time
import re
import shutil
import pathlib

_base_dir = pathlib.Path(__file__).resolve().parent.parent
_frontend_dist = _base_dir / "frontend" / "dist"

app = Flask(
    __name__,
    static_folder=str(_frontend_dist / "assets"),
    static_url_path="/assets",
)
CORS(app)

UPLOAD_FOLDER = str(_base_dir / "uploads")
OUTPUT_FOLDER = str(_base_dir / "outputs")
ALLOWED_EXTENSIONS = {"mp4", "mov", "webm", "avi"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB max

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def get_tts_provider():
    if OPENAI_API_KEY:
        return "openai"
    else:
        raise EnvironmentError(
            "No TTS API key found. Set OPENAI_API_KEY in your .env file. Audio is required."
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


def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        audio_path
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


def frame_thumbnail_url(job_id, frame_num):
    return f"/uploads/{job_id}_frames/frame_{frame_num:04d}.jpg"


def generate_script_from_frames(frames, product_name=None, tone="professional", word_limit=200):
    """Send sampled frames to Claude and generate a voiceover script with frame mappings."""
    total_frames = len(frames)
    if total_frames > 10:
        step = total_frames // 10
        sampled_indices = list(range(0, total_frames, step))[:10]
    else:
        sampled_indices = list(range(total_frames))

    sampled = [frames[i] for i in sampled_indices]

    content = []
    for idx, frame_path in zip(sampled_indices, sampled):
        actual_frame_num = idx + 1
        content.append({"type": "text", "text": f"Frame {actual_frame_num} of {total_frames}:"})
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

These are {len(sampled)} sampled frames from a {total_frames}-frame screencast recorded at 1 frame per second.
Each frame is labeled with its actual frame number in the full video.
Frame N corresponds to the video at approximately second N-1 to second N.

Analyze what's happening across the frames and write a natural, engaging voiceover script.

Rules:
- Write short, punchy sentences that flow naturally when spoken aloud
- Focus on what the USER benefits from, not just what's on screen
- Keep the total script under {word_limit} words
- Start strong — hook the viewer in the first sentence
- Each sentence must be mapped to the frame range it describes
- Frame ranges must be in chronological order and must not overlap
- A sentence can span multiple frames if describing a continuous action
- Every frame should be covered by exactly one sentence's range

Return ONLY a JSON object in this exact format (no markdown, no extra text):
{{"segments": [{{"text": "First sentence.", "frame_start": 1, "frame_end": 5}}, {{"text": "Second sentence.", "frame_start": 6, "frame_end": 12}}]}}

The frame_start and frame_end values must be between 1 and {total_frames} inclusive."""
    })

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": content}]
    )

    raw = message.content[0].text.strip()

    try:
        raw_cleaned = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_cleaned)
        segments = data.get("segments", [])

        validated = []
        for seg in segments:
            text = seg.get("text", "").strip()
            fs = max(1, min(total_frames, int(seg.get("frame_start", 1))))
            fe = max(fs, min(total_frames, int(seg.get("frame_end", fs))))
            if text:
                validated.append({"text": text, "frame_start": fs, "frame_end": fe})

        validated.sort(key=lambda s: s["frame_start"])

        for i in range(1, len(validated)):
            if validated[i]["frame_start"] <= validated[i - 1]["frame_end"]:
                validated[i]["frame_start"] = validated[i - 1]["frame_end"] + 1
            if validated[i]["frame_start"] > validated[i]["frame_end"]:
                validated[i]["frame_end"] = validated[i]["frame_start"]

        if validated:
            return {"segments": validated, "total_frames": total_frames}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass

    # Fallback: plain text with evenly distributed frame ranges
    if raw.startswith("{") or raw.startswith("["):
        text_parts = re.findall(r'"text"\s*:\s*"([^"]+)"', raw)
        if text_parts:
            raw = " ".join(text_parts)

    sentences = split_script_to_segments(raw)
    frames_per_seg = max(1, total_frames // len(sentences))
    fallback = []
    for i, sent in enumerate(sentences):
        fs = i * frames_per_seg + 1
        fe = min(total_frames, (i + 1) * frames_per_seg)
        if i == len(sentences) - 1:
            fe = total_frames
        fallback.append({"text": sent, "frame_start": fs, "frame_end": fe})

    return {"segments": fallback, "total_frames": total_frames}


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
        "model_id": "eleven_turbo_v2_5",
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


def split_script_to_segments(script):
    segments = [s.strip() for s in re.split(r'(?<=[.!?])\s+', script.strip()) if s.strip()]
    return segments


def generate_segment_audio(segments, job_dir):
    seg_dir = os.path.join(job_dir, "segments")
    os.makedirs(seg_dir, exist_ok=True)
    paths = []
    for i, text in enumerate(segments):
        seg_path = os.path.join(seg_dir, f"seg_{i}.mp3")
        generate_voiceover(text, seg_path)
        paths.append(seg_path)
    return paths


def stitch_segment_audio(segment_paths, output_path):
    if len(segment_paths) == 1:
        shutil.copy2(segment_paths[0], output_path)
        return output_path

    concat_dir = os.path.dirname(segment_paths[0])
    list_path = os.path.join(concat_dir, "concat_list.txt")
    with open(list_path, "w") as f:
        for p in segment_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", output_path, "-y"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"ffmpeg concat error: {result.stderr}")
    return output_path


def assemble_synced_video(video_path, segment_data, job_dir, output_path):
    """Assemble video with narration synchronized to frame ranges.

    segment_data: list of dicts with text, frame_start, frame_end, audio_path, audio_duration.
    """
    temp_dir = os.path.join(job_dir, "sync_parts")
    os.makedirs(temp_dir, exist_ok=True)
    part_paths = []

    for i, seg in enumerate(segment_data):
        vid_start = seg["frame_start"] - 1
        vid_end = seg["frame_end"]
        vid_duration = vid_end - vid_start
        audio_dur = seg["audio_duration"]

        if vid_duration <= 0 or audio_dur <= 0:
            continue

        speed_factor = max(0.25, min(4.0, audio_dur / vid_duration))

        part_path = os.path.join(temp_dir, f"part_{i:03d}.mp4")
        cmd = [
            "ffmpeg",
            "-ss", str(vid_start),
            "-t", str(vid_duration),
            "-i", video_path,
            "-i", seg["audio_path"],
            "-filter_complex",
            f"[0:v]setpts={speed_factor}*PTS[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-shortest",
            part_path, "-y"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Segment {i} sync failed: {result.stderr}")
        part_paths.append(part_path)

    if not part_paths:
        raise Exception("No synchronized segments produced")

    concat_list = os.path.join(temp_dir, "concat.txt")
    with open(concat_list, "w") as f:
        for p in part_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy",
        output_path, "-y"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Concat failed: {result.stderr}")

    shutil.rmtree(temp_dir, ignore_errors=True)
    return output_path


CIRCLE_OVERLAY_PATH = os.path.join(OUTPUT_FOLDER, "_circle_highlight.png")


def ensure_circle_overlay():
    """Generate a translucent orange circle PNG for cursor highlights."""
    if os.path.exists(CIRCLE_OVERLAY_PATH):
        return CIRCLE_OVERLAY_PATH
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    cmd = [
        "ffmpeg", "-f", "lavfi", "-i",
        "color=c=black@0:s=100x100:d=0.04,format=rgba,"
        "geq=r=255:g=107:b=53:"
        "a='if(lte(hypot(X-50,Y-50),45),"
        "if(lte(hypot(X-50,Y-50),30),180,"
        "180*(45-hypot(X-50,Y-50))/15),0)'",
        "-frames:v", "1", "-update", "1", "-y", CIRCLE_OVERLAY_PATH
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Circle overlay generation failed: {result.stderr}")
    return CIRCLE_OVERLAY_PATH


def _pick_interactions(interactions, max_count=5):
    """Pick up to max_count evenly-spaced interaction points."""
    if not interactions or len(interactions) <= max_count:
        return interactions or []
    sorted_ix = sorted(interactions, key=lambda x: x["timestamp"])
    step = len(sorted_ix) / max_count
    return [sorted_ix[int(i * step)] for i in range(max_count)]


def build_smooth_zoom_filter(interactions, width, height, duration, zoom_level=1.5):
    """Build a scale+crop filter with smooth animated zoom via per-frame expressions."""
    picked = _pick_interactions(interactions)
    if not picked:
        return ""

    ease_dur = 0.5
    hold_dur = 1.5
    dz = zoom_level - 1.0

    z_parts = []
    cx_parts = []
    cy_parts = []

    for ix in picked:
        t = ix["timestamp"]
        t0 = max(0, t - ease_dur)
        t1 = t
        t2 = t + hold_dur
        t3 = min(duration, t + hold_dur + ease_dur)
        cx = int(ix["x_pct"] * width)
        cy = int(ix["y_pct"] * height)

        z_parts.append(
            f"if(between(t,{t0:.2f},{t1:.2f}),"
            f"1+{dz:.2f}*(t-{t0:.2f})/{ease_dur:.2f},"
            f"if(between(t,{t1:.2f},{t2:.2f}),"
            f"{zoom_level:.2f},"
            f"if(between(t,{t2:.2f},{t3:.2f}),"
            f"{zoom_level:.2f}-{dz:.2f}*(t-{t2:.2f})/{ease_dur:.2f},"
        )
        cx_parts.append(f"if(between(t,{t0:.2f},{t3:.2f}),{cx},")
        cy_parts.append(f"if(between(t,{t0:.2f},{t3:.2f}),{cy},")

    zoom_expr = "".join(z_parts) + "1" + ")" * (len(z_parts) * 3)
    cx_expr = "".join(cx_parts) + str(width // 2) + ")" * len(cx_parts)
    cy_expr = "".join(cy_parts) + str(height // 2) + ")" * len(cy_parts)

    crop_x = f"max(0,min(iw-{width},{cx_expr}*({zoom_expr})-{width}/2))"
    crop_y = f"max(0,min(ih-{height},{cy_expr}*({zoom_expr})-{height}/2))"

    return (
        f"scale=w='trunc(iw*({zoom_expr})/2)*2':"
        f"h='trunc(ih*({zoom_expr})/2)*2':"
        f"flags=lanczos:eval=frame,"
        f"crop={width}:{height}:"
        f"x='{crop_x}':"
        f"y='{crop_y}'"
    )


def build_transition_filter(scene_changes, duration):
    """Build FFmpeg fade filter expressions for transitions."""
    filters = []
    if duration < 3:
        return filters

    filters.append(f"fade=t=in:st=0:d=0.5")
    filters.append(f"fade=t=out:st={duration - 0.5:.2f}:d=0.5")

    if duration < 10 or not scene_changes:
        return filters

    min_gap = 2.5
    filtered_changes = []
    for t in scene_changes:
        if t < 1 or t > duration - 1:
            continue
        if not filtered_changes or (t - filtered_changes[-1]) >= min_gap:
            filtered_changes.append(t)

    for t in filtered_changes:
        filters.append(
            f"fade=t=out:st={t - 0.4:.2f}:d=0.4"
            f":enable='between(t,{t - 0.4:.2f},{t:.2f})'"
        )
        filters.append(
            f"fade=t=in:st={t:.2f}:d=0.4"
            f":enable='between(t,{t:.2f},{t + 0.4:.2f})'"
        )

    return filters


def build_enhancement_filter_complex(interactions, scene_changes, width, height, duration,
                                      zoom_level=1.5):
    """Build a filter_complex graph: cursor circles → smooth zoom → transitions."""
    picked = _pick_interactions(interactions)
    chains = []
    current_label = "0:v"

    if picked:
        n = len(picked)
        split_labels = "".join(f"[c{i}]" for i in range(n))
        chains.append(f"[2:v]format=rgba,split={n}{split_labels}")

        for i, ix in enumerate(picked):
            t = ix["timestamp"]
            cx = max(0, int(ix["x_pct"] * width) - 50)
            cy = max(0, int(ix["y_pct"] * height) - 50)
            t_start = max(0, t - 0.3)
            t_end = min(duration, t + 1.8)
            out_label = f"ov{i}"
            chains.append(
                f"[{current_label}][c{i}]overlay=x={cx}:y={cy}:"
                f"enable='between(t,{t_start:.2f},{t_end:.2f})':"
                f"format=yuv420[{out_label}]"
            )
            current_label = out_label

    zoom_str = build_smooth_zoom_filter(picked, width, height, duration, zoom_level)
    if zoom_str:
        chains.append(f"[{current_label}]{zoom_str}[out]")
    else:
        chains.append(f"[{current_label}]null[out]")

    return ";".join(chains)


def merge_audio_with_video(video_path, audio_path, output_path,
                           filter_complex=None, circle_path=None):
    """Merge voiceover into the full video, optionally applying enhancement filters."""
    cmd = ["ffmpeg", "-i", video_path, "-i", audio_path]

    if circle_path:
        cmd += ["-loop", "1", "-i", circle_path]

    if filter_complex:
        cmd += ["-filter_complex", filter_complex]
        cmd += ["-map", "[out]", "-map", "1:a"]
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]
    else:
        cmd += ["-c:v", "copy"]
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]

    cmd += ["-c:a", "aac", "-shortest", output_path, "-y"]
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

@app.route("/api/generate-script", methods=["POST"])
def generate_script_endpoint():
    """Phase 1: Upload video, extract frames, generate script. No TTS yet."""
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    product_name = request.form.get("product_name", "")
    tone = request.form.get("tone", "professional")
    word_limit = int(request.form.get("word_limit", "200"))

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Use mp4, mov, webm, or avi"}), 400

    job_id = str(uuid.uuid4())[:8]
    filename = secure_filename(file.filename)
    video_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{filename}")
    file.save(video_path)

    try:
        frames_dir = os.path.join(UPLOAD_FOLDER, f"{job_id}_frames")
        frames = extract_frames(video_path, frames_dir, fps=1)
        if not frames:
            return jsonify({"error": "Could not extract frames from video"}), 500

        duration = get_video_duration(video_path)
        vid_w, vid_h = get_video_dimensions(video_path)

        script_data = generate_script_from_frames(frames, product_name, tone, word_limit)
        segments = script_data["segments"]
        total_frames = script_data["total_frames"]
        script = " ".join(seg["text"] for seg in segments)

        meta = {
            "video_path": video_path,
            "frames_dir": frames_dir,
            "duration": duration,
            "width": vid_w,
            "height": vid_h,
            "frame_count": total_frames,
            "product_name": product_name,
            "tone": tone,
        }
        job_dir = os.path.join(OUTPUT_FOLDER, job_id)
        os.makedirs(job_dir, exist_ok=True)

        meta["segments"] = [
            {"index": i, "text": s["text"], "frame_start": s["frame_start"], "frame_end": s["frame_end"]}
            for i, s in enumerate(segments)
        ]
        with open(os.path.join(job_dir, "meta.json"), "w") as f:
            json.dump(meta, f)

        segments_response = [
            {
                "index": i,
                "text": s["text"],
                "frame_start": s["frame_start"],
                "frame_end": s["frame_end"],
                "frame_thumbnail": frame_thumbnail_url(job_id, s["frame_start"]),
            }
            for i, s in enumerate(segments)
        ]

        return jsonify({
            "job_id": job_id,
            "script": script,
            "segments": segments_response,
            "frame_count": total_frames,
            "duration": duration,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/process", methods=["POST"])
def process_screencast():
    """Phase 2: Take a confirmed script + job_id, run TTS and build video."""
    data = request.get_json()
    if not data or "job_id" not in data or "script" not in data:
        return jsonify({"error": "job_id and script are required"}), 400

    job_id = data["job_id"]
    script = data["script"]
    generate_short = data.get("generate_short", True)
    manual_start = data.get("manual_start")
    manual_end = data.get("manual_end")

    meta_path = os.path.join(OUTPUT_FOLDER, job_id, "meta.json")
    if not os.path.exists(meta_path):
        return jsonify({"error": "Job not found. Generate a script first."}), 404

    try:
        get_tts_provider()
    except EnvironmentError as e:
        return jsonify({"error": str(e)}), 500

    try:
        with open(meta_path) as f:
            meta = json.load(f)

        video_path = meta["video_path"]
        frames_dir = meta["frames_dir"]
        duration = meta["duration"]
        vid_w = meta["width"]
        vid_h = meta["height"]
        product_name = meta.get("product_name", "")

        frames = sorted([
            os.path.join(frames_dir, f)
            for f in os.listdir(frames_dir) if f.endswith(".jpg")
        ])

        job_dir = os.path.join(OUTPUT_FOLDER, job_id)

        saved_segments = meta.get("segments", [])

        request_segments = data.get("segments")
        if request_segments and len(request_segments) > 0 and "frame_start" in request_segments[0]:
            saved_segments = request_segments
            segments = [s["text"] for s in request_segments]
            has_frame_mapping = True
        elif saved_segments and "frame_start" in saved_segments[0]:
            segments = [s["text"] for s in saved_segments]
            has_frame_mapping = True
        else:
            segments = split_script_to_segments(script)
            has_frame_mapping = False

        segment_paths = generate_segment_audio(segments, job_dir)

        audio_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_voiceover.mp3")
        stitch_segment_audio(segment_paths, audio_path)
        audio_url = f"/outputs/{job_id}_voiceover.mp3"

        if has_frame_mapping:
            segment_data = []
            for i, seg_meta in enumerate(saved_segments):
                seg_info = {
                    "text": seg_meta["text"],
                    "frame_start": seg_meta["frame_start"],
                    "frame_end": seg_meta["frame_end"],
                    "audio_path": segment_paths[i],
                    "audio_duration": get_audio_duration(segment_paths[i]),
                }
                segment_data.append(seg_info)
        else:
            segment_data = None

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

        filter_complex = None
        circle_path = None
        enhancements_applied = False

        try:
            if interactions:
                circle_path = ensure_circle_overlay()
            filter_complex = build_enhancement_filter_complex(
                interactions, scene_changes, vid_w, vid_h, duration,
            )
        except Exception as e:
            print(f"Filter build failed, proceeding without enhancements: {e}")
            filter_complex = None
            circle_path = None

        full_video_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_demo.mp4")
        if segment_data:
            try:
                assemble_synced_video(video_path, segment_data, job_dir, full_video_path)
                enhancements_applied = False
            except Exception as e:
                app.logger.error(f"Synced assembly failed, falling back to merge: {e}")
                merge_audio_with_video(video_path, audio_path, full_video_path)
                enhancements_applied = False
        else:
            try:
                merge_audio_with_video(video_path, audio_path, full_video_path,
                                       filter_complex=filter_complex, circle_path=circle_path)
                enhancements_applied = filter_complex is not None
            except Exception:
                if filter_complex:
                    print("Enhanced merge failed, retrying without filters...")
                    merge_audio_with_video(video_path, audio_path, full_video_path)
                else:
                    raise
        full_video_url = f"/outputs/{job_id}_demo.mp4"

        short_url = None
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

        if segment_data:
            meta["segments"] = [
                {"index": i, "text": sd["text"], "frame_start": sd["frame_start"],
                 "frame_end": sd["frame_end"], "audio_duration": sd["audio_duration"]}
                for i, sd in enumerate(segment_data)
            ]
        else:
            meta["segments"] = [{"index": i, "text": s} for i, s in enumerate(segments)]
        meta["cached_enhancements"] = {
            "interactions": interactions,
            "scene_changes": scene_changes,
            "highlight": highlight,
            "short_title": short_title,
            "filter_complex": filter_complex,
            "circle_path": circle_path,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        segments_response = []
        for i, s in enumerate(segments):
            seg_resp = {"index": i, "text": s, "audio_url": f"/outputs/{job_id}/segments/seg_{i}.mp3"}
            if segment_data:
                seg_resp["frame_start"] = segment_data[i]["frame_start"]
                seg_resp["frame_end"] = segment_data[i]["frame_end"]
                seg_resp["frame_thumbnail"] = frame_thumbnail_url(job_id, segment_data[i]["frame_start"])
            segments_response.append(seg_resp)

        return jsonify({
            "job_id": job_id,
            "script": script,
            "segments": segments_response,
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


@app.route("/api/regenerate-segment", methods=["POST"])
def regenerate_segment():
    data = request.get_json()
    job_id = data.get("job_id")
    segment_index = data.get("segment_index")
    new_text = data.get("new_text")

    if not job_id or segment_index is None or not new_text:
        return jsonify({"error": "job_id, segment_index, and new_text are required"}), 400

    meta_path = os.path.join(OUTPUT_FOLDER, job_id, "meta.json")
    if not os.path.exists(meta_path):
        return jsonify({"error": "Job not found"}), 404

    try:
        with open(meta_path) as f:
            meta = json.load(f)

        stored_segments = meta.get("segments", [])
        if segment_index < 0 or segment_index >= len(stored_segments):
            return jsonify({"error": f"Invalid segment index {segment_index}"}), 400

        stored_segments[segment_index]["text"] = new_text.strip()

        job_dir = os.path.join(OUTPUT_FOLDER, job_id)
        seg_path = os.path.join(job_dir, "segments", f"seg_{segment_index}.mp3")
        generate_voiceover(new_text.strip(), seg_path)

        all_seg_paths = [
            os.path.join(job_dir, "segments", f"seg_{s['index']}.mp3")
            for s in stored_segments
        ]
        audio_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_voiceover.mp3")
        stitch_segment_audio(all_seg_paths, audio_path)

        video_path = meta["video_path"]
        has_frame_mapping = "frame_start" in stored_segments[0]

        full_video_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_demo.mp4")

        if has_frame_mapping:
            segment_data = []
            for s in stored_segments:
                seg_audio = os.path.join(job_dir, "segments", f"seg_{s['index']}.mp3")
                segment_data.append({
                    "text": s["text"],
                    "frame_start": s["frame_start"],
                    "frame_end": s["frame_end"],
                    "audio_path": seg_audio,
                    "audio_duration": get_audio_duration(seg_audio),
                })
            try:
                assemble_synced_video(video_path, segment_data, job_dir, full_video_path)
            except Exception as e:
                app.logger.error(f"Synced re-assembly failed, falling back: {e}")
                merge_audio_with_video(video_path, audio_path, full_video_path)

            for i, sd in enumerate(segment_data):
                stored_segments[i]["audio_duration"] = sd["audio_duration"]
        else:
            cached = meta.get("cached_enhancements", {})
            filter_complex = cached.get("filter_complex")
            circle_path = cached.get("circle_path")
            try:
                merge_audio_with_video(video_path, audio_path, full_video_path,
                                       filter_complex=filter_complex, circle_path=circle_path)
            except Exception:
                if filter_complex:
                    merge_audio_with_video(video_path, audio_path, full_video_path)
                else:
                    raise

        meta["segments"] = stored_segments
        with open(meta_path, "w") as f:
            json.dump(meta, f)

        ts = int(time.time())

        segments_response = []
        for s in stored_segments:
            seg_resp = {
                "index": s["index"], "text": s["text"],
                "audio_url": f"/outputs/{job_id}/segments/seg_{s['index']}.mp3?t={ts}",
            }
            if has_frame_mapping:
                seg_resp["frame_start"] = s["frame_start"]
                seg_resp["frame_end"] = s["frame_end"]
                seg_resp["frame_thumbnail"] = frame_thumbnail_url(job_id, s["frame_start"])
            segments_response.append(seg_resp)

        return jsonify({
            "segments": segments_response,
            "full_video_url": f"/outputs/{job_id}_demo.mp4?t={ts}",
            "audio_url": f"/outputs/{job_id}_voiceover.mp3?t={ts}",
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
        job_dir = os.path.join(OUTPUT_FOLDER, job_id)
        os.makedirs(job_dir, exist_ok=True)

        segments = split_script_to_segments(script)
        segment_paths = generate_segment_audio(segments, job_dir)

        audio_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_voiceover.mp3")
        stitch_segment_audio(segment_paths, audio_path)
        audio_url = f"/outputs/{job_id}_voiceover.mp3"

        duration = get_video_duration(video_path)
        vid_w, vid_h = get_video_dimensions(video_path)

        meta_path = os.path.join(job_dir, "meta.json")
        cached = {}
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                cached = json.load(f).get("cached_enhancements", {})

        filter_complex = cached.get("filter_complex")
        circle_path = cached.get("circle_path")

        if not filter_complex:
            frames_dir = os.path.join(upload_dir, f"{job_id}_frames")
            frames = sorted([os.path.join(frames_dir, f) for f in os.listdir(frames_dir) if f.endswith(".jpg")])
            try:
                enhancements = detect_enhancements(frames, duration)
                interactions = enhancements.get("interactions", [])
                scene_changes = enhancements.get("scene_changes", [])
                if interactions:
                    circle_path = ensure_circle_overlay()
                filter_complex = build_enhancement_filter_complex(
                    interactions, scene_changes, vid_w, vid_h, duration,
                )
            except Exception:
                filter_complex = None
                circle_path = None

        full_video_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_demo.mp4")
        try:
            merge_audio_with_video(video_path, audio_path, full_video_path,
                                   filter_complex=filter_complex, circle_path=circle_path)
        except Exception:
            if filter_complex:
                merge_audio_with_video(video_path, audio_path, full_video_path)
            else:
                raise

        provider = TTS_PROVIDER or get_tts_provider()

        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            meta["segments"] = [{"index": i, "text": s} for i, s in enumerate(segments)]
            with open(meta_path, "w") as f:
                json.dump(meta, f)

        ts = int(time.time())
        segments_response = [
            {"index": i, "text": s, "audio_url": f"/outputs/{job_id}/segments/seg_{i}.mp3?t={ts}"}
            for i, s in enumerate(segments)
        ]

        return jsonify({
            "audio_url": audio_url,
            "full_video_url": f"/outputs/{job_id}_demo.mp4?t={ts}",
            "segments": segments_response,
            "tts_provider": provider,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/outputs/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "tts_provider": TTS_PROVIDER or "not yet resolved"})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    file_path = _frontend_dist / path
    if path and file_path.is_file():
        return send_from_directory(str(_frontend_dist), path)
    return send_from_directory(str(_frontend_dist), "index.html")


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host="0.0.0.0", port=port)