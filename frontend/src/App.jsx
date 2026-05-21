import { useState, useRef, useCallback } from "react";

const API_BASE = "http://localhost:5001";

const TONES = [
  { value: "professional", label: "Professional", desc: "SaaS product demo style" },
  { value: "friendly", label: "Friendly", desc: "Warm & conversational" },
  { value: "energetic", label: "Energetic", desc: "Startup pitch energy" },
];


function UploadIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="17 8 12 3 7 8"/>
      <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{animation: "spin 1s linear infinite"}}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="9" y="9" width="13" height="13" rx="2"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  );
}

function Toggle({ value, onChange, label, desc }) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer", userSelect: "none" }}>
      <div onClick={() => onChange(!value)} style={{
        width: 40, height: 22, borderRadius: 11,
        background: value ? "#ff6b35" : "#ffffff18",
        position: "relative", transition: "background 0.2s", flexShrink: 0,
      }}>
        <div style={{
          position: "absolute", top: 3, left: value ? 21 : 3,
          width: 16, height: 16, borderRadius: "50%",
          background: "white", transition: "left 0.2s",
        }} />
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 500 }}>{label}</div>
        {desc && <div style={{ fontSize: 12, color: "#ffffff40" }}>{desc}</div>}
      </div>
    </label>
  );
}

