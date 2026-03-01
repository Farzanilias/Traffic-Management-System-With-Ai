from flask import Flask, request, jsonify
import mysql.connector
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
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
import requests  # <-- ADDED for API requests

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
def detect_violation_and_plate(img):
    violation_found = False
    violation_type_found = ""
    plate_text_clean = None
    annotated_img = img.copy()
    
    try:
        helmet_results = helmet_model(img)
    except Exception as e:
        print(f"Helmet model inference error: {e}")
        print(traceback.format_exc())
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
                            color = (0, 0, 255)
                        else:
                            color = (0, 255, 0)
                        cv2.rectangle(annotated_img, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(annotated_img, f'{class_name}', (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
                        if 'without' in str(class_name).lower():
                            violation_found = True
                            violation_type_found = 'Without Helmet'
                    except Exception as e:
                        pass
                except Exception as e:
                    pass
    except Exception as e:
        pass
    
    if violation_found:
        print("Violation detected! Searching for license plate...")
        
        ROBOFLOW_API_KEY = "KqzgJ8XEdQAFGtUdniRg" # Update this to your Roboflow key!
        PROJECT_ENDPOINT = "https://detect.roboflow.com/indian-car-bike-number-plate/2"
        
        candidates = []
        try:
            retval, buffer = cv2.imencode('.jpg', img)
            img_b64 = base64.b64encode(buffer).decode("ascii")
            
            resp = requests.post(
                PROJECT_ENDPOINT,
                params={"api_key": ROBOFLOW_API_KEY, "confidence": 10}, 
                data=img_b64,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if resp.status_code == 200:
                predictions = resp.json().get("predictions", [])
                for pred in predictions:
                    width = pred["width"]
                    height = pred["height"]
                    x1 = int(pred["x"] - (width / 2))
                    y1 = int(pred["y"] - (height / 2))
                    x2 = int(pred["x"] + (width / 2))
                    y2 = int(pred["y"] + (height / 2))
                    score = pred["confidence"]
                    area = width * height
                    candidates.append((score, area, x1, y1, x2, y2))
        except Exception as e:
            pass

        candidates.sort(key=lambda t: (t[0] * t[1]), reverse=True)

        # =====================================================================
        # OLD OCR LOGIC (EasyOCR / PaddleOCR) - COMMENTED OUT FOR FUTURE USE
        # =====================================================================
        """
        def preprocess_for_ocr(crop):
            try:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            except Exception:
                gray = crop
            h, w = gray.shape[:2]
            target_h = 200
            scale = max(1, target_h // max(1, h))
            if scale > 1:
                gray = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
            try:
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                gray = clahe.apply(gray)
            except Exception:
                pass
            gray = cv2.bilateralFilter(gray, 9, 75, 75)
            try:
                gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            except Exception:
                pass
            try:
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
                gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
            except Exception:
                pass
            return gray

        def extra_preprocess_variants(crop):
            variants = []
            try:
                gray = preprocess_for_ocr(crop)
                variants.append(gray)
            except Exception:
                pass
            try:
                inv = 255 - cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                variants.append(inv)
            except Exception:
                pass
            try:
                kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
                sharp = cv2.filter2D(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), -1, kernel)
                variants.append(sharp)
            except Exception:
                pass
            try:
                imgf = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)/255.0
                for g in [0.8, 1.2, 1.5]:
                    gamma = np.clip(255.0 * np.power(imgf, g), 0, 255).astype(np.uint8)
                    variants.append(gamma)
            except Exception:
                pass
            return variants

        for cand in candidates:
            _, _, px1, py1, px2, py2 = cand
            padding = 8
            py1c, py2c = max(0, py1 - padding), min(img.shape[0], py2 + padding)
            px1c, px2c = max(0, px1 - padding), min(img.shape[1], px2 + padding)
            plate_crop = img[py1c:py2c, px1c:px2c]

            if plate_crop.size == 0:
                continue

            tried_text = None
            variants = [preprocess_for_ocr(plate_crop), plate_crop]
            angles = [0, 90, 270]
            for var in variants:
                for ang in angles:
                    try:
                        if ang != 0:
                            M = cv2.getRotationMatrix2D((var.shape[1]//2, var.shape[0]//2), ang, 1)
                            rotated = cv2.warpAffine(var, M, (var.shape[1], var.shape[0]))
                        else:
                            rotated = var

                        plate_text_clean = None
                        try:
                            if paddle_available and os.environ.get('ENABLE_PADDLEOCR') == '1':
                                try:
                                    global reader_paddle
                                    if reader_paddle is None:
                                        import paddleocr as _paddleocr_mod
                                        reader_paddle = _paddleocr_mod.PaddleOCR(use_textline_orientation=True, lang='en')
                                    try:
                                        ocr_result = reader_paddle.ocr(rotated)
                                    except TypeError:
                                        ocr_result = reader_paddle.predict(rotated)
                                    texts = []
                                    for item in ocr_result:
                                        try:
                                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                                candidate = item[1]
                                                if isinstance(candidate, (list, tuple)) and len(candidate) >= 1:
                                                    t = candidate[0]
                                                else:
                                                    t = candidate
                                            elif isinstance(item, dict) and 'text' in item:
                                                t = item.get('text')
                                            elif isinstance(item, str):
                                                t = item
                                            else:
                                                continue
                                            if t:
                                                texts.append(str(t))
                                        except Exception:
                                            continue
                                    if texts:
                                        best = max(texts, key=lambda s: len(''.join(filter(str.isalnum, str(s)))))
                                        plate_text = str(best)
                                        plate_text_clean = "".join(filter(str.isalnum, plate_text)).upper()
                                except Exception as e:
                                    print(f"PaddleOCR runtime error: {e}")
                        except Exception:
                            pass

                        if not plate_text_clean:
                            try:
                                ocr_result = reader.readtext(rotated)
                                texts = []
                                for item in ocr_result:
                                    try:
                                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                                            if isinstance(item[1], (list, tuple)):
                                                t = item[1][0]
                                            else:
                                                t = item[1]
                                        elif isinstance(item, str):
                                            t = item
                                        else:
                                            continue
                                        texts.append(t)
                                    except Exception:
                                        continue
                                if texts:
                                    best = max(texts, key=lambda s: len(''.join(filter(str.isalnum, str(s)))))
                                    plate_text = str(best)
                                    plate_text_clean = "".join(filter(str.isalnum, plate_text)).upper()
                            except Exception as e:
                                print(f"EasyOCR error: {e}")

                        if plate_text_clean and len(plate_text_clean) >= 3:
                            print(f"Plate found: {plate_text_clean}")
                            cv2.rectangle(annotated_img, (px1c, py1c), (px2c, py2c), (0, 255, 0), 2)
                            cv2.putText(annotated_img, f'{plate_text_clean}', (px1c, py1c - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                            return violation_type_found, plate_text_clean, annotated_img
                    except Exception as e:
                        print(f"OCR variant error: {e}")
        """
        # =====================================================================
        # NEW OCR LOGIC: PlateRecognizer API
        # =====================================================================
        PLATE_REC_TOKEN = "cf0c77976c4e4fc7f23ec6307467d9b0b950b522"
        
        for cand in candidates:
            _, _, px1, py1, px2, py2 = cand
            
            # FIXED: Increased padding to give API more context
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
                    # FIXED: Send as a proper multipart/form-data file tuple
                    files={'upload': ('plate.jpg', buffer.tobytes(), 'image/jpeg')},
                    data={'regions': 'in'} # Optimizes for Indian plate layouts!
                )
                
                res_json = response.json()
                
                # DEBUG: Print the exact raw data PlateRecognizer sends back!
                print(f"--- PlateRecognizer Raw JSON ---: {res_json}")
                
                if res_json.get('results') and len(res_json['results']) > 0:
                    # Grab the plate text and clean it up
                    plate_text_clean = res_json['results'][0]['plate'].upper()
                    print(f"Plate found by PlateRecognizer: {plate_text_clean}")
                    
                    # Draw the bounding box and text on the final image
                    cv2.rectangle(annotated_img, (px1c, py1c), (px2c, py2c), (0, 255, 0), 2)
                    cv2.putText(annotated_img, f'{plate_text_clean}', (px1c, py1c - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                    
                    return violation_type_found, plate_text_clean, annotated_img
                else:
                    print("PlateRecognizer couldn't confidently read this crop.")
            except Exception as e:
                print(f"PlateRecognizer API error: {e}")

        # if we reach here, no plate read
        plate_text_clean = None
            
        if not plate_text_clean:
            print("Violation found, but no license plate was read.")
    else:
        print("No violations found in this image.")

    return violation_type_found, plate_text_clean, annotated_img

@app.route('/evidence/<path:filename>')
def serve_evidence_image(filename):
    return send_from_directory('evidence_uploads', filename)

@app.route('/dashboard-stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM Vehicle")
        total_vehicles = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM Violations")
        total_violations = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(FineAmount) FROM Violations WHERE Status = 'Paid'")
        total_paid_result = cursor.fetchone()[0]
        total_paid = float(total_paid_result or 0)
        cursor.execute("SELECT SUM(FineAmount) FROM Violations WHERE Status = 'Unpaid'")
        total_unpaid_result = cursor.fetchone()[0]
        total_unpaid = float(total_unpaid_result or 0)
        cursor.execute("""
            SELECT ViolationType, COUNT(*) as count 
            FROM Violations 
            GROUP BY ViolationType 
            ORDER BY count DESC 
            LIMIT 1
        """)
        top_violation_result = cursor.fetchone()
        top_violation = top_violation_result[0] if top_violation_result else "N/A"

        cursor.close()
        db.close()

        return jsonify({
            "total_vehicles": total_vehicles,
            "total_violations": total_violations,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
            "top_violation": top_violation
        }), 200

    except Exception as e:
        print(f"Error in /dashboard-stats: {str(e)}")
        if 'db' in locals() and db.is_connected():
            cursor.close()
            db.close()
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

@app.route('/my-profile-stats', methods=['GET'])
@jwt_required()
def get_my_profile_stats():
    current_user_username = get_jwt_identity()
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = db.cursor()
        cursor.execute("SELECT role FROM loginuser WHERE username = %s", (current_user_username,))
        role_result = cursor.fetchone()
        user_role = role_result[0] if role_result else "N/A"
        cursor.execute("SELECT COUNT(*) FROM Violations WHERE ReportedBy = %s", (current_user_username,))
        violations_reported = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM Vehicle WHERE RegisteredBy = %s", (current_user_username,))
        vehicles_registered = cursor.fetchone()[0]

        cursor.close()
        db.close()

        return jsonify({
            "username": current_user_username,
            "role": user_role,
            "violations_reported": violations_reported,
            "vehicles_registered": vehicles_registered
        }), 200

    except Exception as e:
        print(f"Error in /my-profile-stats: {str(e)}")
        if 'db' in locals() and db.is_connected():
            cursor.close()
            db.close()
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

@app.route('/register-vehicle', methods=['POST'])
def register_vehicle():
    data = request.json
    query = "INSERT INTO Vehicle (OwnerName, LicensePlate, VehicleType, Contact, Address) VALUES (%s, %s, %s, %s, %s)"
    values = (data['OwnerName'], data['LicensePlate'], data['VehicleType'], data['Contact'], data['Address'])
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute(query, values)
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Vehicle registered successfully!"}), 201
    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 400

@app.route("/delete-vehicle/<license_plate>", methods=["DELETE"])
@jwt_required()
def delete_vehicle(license_plate):
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    user_role = claims.get("role")

    if user_role != 'admin':
        return jsonify({"error": "Unauthorized: Only admins can perform this action"}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Vehicle WHERE LicensePlate = %s", (license_plate,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": f"Vehicle {license_plate} deleted successfully"}), 200

@app.route('/get-vehicles', methods=['GET'])
@jwt_required()
def get_vehicles():
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT * FROM Vehicle")
        vehicles = cursor.fetchall()
        vehicle_list = [{
            "VehicleID": v[0],
            "OwnerName": v[1],
            "LicensePlate": v[2],
            "VehicleType": v[3],
            "Contact": v[4],
            "Address": v[5]
        } for v in vehicles]
        cursor.close()
        db.close()
        return jsonify(vehicle_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-vehicle/<license_plate>', methods=['GET'])
def get_vehicle(license_plate):
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT * FROM Vehicle WHERE LicensePlate = %s", (license_plate,))
        vehicle = cursor.fetchone()

        if not vehicle:
            cursor.close()
            db.close()
            return jsonify({"error": "Vehicle not found"}), 404

        vehicle_data = {
            "VehicleID": vehicle[0],
            "OwnerName": vehicle[1],
            "LicensePlate": vehicle[2],
            "VehicleType": vehicle[3],
            "Contact": vehicle[4],
            "Address": vehicle[5]
        }
        cursor.close()
        db.close()
        return jsonify(vehicle_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add-violation', methods=['POST'])
def add_violation():
    data = request.json
    try:
        db = get_db_connection()
        if not db:
            return jsonify({"error": "Database connection failed"}), 500
        cursor = db.cursor()
        cursor.execute("SELECT VehicleID FROM Vehicle WHERE LicensePlate = %s", (data['LicensePlate'],))
        vehicle = cursor.fetchone()

        if not vehicle:
            cursor.close()
            db.close()
            return jsonify({"error": "Vehicle not found"}), 404

        vehicle_id = vehicle[0]
        query = "INSERT INTO Violations (VehicleID, ViolationType, FineAmount, Location) VALUES (%s, %s, %s, %s)"
        values = (vehicle_id, data['ViolationType'], data['FineAmount'], data['Location'])
        cursor.execute(query, values)
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Violation recorded successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/autodetect', methods=['POST'])
@jwt_required()
def autodetect_violation():
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

        if not plate_number:
            response_payload = {
                "message": f"Violation ({violation_type}) detected, but the license plate was unreadable.",
                "violation_type": violation_type,
                "license_plate": None,
                "evidence_filename": unique_filename
            }
            if annotated_b64:
                response_payload["annotated_image"] = f"data:image/jpeg;base64,{annotated_b64}"
            return jsonify(response_payload), 200

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

        return jsonify(response_payload), 201

    except Exception as e:
        print(f"Error in /autodetect: {str(e)}")
        if 'db' in locals() and db.is_connected():
            db.rollback()
            cursor.close()
            db.close()
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

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
    
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')