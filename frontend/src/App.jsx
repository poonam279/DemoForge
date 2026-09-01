import { useState, useRef, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "";

async function safeJson(res) {
  const text = await res.text();
  if (!text) throw new Error("Server returned an empty response — request may have timed out");
  try { return JSON.parse(text); }
  catch { throw new Error(`Server error: ${text.slice(0, 200)}`); }
}

const TONES = [
  { value: "professional", label: "Professional", desc: "SaaS product demo style" },
  { value: "friendly", label: "Friendly", desc: "Warm & conversational" },
  { value: "energetic", label: "Energetic", desc: "Startup pitch energy" },
];

const MODES = [
  { value: 200, label: "Quick Demo", desc: "~90s · Social reels" },
  { value: 600, label: "Standard", desc: "~4min · Walkthroughs" },
  { value: 1200, label: "Deep Dive", desc: "~8min · Training" },
];

const splitToSegments = (text) =>
  text.trim().split(/(?<=[.!?])\s+/).filter(Boolean);


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
  const [wordLimit, setWordLimit] = useState(200);
  const [generateShort, setGenerateShort] = useState(false); // disabled for now — set to true and uncomment UI to re-enable social clips
  const [highlightMode, setHighlightMode] = useState("auto");
  const [manualStart, setManualStart] = useState("");
  const [manualEnd, setManualEnd] = useState("");

  // Two-phase state: idle | generatingScript | scriptReady | generatingVideo | result
  const [phase, setPhase] = useState("idle");
  const [step, setStep] = useState("");
  const [jobId, setJobId] = useState(null);
  const [script, setScript] = useState("");
  const [scriptMeta, setScriptMeta] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [segments, setSegments] = useState([]);
  const [editingSegment, setEditingSegment] = useState(null);
  const [editingSegmentText, setEditingSegmentText] = useState("");
  const [regeneratingSegment, setRegeneratingSegment] = useState(null);
  const fileInputRef = useRef();

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }, []);

  const scriptSteps = [
    "Extracting frames from your screencast...",
    "Analysing screen content with Claude...",
    "Writing voiceover script...",
  ];

  const videoSteps = [
    "Generating voiceover audio...",
    "Detecting interactions & scene changes...",
    "Applying video enhancements...",
    "Creating full demo video...",
    generateShort ? "Cutting social short clip..." : null,
  ].filter(Boolean);

  const handleGenerateScript = async () => {
    if (!file) return;
    setPhase("generatingScript");
    setError(null);
    setResult(null);
    setJobId(null);
    setScript("");

    const formData = new FormData();
    formData.append("video", file);
    formData.append("product_name", productName);
    formData.append("tone", tone);
    formData.append("word_limit", wordLimit.toString());

    let stepIdx = 0;
    setStep(scriptSteps[0]);
    const stepInterval = setInterval(() => {
      if (stepIdx < scriptSteps.length - 1) {
        stepIdx++;
        setStep(scriptSteps[stepIdx]);
      }
    }, 3500);

    try {
      const res = await fetch(`${API_BASE}/api/generate-script`, { method: "POST", body: formData });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Something went wrong");
      setJobId(data.job_id);
      setScript(data.script);
      if (data.segments && data.segments.length > 0) {
        setSegments(data.segments);
      } else {
        setSegments(splitToSegments(data.script).map((text, i) => ({ index: i, text })));
      }
      setScriptMeta({ frame_count: data.frame_count, duration: data.duration });
      setPhase("scriptReady");
    } catch (err) {
      setError(err.message);
      setPhase("idle");
    } finally {
      clearInterval(stepInterval);
      setStep("");
    }
  };

  const handleConfirmAndGenerate = async () => {
    const finalScript = segments.length > 0
      ? segments.map((s) => s.text).join(" ")
      : script;
    if (!jobId || !finalScript) return;
    setPhase("generatingVideo");
    setError(null);

    const body = {
      job_id: jobId,
      script: finalScript,
      segments: segments,
      generate_short: generateShort,
    };
    if (generateShort && highlightMode === "manual" && manualStart && manualEnd) {
      body.manual_start = manualStart;
      body.manual_end = manualEnd;
    }

    let stepIdx = 0;
    setStep(videoSteps[0]);
    const stepInterval = setInterval(() => {
      if (stepIdx < videoSteps.length - 1) {
        stepIdx++;
        setStep(videoSteps[stepIdx]);
      }
    }, 3500);

    try {
      const res = await fetch(`${API_BASE}/api/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Something went wrong");
      setResult(data);
      setSegments(data.segments || []);
      setPhase("result");
    } catch (err) {
      setError(err.message);
      setPhase("scriptReady");
    } finally {
      clearInterval(stepInterval);
      setStep("");
    }
  };

  const handleCancel = () => {
    if (jobId) {
      fetch(`${API_BASE}/api/cleanup/${jobId}`, { method: "POST" }).catch(() => {});
    }
    setPhase("idle");
    setJobId(null);
    setScript("");
    setScriptMeta(null);
    setError(null);
    setSegments([]);
    setEditingSegment(null);
    setRegeneratingSegment(null);
  };

  const copyScript = () => {
    const text = phase === "result"
      ? result.script
      : segments.length > 0
        ? segments.map((s) => s.text).join(" ")
        : script;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const totalWordCount = () => {
    const text = segments.length > 0
      ? segments.map((s) => s.text).join(" ")
      : script;
    return wordCount(text);
  };

  const updateSegmentText = (index, newText) => {
    setSegments((prev) => prev.map((s) => s.index === index ? { ...s, text: newText } : s));
  };

  const deleteSegment = (index) => {
    setSegments((prev) => {
      const filtered = prev.filter((s) => s.index !== index);
      const deletedSeg = prev.find((s) => s.index === index);
      return filtered.map((s, i) => {
        const updated = { ...s, index: i };
        if (deletedSeg && deletedSeg.frame_end && i === Math.max(0, index - 1)) {
          updated.frame_end = Math.max(s.frame_end || 0, deletedSeg.frame_end);
        }
        return updated;
      });
    });
  };

  const addSegment = () => {
    const lastSeg = segments[segments.length - 1];
    const newSeg = { index: segments.length, text: "" };
    if (lastSeg && lastSeg.frame_end) {
      newSeg.frame_start = lastSeg.frame_end;
      newSeg.frame_end = lastSeg.frame_end;
    }
    setSegments((prev) => [...prev, newSeg]);
    setEditingSegment(segments.length);
    setEditingSegmentText("");
  };

  const wordCount = (text) => text.trim().split(/\s+/).filter(Boolean).length;

  const regenerateWithEdit = async () => {
    setRegenerating(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: result.job_id, script: result._editedScript }),
      });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Regeneration failed");
      setResult((prev) => ({ ...prev, ...data, script: prev._editedScript, _editing: false }));
      if (data.segments) setSegments(data.segments);
    } catch (err) {
      setError(err.message);
    } finally {
      setRegenerating(false);
    }
  };

  const regenerateSegment = async (segmentIndex, newText) => {
    setRegeneratingSegment(segmentIndex);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/regenerate-segment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: result.job_id, segment_index: segmentIndex, new_text: newText }),
      });
      const data = await safeJson(res);
      if (!res.ok) throw new Error(data.error || "Segment regeneration failed");
      setSegments(data.segments);
      setResult((prev) => ({
        ...prev,
        full_video_url: data.full_video_url,
        audio_url: data.audio_url,
        script: data.segments.map((s) => s.text).join(" "),
      }));
      setEditingSegment(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setRegeneratingSegment(null);
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
          Screencast → Narrated Demo
        </span>
      </div>

      <div style={{ maxWidth: 780, margin: "0 auto", padding: "60px 24px" }}>

        {/* Hero */}
        <div style={{ marginBottom: 56, animation: "fadeUp 0.5s ease both" }}>
          <h1 style={{ fontFamily: "'DM Serif Display', serif", fontSize: "clamp(36px, 5vw, 52px)", fontWeight: 400, lineHeight: 1.1, letterSpacing: "-0.03em", marginBottom: 16 }}>
          
            <em style={{ color: "#ff6b35" }}>  Raw screencast in.<br /> narrated demo video out.</em>
          </h1>
          <p style={{ color: "#ffffff60", fontSize: 17, lineHeight: 1.6, maxWidth: 720 }}>
            Upload any screencast — DemoForge writes the script, generates the voiceover, and produces a full narrated demo video. No editing. No account. Bring your own keys.
          </p>
        </div>

        {/* Phase 1: Form */}
        {(phase === "idle" || phase === "generatingScript") && (
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

              {/* Script length */}
              <div>
                {label("SCRIPT LENGTH")}
                <div style={{ display: "flex", gap: 10 }}>
                  {MODES.map((m) => (
                    <button key={m.value} onClick={() => setWordLimit(m.value)} style={{
                      flex: 1, padding: "12px 8px", borderRadius: 10,
                      border: `1.5px solid ${wordLimit === m.value ? "#ff6b35" : "#ffffff14"}`,
                      background: wordLimit === m.value ? "#ff6b350f" : "#ffffff04",
                      color: wordLimit === m.value ? "#ff6b35" : "#ffffff60",
                      cursor: "pointer", fontSize: 13, fontWeight: wordLimit === m.value ? 500 : 400,
                      transition: "all 0.15s ease", textAlign: "center", fontFamily: "inherit",
                    }}>
                      <div style={{ marginBottom: 2 }}>{m.label}</div>
                      <div style={{ fontSize: 11, opacity: 0.6 }}>{m.desc}</div>
                    </button>
                  ))}
                </div>
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
            </div>

            {/* Generate Script button */}
            <button onClick={handleGenerateScript} disabled={!file || phase === "generatingScript"} style={{
              width: "100%", padding: "16px", borderRadius: 12, border: "none",
              background: !file || phase === "generatingScript" ? "#ffffff12" : "#ff6b35",
              color: !file || phase === "generatingScript" ? "#ffffff30" : "white",
              fontSize: 16, fontWeight: 500, cursor: !file || phase === "generatingScript" ? "not-allowed" : "pointer",
              transition: "all 0.2s ease", display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
              fontFamily: "inherit",
            }}>
              {phase === "generatingScript" ? (
                <>
                  <SpinnerIcon />
                  <span style={{ animation: "pulse 1.5s ease infinite" }}>{step || "Generating script..."}</span>
                </>
              ) : "Generate Script →"}
            </button>
          </div>
        )}

        {/* Phase 2: Script review */}
        {(phase === "scriptReady" || phase === "generatingVideo") && (
          <div style={{ animation: "fadeUp 0.4s ease both" }}>
            <div style={{ height: 1, background: "linear-gradient(90deg, #ff6b3540, transparent)", marginBottom: 32 }} />

            <h2 style={{ fontFamily: "'DM Serif Display', serif", fontSize: 28, fontWeight: 400, marginBottom: 8, letterSpacing: "-0.02em" }}>
              Review your script
            </h2>
            <p style={{ color: "#ffffff40", fontSize: 14, marginBottom: 24 }}>
              {scriptMeta?.frame_count} frames analysed · {Math.round(scriptMeta?.duration || 0)}s video · Edit segments below, then confirm to generate audio and video.
            </p>

            <div style={{ background: "#ffffff06", border: "1px solid #ffffff10", borderRadius: 16, padding: 24, marginBottom: 20, opacity: phase === "generatingVideo" ? 0.5 : 1, pointerEvents: phase === "generatingVideo" ? "none" : "auto", transition: "opacity 0.2s" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <span style={{ fontSize: 12, color: "#ffffff50", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  Voiceover Script · {segments.length} segment{segments.length !== 1 ? "s" : ""}
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{
                    fontSize: 12,
                    color: totalWordCount() > wordLimit ? "#ff6b6b" : "#ffffff40",
                  }}>
                    {totalWordCount()} / {wordLimit} words
                  </span>
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

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {segments.map((seg) => (
                  <div key={seg.index} style={{
                    display: "flex", alignItems: "flex-start", gap: 12,
                    padding: "12px 14px", borderRadius: 10,
                    background: editingSegment === seg.index ? "#ffffff0c" : "#ffffff04",
                    border: `1px solid ${editingSegment === seg.index ? "#ff6b3530" : "#ffffff08"}`,
                    transition: "all 0.2s",
                  }}>
                    {seg.frame_thumbnail ? (
                      <img
                        src={`${API_BASE}${seg.frame_thumbnail}`}
                        alt={`Frame ${seg.frame_start}`}
                        style={{
                          width: 72, height: 44, objectFit: "cover", borderRadius: 6,
                          border: "1px solid #ffffff10", flexShrink: 0,
                        }}
                      />
                    ) : (
                      <span style={{
                        fontSize: 11, color: "#ffffff30", fontWeight: 500,
                        minWidth: 24, textAlign: "right", paddingTop: 3,
                      }}>
                        {seg.index + 1}
                      </span>
                    )}
                    <div style={{ flex: 1 }}>
                      {editingSegment === seg.index ? (
                        <>
                          <textarea
                            value={editingSegmentText}
                            onChange={(e) => setEditingSegmentText(e.target.value)}
                            autoFocus
                            style={{
                              width: "100%", minHeight: 60, fontSize: 14, lineHeight: 1.7,
                              color: "#e8e6e0", background: "#ffffff08", border: "1px solid #ffffff20",
                              borderRadius: 8, padding: "8px 12px", fontFamily: "inherit", resize: "vertical",
                              outline: "none",
                            }}
                          />
                          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                            <button
                              onClick={() => { updateSegmentText(seg.index, editingSegmentText); setEditingSegment(null); }}
                              style={{
                                padding: "6px 14px", borderRadius: 6, border: "none",
                                background: "#ff6b35", color: "white",
                                fontSize: 12, fontWeight: 500, cursor: "pointer",
                                fontFamily: "inherit",
                              }}
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingSegment(null)}
                              style={{
                                padding: "6px 14px", borderRadius: 6, border: "1px solid #ffffff20",
                                background: "transparent", color: "#ffffff60",
                                fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                              }}
                            >
                              Cancel
                            </button>
                            {segments.length > 1 && (
                              <button
                                onClick={() => { deleteSegment(seg.index); setEditingSegment(null); }}
                                style={{
                                  padding: "6px 14px", borderRadius: 6, border: "1px solid #ff6b6b30",
                                  background: "transparent", color: "#ff6b6b80",
                                  fontSize: 12, cursor: "pointer", fontFamily: "inherit", marginLeft: "auto",
                                }}
                              >
                                Delete
                              </button>
                            )}
                          </div>
                        </>
                      ) : (
                        <>
                          <p style={{ fontSize: 14, lineHeight: 1.7, color: "#e8e6e0cc", margin: 0 }}>
                            {seg.text}
                          </p>
                          {seg.frame_start != null && seg.frame_end != null && (
                            <span style={{
                              fontSize: 11, color: "#ffffff30", marginTop: 4, display: "inline-block",
                            }}>
                              Frames {seg.frame_start}–{seg.frame_end} ({seg.frame_end - seg.frame_start + 1}s)
                            </span>
                          )}
                        </>
                      )}
                    </div>
                    {editingSegment !== seg.index && (
                      <button
                        onClick={() => { setEditingSegment(seg.index); setEditingSegmentText(seg.text); }}
                        style={{
                          padding: "4px 10px", borderRadius: 6, border: "1px solid #ffffff14",
                          background: "#ffffff08", color: "#ffffff50",
                          fontSize: 11, cursor: "pointer", fontFamily: "inherit",
                          whiteSpace: "nowrap", transition: "all 0.15s", flexShrink: 0,
                        }}
                      >
                        Edit
                      </button>
                    )}
                  </div>
                ))}
              </div>

              <button onClick={addSegment} style={{
                marginTop: 12, padding: "8px 16px", borderRadius: 8,
                border: "1px dashed #ffffff20", background: "transparent",
                color: "#ffffff40", fontSize: 12, cursor: "pointer",
                fontFamily: "inherit", width: "100%", transition: "all 0.15s",
              }}>
                + Add Segment
              </button>
            </div>

            {/* Short clip options — commented out for now, uncomment to re-enable
            <div style={{ background: "#ffffff04", border: "1px solid #ffffff0a", borderRadius: 14, padding: 18, marginBottom: 20 }}>
              <Toggle value={generateShort} onChange={setGenerateShort}
                label="Generate social short clip"
                desc="Auto-cuts a 10-20s highlight, formatted 9:16 for Instagram, TikTok & Reels" />

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
                        {mode === "auto" ? "AI picks the best moment" : "I'll mark the moment"}
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
            */}

            {/* Action buttons */}
            <div style={{ display: "flex", gap: 12 }}>
              <button onClick={handleConfirmAndGenerate} disabled={phase === "generatingVideo"} style={{
                flex: 1, padding: "16px", borderRadius: 12, border: "none",
                background: phase === "generatingVideo" ? "#ffffff12" : "#ff6b35",
                color: phase === "generatingVideo" ? "#ffffff30" : "white",
                fontSize: 16, fontWeight: 500, cursor: phase === "generatingVideo" ? "not-allowed" : "pointer",
                transition: "all 0.2s ease", display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
                fontFamily: "inherit",
              }}>
                {phase === "generatingVideo" ? (
                  <>
                    <SpinnerIcon />
                    <span style={{ animation: "pulse 1.5s ease infinite" }}>{step || "Generating..."}</span>
                  </>
                ) : "Confirm & Generate Video →"}
              </button>
              <button onClick={handleCancel} disabled={phase === "generatingVideo"} style={{
                padding: "16px 24px", borderRadius: 12, border: "1px solid #ffffff20",
                background: "transparent", color: "#ffffff60",
                fontSize: 16, cursor: phase === "generatingVideo" ? "not-allowed" : "pointer",
                fontFamily: "inherit", transition: "all 0.2s",
              }}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ marginTop: 24, padding: "16px 20px", borderRadius: 12, background: "#ff000010", border: "1px solid #ff000030", color: "#ff6b6b", fontSize: 14, animation: "fadeUp 0.3s ease both" }}>
            {error}
          </div>
        )}

        {/* Results */}
        {phase === "result" && result && (
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

            {/* Script segments */}
            <div style={{ background: "#ffffff06", border: "1px solid #ffffff10", borderRadius: 16, padding: 24, marginBottom: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <span style={{ fontSize: 12, color: "#ffffff50", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  Voiceover Script · {segments.length} segment{segments.length !== 1 ? "s" : ""}
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => setResult((prev) => ({ ...prev, _editing: true, _editedScript: prev.script }))} style={{
                    display: "flex", alignItems: "center", gap: 6,
                    background: "#ffffff10", border: "none", borderRadius: 8,
                    padding: "6px 12px", color: "#ffffff60",
                    fontSize: 12, cursor: "pointer", fontFamily: "inherit", transition: "all 0.2s",
                  }}>
                    Re-record All
                  </button>
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

              {result._editing ? (
                <>
                  <textarea
                    value={result._editedScript}
                    onChange={(e) => setResult((prev) => ({ ...prev, _editedScript: e.target.value }))}
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
                      {regenerating ? <><SpinnerIcon /> Re-recording all...</> : "Re-record All Segments"}
                    </button>
                    <button onClick={() => setResult((prev) => ({ ...prev, _editing: false }))} style={{
                      padding: "10px 20px", borderRadius: 8, border: "1px solid #ffffff20",
                      background: "transparent", color: "#ffffff60",
                      fontSize: 13, cursor: "pointer", fontFamily: "inherit",
                    }}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {segments.map((seg) => (
                    <div key={seg.index} style={{
                      display: "flex", alignItems: "flex-start", gap: 12,
                      padding: "12px 14px", borderRadius: 10,
                      background: editingSegment === seg.index ? "#ffffff0c" : "#ffffff04",
                      border: `1px solid ${editingSegment === seg.index ? "#ff6b3530" : "#ffffff08"}`,
                      transition: "all 0.2s",
                    }}>
                      {seg.frame_thumbnail ? (
                        <img
                          src={`${API_BASE}${seg.frame_thumbnail}`}
                          alt={`Frame ${seg.frame_start}`}
                          style={{
                            width: 72, height: 44, objectFit: "cover", borderRadius: 6,
                            border: "1px solid #ffffff10", flexShrink: 0,
                          }}
                        />
                      ) : (
                        <span style={{
                          fontSize: 11, color: "#ffffff30", fontWeight: 500,
                          minWidth: 24, textAlign: "right", paddingTop: 3,
                        }}>
                          {seg.index + 1}
                        </span>
                      )}
                      <div style={{ flex: 1 }}>
                        {editingSegment === seg.index ? (
                          <>
                            <textarea
                              value={editingSegmentText}
                              onChange={(e) => setEditingSegmentText(e.target.value)}
                              disabled={regeneratingSegment === seg.index}
                              style={{
                                width: "100%", minHeight: 60, fontSize: 14, lineHeight: 1.7,
                                color: "#e8e6e0", background: "#ffffff08", border: "1px solid #ffffff20",
                                borderRadius: 8, padding: "8px 12px", fontFamily: "inherit", resize: "vertical",
                                outline: "none", opacity: regeneratingSegment === seg.index ? 0.5 : 1,
                              }}
                            />
                            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                              <button
                                onClick={() => regenerateSegment(seg.index, editingSegmentText)}
                                disabled={regeneratingSegment === seg.index}
                                style={{
                                  padding: "6px 14px", borderRadius: 6, border: "none",
                                  background: regeneratingSegment === seg.index ? "#ffffff12" : "#ff6b35",
                                  color: regeneratingSegment === seg.index ? "#ffffff30" : "white",
                                  fontSize: 12, fontWeight: 500,
                                  cursor: regeneratingSegment === seg.index ? "not-allowed" : "pointer",
                                  fontFamily: "inherit", display: "flex", alignItems: "center", gap: 6,
                                }}
                              >
                                {regeneratingSegment === seg.index ? <><SpinnerIcon /> Re-recording...</> : "Save & Re-record"}
                              </button>
                              <button
                                onClick={() => setEditingSegment(null)}
                                disabled={regeneratingSegment === seg.index}
                                style={{
                                  padding: "6px 14px", borderRadius: 6, border: "1px solid #ffffff20",
                                  background: "transparent", color: "#ffffff60",
                                  fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                                }}
                              >
                                Cancel
                              </button>
                            </div>
                          </>
                        ) : (
                          <>
                            <p style={{ fontSize: 14, lineHeight: 1.7, color: "#e8e6e0cc", margin: 0 }}>
                              {seg.text}
                            </p>
                            {seg.frame_start != null && seg.frame_end != null && (
                              <span style={{
                                fontSize: 11, color: "#ffffff30", marginTop: 4, display: "inline-block",
                              }}>
                                Frames {seg.frame_start}–{seg.frame_end} ({seg.frame_end - seg.frame_start + 1}s)
                              </span>
                            )}
                          </>
                        )}
                      </div>
                      {editingSegment !== seg.index && (
                        <button
                          onClick={() => { setEditingSegment(seg.index); setEditingSegmentText(seg.text); }}
                          style={{
                            padding: "4px 10px", borderRadius: 6, border: "1px solid #ffffff14",
                            background: "#ffffff08", color: "#ffffff50",
                            fontSize: 11, cursor: "pointer", fontFamily: "inherit",
                            whiteSpace: "nowrap", transition: "all 0.15s", flexShrink: 0,
                          }}
                        >
                          Re-record
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Full demo video */}
            {result.full_video_url && (
              <VideoCard title="Full Narrated Demo" badge="Full Length" badgeColor="#ff6b35" url={result.full_video_url}>
                <a href={`${API_BASE}${result.full_video_url}${result.full_video_url.includes("?") ? "&" : "?"}download=1`} download style={{ display: "inline-block", marginTop: 12, fontSize: 13, color: "#ff6b35", textDecoration: "none" }}>
                  ↓ Download MP4
                </a>
              </VideoCard>
            )}

            {/* Social short — commented out for now, uncomment to re-enable
            {result.short_clip_url && (
              <VideoCard
                title="Social Short Clip"
                badge="Instagram · TikTok · Reels"
                badgeColor="#a855f7"
                url={result.short_clip_url}
                highlight={result.highlight}
              >
                <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
                  <a href={`${API_BASE}${result.short_clip_url}${result.short_clip_url.includes("?") ? "&" : "?"}download=1`} download style={{ fontSize: 13, color: "#a855f7", textDecoration: "none" }}>
                    ↓ Download Short (9:16)
                  </a>
                </div>
              </VideoCard>
            )}
            */}

            {/* Audio download */}
            {result.audio_url && (
              <div style={{ background: "#ffffff04", border: "1px solid #ffffff08", borderRadius: 12, padding: "14px 18px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 13, color: "#ffffff40" }}>Voiceover audio only</span>
                <a href={`${API_BASE}${result.audio_url}${result.audio_url.includes("?") ? "&" : "?"}download=1`} download style={{ fontSize: 13, color: "#ffffff50", textDecoration: "none" }}>
                  ↓ Download MP3
                </a>
              </div>
            )}

            {/* Start over */}
            <button onClick={handleCancel} style={{
              marginTop: 24, width: "100%", padding: "14px", borderRadius: 12,
              border: "1px solid #ffffff15", background: "transparent",
              color: "#ffffff50", fontSize: 14, cursor: "pointer", fontFamily: "inherit",
              transition: "all 0.2s",
            }}>
              Start New Demo
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