function VideoCard({ title, badge, badgeColor, url, highlight, children }) {
  return (
    <div style={{
      background: badgeColor ? `${badgeColor}08` : "#ffffff06",
      border: `1px solid ${badgeColor ? `${badgeColor}25` : "#ffffff10"}`,
      borderRadius: 16, padding: 20, marginBottom: 20,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span style={{ fontSize: 12, color: badgeColor ? `${badgeColor}90` : "#ffffff50", letterSpacing: "0.08em", textTransform: "uppercase" }}>
          {title}
        </span>
        {badge && (
          <span style={{
            fontSize: 11, padding: "3px 8px", borderRadius: 6,
            background: `${badgeColor}18`, color: badgeColor,
            border: `1px solid ${badgeColor}30`,
            letterSpacing: "0.04em", textTransform: "uppercase",
          }}>{badge}</span>
        )}
      </div>
      {highlight && (
        <div style={{
          fontSize: 12, color: "#ffffff40", marginBottom: 12,
          padding: "8px 12px", background: "#ffffff06", borderRadius: 8,
        }}>
          ✦ {highlight.source === "ai" ? "AI picked" : "You marked"} · {highlight.start_time}s – {highlight.end_time}s
          {highlight.reason && <span style={{ color: "#ffffff30" }}> · {highlight.reason}</span>}
        </div>
      )}
      <video controls src={`${API_BASE}${url}`} style={{ width: "100%", borderRadius: 8, background: "#000" }} />
      {children}
    </div>
  );
}

export default function App() {
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [productName, setProductName] = useState("");
  const [tone, setTone] = useState("professional");
  const [generateShort, setGenerateShort] = useState(true);
  const [highlightMode, setHighlightMode] = useState("auto"); // "auto" | "manual"
  const [manualStart, setManualStart] = useState("");
  const [manualEnd, setManualEnd] = useState("");
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [editingScript, setEditingScript] = useState(false);
  const [editedScript, setEditedScript] = useState("");
  const [regenerating, setRegenerating] = useState(false);
  const fileInputRef = useRef();

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }, []);

  const steps = [
    "Extracting frames from your screencast...",
    "Analysing screen content with Claude...",
    "Writing voiceover script...",
    "Generating audio...",
    "Detecting interactions & scene changes...",
    "Applying video enhancements...",
    "Creating full demo video...",
    generateShort ? "Cutting social short clip..." : null,
  ].filter(Boolean);

  const handleSubmit = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append("video", file);
    formData.append("product_name", productName);
    formData.append("tone", tone);
    formData.append("generate_short", generateShort.toString());
    if (generateShort && highlightMode === "manual" && manualStart && manualEnd) {
      formData.append("manual_start", manualStart);
      formData.append("manual_end", manualEnd);
    }

    let stepIdx = 0;
    const stepInterval = setInterval(() => {
      if (stepIdx < steps.length - 1) {
        stepIdx++;
        setStep(steps[stepIdx]);
      }
    }, 3500);

    setStep(steps[0]);

    try {
      const res = await fetch(`${API_BASE}/api/process`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Something went wrong");
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      clearInterval(stepInterval);
      setLoading(false);
      setStep("");
    }
  };

  const copyScript = () => {
    navigator.clipboard.writeText(editingScript ? editedScript : result.script);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const startEditing = () => {
    setEditedScript(result.script);
    setEditingScript(true);
  };

  const regenerateWithEdit = async () => {
    setRegenerating(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: result.job_id, script: editedScript }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Regeneration failed");
      setResult((prev) => ({ ...prev, ...data, script: editedScript }));
      setEditingScript(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setRegenerating(false);
    }
  };

  const label = (text) => (
    <div style={{ fontSize: 13, color: "#ffffff60", marginBottom: 8, letterSpacing: "0.04em" }}>{text}</div>
  );

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0f", color: "#e8e6e0", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&family=DM+Serif+Display:ital@0;1&display=swap');
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeUp { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:translateY(0); } }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::selection { background: #ff6b3520; color: #ff6b35; }
        input[type=text]:focus, input[type=number]:focus { border-color: #ff6b35 !important; outline: none; }
      `}</style>

      {/* Header */}
      <div style={{ borderBottom: "1px solid #ffffff0f", padding: "20px 40px", display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ width: 32, height: 32, background: "#ff6b35", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        </div>
        <span style={{ fontFamily: "'DM Serif Display', serif", fontSize: 20, letterSpacing: "-0.02em" }}>DemoForge</span>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#ffffff40", letterSpacing: "0.08em", textTransform: "uppercase" }}>
          Screencast → Demo + Social Clip
        </span>
      </div>

      <div style={{ maxWidth: 780, margin: "0 auto", padding: "60px 24px" }}>

        {/* Hero */}
        <div style={{ marginBottom: 56, animation: "fadeUp 0.5s ease both" }}>
          <h1 style={{ fontFamily: "'DM Serif Display', serif", fontSize: "clamp(36px, 5vw, 52px)", fontWeight: 400, lineHeight: 1.1, letterSpacing: "-0.03em", marginBottom: 16 }}>
            Raw screencast in.<br />
            <em style={{ color: "#ff6b35" }}>Narrated video + social clip out.</em>
          </h1>
          <p style={{ color: "#ffffff60", fontSize: 17, lineHeight: 1.6, maxWidth: 720 }}>
            Upload any screencast — DemoForge writes the script, generates the voiceover, and produces a full narrated video <em>and</em> a social-ready short. No editing. No account. Bring your own keys.
          </p>
        </div>

        {/* Form */}
        <div style={{ animation: "fadeUp 0.5s 0.1s ease both", opacity: 0, animationFillMode: "forwards" }}>

          {/* Upload */}
          <div
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            style={{
              border: `1.5px dashed ${dragOver ? "#ff6b35" : file ? "#ff6b3560" : "#ffffff18"}`,
              borderRadius: 16, padding: "48px 24px", textAlign: "center", cursor: "pointer",
              background: dragOver ? "#ff6b350a" : file ? "#ff6b350a" : "#ffffff04",
              transition: "all 0.2s ease", marginBottom: 28,
            }}
          >
            <input ref={fileInputRef} type="file" accept=".mp4,.mov,.webm,.avi" style={{ display: "none" }} onChange={(e) => setFile(e.target.files[0])} />
            {file ? (
              <div>
                <div style={{ width: 48, height: 48, background: "#ff6b3520", borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px", color: "#ff6b35" }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="2" y="2" width="20" height="20" rx="4"/>
                    <polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none"/>
                  </svg>
                </div>
                <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 4 }}>{file.name}</div>
                <div style={{ fontSize: 13, color: "#ffffff40" }}>{(file.size / 1024 / 1024).toFixed(1)} MB · Click to change</div>
              </div>
            ) : (
              <div>
                <div style={{ color: "#ffffff30", marginBottom: 12 }}><UploadIcon /></div>
                <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 6 }}>Drop your screencast here</div>
                <div style={{ fontSize: 13, color: "#ffffff40" }}>MP4, MOV, WebM, AVI · up to 200MB</div>
              </div>
            )}
          </div>

          <div style={{ display: "grid", gap: 22, marginBottom: 28 }}>

            {/* Product name */}
            <div>
              {label("PRODUCT NAME (optional)")}
              <input type="text" value={productName} onChange={(e) => setProductName(e.target.value)} placeholder="e.g. Neve, PPOM, Appointly..."
                style={{ width: "100%", background: "#ffffff08", border: "1px solid #ffffff14", borderRadius: 10, padding: "12px 16px", color: "#e8e6e0", fontSize: 15, transition: "border-color 0.2s" }} />
            </div>

            {/* Tone */}
            <div>
              {label("VOICEOVER TONE")}
              <div style={{ display: "flex", gap: 10 }}>
                {TONES.map((t) => (
                  <button key={t.value} onClick={() => setTone(t.value)} style={{
                    flex: 1, padding: "12px 8px", borderRadius: 10,
                    border: `1.5px solid ${tone === t.value ? "#ff6b35" : "#ffffff14"}`,
                    background: tone === t.value ? "#ff6b350f" : "#ffffff04",
                    color: tone === t.value ? "#ff6b35" : "#ffffff60",
                    cursor: "pointer", fontSize: 13, fontWeight: tone === t.value ? 500 : 400,
                    transition: "all 0.15s ease", textAlign: "center", fontFamily: "inherit",
                  }}>
                    <div style={{ marginBottom: 2 }}>{t.label}</div>
                    <div style={{ fontSize: 11, opacity: 0.6 }}>{t.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Short clip section */}
            <div style={{ background: "#ffffff04", border: "1px solid #ffffff0a", borderRadius: 14, padding: 18, textAlign: "left" }}>
              <Toggle value={generateShort} onChange={setGenerateShort}
                label="Generate social short clip"
                desc="Auto-cuts a 10–20s highlight, formatted 9:16 for Instagram, TikTok & Reels" />

              {generateShort && (
                <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #ffffff08" }}>
                  {label("HIGHLIGHT SELECTION")}
                  <div style={{ display: "flex", gap: 10, marginBottom: highlightMode === "manual" ? 14 : 0 }}>
                    {["auto", "manual"].map((mode) => (
                      <button key={mode} onClick={() => setHighlightMode(mode)} style={{
                        flex: 1, padding: "10px", borderRadius: 8,
                        border: `1.5px solid ${highlightMode === mode ? "#ff6b35" : "#ffffff14"}`,
                        background: highlightMode === mode ? "#ff6b350f" : "#ffffff04",
                        color: highlightMode === mode ? "#ff6b35" : "#ffffff50",
                        cursor: "pointer", fontSize: 13, fontFamily: "inherit",
                        transition: "all 0.15s",
                      }}>
                        {mode === "auto" ? "✦ AI picks the best moment" : "✎ I'll mark the moment"}
                      </button>
                    ))}
                  </div>

                  {highlightMode === "manual" && (
                    <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                      <div style={{ flex: 1 }}>
                        {label("START (seconds)")}
                        <input type="number" value={manualStart} onChange={(e) => setManualStart(e.target.value)} placeholder="e.g. 12"
                          style={{ width: "100%", background: "#ffffff08", border: "1px solid #ffffff14", borderRadius: 8, padding: "10px 14px", color: "#e8e6e0", fontSize: 14, transition: "border-color 0.2s" }} />
                      </div>
                      <div style={{ flex: 1 }}>
                        {label("END (seconds)")}
                        <input type="number" value={manualEnd} onChange={(e) => setManualEnd(e.target.value)} placeholder="e.g. 27"
                          style={{ width: "100%", background: "#ffffff08", border: "1px solid #ffffff14", borderRadius: 8, padding: "10px 14px", color: "#e8e6e0", fontSize: 14, transition: "border-color 0.2s" }} />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Submit */}
          <button onClick={handleSubmit} disabled={!file || loading} style={{
            width: "100%", padding: "16px", borderRadius: 12, border: "none",
            background: !file || loading ? "#ffffff12" : "#ff6b35",
            color: !file || loading ? "#ffffff30" : "white",
            fontSize: 16, fontWeight: 500, cursor: !file || loading ? "not-allowed" : "pointer",
            transition: "all 0.2s ease", display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
            fontFamily: "inherit",
          }}>
            {loading ? (
              <>
                <SpinnerIcon />
                <span style={{ animation: "pulse 1.5s ease infinite" }}>{step || "Processing..."}</span>
              </>
            ) : "Generate Demo →"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div style={{ marginTop: 24, padding: "16px 20px", borderRadius: 12, background: "#ff000010", border: "1px solid #ff000030", color: "#ff6b6b", fontSize: 14, animation: "fadeUp 0.3s ease both" }}>
            ⚠️ {error}
          </div>
        )}

        {/* Results */}
        {result && (
          <div style={{ marginTop: 48, animation: "fadeUp 0.4s ease both" }}>
            <div style={{ height: 1, background: "linear-gradient(90deg, #ff6b3540, transparent)", marginBottom: 40 }} />

            <h2 style={{ fontFamily: "'DM Serif Display', serif", fontSize: 28, fontWeight: 400, marginBottom: 8, letterSpacing: "-0.02em" }}>
              Your demo is ready
            </h2>
            <p style={{ color: "#ffffff40", fontSize: 14, marginBottom: 32 }}>
              {result.frame_count} frames analysed · {Math.round(result.duration)}s video ·&nbsp;
              <span style={{
                color: result.tts_provider === "elevenlabs" ? "#ff6b35" : "#60a5fa",
              }}>
                {result.tts_provider === "elevenlabs" ? "ElevenLabs" : "OpenAI TTS"}
              </span>
              {result.enhancements_applied && (
                <span style={{ color: "#34d399" }}>
                  &nbsp;· Enhanced ({result.interactions_detected} zoom{result.interactions_detected !== 1 ? "s" : ""}, {result.scene_changes_detected} transition{result.scene_changes_detected !== 1 ? "s" : ""})
                </span>
              )}
            </p>

            {/* Script */}
            <div style={{ background: "#ffffff06", border: "1px solid #ffffff10", borderRadius: 16, padding: 24, marginBottom: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <span style={{ fontSize: 12, color: "#ffffff50", letterSpacing: "0.08em", textTransform: "uppercase" }}>Voiceover Script</span>
                <div style={{ display: "flex", gap: 8 }}>
                  {!editingScript && (
                    <button onClick={startEditing} style={{
                      display: "flex", alignItems: "center", gap: 6,
                      background: "#ffffff10", border: "none", borderRadius: 8,
                      padding: "6px 12px", color: "#ffffff60",
                      fontSize: 12, cursor: "pointer", fontFamily: "inherit", transition: "all 0.2s",
                    }}>
                      ✎ Edit
                    </button>
                  )}
                  <button onClick={copyScript} style={{
                    display: "flex", alignItems: "center", gap: 6,
                    background: copied ? "#ff6b3520" : "#ffffff10", border: "none", borderRadius: 8,
                    padding: "6px 12px", color: copied ? "#ff6b35" : "#ffffff60",
                    fontSize: 12, cursor: "pointer", fontFamily: "inherit", transition: "all 0.2s",
                  }}>
                    {copied ? <CheckIcon /> : <CopyIcon />}
                    {copied ? "Copied!" : "Copy"}
                  </button>
                </div>
              </div>
              {editingScript ? (
                <>
                  <textarea
                    value={editedScript}
                    onChange={(e) => setEditedScript(e.target.value)}
                    style={{
                      width: "100%", minHeight: 180, fontSize: 16, lineHeight: 1.8,
                      color: "#e8e6e0", background: "#ffffff08", border: "1px solid #ffffff20",
                      borderRadius: 10, padding: 16, fontFamily: "inherit", resize: "vertical",
                      outline: "none",
                    }}
                  />
                  <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
                    <button onClick={regenerateWithEdit} disabled={regenerating} style={{
                      padding: "10px 20px", borderRadius: 8, border: "none",
                      background: regenerating ? "#ffffff12" : "#ff6b35",
                      color: regenerating ? "#ffffff30" : "white",
                      fontSize: 13, fontWeight: 500, cursor: regenerating ? "not-allowed" : "pointer",
                      fontFamily: "inherit", display: "flex", alignItems: "center", gap: 8,
                    }}>
                      {regenerating ? <><SpinnerIcon /> Regenerating...</> : "Regenerate Audio & Video"}
                    </button>
                    <button onClick={() => setEditingScript(false)} style={{
                      padding: "10px 20px", borderRadius: 8, border: "1px solid #ffffff20",
                      background: "transparent", color: "#ffffff60",
                      fontSize: 13, cursor: "pointer", fontFamily: "inherit",
                    }}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <p style={{ fontSize: 16, lineHeight: 1.8, color: "#e8e6e0cc", whiteSpace: "pre-wrap" }}>{result.script}</p>
              )}
            </div>

            {/* Full demo video */}
            {result.full_video_url && (
              <VideoCard title="Full Narrated Demo" badge="Full Length" badgeColor="#ff6b35" url={result.full_video_url}>
                <a href={`${API_BASE}${result.full_video_url}`} download style={{ display: "inline-block", marginTop: 12, fontSize: 13, color: "#ff6b35", textDecoration: "none" }}>
                  ↓ Download MP4
                </a>
              </VideoCard>
            )}

            {/* Social short */}
            {result.short_clip_url && (
              <VideoCard
                title="Social Short Clip"
                badge="Instagram · TikTok · Reels"
                badgeColor="#a855f7"
                url={result.short_clip_url}
                highlight={result.highlight}
              >
                <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
                  <a href={`${API_BASE}${result.short_clip_url}`} download style={{ fontSize: 13, color: "#a855f7", textDecoration: "none" }}>
                    ↓ Download Short (9:16)
                  </a>
                </div>
              </VideoCard>
            )}

            {/* Audio download */}
            {result.audio_url && (
              <div style={{ background: "#ffffff04", border: "1px solid #ffffff08", borderRadius: 12, padding: "14px 18px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 13, color: "#ffffff40" }}>Voiceover audio only</span>
                <a href={`${API_BASE}${result.audio_url}`} download style={{ fontSize: 13, color: "#ffffff50", textDecoration: "none" }}>
                  ↓ Download MP3
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
