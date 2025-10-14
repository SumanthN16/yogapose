import cv2
import math
import json
from collections import OrderedDict

# --- MODEL PATHS (set these) ---
protoFile = "pose_deploy_linevec.prototxt"
weightsFile = "pose_iter_440000.caffemodel"

# Joint / angle definitions (same as before)
JOINTS_15 = OrderedDict([
    ("Nose", 0),
    ("Neck", 1),
    ("RShoulder", 2),
    ("RElbow", 3),
    ("RWrist", 4),
    ("LShoulder", 5),
    ("LElbow", 6),
    ("LWrist", 7),
    ("RHip", 8),
    ("RKnee", 9),
    ("RAnkle", 10),
    ("LHip", 11),
    ("LKnee", 12),
    ("LAnkle", 13),
    ("MidHip", 1)
])
POSE_PAIRS = [
    ("Neck", "RShoulder"), ("Neck", "LShoulder"),
    ("RShoulder", "RElbow"), ("RElbow", "RWrist"),
    ("LShoulder", "LElbow"), ("LElbow", "LWrist"),
    ("Neck", "RHip"), ("Neck", "LHip"),
    ("RHip", "RKnee"), ("RKnee", "RAnkle"),
    ("LHip", "LKnee"), ("LKnee", "LAnkle")
]
ANGLE_JOINTS = {
    "R_Elbow": ("RShoulder", "RElbow", "RWrist"),
    "L_Elbow": ("LShoulder", "LElbow", "LWrist"),
    "R_Shoulder": ("Neck", "RShoulder", "RElbow"),
    "L_Shoulder": ("Neck", "LShoulder", "LElbow"),
    "R_Knee": ("RHip", "RKnee", "RAnkle"),
    "L_Knee": ("LHip", "LKnee", "LAnkle"),
    "R_Hip": ("Neck", "RHip", "RKnee"),
    "L_Hip": ("Neck", "LHip", "LKnee")
}
threshold = 0.1  # confidence threshold

def angle_between_points(a, v, b):
    ax, ay = a[0] - v[0], a[1] - v[1]
    bx, by = b[0] - v[0], b[1] - v[1]
    dot = ax*bx + ay*by
    na = math.hypot(ax, ay)
    nb = math.hypot(bx, by)
    if na == 0 or nb == 0:
        return None
    cosang = dot / (na * nb)
    cosang = max(-1.0, min(1.0, cosang))
    return math.degrees(math.acos(cosang))

def get_keypoint_from_map(probMap, thresh):
    minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(probMap)
    if maxVal > thresh:
        return maxLoc[0], maxLoc[1], maxVal
    return None

def compute_pose_and_angles(img, net):
    h, w = img.shape[:2]
    inW, inH = 368, 368
    blob = cv2.dnn.blobFromImage(img, 1.0/255, (inW, inH), (0,0,0), swapRB=False, crop=False)
    net.setInput(blob)
    output = net.forward()
    nPoints = output.shape[1]

    points = {}
    for name, idx in JOINTS_15.items():
        if idx < nPoints:
            probMap = output[0, idx, :, :]
            kp = get_keypoint_from_map(probMap, threshold)
            if kp:
                x = int((w * kp[0]) / probMap.shape[1])
                y = int((h * kp[1]) / probMap.shape[0])
                conf = kp[2]
                points[name] = (x, y, conf)
            else:
                points[name] = None
        else:
            points[name] = None

    # compute MidHip
    rh = points.get("RHip")
    lh = points.get("LHip")
    if rh and lh and rh is not None and lh is not None:
        mx = int((rh[0] + lh[0]) / 2)
        my = int((rh[1] + lh[1]) / 2)
        mc = (rh[2] + lh[2]) / 2
        points["MidHip"] = (mx, my, mc)
    else:
        points["MidHip"] = None

    angles = {}
    for aname, (pa, pv, pb) in ANGLE_JOINTS.items():
        A = points.get(pa)
        V = points.get(pv)
        B = points.get(pb)
        if A and V and B and A is not None and V is not None and B is not None:
            ang = angle_between_points((A[0], A[1]), (V[0], V[1]), (B[0], B[1]))
            if ang is not None:
                angles[aname] = round(ang, 1)
            else:
                angles[aname] = None
        else:
            angles[aname] = None

    return points, angles

def load_template(template_json_path):
    with open(template_json_path, "r") as f:
        data = json.load(f)
    return data.get("angles", {})

def compare_feedback(template_angles, live_angles, tolerance=15.0):
    feedback = {}
    for aname, t_ang in template_angles.items():
        l_ang = live_angles.get(aname)
        if t_ang is None or l_ang is None:
            feedback[aname] = (None, None)
        else:
            diff = l_ang - t_ang
            instr = None
            if abs(diff) <= tolerance:
                instr = "OK"
            else:
                if diff > 0:
                    instr = f"Reduce by {abs(diff):.1f}°"
                else:
                    instr = f"Raise / extend by {abs(diff):.1f}°"
            feedback[aname] = (diff, instr)
    return feedback

def overlay_feedback(img, points, feedback):
    vis = img.copy()
    for (a, b) in POSE_PAIRS:
        pa = points.get(a)
        pb = points.get(b)
        if pa and pb and pa is not None and pb is not None:
            cv2.line(vis, (pa[0], pa[1]), (pb[0], pb[1]), (0,255,0), 2)
    for name, pt in points.items():
        if pt and pt is not None:
            cv2.circle(vis, (pt[0], pt[1]), 4, (0,0,255), -1)
            cv2.putText(vis, name, (pt[0]+5, pt[1]+5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)

    for aname, (diff, instr) in feedback.items():
        if instr:
            trip = ANGLE_JOINTS.get(aname)
            if trip:
                vname = trip[1]
                vpt = points.get(vname)
                if vpt and vpt is not None:
                    color = (0,255,0) if instr == "OK" else (0,0,255)
                    cv2.putText(vis, instr, (vpt[0]+10, vpt[1]-10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return vis

def run_live_comparison(template_json_path):
    net = cv2.dnn.readNetFromCaffe(protoFile, weightsFile)
    template_angles = load_template(template_json_path)
    print("Template angles:", template_angles)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open webcam")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        points, live_angles = compute_pose_and_angles(frame, net)
        feedback = compare_feedback(template_angles, live_angles, tolerance=30.0)
        vis = overlay_feedback(frame, points, feedback)

        y0 = 20
        for aname, ang in live_angles.items():
            if ang is not None:
                cv2.putText(vis, f"{aname}: {ang}°", (10, y0),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,0), 1)
                y0 += 20

        cv2.imshow("Pose Feedback", vis)
        key = cv2.waitKey(1)
        if key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    template_json = "output_angles.json"  # set your template JSON path here
    run_live_comparison(template_json)
