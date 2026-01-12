from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# In-memory storage for sensor data (replace with database in production)
sensor_data_store = []

@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/api/sensor-data', methods=['POST'])
def receive_sensor_data():
    """Endpoint to receive sensor data from ESP32"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['temperature', 'humidity', 'pressure', 'timestamp']
        if not all(field in data for field in required_fields):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields'
            }), 400
        
        # Add server timestamp
        data['server_timestamp'] = datetime.now().isoformat()
        
        # Store data (append to in-memory list)
        sensor_data_store.append(data)
        
        # Keep only last 1000 entries to prevent memory overflow
        if len(sensor_data_store) > 1000:
            sensor_data_store.pop(0)
        
        print(f"Received sensor data: Temp={data['temperature']}°C, "
              f"Humidity={data['humidity']}%, Pressure={data['pressure']}hPa")
        
        return jsonify({
            'status': 'success',
            'message': 'Data received successfully'
        }), 200
        
    except Exception as e:
        print(f"Error processing sensor data: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/sensor-data', methods=['GET'])
def get_sensor_data():
    """Endpoint to retrieve stored sensor data"""
    try:
        # Get query parameters for filtering
        limit = request.args.get('limit', default=100, type=int)
        
        # Return the last 'limit' entries
        return jsonify({
            'status': 'success',
            'count': len(sensor_data_store[-limit:]),
            'data': sensor_data_store[-limit:]
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/sensor-data/latest', methods=['GET'])
def get_latest_sensor_data():
    """Endpoint to retrieve the latest sensor reading"""
    try:
        if not sensor_data_store:
            return jsonify({
                'status': 'success',
                'data': None
            }), 200
        
        return jsonify({
            'status': 'success',
            'data': sensor_data_store[-1]
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    }), 200

if __name__ == '__main__':
    # Get configuration from environment variables
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"Starting Flask server on {host}:{port}")
    print(f"Debug mode: {debug}")
    
    app.run(host=host, port=port, debug=debug)
