import React, { useCallback, useEffect, useRef, useState } from "react";

// Single-file React component (Tailwind assumed available)
// Upgraded to draw live joint points, skeleton lines, show accuracy, and voice feedback

export default function YogaPoseApp() {
  const [page, setPage] = useState("compare"); // 'compare' or 'add'

  return (
    <div className="min-h-screen bg-gray-50 text-gray-800">
      <header className="bg-white shadow p-4 sticky top-0 z-20">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Yoga Pose Studio</h1>
          <nav className="space-x-2">
            <button
              onClick={() => setPage("compare")}
              className={`px-4 py-2 rounded-lg font-medium ${page === "compare" ? "bg-green-600 text-white" : "bg-gray-100"}`}
            >
              Compare (Live)
            </button>
            <button
              onClick={() => setPage("add")}
              className={`px-4 py-2 rounded-lg font-medium ${page === "add" ? "bg-green-600 text-white" : "bg-gray-100"}`}
            >
              Add Pose
            </button>
          </nav>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6">
        {page === "compare" ? <ComparePage /> : <AddPosePage />}
      </main>

      <footer className="text-center text-sm text-gray-500 p-6">Made for the Yoga Pose API — connects to /upload_pose, /asanas/{"<name>"}, /compare_pose</footer>
    </div>
  );
}

