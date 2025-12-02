import os
import cv2
import numpy as np
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import mediapipe as mp
import json
import threading

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:3000"])
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database setup
def init_db():
    with sqlite3.connect("poses.db") as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS asanas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS poses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asana_name TEXT,
            pose_name TEXT,
            pose_number INTEGER,
            image_path TEXT,
            joints TEXT,
            angles TEXT,
            FOREIGN KEY(asana_name) REFERENCES asanas(name)
        )""")
        con.commit()
init_db()

# Mediapipe setup
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=True,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.6)

def get_pose_landmarks(image):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    res = pose.process(rgb)
    if not res.pose_landmarks:
        return []
    return [(lm.x, lm.y, lm.visibility) for lm in res.pose_landmarks.landmark]

def compute_key_angles(pts):
    if len(pts) < 33:
        return {}
    p = [(x, y) for x, y, _ in pts]
    def g(idx): return p[idx]
    return {
        "left_elbow": calc_angle(g(11), g(13), g(15)),
        "right_elbow": calc_angle(g(12), g(14), g(16)),
        "left_knee": calc_angle(g(23), g(25), g(27)),
        "right_knee": calc_angle(g(24), g(26), g(28)),
        "left_shoulder": calc_angle(g(13), g(11), g(23)),
        "right_shoulder": calc_angle(g(14), g(12), g(24)),
        "hip": calc_angle(g(11), g(23), g(25))
    }

def calc_angle(a, b, c):
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    ba = a - b
    bc = c - b
    denom = (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    cosine = np.dot(ba, bc) / denom
    cosine = np.clip(cosine, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))

@app.route("/asanas", methods=["GET"])
def get_asanas():
    with sqlite3.connect("poses.db") as con:
        cur = con.cursor()
        cur.execute("SELECT name FROM asanas")
        asanas = [row[0] for row in cur.fetchall()]
    return jsonify(asanas)

@app.route("/asanas/<name>", methods=["GET"])
def get_asana_poses(name):
    with sqlite3.connect("poses.db") as con:
        cur = con.cursor()
        cur.execute("SELECT id, pose_name, pose_number, image_path FROM poses WHERE asana_name = ?", (name,))
        poses = []
        for row in cur.fetchall():
            poses.append({
                "pose_id": row[0],
                "pose_name": row[1],
                "pose_number": row[2],
                "image_url": f"http://127.0.0.1:5000/uploads/{row[3]}"
            })
    return jsonify({"poses": poses})

@app.route("/upload_pose", methods=["POST"])
def upload_pose():
    asana_name = request.form.get("asana_name")
    pose_name = request.form.get("pose_name")
    pose_number = int(request.form.get("pose_number"))
    file = request.files.get("image")

    if not all([asana_name, pose_name, file]):
        return jsonify({"error": "Missing required fields"}), 400

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    img = cv2.imread(path)
    pts = get_pose_landmarks(img)
    if not pts:
        return jsonify({"error": "Could not detect pose in image"}), 400

    angles = compute_key_angles(pts)

    with sqlite3.connect("poses.db") as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO asanas (name) VALUES (?)", (asana_name,))
        cur.execute("INSERT INTO poses (asana_name, pose_name, pose_number, image_path, joints, angles) VALUES (?, ?, ?, ?, ?, ?)",
                    (asana_name, pose_name, pose_number, filename, json.dumps(pts), json.dumps(angles)))
        con.commit()

    return jsonify({"message": "Pose uploaded successfully"})

@app.route("/compare_pose", methods=["POST"])
def compare_pose():
    try:
        new_image = request.files.get("new_image")
        asana_name = request.form.get("asana_name")
        reference_pose_number = int(request.form.get("reference_pose_number"))
        tolerance_percent = float(request.form.get("tolerance", 20.0)) / 100.0  # default 20%

        if not all([new_image, asana_name]):
            return jsonify({"error": "Missing required fields"}), 400

        # Save temp image
        temp_path = os.path.join(UPLOAD_FOLDER, "temp.jpg")
        new_image.save(temp_path)

        img = cv2.imread(temp_path)
        if img is None:
            return jsonify({"error": "Invalid image file"}), 400

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        res = pose.process(rgb)

        if not res.pose_landmarks:
            return jsonify({"error": "Could not detect pose in new image"}), 400

        new_pts = [(lm.x, lm.y, lm.visibility) for lm in res.pose_landmarks.landmark]

        # Check full body visibility: at least 60% of landmarks visible (>0.5)
        visible_count = sum(1 for _, _, v in new_pts if v > 0.5)
        if visible_count < 0.6 * 33:  # 33 landmarks
            return jsonify({"error": "Full body not detected"}), 400

        new_angles = compute_key_angles(new_pts)

        # Get reference
        with sqlite3.connect("poses.db") as con:
            cur = con.cursor()
            cur.execute("SELECT pose_name, joints, angles FROM poses WHERE asana_name = ? AND pose_number = ?",
                        (asana_name, reference_pose_number))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Reference pose not found"}), 404

            ref_pose_name, ref_joints_str, ref_angles_str = row
            ref_pts = json.loads(ref_joints_str)
            ref_angles = json.loads(ref_angles_str)

        adjustments = []
        for joint, ref_ang in ref_angles.items():
            if joint in new_angles:
                new_ang = new_angles[joint]
                diff = new_ang - ref_ang
                tolerance_deg = tolerance_percent * abs(ref_ang)  # percentage of reference angle
                if abs(diff) > tolerance_deg:
                    adjustments.append({
                        "joint_name": joint,
                        "adjustment": "straighten" if diff > 0 else "bend",
                        "original_angle": ref_ang,
                        "new_angle": new_ang,
                        "difference": diff
                    })
        # LIVE JOINT FEEDBACK (coordinates + correctness)
        live_joint_feedback = []
        h, w, _ = img.shape

        # Tolerance in degrees based on your % logic
        tolerance_degrees = {
            j: tolerance_percent * abs(ref_angles[j])
            for j in ref_angles
        }

        # Mapping your angle names → Mediapipe indexes
        JOINT_LANDMARK_MAP = {
            "left_elbow": mp_pose.PoseLandmark.LEFT_ELBOW,
            "right_elbow": mp_pose.PoseLandmark.RIGHT_ELBOW,
            "left_knee": mp_pose.PoseLandmark.LEFT_KNEE,
            "right_knee": mp_pose.PoseLandmark.RIGHT_KNEE,
            "left_shoulder": mp_pose.PoseLandmark.LEFT_SHOULDER,
            "right_shoulder": mp_pose.PoseLandmark.RIGHT_SHOULDER,
            "hip": mp_pose.PoseLandmark.LEFT_HIP,  # choose left hip for the hip angle
        }

        for joint_name, ref_angle in ref_angles.items():
            if joint_name not in new_angles:
                continue  # landmark not available

            new_angle = new_angles[joint_name]
            lm = JOINT_LANDMARK_MAP.get(joint_name)
            if lm is None:
                continue

            lx = res.pose_landmarks.landmark[lm].x * w
            ly = res.pose_landmarks.landmark[lm].y * h

            is_correct = abs(new_angle - ref_angle) <= tolerance_degrees[joint_name]

            live_joint_feedback.append({
                "joint_name": joint_name,
                "x": float(lx),
                "y": float(ly),
                "is_correct": is_correct
            })

        # -----------------------------
        # EXTRA FEATURES: Skeleton + Accuracy + Audio Feedback
        # -----------------------------

        # 1. Skeleton lines (connections from Mediapipe Pose)
        POSE_CONNECTIONS = [
            (11, 13), (13, 15),   # Left Arm
            (12, 14), (14, 16),   # Right Arm
            (11, 12),             # Shoulders
            (23, 24),             # Hips
            (11, 23), (12, 24),   # Torso sides
            (23, 25), (25, 27),   # Left Leg
            (24, 26), (26, 28)    # Right Leg
        ]

        h, w, _ = img.shape

        skeleton_lines = []
        for a, b in POSE_CONNECTIONS:
            ax = new_pts[a][0] * w
            ay = new_pts[a][1] * h
            bx = new_pts[b][0] * w
            by = new_pts[b][1] * h
            skeleton_lines.append({
                "x1": float(ax), "y1": float(ay),
                "x2": float(bx), "y2": float(by)
            })

        # 2. Percentage Accuracy Calculation
        total_joints = 0
        correct_joints = 0

        for joint, ref_ang in ref_angles.items():
            if joint in new_angles:
                total_joints += 1
                new_ang = new_angles[joint]
                diff = abs(new_ang - ref_ang)
                tolerance_deg = tolerance_percent * abs(ref_ang)

                if diff <= tolerance_deg:
                    correct_joints += 1

        pose_accuracy = 0
        if total_joints > 0:
            pose_accuracy = round((correct_joints / total_joints) * 100, 2)

        # 3. Audio Feedback (Correct / Wrong)
        audio_feedback = "correct" if pose_accuracy >= 80 else "wrong"

        # Add to response
        extra_feedback = {
            "skeleton": skeleton_lines,
            "pose_accuracy": pose_accuracy,
            "audio_feedback": audio_feedback
        }

        return jsonify({
            "reference_pose": {
                "pose_name": ref_pose_name,
                "pose_number": reference_pose_number
            },
            "adjustments_needed": adjustments,
            "live_feedback": live_joint_feedback,
            "skeleton": skeleton_lines,
            "pose_accuracy": pose_accuracy,
            "audio_feedback": audio_feedback,
            "extra_feedback": extra_feedback
        })
    except Exception as e:
        app.logger.error(f"Error in compare_pose: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/uploads/<filename>")
def get_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
