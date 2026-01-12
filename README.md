# Wireless ESP32 Sensor Platform

A complete IoT solution for collecting sensor data from ESP32 devices and visualizing it through a Flask web server.

## 🏗️ Project Structure

```
wireless-esp32-sensor-platform/
├── firmware/                    # ESP32 firmware (PlatformIO)
│   ├── platformio.ini          # PlatformIO configuration
│   ├── src/                    # Source files
│   │   └── main.cpp           # Main ESP32 application
│   ├── include/               # Header files
│   ├── lib/                   # Custom libraries
│   ├── test/                  # Unit tests
│   └── README.md              # Firmware documentation
│
├── server/                     # Flask web server
│   ├── app.py                 # Main Flask application
│   ├── requirements.txt       # Python dependencies
│   ├── config/               # Configuration files
│   │   └── .env.example     # Environment variables template
│   ├── static/              # Static files (CSS, JS, images)
│   ├── templates/           # HTML templates
│   │   └── index.html      # Dashboard page
│   └── README.md           # Server documentation
│
├── .gitignore               # Git ignore rules
└── README.md               # This file
```

## 🚀 Quick Start

### ESP32 Firmware Setup

1. Install [PlatformIO](https://platformio.org/install)
2. Navigate to the firmware directory:
   ```bash
   cd firmware
   ```
3. Configure WiFi and server settings in `platformio.ini`
4. Build and upload to ESP32:
   ```bash
   pio run --target upload
   ```
5. Monitor serial output:
   ```bash
   pio device monitor
   ```

See [firmware/README.md](firmware/README.md) for detailed instructions.

### Flask Server Setup

1. Navigate to the server directory:
   ```bash
   cd server
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the server:
   ```bash
   python app.py
   ```
5. Open your browser to `http://localhost:5000`

See [server/README.md](server/README.md) for detailed instructions.

## 📡 How It Works

1. **ESP32 Firmware**: 
   - Connects to WiFi network
   - Reads sensor data (temperature, humidity, pressure)
   - Sends data to Flask server via HTTP POST requests
   - Currently uses simulated data (replace with actual sensors)

2. **Flask Server**:
   - Receives sensor data via REST API
   - Stores data in memory (replace with database for production)
   - Provides web dashboard for real-time visualization
   - Exposes API endpoints for data retrieval

## 🔧 Configuration

### ESP32 Configuration

Edit `firmware/platformio.ini` to set:
- `WIFI_SSID`: Your WiFi network name
- `WIFI_PASSWORD`: Your WiFi password
- `SERVER_HOST`: Flask server IP address
- `SERVER_PORT`: Flask server port (default: 5000)

### Server Configuration

Create `server/config/.env` from the example:
```bash
cp server/config/.env.example server/config/.env
```

Edit as needed:
- `FLASK_HOST`: Server bind address (default: 0.0.0.0)
- `FLASK_PORT`: Server port (default: 5000)
- `FLASK_DEBUG`: Debug mode (default: False)

## 📊 API Endpoints

- `POST /api/sensor-data` - Receive sensor data from ESP32
- `GET /api/sensor-data?limit=100` - Get stored sensor data
- `GET /api/sensor-data/latest` - Get most recent reading
- `GET /health` - Health check endpoint
- `GET /` - Web dashboard

## 🔌 Adding Real Sensors

Replace the simulated sensor readings in `firmware/src/main.cpp` with actual sensor libraries:

**Popular sensor options:**
- **DHT22**: Temperature & Humidity
- **BME280**: Temperature, Humidity & Pressure
- **BMP280**: Temperature & Pressure
- **DS18B20**: Temperature

Add required libraries to `lib_deps` in `firmware/platformio.ini`.

## 🛠️ Development

### Prerequisites
- PlatformIO Core or PlatformIO IDE
- Python 3.7+
- ESP32 development board
- USB cable for programming

### Testing
- Firmware: Use PlatformIO unit testing framework
- Server: Add Python unit tests for API endpoints

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Support

For issues and questions, please open an issue on GitHub.