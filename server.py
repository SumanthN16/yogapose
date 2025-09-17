import json
import base64
import numpy as np
import cv2
import mediapipe as mp
import os
import time
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

POSE_IMAGE_DIR = 'static/ideal_poses'
if not os.path.exists(POSE_IMAGE_DIR):
    os.makedirs(POSE_IMAGE_DIR)

def load_ideal_poses():
    try:
        with open('ideal_poses.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

IDEAL_POSES = load_ideal_poses()
current_pose_name = ""

def calculate_angle(a, b, c):
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    if angle > 180.0:
        angle = 360 - angle
    return int(round(angle))

def extract_all_angles(landmarks):
    angles = {}

    left_shoulder = [landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].x, landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value].y]
    right_shoulder = [landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y]
    left_elbow = [landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value].x, landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value].y]
    right_elbow = [landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value].y]
    left_wrist = [landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value].x, landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value].y]
    right_wrist = [landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value].y]
    left_hip = [landmarks[mp_pose.PoseLandmark.LEFT_HIP.value].x, landmarks[mp_pose.PoseLandmark.LEFT_HIP.value].y]
    right_hip = [landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].y]
    left_knee = [landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value].x, landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value].y]
    right_knee = [landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].y]
    left_ankle = [landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value].x, landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value].y]
    right_ankle = [landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value].y]
    
    angles['left_elbow'] = calculate_angle(left_shoulder, left_elbow, left_wrist)
    angles['right_elbow'] = calculate_angle(right_shoulder, right_elbow, right_wrist)
    angles['left_shoulder'] = calculate_angle(left_hip, left_shoulder, left_elbow)
    angles['right_shoulder'] = calculate_angle(right_hip, right_shoulder, right_elbow)
    angles['left_hip'] = calculate_angle(left_shoulder, left_hip, left_knee)
    angles['right_hip'] = calculate_angle(right_shoulder, right_hip, right_knee)
    angles['left_knee'] = calculate_angle(left_hip, left_knee, left_ankle)
    angles['right_knee'] = calculate_angle(right_hip, right_knee, right_ankle)
    
    left_foot_index = [landmarks[mp_pose.PoseLandmark.LEFT_FOOT_INDEX.value].x, landmarks[mp_pose.PoseLandmark.LEFT_FOOT_INDEX.value].y]
    right_foot_index = [landmarks[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX.value].x, landmarks[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX.value].y]
    
    angles['left_ankle'] = calculate_angle(left_knee, left_ankle, left_foot_index)
    angles['right_ankle'] = calculate_angle(right_knee, right_ankle, right_foot_index)

    mid_shoulder = [(left_shoulder[0] + right_shoulder[0])/2, (left_shoulder[1] + right_shoulder[1])/2]
    mid_hip = [(left_hip[0] + right_hip[0])/2, (left_hip[1] + right_hip[1])/2]
    angles['spine'] = calculate_angle(mid_shoulder, mid_hip, [mid_hip[0], mid_hip[1] + 1])
    
    return angles

def get_feedback(current_angles, ideal_angles):
    feedback = {}
    for joint, ideal_angle in ideal_angles.items():
        if joint in current_angles:
            current_angle = current_angles[joint]
            deviation = abs(current_angle - ideal_angle)
            tolerance = 0.20 * ideal_angle
            if deviation > tolerance:
                if current_angle < ideal_angle:
                    feedback[joint] = f"Adjust your {joint.replace('_', ' ')}: Angle is too small. Try to extend more."
                else:
                    feedback[joint] = f"Adjust your {joint.replace('_', ' ')}: Angle is too wide. Try to bend more."
    return feedback

@socketio.on('video_stream')
def handle_video_stream(data):
    global current_pose_name
    
    image_data = base64.b64decode(data.split(',')[1])
    nparr = np.frombuffer(image_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Corrected: Removed the timestamp argument
    results = pose.process(image=frame_rgb)

    current_angles = {}
    feedback_messages = {}

    if results.pose_landmarks:
        mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
        current_angles = extract_all_angles(results.pose_landmarks.landmark)

        if current_pose_name in IDEAL_POSES:
            feedback_messages = get_feedback(current_angles, IDEAL_POSES[current_pose_name])
            
    retval, buffer = cv2.imencode('.jpg', frame)
    processed_frame_b64 = base64.b64encode(buffer).decode('utf-8')
    
    emit('processed_video', {'frame': processed_frame_b64, 'feedback': feedback_messages, 'current_pose_name': current_pose_name})

@socketio.on('add_pose')
def handle_add_pose(data):
    try:
        image_data = base64.b64decode(data['image'].split(',')[1])
        pose_name = data['name'].replace(" ", "_").lower()
        
        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(image=frame_rgb)
        
        if results.pose_landmarks:
            new_pose_angles = extract_all_angles(results.pose_landmarks.landmark)
            
            image_path = os.path.join(POSE_IMAGE_DIR, f"{pose_name}.jpg")
            cv2.imwrite(image_path, frame)

            IDEAL_POSES[pose_name] = new_pose_angles
            with open('ideal_poses.json', 'w') as f:
                json.dump(IDEAL_POSES, f, indent=4)
            
            print(f"Successfully added pose: {pose_name}")
            emit('pose_added', {'success': True, 'pose_name': pose_name})
            emit('pose_list', {'poses': list(IDEAL_POSES.keys())})
        else:
            emit('pose_added', {'success': False, 'message': 'Could not detect pose in the image.'})
    
    except Exception as e:
        print(f"Error adding pose: {e}")
        emit('pose_added', {'success': False, 'message': f'Server error: {str(e)}'})

@socketio.on('select_pose')
def handle_select_pose(data):
    global current_pose_name
    selected_pose = data['pose_name']
    if selected_pose in IDEAL_POSES:
        current_pose_name = selected_pose
        print(f"Current pose selected: {current_pose_name}")
        ideal_pose_url = f"/{POSE_IMAGE_DIR}/{selected_pose}.jpg"
        emit('set_ideal_pose', {'ideal_pose_url': ideal_pose_url})

@socketio.on('connect')
def on_connect():
    global current_pose_name
    poses = list(IDEAL_POSES.keys())
    if poses:
        current_pose_name = poses[0]
        ideal_pose_url = f"/{POSE_IMAGE_DIR}/{current_pose_name}.jpg"
        emit('pose_list', {'poses': poses, 'ideal_pose_url': ideal_pose_url})
    else:
        emit('pose_list', {'poses': []})

@app.route('/')
def index():
    return render_template_string(open('index.html').read())

if __name__ == '__main__':
    socketio.run(app, debug=True)