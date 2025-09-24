import os
import cv2
import numpy as np
from flask import Flask, render_template, Response, request, jsonify
from werkzeug.utils import secure_filename
import mediapipe as mp
import threading

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- Globals ----------
latest_feedback = ""      # ✅ Global feedback text
feedback_lock = threading.Lock()

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=False,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.6,
                    min_tracking_confidence=0.6)
mp_drawing = mp.solutions.drawing_utils

# global reference
reference_angles = None
reference_points = None

def calc_angle(a,b,c):
    """Angle at b (in degrees) using 3 normalized points"""
    a,b,c = np.array(a), np.array(b), np.array(c)
    ba = a - b
    bc = c - b
    cosine = np.dot(ba,bc) / (np.linalg.norm(ba)*np.linalg.norm(bc) + 1e-6)
    return np.degrees(np.arccos(np.clip(cosine,-1.0,1.0)))

def get_pose_landmarks(image):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    res = pose.process(rgb)
    if not res.pose_landmarks: return []
    return [(lm.x, lm.y, lm.visibility) for lm in res.pose_landmarks.landmark]

def compute_key_angles(pts):
    """Return a dict of key joint angles for pose comparison."""
    if len(pts) < 33: return {}
    # Use only x,y
    p = [(x,y) for x,y,_ in pts]
    def g(idx): return p[idx]
    return {
        "left_elbow":  calc_angle(g(11), g(13), g(15)),
        "right_elbow": calc_angle(g(12), g(14), g(16)),
        "left_knee":   calc_angle(g(23), g(25), g(27)),
        "right_knee":  calc_angle(g(24), g(26), g(28)),
        "left_shldr":  calc_angle(g(13), g(11), g(23)),
        "right_shldr": calc_angle(g(14), g(12), g(24)),
        "hip":         calc_angle(g(11), g(23), g(25))
    }

def body_ratio(pts):
    """Simple height measure to normalize distances."""
    if len(pts) < 33: return 1
    return np.linalg.norm(np.array(pts[11][:2]) - np.array(pts[27][:2]))

@app.route("/", methods=["GET", "POST"])
def index():
    global reference_angles, reference_points
    ref_image = None
    if request.method == "POST":
        f = request.files["ref_image"]
        filename = secure_filename(f.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        f.save(path)

        img = cv2.imread(path)
        pts = get_pose_landmarks(img)
        if pts:
            reference_points = pts
            reference_angles = compute_key_angles(pts)
            ref_image = filename
    return render_template("index.html", ref_image=ref_image)

def generate_camera():
    global latest_feedback
    cap = cv2.VideoCapture(0)
    tolerance = 15      # degrees
    # feedback_text = ""

    while True:
        ret, frame = cap.read()
        if not ret: break
        frame = cv2.flip(frame,1)
        pts = get_pose_landmarks(frame)

        feedback = []
        color_map = {}

        if not pts:
            feedback.append("Full body not detected – step back")
        else:
            # check number of bodies (mediapipe gives only best detection,
            # but we can use segmentation mask area to estimate)
            # → simplified check: if key landmarks are low visibility
            visible = [v for _,_,v in pts if v>0.5]
            if len(visible)<15:
                feedback.append("Full body not fully visible")

            if reference_angles:
                cur_angles = compute_key_angles(pts)
                for k,ref_angle in reference_angles.items():
                    if k in cur_angles:
                        if abs(cur_angles[k]-ref_angle) > tolerance:
                            feedback.append(f"Adjust {k.replace('_',' ')}")
                            color_map[k] = (0,0,255)  # red
                        else:
                            color_map[k] = (0,255,0)  # green
        
        # Draw skeleton
        # ---------- Drawing section ----------
        if pts:
            # Use the raw mediapipe output to draw skeleton
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=2),
                    connection_drawing_spec=mp_drawing.DrawingSpec(color=(0,255,0), thickness=2))
        # Custom joint coloring
        h,w = frame.shape[:2]
        if pts:
            p2d = [(int(x*w), int(y*h)) for x,y,_ in pts]
            for name,col in color_map.items():
                if "elbow" in name:
                    idx = 13 if "left" in name else 14
                elif "knee" in name:
                    idx = 25 if "left" in name else 26
                elif "shldr" in name:
                    idx = 11 if "left" in name else 12
                elif "hip" in name:
                    idx = 23
                else: continue
                cv2.circle(frame, p2d[idx], 6, col, -1)
        with feedback_lock:
            latest_feedback = ", ".join(feedback) if feedback else "Good posture!"
                    
        # feedback_text = ", ".join(feedback) if feedback else "Good posture!"
        # cv2.putText(frame, feedback_text, (10,30),
        #             cv2.FONT_HERSHEY_SIMPLEX, 0.7,(255,255,0),2)

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