// ---------------- Compare Page ----------------
function ComparePage() {
  const videoRef = useRef(null);
  const captureCanvasRef = useRef(null); // hidden canvas used to capture frames
  const overlayRef = useRef(null); // visible drawing canvas

  const [asanas, setAsanas] = useState([]);
  const [selectedAsana, setSelectedAsana] = useState("");
  const [posesInAsana, setPosesInAsana] = useState([]);
  const [selectedPoseNumber, setSelectedPoseNumber] = useState(1);
  const [selectedPose, setSelectedPose] = useState(null);
  const [tolerance, setTolerance] = useState(20);
  const [feedback, setFeedback] = useState(null);
  const [isComparing, setIsComparing] = useState(false);
  const [error, setError] = useState(null);
  const [continuousMode, setContinuousMode] = useState(false);

  // local copy of last live_feedback (used for drawing loop)
  const lastFeedbackRef = useRef(null);
  const lastAudioRef = useRef(null);

  useEffect(() => {
    startCamera();
    fetchAsanas();
    const handleResize = () => resizeOverlay();
    window.addEventListener("resize", handleResize);
    return () => {
      stopCamera();
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  useEffect(() => {
    if (selectedPose && continuousMode) {
      const interval = setInterval(() => {
        handleCompareOnce();
      }, 1200);
      return () => clearInterval(interval);
    }
  }, [selectedPose, continuousMode, tolerance, handleCompareOnce]);

  useEffect(() => {
    startDrawingLoop();
    // stop on unmount
    return () => stopDrawingLoop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startDrawingLoop() {
    let rafId = null;
    const loop = () => {
      drawOverlay(lastFeedbackRef.current);
      rafId = requestAnimationFrame(loop);
    };
    loop();
    overlayRef.current.__rafId = rafId;
  }

  function stopDrawingLoop() {
    const c = overlayRef.current;
    if (c && c.__rafId) {
      cancelAnimationFrame(c.__rafId);
      delete c.__rafId;
    }
  }

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        resizeOverlay();
      }
    } catch (e) {
      console.error("Could not access camera", e);
      setError("Could not access camera. Allow camera permissions or use a device with a camera.");
    }
  }

  function stopCamera() {
    if (videoRef.current && videoRef.current.srcObject) {
      const tracks = videoRef.current.srcObject.getTracks();
      tracks.forEach((t) => t.stop());
      videoRef.current.srcObject = null;
    }
  }

  function resizeOverlay() {
    const video = videoRef.current;
    const canvas = overlayRef.current;
    if (!video || !canvas) return;
    // match canvas CSS size to video element size
    const rect = video.getBoundingClientRect();
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";
    // set backing store size to video resolution for crisp drawing
    canvas.width = video.videoWidth || rect.width;
    canvas.height = video.videoHeight || rect.height;
  }

  async function fetchAsanas() {
    try {
      const resp = await fetch("http://127.0.0.1:5000/asanas");
      if (!resp.ok) throw new Error("no-asanas-endpoint");
      const data = await resp.json();
      if (Array.isArray(data)) {
        setAsanas(data);
        if (data.length) setSelectedAsana(data[0]);
      } else if (data.asanas && Array.isArray(data.asanas)) {
        setAsanas(data.asanas);
        if (data.asanas.length) setSelectedAsana(data.asanas[0]);
      }
    } catch (e) {
      console.warn("Could not fetch asana list:", e);
    }
  }

  useEffect(() => {
    if (!selectedAsana) return;
    fetch(`http://127.0.0.1:5000/asanas/${encodeURIComponent(selectedAsana)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data && data.poses) {
          setPosesInAsana(data.poses);
          if (data.poses.length > 0) {
            setSelectedPose(data.poses[0]);
            setSelectedPoseNumber(data.poses[0].pose_number);
          }
        } else {
          setPosesInAsana([]);
          setSelectedPose(null);
        }
      })
      .catch((err) => {
        console.warn("Could not fetch asana details", err);
        setPosesInAsana([]);
        setSelectedPose(null);
      });
  }, [selectedAsana]);

  async function handleCompareOnce() {
    setIsComparing(true);
    setFeedback(null);
    setError(null);

    try {
      const blob = await captureFrame();
      if (!blob) throw new Error("Could not capture frame");

      const fd = new FormData();
      fd.append("new_image", blob, "live.jpg");
      fd.append("asana_name", selectedAsana || "");
      fd.append("reference_pose_number", String(selectedPoseNumber));
      fd.append("tolerance", String(tolerance));

      const resp = await fetch("http://127.0.0.1:5000/compare_pose", {
        method: "POST",
        body: fd,
      });

      const result = await resp.json();
      if (!resp.ok) {
        setError(result.error || JSON.stringify(result));
        setIsComparing(false);
        return;
      }

      setFeedback(result);
      lastFeedbackRef.current = result;

      // speak audio feedback
      if (result.audio_feedback && lastAudioRef.current !== result.audio_feedback) {
        speakFeedback(result.audio_feedback);
        lastAudioRef.current = result.audio_feedback;
      }
    } catch (e) {
      console.error(e);
      setError(String(e));
    } finally {
      setIsComparing(false);
    }
  }


  function captureFrame() {
    const video = videoRef.current;
    const canvas = captureCanvasRef.current;
    if (!video || !canvas) return null;
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, w, h);
    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.9);
    });
  }

  // simple TTS for audio feedback
  function speakFeedback(flag) {
    try {
      const utterance = new SpeechSynthesisUtterance(flag === "correct" ? "Correct" : "Wrong");
      utterance.lang = "en-US";
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      // ignore TTS failures
    }
  }

  function drawOverlay(data) {
    const canvas = overlayRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;
    const ctx = canvas.getContext("2d");
    // Clear
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw semi-transparent background when no data
    if (!data) return;

    // draw skeleton lines
    if (Array.isArray(data.skeleton)) {
      ctx.lineWidth = 3;
      data.skeleton.forEach((seg) => {
        ctx.beginPath();
        ctx.strokeStyle = "rgba(0,0,0,0.5)";
        ctx.moveTo(seg.x1, seg.y1);
        ctx.lineTo(seg.x2, seg.y2);
        ctx.stroke();
      });
    }

    // draw joints
    if (Array.isArray(data.live_feedback)) {
      data.live_feedback.forEach((j) => {
        const color = j.is_correct ? "#22c55e" : "#ef4444"; // green/red
        ctx.beginPath();
        ctx.fillStyle = color;
        ctx.strokeStyle = "#00000055";
        ctx.lineWidth = 1;
        // radius relative to canvas size
        const r = Math.max(6, Math.min(12, canvas.width / 80));
        ctx.arc(j.x, j.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // label
        ctx.font = "14px Arial";
        ctx.fillStyle = color;
        const label = j.joint_name.replace(/_/g, " ");
        ctx.fillText(label, j.x + r + 4, j.y + 4);
      });
    }

    // draw accuracy badge
    if (typeof data.pose_accuracy === "number") {
      const score = data.pose_accuracy;
      // top-right corner
      const pad = 12;
      const boxW = 110;
      const boxH = 46;
      const x = canvas.width - boxW - pad;
      const y = pad;

      // background
      ctx.fillStyle = "rgba(255,255,255,0.9)";
      ctx.strokeStyle = "#e5e7eb";
      roundRect(ctx, x, y, boxW, boxH, 8, true, true);

      // text
      ctx.fillStyle = "#111827";
      ctx.font = "bold 16px Arial";
      ctx.fillText(`Accuracy`, x + 12, y + 18);
      ctx.font = "bold 18px Arial";
      ctx.fillStyle = score >= 80 ? "#15803d" : score >= 50 ? "#d97706" : "#b91c1c";
      ctx.fillText(`${score}%`, x + 12, y + 38);
    }
  }

  function roundRect(ctx, x, y, w, h, r, fill, stroke) {
    if (typeof r === 'number') {
      r = {tl: r, tr: r, br: r, bl: r};
    }
    ctx.beginPath();
    ctx.moveTo(x + r.tl, y);
    ctx.lineTo(x + w - r.tr, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r.tr);
    ctx.lineTo(x + w, y + h - r.br);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r.br, y + h);
    ctx.lineTo(x + r.bl, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r.bl);
    ctx.lineTo(x, y + r.tl);
    ctx.quadraticCurveTo(x, y, x + r.tl, y);
    ctx.closePath();
    if (fill) ctx.fill();
    if (stroke) ctx.stroke();
  }

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white p-4 rounded-lg shadow">
          <h2 className="font-semibold mb-2">Live Camera</h2>

          <div className="relative border rounded overflow-hidden" style={{height: 384}}>
            <video ref={videoRef} className="w-full h-full object-cover bg-black" playsInline muted />

            {/* overlay canvas sits on top for drawing skeleton & joints */}
            <canvas ref={overlayRef} className="absolute top-0 left-0 pointer-events-none" />
          </div>

          {/* hidden capture canvas used to create image blob for backend */}
          <canvas ref={captureCanvasRef} className="hidden" />

          {isComparing && <div className="text-sm text-gray-500 mt-2">Comparing...</div>}
          {error && <div className="text-sm text-red-600 mt-2">{error}</div>}
        </div>

        <div className="bg-white p-4 rounded-lg shadow">
          <h2 className="font-semibold mb-2">Reference Pose</h2>
          {selectedPose ? (
            <div className="text-center">
              <img src={selectedPose.image_url} alt={selectedPose.pose_name} className="w-full h-64 object-contain bg-gray-100 rounded mb-2" />
              <div className="font-medium">{selectedPose.pose_name || `Pose ${selectedPose.pose_number}`}</div>
              <div className="text-sm text-gray-500">#{selectedPose.pose_number}</div>
            </div>
          ) : (
            <div className="w-full h-64 flex items-center justify-center bg-gray-100 rounded text-gray-500">
              Select an asana and pose to start comparison
            </div>
          )}
        </div>
      </section>

      <section className="bg-white p-4 rounded-lg shadow">
        <h2 className="font-semibold mb-4">Settings</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Asana Name</label>
            <div className="flex gap-2">
              <select
                value={selectedAsana}
                onChange={(e) => setSelectedAsana(e.target.value)}
                className="flex-1 p-2 border rounded"
              >
                <option value="">-- choose or type below --</option>
                {asanas.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
              <button onClick={() => fetchAsanas()} className="px-3 py-2 bg-gray-100 rounded">Refresh</button>
            </div>
            <input type="text" value={selectedAsana} onChange={(e)=>setSelectedAsana(e.target.value)} className="w-full p-2 border rounded mt-2" placeholder="e.g., Surya Namaskar" />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Reference Pose</label>
            <select value={selectedPoseNumber} onChange={(e) => {
              setSelectedPoseNumber(Number(e.target.value));
              const pose = posesInAsana.find(p => p.pose_number === Number(e.target.value));
              setSelectedPose(pose || null);
            }} className="w-full p-2 border rounded">
              {posesInAsana.map((p) => (
                <option key={p.pose_id} value={p.pose_number}>{p.pose_name || `Pose ${p.pose_number}`}</option>
              ))}
            </select>
          </div>

        </div>

        <div className="mt-4 flex gap-2">
          <button
            onClick={() => { setContinuousMode(!continuousMode); }}
            className={`px-4 py-2 rounded ${continuousMode ? "bg-red-500 text-white" : "bg-green-600 text-white"}`}
            disabled={!selectedPose}
          >
            {continuousMode ? "Stop Live Comparison" : "Start Live Comparison"}
          </button>
          <button onClick={handleCompareOnce} className="px-4 py-2 rounded bg-gray-100" disabled={!selectedPose}>
            Compare Once
          </button>
        </div>
      </section>

      <section className="bg-white p-4 rounded-lg shadow">
        <h2 className="font-semibold mb-2">Feedback</h2>

        {!feedback && <div className="text-sm text-gray-500">No feedback yet. Perform a comparison to see suggested adjustments.</div>}

        {feedback && (
          <div>
            <div className="mb-2 text-sm text-gray-600">Comparing live frame to <strong>{feedback.reference_pose?.pose_name || "reference"}</strong> (Pose #{feedback.reference_pose?.pose_number})</div>

            <div className="flex items-center gap-3 mb-3">
              <div className="text-sm">Pose Accuracy:</div>
              <div className="font-bold text-lg">{feedback.pose_accuracy ?? 0}%</div>
              <div className="text-xs text-gray-500">(Audio: {feedback.audio_feedback})</div>
            </div>

            {Array.isArray(feedback.adjustments_needed) && feedback.adjustments_needed.length === 0 && (
              <div className="p-3 rounded bg-green-50 text-green-700">Great! No major adjustments (within threshold).</div>
            )}

            {Array.isArray(feedback.adjustments_needed) && feedback.adjustments_needed.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {feedback.adjustments_needed.map((adj, idx) => (
                  <div key={idx} className="p-3 border rounded">
                    <div className="font-medium">{adj.joint_name}</div>
                    <div className="text-sm">Adjustment: <strong>{adj.adjustment}</strong></div>
                    <div className="text-sm">Reference angle: {Number(adj.original_angle).toFixed(1)}°</div>
                    <div className="text-sm">Your angle: {Number(adj.new_angle).toFixed(1)}°</div>
                    <div className="text-sm text-gray-500">Difference: {Number(adj.difference).toFixed(1)}°</div>
                  </div>
                ))}
              </div>
            )}

          </div>
        )}
      </section>
    </div>
  );
}

// ---------------- Add Pose Page ----------------
function AddPosePage() {
  const [asanaName, setAsanaName] = useState("");
  const [poseName, setPoseName] = useState("");
  const [poseNumber, setPoseNumber] = useState(1);
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleUpload(e) {
    e.preventDefault();
    setSaving(true);
    setResult(null);
    setError(null);

    if (!asanaName || !poseName || !file) {
      setError("Please provide asana name, pose name and select an image.");
      setSaving(false);
      return;
    }

    const fd = new FormData();
    fd.append("image", file, file.name);
    fd.append("asana_name", asanaName);
    fd.append("pose_name", poseName);
    fd.append("pose_number", String(poseNumber));

    try {
      const resp = await fetch("http://127.0.0.1:5000/upload_pose", { method: "POST", body: fd });
      const json = await resp.json();
      if (!resp.ok) {
        setError(json.error || JSON.stringify(json));
      } else {
        setResult(json);
        setAsanaName("");
        setPoseName("");
        setPoseNumber(1);
        setFile(null);
      }
    } catch (e) {
      console.error(e);
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-white p-6 rounded-lg shadow">
      <h2 className="text-xl font-semibold mb-4">Add a New Pose</h2>
      <form onSubmit={handleUpload} className="space-y-4">
        <div>
          <label className="block text-sm font-medium">Asana Name</label>
          <input type="text" value={asanaName} onChange={(e)=>setAsanaName(e.target.value)} className="w-full p-2 border rounded" placeholder="e.g., Surya Namaskar" />
        </div>

        <div>
          <label className="block text-sm font-medium">Pose Name</label>
          <input type="text" value={poseName} onChange={(e)=>setPoseName(e.target.value)} className="w-full p-2 border rounded" placeholder="e.g., Uttanasana" />
        </div>

        <div>
          <label className="block text-sm font-medium">Pose Number (index within asana sequence)</label>
          <input type="number" min={1} value={poseNumber} onChange={(e)=>setPoseNumber(Number(e.target.value))} className="w-32 p-2 border rounded" />
        </div>

        <div>
          <label className="block text-sm font-medium">Pose Image (photo)</label>
          <input type="file" accept="image/*" onChange={(e)=>setFile(e.target.files?.[0] ?? null)} className="mt-2" />
        </div>

        <div className="flex gap-2">
          <button type="submit" className="px-4 py-2 bg-green-600 text-white rounded" disabled={saving}>{saving ? "Uploading..." : "Upload Pose"}</button>
          <button type="button" onClick={()=>{ setAsanaName(""); setPoseName(""); setPoseNumber(1); setFile(null); setResult(null); setError(null); }} className="px-4 py-2 bg-gray-100 rounded">Reset</button>
        </div>

        {result && <div className="p-3 rounded bg-green-50 text-green-700">Uploaded successfully: {JSON.stringify(result)}</div>}
        {error && <div className="p-3 rounded bg-red-50 text-red-700">Error: {String(error)}</div>}
      </form>

      <div className="mt-6 text-sm text-gray-500">Notes: The server must expose <code>/upload_pose</code> and <code>/compare_pose</code>. If the server is running on a different origin expose CORS or host this UI from the same origin.</div>
    </div>
  );
}
