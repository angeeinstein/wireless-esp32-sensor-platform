#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>

// WiFi credentials (override with build flags)
#ifndef WIFI_SSID
#define WIFI_SSID "your_wifi_ssid"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "your_wifi_password"
#endif

// Server configuration (override with build flags)
#ifndef SERVER_HOST
#define SERVER_HOST "192.168.1.100"
#endif

#ifndef SERVER_PORT
#define SERVER_PORT 5000
#endif

// Sensor data structure
struct SensorData {
  float temperature;
  float humidity;
  float pressure;
  unsigned long timestamp;
};

void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  const int maxAttempts = 30; // 15 seconds timeout
  
  while (WiFi.status() != WL_CONNECTED && attempts < maxAttempts) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("WiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("WiFi connection failed! Restarting...");
    delay(5000);
    ESP.restart();
  }
}

bool sendSensorData(const SensorData& data) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected!");
    return false;
  }
  
  HTTPClient http;
  
  // Construct URL
  String url = "http://" + String(SERVER_HOST) + ":" + String(SERVER_PORT) + "/api/sensor-data";
  
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  
  // Create JSON payload
  String jsonPayload = "{";
  jsonPayload += "\"temperature\":" + String(data.temperature, 2) + ",";
  jsonPayload += "\"humidity\":" + String(data.humidity, 2) + ",";
  jsonPayload += "\"pressure\":" + String(data.pressure, 2) + ",";
  jsonPayload += "\"timestamp\":" + String(data.timestamp);
  jsonPayload += "}";
  
  // Send POST request
  int httpResponseCode = http.POST(jsonPayload);
  
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("HTTP Response code: " + String(httpResponseCode));
    Serial.println("Response: " + response);
    http.end();
    return true;
  } else {
    Serial.println("Error sending data: " + String(httpResponseCode));
    http.end();
    return false;
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("ESP32 Sensor Platform Starting...");
  
  // Connect to WiFi
  connectWiFi();
}

void loop() {
  // Simulate sensor readings (replace with actual sensor code)
  SensorData data;
  data.temperature = random(200, 300) / 10.0;  // 20.0 to 30.0
  data.humidity = random(400, 600) / 10.0;     // 40.0 to 60.0
  data.pressure = random(9800, 10200) / 10.0;  // 980.0 to 1020.0
  data.timestamp = millis();
  
  // Send data to server
  Serial.println("Sending sensor data...");
  sendSensorData(data);
  
  // Wait 10 seconds before next reading
  delay(10000);
}
