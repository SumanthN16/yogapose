# Yoga Pose Detection and Comparison System

A comprehensive yoga pose detection and comparison system built with Python (Flask), React, and MediaPipe. The system allows users to upload reference poses, perform real-time pose comparison via webcam, and manage yoga sequences through a web interface.

## Project Components

- **API Server** (`api.py`): RESTful API for pose management and comparison
- **Poses Web App** (`poses/`): Simple web interface for pose comparison with live camera feedback
- **With Login App** (`with_login/`): Authenticated web app with user management and pose comparison
- **React Frontend** (`yoga-pose-frontend/`): Modern React-based interface for pose management and comparison

## Prerequisites

- Python 3.8+
- Node.js 14+ (for React frontend)
- Webcam (for live pose comparison)
- Git

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/SumanthN16/yogapose.git
cd yogapose
```

### 2. Backend Setup

#### Create Virtual Environment
```bash
python -m venv .venv
```

#### Activate Virtual Environment
- **Windows:**
  ```bash
  .venv\Scripts\activate
  ```
- **macOS/Linux:**
  ```bash
  source .venv/bin/activate
  ```

#### Install Python Dependencies
```bash
pip install -r requirements.txt
```

#### Initialize Database
The databases are automatically created when you run the applications for the first time.

### 3. Frontend Setup

#### Install Node.js Dependencies
```bash
cd yoga-pose-frontend
npm install
cd ..
```

### 4. Running the Applications

#### Option A: Run API Server Only
```bash
python api.py
```
- Access API at: http://127.0.0.1:5000
- API endpoints:
  - `GET /asanas` - List all asanas
  - `GET /asanas/<name>` - Get poses for specific asana
  - `POST /upload_pose` - Upload new pose
  - `POST /compare_pose` - Compare live pose with reference

#### Option B: Run Poses Web App
```bash
cd poses
python app.py
```
- Access at: http://127.0.0.1:5000
- Features: Upload reference image, live camera comparison

#### Option C: Run With Login App
```bash
cd with_login
python app.py
```
- Access at: http://127.0.0.1:5000
- Features: User authentication, pose comparison with login

#### Option D: Run React Frontend
```bash
cd yoga-pose-frontend
npm start
```
- Access at: http://localhost:3000
- Features: Modern UI for pose management and comparison

## Detailed Setup and Usage

### Database Setup

The system uses SQLite databases:
- `poses.db` - Stores pose data and asanas
- `with_login/database.db` - Stores user accounts

Databases are automatically created on first run.

### Adding Poses

1. **Via API:**
   ```bash
   curl -X POST http://127.0.0.1:5000/upload_pose \
     -F "asana_name=Surya Namaskar" \
     -F "pose_name=Uttanasana" \
     -F "pose_number=2" \
     -F "image=@path/to/image.jpg"
   ```

2. **Via React Frontend:**
   - Start the React app
   - Navigate to "Add Pose" tab
   - Fill in asana name, pose name, number, and upload image

### Pose Comparison

1. **Live Comparison:**
   - Select an asana and reference pose
   - Allow camera access
   - Click "Start Live Comparison" for continuous feedback
   - Or use "Compare Once" for single comparison

2. **Tolerance Settings:**
   - Adjust tolerance percentage (5-50%) for pose matching sensitivity
   - Lower tolerance = stricter matching

### Running Multiple Components

To run the full system:

1. **Terminal 1 - API Server:**
   ```bash
   python api.py
   ```

2. **Terminal 2 - React Frontend:**
   ```bash
   cd yoga-pose-frontend
   npm start
   ```

3. **Terminal 3 - Poses App (optional):**
   ```bash
   cd poses
   python app.py
   ```

4. **Terminal 4 - With Login App (optional):**
   ```bash
   cd with_login
   python app.py
   ```

## Build Script

Use the included `build.py` script for automated setup:

```bash
python build.py
```

This script will:
- Create virtual environment
- Install Python dependencies
- Install Node.js dependencies
- Initialize databases
- Provide run commands

## Troubleshooting

### Common Issues

1. **Camera Access Denied:**
   - Ensure browser has camera permissions
   - Try running in HTTPS or localhost

2. **MediaPipe Import Error:**
   - Ensure all requirements are installed
   - Check Python version compatibility

3. **Database Errors:**
   - Delete existing .db files and restart
   - Check file permissions

4. **Port Conflicts:**
   - Change port in app.py files if 5000 is occupied
   - Update CORS origins in api.py

### Dependencies

Key Python packages:
- Flask - Web framework
- MediaPipe - Pose detection
- OpenCV - Image processing
- SQLite3 - Database

Key Node.js packages:
- React - Frontend framework
- Tailwind CSS - Styling

## API Documentation

### Endpoints

- `GET /asanas` - Returns list of asana names
- `GET /asanas/<name>` - Returns poses for specific asana
- `POST /upload_pose` - Upload new pose (form-data: asana_name, pose_name, pose_number, image)
- `POST /compare_pose` - Compare pose (form-data: new_image, asana_name, reference_pose_number, tolerance)
- `GET /uploads/<filename>` - Serve uploaded images

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and test
4. Submit a pull request

## License

This project is open source. See LICENSE file for details.
