#!/usr/bin/env python3
"""
Build script for Yoga Pose Detection System
Automates setup, dependency installation, and provides run commands
"""

import os
import sys
import subprocess
import platform
import shutil

def run_command(command, cwd=None, shell=False):
    """Run a shell command and return success status"""
    try:
        print(f"Running: {command}")
        result = subprocess.run(
            command if shell else command.split(),
            cwd=cwd,
            shell=shell,
            capture_output=True,
            text=True,
            check=True
        )
        print("✓ Success")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed: {e}")
        print(f"Error output: {e.stderr}")
        return False

def check_python_version():
    """Check if Python version is 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("✗ Python 3.8+ required")
        return False
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_node_version():
    """Check if Node.js is installed"""
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✓ Node.js {version}")
            return True
    except FileNotFoundError:
        pass
    print("✗ Node.js not found. Please install Node.js 14+ from https://nodejs.org")
    return False

def create_venv():
    """Create virtual environment"""
    if os.path.exists(".venv"):
        print("Virtual environment already exists")
        return True

    print("Creating virtual environment...")
    return run_command("python -m venv .venv")

def activate_venv():
    """Get activation command for current platform"""
    if platform.system() == "Windows":
        return ".venv\\Scripts\\activate"
    else:
        return "source .venv/bin/activate"

def install_python_deps():
    """Install Python dependencies"""
    if not os.path.exists("requirements.txt"):
        print("✗ requirements.txt not found")
        return False

    # Activate venv and install
    activate_cmd = activate_venv()
    command = f"{activate_cmd} && pip install -r requirements.txt"
    return run_command(command, shell=True)

def install_node_deps():
    """Install Node.js dependencies for React frontend"""
    if not os.path.exists("yoga-pose-frontend"):
        print("React frontend directory not found, skipping...")
        return True

    print("Installing Node.js dependencies...")
    return run_command("npm install", cwd="yoga-pose-frontend")

def init_databases():
    """Initialize SQLite databases by running apps briefly"""
    print("Initializing databases...")

    # Run API server briefly to create poses.db
    try:
        # Import and run init_db from api.py
        sys.path.insert(0, os.getcwd())
        import api
        api.init_db()
        print("✓ poses.db initialized")
    except Exception as e:
        print(f"Warning: Could not initialize poses.db: {e}")

    # Run with_login app briefly to create database.db
    try:
        os.chdir("with_login")
        import app as login_app
        login_app.init_db()
        os.chdir("..")
        print("✓ with_login/database.db initialized")
    except Exception as e:
        print(f"Warning: Could not initialize with_login database: {e}")

def print_run_commands():
    """Print commands to run each component"""
    print("\n" + "="*50)
    print("BUILD COMPLETE! Here are the run commands:")
    print("="*50)

    activate_cmd = activate_venv()

    print("\n1. API Server:")
    print(f"   {activate_cmd} && python api.py")
    print("   Access at: http://127.0.0.1:5000")

    print("\n2. React Frontend:")
    print("   cd yoga-pose-frontend")
    print("   npm start")
    print("   Access at: http://localhost:3000")

    print("\n3. Poses Web App:")
    print(f"   cd poses && {activate_cmd} && python app.py")
    print("   Access at: http://127.0.0.1:5000")

    print("\n4. With Login App:")
    print(f"   cd with_login && {activate_cmd} && python app.py")
    print("   Access at: http://127.0.0.1:5000")

    print("\nNote: Run components in separate terminals")
    print("Make sure to activate the virtual environment for Python apps")

def main():
    """Main build process"""
    print("Yoga Pose Detection System - Build Script")
    print("="*50)

    # Check prerequisites
    if not check_python_version():
        return 1

    check_node_version()  # Warning only, not blocking

    # Create virtual environment
    if not create_venv():
        return 1

    # Install dependencies
    if not install_python_deps():
        return 1

    if not install_node_deps():
        print("Warning: Node.js dependencies not installed")

    # Initialize databases
    init_databases()

    # Print run commands
    print_run_commands()

    print("\n✓ Build completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
