import os
import time
import sys

def main():
    try:
        from roboflow import Roboflow
    except Exception as e:
        print('Missing roboflow package; please pip install roboflow')
        raise

    try:
        from ultralytics import YOLO
    except Exception as e:
        print('Missing ultralytics package; please pip install ultralytics')
        raise

    # Use environment variable if set, otherwise fallback to provided key
    api_key = os.environ.get('ROBOFLOW_API_KEY', 'KqzgJ8XEdQAFGtUdniRg')

    print('Initializing Roboflow client...')
    rf = Roboflow(api_key=api_key)

    print('Accessing workspace and project...')
    workspace_name = 'indiannumberplatesdetection'
    project_name = 'indian-car-bike-number-plate'
    version_number = 1

    try:
        project = rf.workspace(workspace_name).project(project_name)
        version = project.version(version_number)
    except Exception as e:
        print('Failed to access project/version:', e)
        sys.exit(2)

    print('Starting dataset download (yolov8 format)...')
    dataset = version.download('yolov8')
    print('Download complete. Dataset location:', dataset.location)

    data_yaml = os.path.join(dataset.location, 'data.yaml')
    if not os.path.exists(data_yaml):
        print('data.yaml not found under dataset location; listing files:')
        for p, dirs, files in os.walk(dataset.location):
            for f in files[:50]:
                print(os.path.join(p, f))
        print('Exiting.')
        sys.exit(3)

    print('Preparing to train YOLOv8 model on dataset...')
    # Use a small base model for faster convergence on limited resources
    base_model = os.environ.get('YOLO_BASE', 'yolov8n.pt')

    print('Loading base model:', base_model)
    model = YOLO(base_model)

    # Training config
    epochs = int(os.environ.get('YOLO_EPOCHS', '30'))
    imgsz = int(os.environ.get('YOLO_IMGSZ', '640'))
    batch = int(os.environ.get('YOLO_BATCH', '16'))

    print(f'Starting training: epochs={epochs}, imgsz={imgsz}, batch={batch}')
    # The 'name' parameter controls the output directory under runs/train
    model.train(data=data_yaml, epochs=epochs, imgsz=imgsz, batch=batch, name='roboflow_plate_train')

    print('Training finished. Best weights should be under runs/train/roboflow_plate_train/weights')

if __name__ == '__main__':
    main()
