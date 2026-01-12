# ESP32 Firmware

This directory contains the PlatformIO-based firmware for the ESP32 sensor platform.

## Structure

```
firmware/
├── platformio.ini          # PlatformIO configuration
├── src/                    # Source files
│   └── main.cpp           # Main application code
├── include/               # Header files
├── lib/                   # Custom libraries
└── test/                  # Unit tests
```

## Setup

1. Install [PlatformIO](https://platformio.org/)
2. Configure WiFi and server settings in `platformio.ini` or `src/main.cpp`
3. Build the project: `pio run`
4. Upload to ESP32: `pio run --target upload`
5. Monitor serial output: `pio device monitor`

## Configuration

Update the following in `platformio.ini`:
- `WIFI_SSID`: Your WiFi network name
- `WIFI_PASSWORD`: Your WiFi password
- `SERVER_HOST`: Flask server IP address
- `SERVER_PORT`: Flask server port (default: 5000)

## Sensor Integration

Replace the simulated sensor readings in `main.cpp` with actual sensor library code:
- Temperature/Humidity: DHT22, BME280
- Pressure: BMP280, BME280
- Add libraries to `lib_deps` in `platformio.ini`
