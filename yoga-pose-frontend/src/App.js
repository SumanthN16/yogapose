import React, { useCallback, useEffect, useRef, useState } from "react";

// Default export React component (single-file app)
// Tailwind is used for styling (no imports required in this environment)
// This component provides two pages: Compare (live camera vs reference JSON pose)
// and Add Pose (upload an image + metadata to the backend).

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
  const canvasRef = useRef(null);
  const [asanas, setAsanas] = useState([]); // array of {asana_name}
  const [selectedAsana, setSelectedAsana] = useState("");
  const [posesInAsana, setPosesInAsana] = useState([]); // from /asanas/:name
  const [selectedPoseNumber, setSelectedPoseNumber] = useState(1);
  const [selectedPose, setSelectedPose] = useState(null);
  const [tolerance, setTolerance] = useState(20); // percentage
  const [feedback, setFeedback] = useState(null);
  const [isComparing, setIsComparing] = useState(false);
  const [error, setError] = useState(null);
  const [continuousMode, setContinuousMode] = useState(false);
  // Start camera on mount
  useEffect(() => {
    startCamera();
    fetchAsanas();

    return () => {
      stopCamera();
    };
  }, []);

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
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

  async function fetchAsanas() {
    // Try to fetch a list of asanas. The backend provided earlier doesn't include a list endpoint,
    // so this call might fail. We attempt /asanas (expecting JSON list) and fall back to nothing.
    try {
      const resp = await fetch("http://127.0.0.1:5000/asanas");
      if (!resp.ok) throw new Error("no-asanas-endpoint");
      const data = await resp.json();
      // If server returns a list of names, use that. Otherwise, if server returned an object, adapt.
      if (Array.isArray(data)) {
        setAsanas(data);
        if (data.length) setSelectedAsana(data[0]);
      } else if (data.asanas && Array.isArray(data.asanas)) {
        setAsanas(data.asanas);
        if (data.asanas.length) setSelectedAsana(data.asanas[0]);
      } else {
        // unknown shape — ignore
        console.warn("/asanas returned unexpected shape", data);
      }
    } catch (e) {
      // Graceful fallback: allow user to type asana name manually
      console.warn("Could not fetch asana list:", e);
    }
  }

  // When asana changes, fetch its poses
  useEffect(() => {
    if (!selectedAsana) return;
    fetch(`http://127.0.0.1:5000/asanas/${encodeURIComponent(selectedAsana)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data && data.poses) {
          setPosesInAsana(data.poses);
          // Auto-select first pose if available
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

  const handleCompareOnce = useCallback(async () => {
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
    } catch (e) {
      console.error(e);
      setError(String(e));
    } finally {
      setIsComparing(false);
    }
  }, [selectedAsana, selectedPoseNumber, tolerance]);

  // Start continuous comparison when pose is selected
  useEffect(() => {
    if (selectedPose && continuousMode) {
      const interval = setInterval(() => {
        handleCompareOnce();
      }, 1500); // every 1.5 seconds
      return () => clearInterval(interval);
    }
  }, [selectedPose, continuousMode, tolerance, handleCompareOnce]);

  function captureFrame() {
    if (!videoRef.current) return null;
    const video = videoRef.current;
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 480;

    canvasRef.current.width = w;
    canvasRef.current.height = h;
    const ctx = canvasRef.current.getContext("2d");
    ctx.drawImage(video, 0, 0, w, h);
    return new Promise((resolve) => {
      canvasRef.current.toBlob((blob) => {
        resolve(blob);
      }, "image/jpeg", 0.9);
    });
  }

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white p-4 rounded-lg shadow">
          <h2 className="font-semibold mb-2">Live Camera</h2>
          <div className="border rounded overflow-hidden">
            <video ref={videoRef} className="w-full h-64 object-cover bg-black" playsInline />
          </div>
          <canvas ref={canvasRef} className="hidden" />
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

          <div>
            <label className="block text-sm font-medium mb-2">Tolerance: {tolerance}%</label>
            <input
              type="range"
              min="5"
              max="50"
              value={tolerance}
              onChange={(e) => setTolerance(Number(e.target.value))}
              className="w-full"
            />
            <div className="text-xs text-gray-500 mt-1">Adjust sensitivity for pose matching</div>
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          <button
            onClick={() => setContinuousMode(!continuousMode)}
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
