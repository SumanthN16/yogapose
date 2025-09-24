import os
import cv2
import numpy as np
from flask import Flask, render_template, Response, request
from werkzeug.utils import secure_filename
import mediapipe as mp

# ------------------ Flask Setup ------------------
app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ------------------ MediaPipe Setup ------------------
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=False, min_detection_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# Global variable to store reference keypoints
reference_points = None

# ------------------ Helpers ------------------
def detect_pose_points(image):
    """
    Detect human pose and return a list of normalized keypoints [(x,y), ...]
    Normalized means 0–1 relative to image size.
    """
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    result = pose.process(rgb)
    if result.pose_landmarks:
        return [(lm.x, lm.y) for lm in result.pose_landmarks.landmark]
    return []

def draw_reference_skeleton(image, points):
    """Draw reference skeleton (optional for debugging)"""
    h, w = image.shape[:2]
    for p in points:
        cv2.circle(image, (int(p[0]*w), int(p[1]*h)), 4, (255,0,0), -1)
    return image

# ------------------ Routes ------------------
@app.route("/", methods=["GET", "POST"])
def index():
    """
    Upload reference pose image.
    Extract its pose keypoints and store them globally.
    """
    global reference_points
    ref_image = None

    if request.method == "POST":
        f = request.files["ref_image"]
        if f:
            filename = secure_filename(f.filename)
            upload_path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(upload_path)
            ref_image = filename

            # Extract keypoints from the uploaded image
            img = cv2.imread(upload_path)
            reference_points = detect_pose_points(img)
            print(f"[INFO] Reference pose set with {len(reference_points)} keypoints.")

    return render_template("index.html", ref_image=ref_image)

def generate_camera():
    """
    Stream camera frames with live joint feedback:
    - Green: correct joint
    - Red: incorrect joint
    - Yellow arrow: direction to move toward reference
    """
    global reference_points
    cap = cv2.VideoCapture(0)
    threshold_ratio = 0.05  # allowed distance ratio relative to image width

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        current_points = detect_pose_points(frame)

        if reference_points and current_points and len(reference_points) == len(current_points):
            h, w = frame.shape[:2]
            for ref, cur in zip(reference_points, current_points):
                ref_px = np.array([ref[0] * w, ref[1] * h])
                cur_px = np.array([cur[0] * w, cur[1] * h])
                dist = np.linalg.norm(ref_px - cur_px)

                if dist < threshold_ratio * w:
                    # ✅ Correct joint – Green
                    cv2.circle(frame, tuple(cur_px.astype(int)), 6, (0, 255, 0), -1)
                else:
                    # ❌ Incorrect joint – Red + Yellow arrow toward target
                    cv2.circle(frame, tuple(cur_px.astype(int)), 6, (0, 0, 255), -1)
                    cv2.arrowedLine(frame,
                                    tuple(cur_px.astype(int)),
                                    tuple(ref_px.astype(int)),
                                    (0, 255, 255), 2, tipLength=0.3)

        # Encode and yield frame
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route("/video_feed")
def video_feed():
    return Response(generate_camera(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# ------------------ Main ------------------
if __name__ == "__main__":
    app.run(debug=True)
