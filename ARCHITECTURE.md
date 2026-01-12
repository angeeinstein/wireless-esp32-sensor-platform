# System Architecture

## Overview

This document describes the architecture of the Wireless ESP32 Sensor Platform.

## System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    SYSTEM ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐                    ┌──────────────────┐
│   ESP32 Device   │                    │  Flask Server    │
│                  │                    │                  │
│  ┌────────────┐  │                    │  ┌────────────┐  │
│  │  Sensors   │  │    WiFi Network    │  │   Web API  │  │
│  │  - Temp    │  │   ────────────────►│  │   Routes   │  │
│  │  - Humidity│  │   HTTP POST        │  └────────────┘  │
│  │  - Pressure│  │   JSON Data        │         │        │
│  └────────────┘  │                    │         ▼        │
│        │         │                    │  ┌────────────┐  │
│        ▼         │                    │  │  In-Memory │  │
│  ┌────────────┐  │                    │  │   Storage  │  │
│  │   WiFi     │  │                    │  └────────────┘  │
│  │  Manager   │  │                    │         │        │
│  └────────────┘  │                    │         ▼        │
│        │         │                    │  ┌────────────┐  │
│        ▼         │                    │  │   Web      │  │
│  ┌────────────┐  │                    │  │ Dashboard  │  │
│  │   HTTP     │  │                    │  └────────────┘  │
│  │  Client    │  │                    │                  │
│  └────────────┘  │                    │                  │
└──────────────────┘                    └──────────────────┘
         │                                        ▲
         │                                        │
         │         HTTP GET (Web Browser)         │
         └────────────────────────────────────────┘
```

## Data Flow

### 1. Sensor Reading (ESP32)
```
Sensors → Read Data → Format JSON → WiFi Module
```

### 2. Data Transmission (ESP32 → Server)
```
HTTP Client → POST Request → JSON Payload → Server API
```

**Endpoint**: `POST http://SERVER_IP:5000/api/sensor-data`

**Payload**:
```json
{
  "temperature": 25.5,
  "humidity": 60.2,
  "pressure": 1013.25,
  "timestamp": 123456789
}
```

### 3. Data Processing (Server)
```
API Endpoint → Validate Data → Store in Memory → Return Response
```

### 4. Data Visualization (Web Browser)
```
Browser → GET Request → Server API → JSON Response → Update Dashboard
```

## Communication Protocol

### ESP32 → Server

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/sensor-data` | Send sensor readings |

### Browser → Server

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Load dashboard |
| GET | `/api/sensor-data/latest` | Get latest reading |
| GET | `/api/sensor-data?limit=N` | Get N recent readings |
| GET | `/health` | Server health check |

## Network Configuration

### ESP32 Requirements
- WiFi 2.4GHz support
- HTTP client capability
- JSON serialization

### Server Requirements
- Python 3.7+
- Flask web framework
- Network accessibility from ESP32

### Network Setup
1. ESP32 and Server must be on the same network (or server must be publicly accessible)
2. Firewall must allow incoming connections on port 5000
3. Static IP recommended for server (or use mDNS/DNS)

## Security Considerations

### Current Implementation (Development)
- ⚠️ No authentication
- ⚠️ HTTP (unencrypted)
- ⚠️ No input sanitization
- ⚠️ In-memory storage (data loss on restart)

### Production Recommendations
- ✅ Add API key authentication
- ✅ Use HTTPS with SSL/TLS
- ✅ Implement input validation and sanitization
- ✅ Use persistent database (PostgreSQL, MongoDB)
- ✅ Add rate limiting
- ✅ Implement proper error handling
- ✅ Use environment variables for secrets
- ✅ Add logging and monitoring

## Scalability

### Current Limitations
- Single ESP32 device
- In-memory storage (limited capacity)
- No data persistence
- Single-threaded Flask server

### Scaling Options
1. **Multiple Devices**: Add device ID to data payload
2. **Database**: Replace in-memory storage with PostgreSQL/MongoDB
3. **Message Queue**: Add Redis/RabbitMQ for buffering
4. **Production Server**: Use Gunicorn/uWSGI + Nginx
5. **Cloud Deployment**: Deploy to AWS/Azure/GCP
6. **Time-Series DB**: Use InfluxDB for sensor data

## Technology Stack

### ESP32 Firmware
- **Language**: C++
- **Framework**: Arduino
- **Platform**: PlatformIO
- **Key Libraries**: 
  - WiFi.h (ESP32 WiFi)
  - HTTPClient.h (HTTP requests)

### Flask Server
- **Language**: Python 3.7+
- **Framework**: Flask
- **Key Libraries**:
  - Flask (web framework)
  - Flask-CORS (cross-origin requests)
  - python-dotenv (environment variables)

### Web Dashboard
- **Frontend**: HTML5 + CSS3 + JavaScript
- **API**: RESTful JSON
- **Updates**: Polling (2-second interval)

## File Structure Reference

```
wireless-esp32-sensor-platform/
├── firmware/              # ESP32 code
│   ├── platformio.ini    # Build configuration
│   ├── src/main.cpp      # Main application
│   ├── include/          # Header files
│   ├── lib/              # Custom libraries
│   └── test/             # Unit tests
│
├── server/               # Flask server
│   ├── app.py           # Main application
│   ├── requirements.txt # Dependencies
│   ├── config/          # Configuration
│   ├── static/          # Static assets
│   └── templates/       # HTML templates
│
├── README.md            # Project documentation
├── QUICKSTART.md        # Setup guide
└── ARCHITECTURE.md      # This file
```

## Future Enhancements

1. **Data Visualization**
   - Add charts (Chart.js, Plotly)
   - Historical data graphs
   - Export data (CSV, JSON)

2. **Advanced Features**
   - Email/SMS alerts
   - Data analytics
   - Machine learning predictions
   - Mobile app

3. **Device Management**
   - OTA (Over-The-Air) updates
   - Remote configuration
   - Device status monitoring
   - Multi-device support

4. **Integration**
   - MQTT support
   - Home Assistant integration
   - InfluxDB + Grafana
   - Cloud IoT platforms
