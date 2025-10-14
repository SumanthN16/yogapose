import os
import cv2
import numpy as np
from flask import Flask, render_template, Response, request, jsonify
from werkzeug.utils import secure_filename
import mediapipe as mp
import threading
import json

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- Globals ----------
latest_feedback = ""      # global feedback text
feedback_lock = threading.Lock()

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=False,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.6,
                    min_tracking_confidence=0.6)
mp_drawing = mp.solutions.drawing_utils

# global reference data
reference_angles = None
reference_joints = None

def calc_angle(a, b, c):
    """Compute angle in degrees at point b using 2D points a, b, c."""
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    ba = a - b
    bc = c - b
    # avoid division by zero
    denom = (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    cosine = np.dot(ba, bc) / denom
    cosine = np.clip(cosine, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))

def get_pose_landmarks(image):
    """Return list of (x, y, visibility) for 33 landmarks or empty if none."""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    res = pose.process(rgb)
    if not res.pose_landmarks:
        return []
    return [(lm.x, lm.y, lm.visibility) for lm in res.pose_landmarks.landmark]

def compute_key_angles(pts):
    """From 33 pts, compute dictionary of selected joint angles (consistent key names)."""
    # Need at least full 33 pts
    if len(pts) < 33:
        return {}
    # Working only x,y parts
    p = [(x, y) for x, y, _ in pts]
    def g(idx): return p[idx]
    # Example mapping (you can adjust or extend)
    return {
        "left_elbow":    calc_angle(g(13), g(11), g(23)),  # maybe adjust this triplet
        "right_elbow":   calc_angle(g(14), g(12), g(24)),
        "left_knee":     calc_angle(g(25), g(23), g(11)),
        "right_knee":    calc_angle(g(26), g(24), g(12)),
        "left_shoulder": calc_angle(g(11), g(13), g(15)),
        "right_shoulder":calc_angle(g(12), g(14), g(16)),
        # you can add more, e.g. hip, back, etc.
    }

@app.route("/", methods=["GET", "POST"])
def index():
    global reference_angles, reference_joints
    ref_image = None
    if request.method == "POST":
        f = request.files["ref_image"]
        filename = secure_filename(f.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        f.save(path)

        # load image and compute reference pose
        img = cv2.imread(path)
        pts = get_pose_landmarks(img)
        if pts:
            reference_joints = pts
            reference_angles = compute_key_angles(pts)
            ref_image = filename
            # Optionally, save the reference JSON for reuse
            ref_json = {
                "image_path": filename,
                "joints": pts,
                "angles": reference_angles
            }
            # You can save to file
            with open(os.path.join(UPLOAD_FOLDER, filename + "_ref.json"), "w") as fjson:
                json.dump(ref_json, fjson)
    return render_template("index.html", ref_image=ref_image)

def generate_camera():
    global latest_feedback, reference_angles
    cap = cv2.VideoCapture(0)
    tolerance = 15.0  # degrees

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        pts = get_pose_landmarks(frame)

        feedback_list = []
        color_map = {}  # angle_name -> color

        if not pts:
            feedback_list.append("Cannot detect full body")
        else:
            # Check visibility
            vis_count = sum(1 for _, _, v in pts if v > 0.5)
            if vis_count < 15:
                feedback_list.append("Body not fully visible")

            if reference_angles:
                cur_angles = compute_key_angles(pts)
                for key, ref_ang in reference_angles.items():
                    if key in cur_angles:
                        live_ang = cur_angles[key]
                        diff = live_ang - ref_ang
                        if abs(diff) > tolerance:
                            feedback_list.append(f"Adjust {key}")
                            color_map[key] = (0, 0, 255)
                        else:
                            color_map[key] = (0, 255, 0)

        # Draw skeleton on frame
        if pts:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                    connection_drawing_spec=mp_drawing.DrawingSpec(color=(0,255,0), thickness=2)
                )

        # Overlay feedback colored joints
        h, w = frame.shape[:2]
        if pts:
            p2d = [(int(x * w), int(y * h)) for x, y, _ in pts]
            for key, col in color_map.items():
                # Map angle_name to a landmark index
                # e.g. left_elbow -> index 13; right_elbow -> 14, etc.
                idx = None
                if key == "left_elbow":
                    idx = 13
                elif key == "right_elbow":
                    idx = 14
                elif key == "left_knee":
                    idx = 25
                elif key == "right_knee":
                    idx = 26
                elif key == "left_shoulder":
                    idx = 11
                elif key == "right_shoulder":
                    idx = 12
                if idx is not None and idx < len(p2d):
                    cv2.circle(frame, p2d[idx], 8, col, -1)

        with feedback_lock:
            if feedback_list:
                latest_feedback = "; ".join(feedback_list)
            else:
                latest_feedback = "Good posture"

        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route("/video_feed")
def video_feed():
    return Response(generate_camera(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/feedback_text")
def feedback_text():
    with feedback_lock:
        return jsonify({"feedback": latest_feedback})

if __name__ == "__main__":
    app.run(debug=True)
