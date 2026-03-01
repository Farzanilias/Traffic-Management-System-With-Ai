#!/usr/bin/env python3
"""
Prepare a small Roboflow-ready dataset by downloading public images,
auto-labeling helmet boxes using the current `Weights/best.pt` model,
and writing YOLO-format labels.

Usage:
  RF dataset prepared at ./data/roboflow_dataset
  Run: python3 scripts/roboflow_prepare.py

Note: Inspect the generated labels before uploading to Roboflow. This is an
automated seed — for best results manually correct bounding boxes in the
Roboflow UI.
"""
import os
import sys
import shutil
import urllib.request
import requests
from pathlib import Path
from ultralytics import YOLO
import cv2
import numpy as np

OUT_DIR = Path('data/roboflow_dataset')
IMAGES_DIR = OUT_DIR / 'images'
LABELS_DIR = OUT_DIR / 'labels'

# A handful of clear public images (Wikimedia). Picked for variety.
IMAGE_URLS = [
    'https://commons.wikimedia.org/wiki/Special:FilePath/Indian_bikers_gang_without_helmet.jpg',
]

def ensure_dirs():
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def download_images():
    saved = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for i, url in enumerate(IMAGE_URLS):
        name = f'image_{i+1}.jpg'
        out = IMAGES_DIR / name
        print('Downloading', url)
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=20)
            if r.status_code == 200:
                with open(out, 'wb') as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
                saved.append(out)
            else:
                print('Failed to download', url, 'HTTP', r.status_code)
        except Exception as e:
            print('Failed to download', url, e)
    return saved


def run_detector_and_write_labels(image_paths):
    # Load model
    model_path = os.environ.get('HELMET_MODEL_PATH', 'Weights/best.pt')
    print('Loading helmet model:', model_path)
    model = YOLO(model_path)
    names = getattr(model, 'names', {})
    # Map names to label indices for YOLO (0 = With Helmet, 1 = Without Helmet)
    label_map = {}
    for k, v in (names.items() if isinstance(names, dict) else enumerate(names)):
        # handle dict or list
        try:
            label_name = v if isinstance(v, str) else names[k]
        except Exception:
            label_name = str(v)
        if 'with' in label_name.lower():
            label_map[k] = 0
        elif 'without' in label_name.lower():
            label_map[k] = 1
        else:
            # unknown classes are ignored
            label_map[k] = None

    for img_path in image_paths:
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        results = model(img)
        yolo_lines = []
        for r in results:
            boxes = getattr(r, 'boxes', []) or []
            for b in boxes:
                try:
                    cls = None
                    if hasattr(b, 'cls'):
                        try:
                            cls = int(b.cls[0])
                        except Exception:
                            cls = int(b.cls)
                    mapped = label_map.get(cls, None)
                    if mapped is None:
                        continue
                    coords = b.xyxy[0]
                    x1, y1, x2, y2 = map(float, coords)
                    # convert to yolo format (x_center, y_center, width, height) normalized
                    xc = ((x1 + x2) / 2.0) / w
                    yc = ((y1 + y2) / 2.0) / h
                    bw = (x2 - x1) / w
                    bh = (y2 - y1) / h
                    yolo_lines.append(f"{mapped} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
                except Exception as e:
                    print('box parse error', e)
        label_file = LABELS_DIR / (img_path.stem + '.txt')
        with open(label_file, 'w') as f:
            f.write('\n'.join(yolo_lines))
        print('Wrote labels for', img_path.name, 'lines=', len(yolo_lines))


def zip_dataset():
    zip_path = OUT_DIR.with_suffix('.zip')
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(OUT_DIR), 'zip', root_dir=str(OUT_DIR))
    print('Created dataset archive:', zip_path)
    return zip_path


def print_upload_instructions(zip_path):
    print('\nDataset prepared at:', OUT_DIR)
    print('Archive:', zip_path)
    print('\nTo upload to Roboflow (manual):')
    print('  - Log in to https://app.roboflow.com and create a new dataset/project')
    print('  - Upload the generated zip file and choose YOLO format')
    print('\nOptional: to upload via API, set RF_API_KEY and run the following (replace <PROJECT> and <DATASET_NAME> as needed):')
    print("curl -X POST -H \"Authorization: Bearer $RF_API_KEY\" -F \"file=@%s\" \"https://api.roboflow.com/dataset/your-dataset-name/upload\"" % str(zip_path))


if __name__ == '__main__':
    ensure_dirs()
    imgs = download_images()
    if not imgs:
        print('No images downloaded, aborting')
        sys.exit(1)
    run_detector_and_write_labels(imgs)
    zip_path = zip_dataset()
    print_upload_instructions(zip_path)
