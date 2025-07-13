import glob
import os
import zipfile
import shutil
import requests
import sys
from urllib.parse import urljoin

# Configuration
VERSION_URL = "https://kendryte-download.canaan-creative.com/developer/tools/canmv_ide_k230/canmv_ide_resources/version.txt"

SOURCE_DIRS = [
    "01-Micropython-Basics",
    "02-Media",
    "03-Machine",
    "04-Cipher",
    "05-AI-Demo",
    "06-Display",
    "07-April-Tags",
    "08-Codes",
    "09-Color-Tracking",
    "10-Drawing",
    "11-Feature-Detection",
    "12-Image-Filters",
    "14-Socket",
    "15-LVGL",
    "16-AI-Cube",
    "17-Sensor",
    "18-NNCase",
    "19-CloudPlatScripts",
    "20-YOLO-Module-Examples",
    "21-AI-With-Others",
    "22-Others",
    "99-HelloWorld",
]

def get_current_version():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(VERSION_URL, headers=headers, timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        for path in ["generated/version.txt", "version.txt"]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read().strip()
        raise RuntimeError("Could not fetch version from URL or local files")

def smart_bump_version(version):
    try:
        major, minor, patch = map(int, version.split('.'))
        if patch < 99:
            patch += 1
        else:
            patch = 0
            if minor < 99:
                minor += 1
            else:
                minor = 0
                major += 1
        return f"{major}.{minor}.{patch}"
    except ValueError:
        raise ValueError(f"Invalid version format: {version} (expected X.Y.Z)")

def write_version_files(version):
    os.makedirs("generated", exist_ok=True)
    with open(os.path.join("generated", "version.txt"), "w") as f:
        f.write(version)

def copy_folder(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

def copy_selected_examples(resource_dir):
    gen_examples = os.path.join("generated", "examples")
    os.makedirs(gen_examples, exist_ok=True)

    for folder in SOURCE_DIRS:
        src = os.path.join(resource_dir, "examples", folder)
        dst = os.path.join(gen_examples, folder)
        if not os.path.exists(src):
            print(f"Warning: Skipped missing folder: {src}")
            continue

        os.makedirs(dst, exist_ok=True)
        for file_name in os.listdir(src):
            if file_name.endswith(".py"):
                shutil.copy2(os.path.join(src, file_name), dst)

def zip_directory(directory_path, zipf, base_dir):
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.join(base_dir, os.path.relpath(file_path, directory_path))
            zipf.write(file_path, arcname)

def main():
    try:
        current_version = get_current_version()
        new_version = smart_bump_version(current_version)
        print(f"Version bumped: {current_version} → {new_version}")

        if len(sys.argv) < 2:
            print("Usage: script.py <source_resource_dir>")
            sys.exit(1)
        resource_dir = sys.argv[1]

        if not os.path.exists(resource_dir):
            print(f"Error: Resources directory not found at {resource_dir}")
            sys.exit(1)

        write_version_files(new_version)

        # Copy selected example folders
        copy_selected_examples(resource_dir)

        # Copy entire models folder
        raw_models = os.path.join(resource_dir, "models")
        gen_models = os.path.join("generated", "models")
        if os.path.exists(raw_models):
            copy_folder(raw_models, gen_models)

        # Create ZIP
        zip_path = os.path.join("generated", f'canmv-ide-resources-{new_version}.zip')
        print(f"Creating resource package: {zip_path}")

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if os.path.exists("generated/examples"):
                zip_directory("generated/examples", zipf, "examples")
            if os.path.exists("generated/models"):
                zip_directory("generated/models", zipf, "models")

        print("Resource package created successfully!")

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
