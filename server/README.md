# Flask Server

This directory contains the Flask web server that receives sensor data from ESP32 devices.

## Structure

```
server/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── config/               # Configuration files
│   └── .env.example     # Environment variables template
├── static/              # Static files (CSS, JS, images)
└── templates/           # HTML templates
    └── index.html       # Dashboard page
```

## Setup

1. Install Python 3.7 or higher
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables (optional):
   ```bash
   cp config/.env.example config/.env
   # Edit .env with your settings
   ```

## Running the Server

```bash
python app.py
```

The server will start on `http://0.0.0.0:5000` by default.

## API Endpoints

### POST /api/sensor-data
Receive sensor data from ESP32.

**Request Body:**
```json
{
  "temperature": 25.5,
  "humidity": 60.2,
  "pressure": 1013.25,
  "timestamp": 123456789
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Data received successfully"
}
```

### GET /api/sensor-data?limit=100
Retrieve stored sensor data.

**Response:**
```json
{
  "status": "success",
  "count": 100,
  "data": [...]
}
```

### GET /api/sensor-data/latest
Get the most recent sensor reading.

**Response:**
```json
{
  "status": "success",
  "data": {
    "temperature": 25.5,
    "humidity": 60.2,
    "pressure": 1013.25,
    "timestamp": 123456789,
    "server_timestamp": "2024-01-12T09:00:00"
  }
}
```

### GET /health
Health check endpoint.

## Dashboard

Access the web dashboard at `http://localhost:5000/` to view real-time sensor data.

## Production Deployment

For production use:
1. Set `FLASK_DEBUG=False`
2. Use a production WSGI server (e.g., Gunicorn, uWSGI)
3. Implement a proper database instead of in-memory storage
4. Add authentication and security measures
5. Set up HTTPS
