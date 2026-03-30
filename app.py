from flask import Flask, request, jsonify
import mysql.connector
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity, verify_jwt_in_request
from flask_bcrypt import Bcrypt
import uuid
import os
import cv2
import numpy as np
import math
from ultralytics import YOLO
import easyocr
import io
from flask import send_from_directory
import base64
import traceback
import requests  
import tempfile # For video processing

# Optional: detect whether PaddleOCR package is installed.
reader_paddle = None
paddle_available = False
import importlib.util
if importlib.util.find_spec('paddleocr') is not None:
    paddle_available = True
    print("PaddleOCR package is installed (not imported). Set ENABLE_PADDLEOCR=1 to enable runtime use.")
else:
    print("PaddleOCR package not installed; falling back to EasyOCR.")
from audit.schema import canonical_violation_payload
from audit.hasher import hash_violation
from datetime import datetime

# initialize flask app
app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'secretig'  
jwt = JWTManager(app)
bcrypt = Bcrypt(app)

print("Loading ML models and OCR readers...")
try:
    HELMET_MODEL_PATH = os.environ.get('HELMET_MODEL_PATH', 'Weights/best.pt')
    PLATE_MODEL_PATH = os.environ.get('PLATE_MODEL_PATH', 'Weights/license_plate_detector.pt')
    helmet_model = YOLO(HELMET_MODEL_PATH)
    raw_names = getattr(helmet_model, 'names', [])
    if isinstance(raw_names, dict):
        helmet_classNames = list(raw_names.values())
    else:
        helmet_classNames = list(raw_names or [])
    
    generic_keywords = {'person', 'car', 'motorcycle', 'truck', 'bicycle'}
    lower_names = set([n.lower() for n in helmet_classNames if isinstance(n, str)])
    if lower_names & generic_keywords:
        bak_path = HELMET_MODEL_PATH + '.bak'
        if os.path.exists(bak_path):
            print(f"Loaded model at {HELMET_MODEL_PATH} looks generic. Falling back to {bak_path}")
            fallback_path = bak_path
            if not fallback_path.endswith('.pt'):
                fallback_path = bak_path + '.pt'
                try:
                    import shutil
                    shutil.copyfile(bak_path, fallback_path)
                except Exception as e:
                    pass
            helmet_model = YOLO(fallback_path)
            raw_names = getattr(helmet_model, 'names', [])
            if isinstance(raw_names, dict):
                helmet_classNames = list(raw_names.values())
            else:
                helmet_classNames = list(raw_names or [])
        else:
            print(f"Warning: Loaded helmet model at {HELMET_MODEL_PATH} appears generic.")
    
    # Load vehicle detector ONCE at startup (not per-request)
    vehicle_detector = YOLO('yolov8n.pt')
    print("Loaded vehicle detector (yolov8n.pt) for motorcycle pre-filtering")
    
    plate_model = None 
    reader = easyocr.Reader(['en'])
    print(f"Loaded helmet model: {HELMET_MODEL_PATH} with classes: {helmet_classNames}")
    print(f"Loaded plate model: USING ROBOFLOW CLOUD API")
    print("EasyOCR loaded successfully.")
except Exception as e:
    print(f"ERROR: Could not load models or OCR readers. {e}")


CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
}) 

# Global handler: respond to ALL OPTIONS preflight requests before JWT blocks them
@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

def get_db_connection():
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            passwd="root",
            database="TrafficDB"
        )
        return db
    except mysql.connector.Error as e:
        print("Error connecting to MySQL:", e)
        return None

