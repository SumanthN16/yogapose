import cv2
import math
import json
from collections import OrderedDict

# --- paths to OpenPose COCO model files ---
protoFile = "pose_deploy_linevec.prototxt"
weightsFile = "pose_iter_440000.caffemodel"

# mapping COCO parts
COCO_BODY_PARTS = {
    0: "Nose",
    1: "Neck",
    2: "RShoulder",
    3: "RElbow",
    4: "RWrist",
    5: "LShoulder",
    6: "LElbow",
    7: "LWrist",
    8: "RHip",
    9: "RKnee",
    10: "RAnkle",
    11: "LHip",
    12: "LKnee",
    13: "LAnkle",
    14: "REye",
    15: "LEye",
    16: "REar",
    17: "LEar"
}

# Use a set of 15 joints (you can adjust) — similar to before
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
    ("MidHip", 1)  # placeholder; to compute later
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
    """Compute angle at v between vectors a→v and b→v (in degrees)."""
    ax, ay = a[0] - v[0], a[1] - v[1]
    bx, by = b[0] - v[0], b[1] - v[1]
    dot = ax*bx + ay*by
    na = math.hypot(ax, ay)
    nb = math.hypot(bx, by)
    if na == 0 or nb == 0:
        return None
    cosang = dot / (na * nb)
    # clamp for numeric stability
    cosang = max(-1.0, min(1.0, cosang))
    ang = math.degrees(math.acos(cosang))
    return ang

def get_keypoint_from_map(probMap, threshold):
    """Return (x, y, confidence) in the probMap if above threshold, else None."""
    minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(probMap)
    if maxVal > threshold:
        return maxLoc[0], maxLoc[1], maxVal
    return None

def process_image(image_path, output_json_path, output_annotated_path=None):
    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"Could not load image {image_path}")

    h_img, w_img = img.shape[:2]

    net = cv2.dnn.readNetFromCaffe(protoFile, weightsFile)
    # optionally: enable GPU if available
    # net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
    # net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

    inWidth = 368
    inHeight = 368
    inpBlob = cv2.dnn.blobFromImage(img, 1.0/255, (inWidth, inHeight),
                                    (0,0,0), swapRB=False, crop=False)
    net.setInput(inpBlob)
    output = net.forward()  # shape: (1, nPoints, H_out, W_out)
    nPoints = output.shape[1]

    points = {}
    for name, idx in JOINTS_15.items():
        if idx < nPoints:
            probMap = output[0, idx, :, :]
            kp = get_keypoint_from_map(probMap, threshold)
            if kp:
                x = int((w_img * kp[0]) / probMap.shape[1])
                y = int((h_img * kp[1]) / probMap.shape[0])
                conf = kp[2]
                points[name] = (x, y, conf)
            else:
                points[name] = None
        else:
            points[name] = None

    # compute MidHip as average of RHip and LHip if available
    rh = points.get("RHip")
    lh = points.get("LHip")
    if rh and lh and rh is not None and lh is not None:
        mx = int((rh[0] + lh[0]) / 2)
        my = int((rh[1] + lh[1]) / 2)
        mc = (rh[2] + lh[2]) / 2
        points["MidHip"] = (mx, my, mc)
    else:
        points["MidHip"] = None

    # annotate image (optional)
    vis = img.copy()
    for pair in POSE_PAIRS:
        a = points.get(pair[0])
        b = points.get(pair[1])
        if a and b and a is not None and b is not None:
            cv2.line(vis, (a[0], a[1]), (b[0], b[1]), (0,255,0), 2)
    for name, pt in points.items():
        if pt and pt is not None:
            cv2.circle(vis, (pt[0], pt[1]), 4, (0,0,255), -1)
            cv2.putText(vis, name, (pt[0] + 5, pt[1] + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)

    # compute angles
    angles = {}
    for ang_name, (pa, pv, pb) in ANGLE_JOINTS.items():
        A = points.get(pa)
        V = points.get(pv)
        B = points.get(pb)
        if A and V and B and A is not None and V is not None and B is not None:
            ang = angle_between_points((A[0], A[1]), (V[0], V[1]), (B[0], B[1]))
            if ang is not None:
                angles[ang_name] = round(ang, 1)
                # optionally draw angle text
                cv2.putText(vis, f"{angles[ang_name]}°", (V[0] + 5, V[1] - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,0), 1)
            else:
                angles[ang_name] = None
        else:
            angles[ang_name] = None

    # assemble JSON data
    data = {
        "image_path": image_path,
        "joints": {},
        "angles": angles
    }
    for name, pt in points.items():
        if pt and pt is not None:
            data["joints"][name] = {
                "x": int(pt[0]), "y": int(pt[1]), "conf": float(pt[2])
            }
        else:
            data["joints"][name] = None

    # write JSON
    with open(output_json_path, "w") as f:
        json.dump(data, f, indent=2)

    # save annotated image if needed
    if output_annotated_path:
        cv2.imwrite(output_annotated_path, vis)

    return data

if __name__ == "__main__":
    # example usage
    img_path = "Namaskarasana.png"
    out_json = "output_angles.json"
    out_vis = "annotated.jpg"
    result = process_image(img_path, out_json, out_vis)
    print("Result:", result)
    print(f"Saved JSON to {out_json}, annotated to {out_vis}")
