import os
import sys
import shutil

def main():
    try:
        from roboflow import Roboflow
    except Exception as e:
        print('Please install roboflow: pip install roboflow')
        raise

    api_key = os.environ.get('ROBOFLOW_API_KEY', 'KqzgJ8XEdQAFGtUdniRg')
    workspace_name = 'indiannumberplatesdetection'
    project_name = 'indian-car-bike-number-plate'
    version_number = 1

    rf = Roboflow(api_key=api_key)
    print('Initialized Roboflow')

    try:
        project = rf.workspace(workspace_name).project(project_name)
        version = project.version(version_number)
    except Exception as e:
        print('Failed to access project/version:', e)
        sys.exit(2)

    # Try common model download API patterns
    tried = []
    download_path = None
    candidates = [
        ('version.model.download', lambda v: getattr(v, 'model', None) and v.model.download('yolov8')),
        ('version.download', lambda v: v.download('yolov8')),
        ('project.model.download', lambda v: getattr(project, 'model', None) and project.model.download('yolov8')),
    ]

    for name, fn in candidates:
        try:
            print('Trying', name)
            res = fn(version)
            if res:
                # res may be an object with location attribute or a path string
                if hasattr(res, 'location'):
                    download_path = res.location
                elif isinstance(res, str):
                    download_path = res
                else:
                    # attempt to string-convert
                    download_path = str(res)
                print('Downloaded to', download_path)
                break
        except Exception as e:
            tried.append((name, str(e)))
            print('Failed', name, e)

    if not download_path:
        print('Could not download model with tried methods. Errors:', tried)
        sys.exit(3)

    # Search for weight files under download_path
    weight_file = None
    for root, dirs, files in os.walk(download_path):
        for f in files:
            if f.endswith('.pt') or f.endswith('.pth'):
                weight_file = os.path.join(root, f)
                break
        if weight_file:
            break

    if not weight_file:
        print('No .pt/.pth weight file found under', download_path)
        sys.exit(4)

    target = os.path.join(os.getcwd(), 'Weights', 'license_plate_detector.pt')
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        shutil.copyfile(weight_file, target)
        print('Copied pretrained weight to', target)
    except Exception as e:
        print('Failed copying weight:', e)
        sys.exit(5)

if __name__ == '__main__':
    main()