@app.route('/test-db', methods=['GET'])
def test_db():
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Failed to connect to the database"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT DATABASE();")
        db_name = cursor.fetchone()[0]
        cursor.close()
        db.close()
        return jsonify({"message": f"Connected to database: {db_name}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
        
    data = request.get_json()
    if not data:
        return jsonify({"message": "No data provided"}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500

        cursor = db.cursor()
        cursor.execute("SELECT password, role FROM loginuser WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if not user:
            return jsonify({"success": False, "message": "Invalid credentials"}), 401

        user_password = user[0]
        user_role = user[1]

        if bcrypt.check_password_hash(user_password, password):
            token = create_access_token(identity=username, additional_claims={"role": user_role})
            return jsonify({
                "success": True,
                "token": token,
                "username": username,
                "role": user_role
            }), 200
        else:
            return jsonify({"success": False, "message": "Invalid credentials"}), 401
            
    except Exception as e:
        print(f"Database error: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    try:
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT username FROM loginuser WHERE username = %s", (username,))
        if cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"message": "Username already exists"}), 400

        cursor.execute(
            "INSERT INTO loginuser (username, password) VALUES (%s, %s)",
            (username, hashed_password)
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "User registered successfully"}), 201
    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    current_user = get_jwt_identity()
    return jsonify(logged_in_as=current_user), 200

def _build_cors_preflight_response():
    response = jsonify({"message": "Preflight request received"})
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "POST")
    return response

#model stuff
def detect_violation_and_plate(img, skip_plate=False):
    violation_found = False
    violation_type_found = ""
    plate_text_clean = None
    annotated_img = img.copy()
    
    # Step 1: Detect motorcycles/bikes first to filter out pedestrians
    try:
        vehicle_results = vehicle_detector(img, classes=[3], verbose=False)  # class 3 = motorcycle
        
        motorcycle_detected = False
        for r in vehicle_results:
            boxes = getattr(r, 'boxes', []) or []
            if len(boxes) > 0:
                motorcycle_detected = True
                break
        
        if not motorcycle_detected:
            # print("No motorcycle detected in image - skipping helmet check")
            return "", None, annotated_img
            
    except Exception as e:
        print(f"Vehicle detection error: {e} - skipping helmet check to avoid false positives")
        return "", None, annotated_img
    
    # Step 2: Run helmet detection only if motorcycle is present
    try:
        helmet_results = helmet_model(img, verbose=False)
    except Exception as e:
        print(f"Helmet model inference error: {e}")
        return "", None, annotated_img

    try:
        for r in helmet_results:
            boxes = getattr(r, 'boxes', []) or []
            for box in boxes:
                try:
                    cls_val = None
                    if hasattr(box, 'cls'):
                        try:
                            cls_val = int(box.cls[0])
                        except Exception:
                            try:
                                cls_val = int(box.cls)
                            except Exception:
                                cls_val = None
                    if cls_val is None:
                        continue

                    class_name = helmet_classNames[cls_val] if 0 <= cls_val < len(helmet_classNames) else str(cls_val)

                    try:
                        try:
                            coords = box.xyxy[0]
                        except Exception:
                            coords = np.array(box.xyxy).reshape(-1)[:4]
                        x1, y1, x2, y2 = map(int, coords)
                        lname = str(class_name).lower()
                        
                        if 'without' in lname or 'no helmet' in lname or 'no-helmet' in lname:
                            color = (0, 0, 255)  # Red for violation
                            label_text = 'NO HELMET'
                            violation_found = True
                            violation_type_found = 'Without Helmet'
                        else:
                            color = (0, 255, 0)  # Green for safe
                            label_text = 'WITH HELMET'
                        
                        # Draw box around detection
                        cv2.rectangle(annotated_img, (x1, y1), (x2, y2), color, 2)
                        
                        # Draw label WITHOUT black background
                        label_y = max(20, y1 - 6)
                        cv2.putText(annotated_img, label_text, (x1 + 3, label_y), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                    except Exception as e:
                        pass
                except Exception as e:
                    pass
    except Exception as e:
        pass
    
    if violation_found and not skip_plate:
        print("Violation detected! Searching for license plate...")
        
        ROBOFLOW_API_KEY = os.environ.get('ROBOFLOW_API_KEY', 'KqzgJ8XEdQAFGtUdniRg')
        PROJECT_ENDPOINT = os.environ.get('ROBOFLOW_ENDPOINT', 'https://detect.roboflow.com/indian-car-bike-number-plate/2')
        
        candidates = []
        try:
            retval, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not retval:
                raise RuntimeError('Failed to encode image for Roboflow')
            img_bytes = buffer.tobytes()
            
            # print('Sending image to Roboflow Cloud API for plate detection...')
            files = {'file': ('image.jpg', img_bytes, 'image/jpeg')}
            params = {'api_key': ROBOFLOW_API_KEY, 'confidence': 40}
            resp = requests.post(PROJECT_ENDPOINT, params=params, files=files, timeout=15)
            
            if resp.status_code == 200:
                predictions = resp.json().get('predictions', [])
                # print(f'Roboflow returned {len(predictions)} plate detections')
                for pred in predictions:
                    try:
                        cx = pred.get('x')
                        cy = pred.get('y')
                        w = pred.get('width')
                        h = pred.get('height')
                        score = float(pred.get('confidence', 0.0))
                        if None in (cx, cy, w, h):
                            continue
                        if w < 30 or h < 15:
                            continue
                        x1 = int(cx - (w / 2))
                        y1 = int(cy - (h / 2))
                        x2 = int(cx + (w / 2))
                        y2 = int(cy + (h / 2))
                        area = max(0, (x2 - x1) * (y2 - y1))
                        candidates.append((score, area, x1, y1, x2, y2))
                        
                    except Exception as e:
                        pass
            else:
                pass
        except Exception as e:
            pass

        candidates.sort(key=lambda t: (t[0] * t[1]), reverse=True)

        PLATE_REC_TOKEN = "cf0c77976c4e4fc7f23ec6307467d9b0b950b522"
        
        for cand in candidates:
            _, _, px1, py1, px2, py2 = cand
            padding = 40
            py1c, py2c = max(0, py1 - padding), min(img.shape[0], py2 + padding)
            px1c, px2c = max(0, px1 - padding), min(img.shape[1], px2 + padding)
            plate_crop = img[py1c:py2c, px1c:px2c]

            if plate_crop.size == 0:
                continue

            try:
                retval, buffer = cv2.imencode('.jpg', plate_crop)
                if not retval:
                    continue
                
                print("Sending padded crop to PlateRecognizer API...")
                response = requests.post(
                    'https://api.platerecognizer.com/v1/plate-reader/',
                    headers={'Authorization': f'Token {PLATE_REC_TOKEN}'},
                    files={'upload': ('plate.jpg', buffer.tobytes(), 'image/jpeg')},
                    data={'regions': 'in'} 
                )
                
                res_json = response.json()
                
                if res_json.get('results') and len(res_json['results']) > 0:
                    plate_text_clean = res_json['results'][0]['plate'].upper()
                    print(f"Plate found by PlateRecognizer: {plate_text_clean}")
                    
                    # Draw Green Box and Number for Final Plate (no background)
                    cv2.rectangle(annotated_img, (px1c, py1c), (px2c, py2c), (0, 255, 0), 2)
                    cv2.putText(annotated_img, f'{plate_text_clean}', (px1c, py1c - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 1)
                    
                    return violation_type_found, plate_text_clean, annotated_img
            except Exception as e:
                pass

        if not plate_text_clean:
            print("Violation found, but no license plate was read.")

    return violation_type_found, plate_text_clean, annotated_img

@app.route('/autodetect', methods=['POST', 'OPTIONS'])
def autodetect_violation():
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = jsonify({"message": "OK"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return response, 200
    
    # Verify JWT token for POST request
    try:
        verify_jwt_in_request()
    except Exception as e:
        return jsonify({"error": f"Unauthorized: {str(e)}"}), 401
    if 'image_file' not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file = request.files['image_file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        contents = file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({"error": "Invalid image file"}), 400
        
        violation_type, plate_number, annotated_img = detect_violation_and_plate(img)

        unique_filename = f"{uuid.uuid4()}.jpg"
        save_path = os.path.join("evidence_uploads", unique_filename)
        success, encoded_image = cv2.imencode('.jpg', annotated_img)
        annotated_b64 = None
        if success:
            with open(save_path, "wb") as f:
                f.write(encoded_image)
            print(f"Evidence file saved to: {save_path}")
            try:
                annotated_b64 = base64.b64encode(encoded_image.tobytes()).decode('utf-8')
            except Exception:
                try:
                    annotated_b64 = base64.b64encode(encoded_image).decode('utf-8')
                except Exception:
                    annotated_b64 = None

        # Case 1: No violation detected at all
        if not violation_type:
            response_payload = {
                "message": "No violation detected in this image.",
                "violation_type": "",
                "license_plate": None,
                "evidence_filename": unique_filename
            }
            if annotated_b64:
                response_payload["annotated_image"] = f"data:image/jpeg;base64,{annotated_b64}"
            resp = jsonify(response_payload)
            resp.headers.add('Access-Control-Allow-Origin', '*')
            return resp, 200

        # Case 2: Violation found but plate unreadable
        if not plate_number:
            response_payload = {
                "message": f"Violation ({violation_type}) detected, but the license plate was unreadable.",
                "violation_type": violation_type,
                "license_plate": None,
                "evidence_filename": unique_filename
            }
            if annotated_b64:
                response_payload["annotated_image"] = f"data:image/jpeg;base64,{annotated_b64}"
            resp = jsonify(response_payload)
            resp.headers.add('Access-Control-Allow-Origin', '*')
            return resp, 200

        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500

        cursor = db.cursor()
        cursor.execute("SELECT VehicleID FROM Vehicle WHERE LicensePlate = %s", (plate_number,))
        vehicle = cursor.fetchone()

        if not vehicle:
            print(f"Vehicle {plate_number} not found. Auto-registering...")
            cursor.execute("SELECT COUNT(*) FROM Vehicle WHERE OwnerName LIKE 'UNKNOWN (%)'")
            count_result = cursor.fetchone()
            unknown_count = count_result[0]
            new_owner_name = f"UNKNOWN ({unknown_count + 1}) (Auto-Detected)"
            register_query = """INSERT INTO Vehicle(OwnerName, LicensePlate, VehicleType, Contact, Address) VALUES (%s, %s, %s, %s, %s)"""
            placeholder_values = (new_owner_name, plate_number, "Motorcycle", "N/A", "N/A")
            cursor.execute(register_query, placeholder_values)
            db.commit()
            vehicle_id = cursor.lastrowid
            print(f"New vehicle registered with ID: {vehicle_id} and Owner: {new_owner_name}")
        else:
            vehicle_id = vehicle[0]

        default_fine = 500 
        default_location = "Auto-Detected via Camera"

        query = "INSERT INTO Violations (VehicleID, ViolationType, FineAmount, Location, evidence_image) VALUES (%s, %s, %s, %s, %s)"
        values = (vehicle_id, violation_type, default_fine, default_location, unique_filename)
        cursor.execute(query, values)
        db.commit()

        violation_id = cursor.lastrowid
        payload = canonical_violation_payload(
            violation_id=violation_id,
            license_plate=plate_number,
            violation_type=violation_type,
            fine_amount=default_fine,
            location=default_location,
            timestamp=datetime.utcnow(),
            evidence_filename=unique_filename
        )
        v_hash = hash_violation(payload)
        cursor.execute(
            "UPDATE Violations SET violation_hash=%s WHERE ViolationID=%s",
            (v_hash, violation_id)
        )
        db.commit()
        cursor.close()
        db.close()

        response_payload = {
            "message": "Success! Violation added.",
            "violation_type": violation_type,
            "license_plate": plate_number,
            "evidence_filename": unique_filename
        }
        if annotated_b64:
            response_payload["annotated_image"] = f"data:image/jpeg;base64,{annotated_b64}"

        resp = jsonify(response_payload)
        resp.headers.add('Access-Control-Allow-Origin', '*')
        resp.headers.add('Content-Type', 'application/json')
        return resp, 201

    except Exception as e:
        print(f"Error in /autodetect: {str(e)}")
        import traceback
        traceback.print_exc()
        if 'db' in locals() and db.is_connected():
            try:
                db.rollback()
                cursor.close()
                db.close()
            except:
                pass
        error_message = str(e) if str(e) else "Unknown detection error"
        resp = jsonify({"error": f"Detection failed: {error_message}", "status": "error"})
        resp.headers.add('Access-Control-Allow-Origin', '*')
        resp.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        resp.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        resp.headers.add('Content-Type', 'application/json')
        return resp, 500

# =====================================================================
# FAST CPU VIDEO PIPELINE (No API, Frame Buffering)
# =====================================================================
@app.route('/autodetect-video', methods=['POST', 'OPTIONS'])
def autodetect_video():
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = jsonify({"message": "OK"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return response, 200
    
    # Verify JWT token for POST request
    try:
        verify_jwt_in_request()
    except Exception as e:
        return jsonify({"error": f"Unauthorized: {str(e)}"}), 401
    
    # Actual POST handling
    if 'video_file' not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files['video_file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        file.save(temp_video.name)
        cap = cv2.VideoCapture(temp_video.name)
        
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # MP4 output for frontend playback
        # MP4 output for broad browser + codec compatibility
        out_filename = f"vid_{uuid.uuid4()}.mp4"
        out_path = os.path.join("evidence_uploads", out_filename)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
        
        # Check if VideoWriter initialized properly
        if not out.isOpened():
            print(f"ERROR: VideoWriter failed to initialize! codec=mp4v, fps={fps}, size=({width},{height})")
            cap.release()
            return jsonify({"error": "Video codec initialization failed"}), 500

        best_violation_type = None
        best_frame_img = None
        
        print(f"Starting FAST video processing - fps={fps}, size={width}x{height}...")
        frame_count = 0
        last_annotated_frame = None
        detection_frequency = 3  # Run YOLO every 3 frames for speed
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            frame_count += 1
            
            # Run YOLO detection every N frames (fast processing)
            if frame_count % detection_frequency == 0 or frame_count == 1:
                # Run helmet detection with YOLO
                v_type, _, annotated_frame = detect_violation_and_plate(frame, skip_plate=True)
                last_annotated_frame = annotated_frame.copy()
                
                # If we found a violation, save it as evidence
                if v_type and not best_violation_type:
                    best_violation_type = v_type
                    best_frame_img = annotated_frame.copy()
                
                out.write(annotated_frame)
            else:
                # For in-between frames, use the last detected frame to maintain continuity
                # This keeps detections visible across all frames without re-running YOLO
                if last_annotated_frame is not None:
                    out.write(last_annotated_frame)
                else:
                    out.write(frame)
            
            if frame_count % 30 == 0:
                print(f"  Processed {frame_count} frames... (Detection every {detection_frequency} frames)")
                import sys
                sys.stdout.flush()  # Force flush to send progress updates

        cap.release()
        out.release()
        try: os.remove(temp_video.name) 
        except: pass

        print("Video processing complete.")

        # Prepare Response
        unique_filename = None
        annotated_b64 = None
        
        if best_frame_img is not None:
            unique_filename = f"{uuid.uuid4()}.jpg"
            save_path = os.path.join("evidence_uploads", unique_filename)
            success, encoded_image = cv2.imencode('.jpg', best_frame_img)
            if success:
                with open(save_path, "wb") as f:
                    f.write(encoded_image)
                annotated_b64 = base64.b64encode(encoded_image.tobytes()).decode('utf-8')

        response_payload = {
            "message": "Video processed! Helmet violations marked in annotated video.",
            "violation_type": best_violation_type,
            "license_plate": None,
            "evidence_filename": unique_filename,
            "video_filename": out_filename,
            "video_url": f"/evidence/{out_filename}"
        }
        
        if annotated_b64:
            response_payload["annotated_image"] = f"data:image/jpeg;base64,{annotated_b64}"
        
        resp = jsonify(response_payload)
        resp.headers.add('Access-Control-Allow-Origin', '*')
        resp.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        resp.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        resp.headers.add('Content-Type', 'application/json')
        return resp, 201

    except Exception as e:
        print(f"Error in continuous /autodetect-video: {str(e)}")
        import traceback
        traceback.print_exc()
        error_message = str(e) if str(e) else "Unknown video processing error"
        resp = jsonify({"error": f"Video processing failed: {error_message}", "status": "error"})
        resp.headers.add('Access-Control-Allow-Origin', '*')
        resp.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        resp.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        resp.headers.add('Content-Type', 'application/json')
        return resp, 500

@app.route('/init-paddle', methods=['POST'])
def init_paddle():
    if not paddle_available:
        return jsonify({"message": "paddleocr package not installed"}), 400
    try:
        global reader_paddle
        if reader_paddle is None:
            import paddleocr as _paddleocr_mod
            reader_paddle = _paddleocr_mod.PaddleOCR(use_textline_orientation=True, lang='en')
        return jsonify({"message": "PaddleOCR initialized"}), 200
    except Exception as e:
        print(f"PaddleOCR init error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/iot/report-speeding', methods=['POST'])
def iot_report_speeding():
    api_key = request.headers.get('X-API-Key')
    if api_key != 'my-secret-iot-key':
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    plate_number = data.get('LicensePlate')
    speed = data.get('Speed')

    if not plate_number or not speed:
        return jsonify({"error": "Missing LicensePlate or Speed"}), 400

    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("SELECT VehicleID FROM Vehicle WHERE LicensePlate = %s", (plate_number,))
        vehicle = cursor.fetchone()
        vehicle_id = None

        if not vehicle:
            print(f"[IoT] Vehicle {plate_number} not found. Auto-registering...")
            cursor.execute("SELECT COUNT(*) FROM Vehicle WHERE OwnerName LIKE 'UNKNOWN (%)'")
            count_result = cursor.fetchone()
            unknown_count = count_result[0]
            new_owner_name = f"UNKNOWN ({unknown_count + 1}) (Auto-Detected)"
            register_query = """INSERT INTO Vehicle(OwnerName, LicensePlate, VehicleType, Contact, Address) VALUES (%s, %s, %s, %s, %s)"""
            placeholder_values = (new_owner_name, plate_number, "UNKNOWN", "N/A", "N/A")
            cursor.execute(register_query, placeholder_values)
            db.commit()
            vehicle_id = cursor.lastrowid
        else:
            vehicle_id = vehicle[0]

        fine_amount = (speed - 90) * 10  
        if fine_amount < 100: fine_amount = 100

        query = """
            INSERT INTO Violations (VehicleID, ViolationType, FineAmount, Location, ReportedBy) 
            VALUES (%s, %s, %s, %s, %s)
        """
        values = (vehicle_id, "Speeding", fine_amount, "Simulated Radar (NH-48)", "IoT-Radar-01")
        cursor.execute(query, values)
        db.commit()
        cursor.close()
        db.close()
        
        return jsonify({"message": f"Successfully logged speeding violation for {plate_number}"}), 201

    except Exception as e:
        print(f"Error in /iot/report-speeding: {str(e)}")
        if 'db' in locals() and db.is_connected():
            db.rollback()
            cursor.close()
            db.close()
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

@app.route('/get-violations/<license_plate>', methods=['GET'])
def get_violations(license_plate):
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT VehicleID FROM Vehicle WHERE LicensePlate = %s", (license_plate,))
        vehicle = cursor.fetchone()

        if not vehicle:
            cursor.close()
            db.close()
            return jsonify({"error": "Vehicle not found"}), 404

        vehicle_id = vehicle[0]
        cursor.execute("SELECT * FROM Violations WHERE VehicleID = %s", (vehicle_id,))
        violations = cursor.fetchall()

        if not violations:
            cursor.close()
            db.close()
            return jsonify({"message": "No violations found for this vehicle."}), 404

        results = [{
            "ViolationID": v[0],
            "VehicleID": v[1],
            "DateTime": v[2].strftime('%Y-%m-%d %H:%M:%S'),
            "ViolationType": v[3],
            "FineAmount": float(v[4]),
            "Status": v[5],
            "Location": v[6],
            "evidence_image": v[8] if len(v) > 8 and v[8] is not None else None
        } for v in violations]

        cursor.close()
        db.close()
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-violation/<int:violation_id>', methods=['GET'])
@jwt_required()
def get_violation(violation_id):
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT * FROM Violations WHERE ViolationID = %s", (violation_id,))
        violation = cursor.fetchone()

        if not violation:
            cursor.close()
            db.close()
            return jsonify({"error": "Violation not found"}), 404

        violation_data = {
            "ViolationID": violation[0],
            "FineAmount": float(violation[4]),
            "Status": violation[5],
        }
        cursor.close()
        db.close()
        return jsonify(violation_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/pay-fine/<int:violation_id>', methods=['PUT'])
@jwt_required()
def pay_fine(violation_id):
    data = request.json
    payment_method = data.get("PaymentMethod", "Online")
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT FineAmount FROM Violations WHERE ViolationID = %s", (violation_id,))
        violation = cursor.fetchone()
        
        if not violation:
            cursor.close()
            db.close()
            return jsonify({"error": "Violation not found"}), 404

        cursor.execute("UPDATE Violations SET Status = 'Paid' WHERE ViolationID = %s", (violation_id,))
        db.commit()

        cursor.execute("""
            INSERT INTO Fines (ViolationID, PaymentStatus, PaymentMethod, DatePaid, Amount) 
            VALUES (%s, 'Completed', %s, NOW(), %s)
        """, (violation_id, payment_method, float(violation[0])))
        db.commit()

        cursor.close()
        db.close()
        return jsonify({"message": "Fine paid successfully!"}), 200
    except mysql.connector.Error as db_error:
        return jsonify({"error": f"Database error: {str(db_error)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Payment processing failed: {str(e)}"}), 400


# ──────────────────────────────────────────────────────────────
#  Routes required by the React frontend
# ──────────────────────────────────────────────────────────────

@app.route('/dashboard-stats', methods=['GET'])
@jwt_required()
def dashboard_stats():
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()

        cursor.execute("SELECT COUNT(*) FROM Vehicle")
        total_vehicles = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM Violations")
        total_violations = cursor.fetchone()[0]

        cursor.execute(
            "SELECT ViolationType, COUNT(*) AS cnt FROM Violations GROUP BY ViolationType ORDER BY cnt DESC LIMIT 1"
        )
        row = cursor.fetchone()
        top_violation = row[0] if row else "N/A"

        cursor.execute("SELECT COALESCE(SUM(FineAmount),0) FROM Violations WHERE Status='Paid'")
        total_paid = float(cursor.fetchone()[0])

        cursor.execute("SELECT COALESCE(SUM(FineAmount),0) FROM Violations WHERE Status='Unpaid'")
        total_unpaid = float(cursor.fetchone()[0])

        cursor.close()
        db.close()
        return jsonify({
            "total_vehicles": total_vehicles,
            "total_violations": total_violations,
            "top_violation": top_violation,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid
        }), 200
    except Exception as e:
        print(f"Error in /dashboard-stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/my-profile-stats', methods=['GET'])
@jwt_required()
def my_profile_stats():
    try:
        username = get_jwt_identity()
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()

        cursor.execute("SELECT role FROM loginuser WHERE username = %s", (username,))
        row = cursor.fetchone()
        role = row[0] if row else "user"

        cursor.execute("SELECT COUNT(*) FROM Vehicle WHERE RegisteredBy = %s", (username,))
        vehicles_registered = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM Violations WHERE ReportedBy = %s", (username,))
        violations_reported = cursor.fetchone()[0]

        cursor.close()
        db.close()
        return jsonify({
            "username": username,
            "role": role,
            "vehicles_registered": vehicles_registered,
            "violations_reported": violations_reported
        }), 200
    except Exception as e:
        print(f"Error in /my-profile-stats: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get-vehicles', methods=['GET'])
@jwt_required()
def get_vehicles():
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT VehicleID, OwnerName, LicensePlate, VehicleType, Contact, Address FROM Vehicle")
        rows = cursor.fetchall()
        vehicles = [{
            "VehicleID": r[0],
            "OwnerName": r[1],
            "LicensePlate": r[2],
            "VehicleType": r[3],
            "Contact": r[4],
            "Address": r[5]
        } for r in rows]
        cursor.close()
        db.close()
        return jsonify(vehicles), 200
    except Exception as e:
        print(f"Error in /get-vehicles: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/delete-vehicle/<license_plate>', methods=['DELETE'])
@jwt_required()
def delete_vehicle(license_plate):
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()

        cursor.execute("SELECT VehicleID FROM Vehicle WHERE LicensePlate = %s", (license_plate,))
        vehicle = cursor.fetchone()
        if not vehicle:
            cursor.close()
            db.close()
            return jsonify({"message": "Vehicle not found"}), 404

        vehicle_id = vehicle[0]
        # Delete related fines first, then violations, then the vehicle
        cursor.execute("DELETE FROM Fines WHERE ViolationID IN (SELECT ViolationID FROM Violations WHERE VehicleID = %s)", (vehicle_id,))
        cursor.execute("DELETE FROM Violations WHERE VehicleID = %s", (vehicle_id,))
        cursor.execute("DELETE FROM Vehicle WHERE VehicleID = %s", (vehicle_id,))
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": f"Vehicle {license_plate} deleted successfully"}), 200
    except Exception as e:
        print(f"Error in /delete-vehicle: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/register-vehicle', methods=['POST'])
@jwt_required()
def register_vehicle():
    data = request.json
    owner = data.get('OwnerName')
    plate = data.get('LicensePlate')
    vtype = data.get('VehicleType', 'Car')
    contact = data.get('Contact', '')
    address = data.get('Address', '')

    if not owner or not plate:
        return jsonify({"error": "OwnerName and LicensePlate are required"}), 400

    try:
        username = get_jwt_identity()
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()

        cursor.execute("SELECT VehicleID FROM Vehicle WHERE LicensePlate = %s", (plate,))
        if cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"error": "A vehicle with this license plate already exists"}), 400

        cursor.execute(
            "INSERT INTO Vehicle (OwnerName, LicensePlate, VehicleType, Contact, Address, RegisteredBy) VALUES (%s,%s,%s,%s,%s,%s)",
            (owner, plate, vtype, contact, address, username)
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Vehicle registered successfully"}), 201
    except Exception as e:
        print(f"Error in /register-vehicle: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/add-violation', methods=['POST'])
@jwt_required()
def add_violation():
    data = request.json
    plate = data.get('LicensePlate')
    v_type = data.get('ViolationType', 'Other')
    fine = data.get('FineAmount', 0)
    location = data.get('Location', '')

    if not plate:
        return jsonify({"error": "LicensePlate is required"}), 400

    try:
        username = get_jwt_identity()
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()

        cursor.execute("SELECT VehicleID FROM Vehicle WHERE LicensePlate = %s", (plate,))
        vehicle = cursor.fetchone()
        if not vehicle:
            cursor.close()
            db.close()
            return jsonify({"error": "Vehicle not found. Register it first."}), 404

        vehicle_id = vehicle[0]
        cursor.execute(
            "INSERT INTO Violations (VehicleID, ViolationType, FineAmount, Location, ReportedBy) VALUES (%s,%s,%s,%s,%s)",
            (vehicle_id, v_type, fine, location, username)
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Violation recorded successfully"}), 201
    except Exception as e:
        print(f"Error in /add-violation: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/evidence/<filename>', methods=['GET', 'OPTIONS'])
def serve_evidence(filename):
    """Serve evidence files (videos, images)"""
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    try:
        evidence_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evidence_uploads')
        response = send_from_directory(evidence_dir, filename)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    except Exception as e:
        print(f"Error serving evidence file {filename}: {e}")
        return jsonify({"error": f"File not found: {filename}"}), 404


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')