# Quick Start Guide

Get your ESP32 sensor platform up and running in minutes!

## Prerequisites

- ESP32 development board
- USB cable
- Computer with Python 3.7+ installed
- PlatformIO installed (via VS Code extension or CLI)
- WiFi network

## Step 1: Set Up the Flask Server

1. Open a terminal and navigate to the server directory:
   ```bash
   cd server
   ```

2. Create a Python virtual environment:
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - Linux/Mac: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Start the server:
   ```bash
   python app.py
   ```

6. Note your computer's IP address:
   - Linux/Mac: `ifconfig` or `ip addr`
   - Windows: `ipconfig`
   
   Look for your local network IP (e.g., 192.168.1.100)

7. Open a browser and go to `http://localhost:5000` to see the dashboard

## Step 2: Configure and Upload ESP32 Firmware

1. Open a new terminal and navigate to the firmware directory:
   ```bash
   cd firmware
   ```

2. Edit `platformio.ini` and update these lines:
   ```ini
   build_flags = 
       -D WIFI_SSID=\"YourWiFiName\"
       -D WIFI_PASSWORD=\"YourWiFiPassword\"
       -D SERVER_HOST=\"YourComputerIP\"
       -D SERVER_PORT=5000
   ```
   Replace:
   - `YourWiFiName` with your WiFi network name
   - `YourWiFiPassword` with your WiFi password
   - `YourComputerIP` with your computer's IP from Step 1.6

3. Connect your ESP32 via USB

4. Build and upload the firmware:
   ```bash
   pio run --target upload
   ```

5. Monitor the serial output:
   ```bash
   pio device monitor
   ```

## Step 3: Watch the Magic Happen! ✨

1. The ESP32 will connect to WiFi
2. It will start sending simulated sensor data every 10 seconds
3. Watch the Flask server console for incoming data
4. Refresh your browser dashboard to see real-time updates

## Troubleshooting

### ESP32 won't connect to WiFi
- Double-check WiFi credentials in platformio.ini
- Ensure ESP32 is within WiFi range
- Try 2.4GHz WiFi (ESP32 doesn't support 5GHz)

### Server connection failed
- Verify server is running and accessible
- Check firewall settings (allow port 5000)
- Ensure ESP32 and computer are on the same network
- Try pinging the server IP from another device

### Serial monitor shows errors
- Check USB cable and connection
- Try pressing the RST button on ESP32
- Verify the correct board is selected in platformio.ini

## Next Steps

1. **Add Real Sensors**: Replace simulated data with actual sensor readings
   - Popular choices: DHT22, BME280, BMP280
   - Add sensor libraries to `lib_deps` in platformio.ini

2. **Enhance the Dashboard**: 
   - Add charts and graphs in `server/templates/index.html`
   - Use Chart.js or Plotly for visualizations

3. **Add Data Persistence**:
   - Replace in-memory storage with SQLite or PostgreSQL
   - Implement data logging and historical analysis

4. **Improve Security**:
   - Add API authentication
   - Enable HTTPS
   - Store credentials securely

## Need Help?

- Check the README files in firmware/ and server/ directories
- Review the code comments in main.cpp and app.py
- Open an issue on GitHub

Happy coding! 🚀
