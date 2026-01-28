// ==== ICM42688 → ESP32 → UDP (32 kSa/s accel, fixed-size frames + XOR parity) ====
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <SPI.h>

// --- Wi-Fi ---
static const char* WIFI_SSID = "yourSSIDhere";
static const char* WIFI_PASS = "yourpasswordhere";
static const char* DEST_IP   = "192.168.1.213";
static const uint16_t DEST_PORT = 9999;
static const uint16_t SRC_PORT  = 12345;

// --- VSPI pins (ESP32) ---
#define PIN_SCK   18
#define PIN_MISO  19
#define PIN_MOSI  23
#define PIN_CS     5

// --- ICM42688 (Bank 0) ---
#define REG_DEVICE_CONFIG      0x11
#define REG_FIFO_CONFIG        0x16
#define REG_FIFO_COUNTH       0x2E
#define REG_FIFO_COUNTL       0x2F
#define REG_FIFO_DATA         0x30
#define REG_PWR_MGMT0         0x4E
#define REG_GYRO_CONFIG0      0x4F
#define REG_ACCEL_CONFIG0     0x50
#define REG_FIFO_CONFIG1      0x5F
#define REG_FIFO_CONFIG2      0x60
#define REG_FIFO_CONFIG3      0x61
#define REG_SIGNAL_PATH_RESET 0x4B
#define REG_WHO_AM_I          0x75
#define WHOAMI_EXPECT         0x47

// --- Sensor config ---
#define ACCEL_ODR_NIBBLE  0x01    // 32 kSa/s (LN only)
#define ACCEL_FS_BITS     0x03    // ±2 g
#define FIFO_CFG_MODE     0x01    // stream-to-FIFO
#define FIFO_CFG1_MASK    0x05    // ACCEL + TEMP
#define FIFO_RESUME_BIT   (1<<6)  // resume partial read

// --- SPI ---
#define SPI_HZ_INIT 1000000
#define SPI_HZ_RUN  24000000   // 24 MHz is fine too; 40 MHz if wiring is short/clean

// --- UDP framing ---
#define UDP_MTU_PAY    1460
#define UDP_HDR_BYTES  18
static const uint8_t  SSIZE = 6;                     // we transmit XYZ only (6 bytes/sample)
static const uint16_t NSAMP_MAX = (UDP_MTU_PAY - UDP_HDR_BYTES) / SSIZE;

// --- FIFO / buffers ---
#define FIFO_BUF_MAX   2048
SPIClass spi(VSPI);
WiFiUDP   udp;

uint8_t fifo_buf[FIFO_BUF_MAX];
uint8_t out_pkt[UDP_HDR_BYTES + NSAMP_MAX*SSIZE];
uint8_t pkt_buf[UDP_HDR_BYTES + NSAMP_MAX*SSIZE];    // payload scratch (we use only the payload area)

uint32_t sent_samp_sec = 0, last_print = 0;

// --- XOR parity over K data packets ---
static const uint8_t  FEC_K = 4;                     // 4 data + 1 parity
uint8_t parity_buf[UDP_MTU_PAY];
uint8_t block_count = 0;
uint32_t block_base_seq = 0;

// --- counters/state ---
uint32_t seq = 0;          // packet sequence
uint32_t sample_id = 0;    // sample id of first sample in a DATA packet
bool imu_ok = false;

// --- helpers ---
inline void cs_lo(){ digitalWrite(PIN_CS, LOW); }
inline void cs_hi(){ digitalWrite(PIN_CS, HIGH); }
inline void be16(uint8_t* p, uint16_t v){ p[0]=v>>8; p[1]=v; }
inline void be32(uint8_t* p, uint32_t v){ p[0]=v>>24; p[1]=v>>16; p[2]=v>>8; p[3]=v; }

uint8_t rd8(uint8_t reg){ cs_lo(); spi.transfer(reg|0x80); uint8_t v=spi.transfer(0); cs_hi(); return v; }
void    wr8(uint8_t reg, uint8_t val){ cs_lo(); spi.transfer(reg&0x7F); spi.transfer(val); cs_hi(); }
void    rdbuf(uint8_t reg, uint8_t* dst, size_t n){ cs_lo(); spi.transfer(reg|0x80); for(size_t i=0;i<n;i++) dst[i]=spi.transfer(0); cs_hi(); }

void send_data_frame(const uint8_t* payload, uint16_t n_samples){
  uint8_t* p = out_pkt;
  be32(p+0,  0xABCD1234u);
  be32(p+4,  seq);
  be16(p+8,  1);                  // step=1 (DATA)
  be32(p+10, sample_id);
  be16(p+14, n_samples);
  be16(p+16, SSIZE);
  memcpy(p+UDP_HDR_BYTES, payload, n_samples*SSIZE);
  udp.beginPacket(DEST_IP, DEST_PORT);
  udp.write(out_pkt, UDP_HDR_BYTES + n_samples*SSIZE);
  udp.endPacket();
}

void send_parity_frame(const uint8_t* payload, uint32_t base_seq){
  uint8_t* p = out_pkt;
  be32(p+0,  0xABCD1234u);
  be32(p+4,  seq);
  be16(p+8,  2);                  // step=2 (PARITY)
  be32(p+10, base_seq);           // block base seq
  be16(p+14, FEC_K);              // n = K
  be16(p+16, SSIZE);
  memcpy(p+UDP_HDR_BYTES, payload, NSAMP_MAX*SSIZE);
  udp.beginPacket(DEST_IP, DEST_PORT);
  udp.write(out_pkt, UDP_HDR_BYTES + NSAMP_MAX*SSIZE);
  udp.endPacket();
}

void wifi_up(){
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setTxPower(WIFI_POWER_19dBm);
  while (WiFi.status()!=WL_CONNECTED) { delay(100); }
  udp.begin(SRC_PORT);
  Serial.printf("WiFi OK: SSID=%s  IP=%s  RSSI=%d dBm\n",
      WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI());
}

void icm_soft_reset(){ wr8(REG_DEVICE_CONFIG, 0x01); delay(2); }

bool icm_init(){
  // WHO_AM_I at low speed
  spi.endTransaction();
  spi.beginTransaction(SPISettings(SPI_HZ_INIT, MSBFIRST, SPI_MODE0));
  uint8_t who = rd8(REG_WHO_AM_I);
  Serial.printf("WHO_AM_I=0x%02X (expect 0x47)\n", who);
  if (who != WHOAMI_EXPECT) return false;

  // Switch to run speed (MODE0, 24 MHz)
  spi.endTransaction();
  spi.beginTransaction(SPISettings(SPI_HZ_RUN, MSBFIRST, SPI_MODE0));

  // 1) Power: Gyro LN + Accel LN (keeps PLL stable at 32k)
  wr8(REG_PWR_MGMT0, 0x0F);     // bits[3:2]=11 gyro LN, bits[1:0]=11 accel LN
  delay(5);
  // 2) Accel ±2g @ 32 kSa/s  -> 0x60 | 0x01 = 0x61
  wr8(REG_ACCEL_CONFIG0, 0x61);
  // 3) FIFO: stream-to-FIFO (0x01)
  wr8(REG_FIFO_CONFIG,  0x01);
  // 4) Route ACCEL only + resume partial read (0x01 | 0x40 = 0x41)
  wr8(REG_FIFO_CONFIG1, 0x41);
  // 5) Optional watermark ~1000 bytes
  wr8(REG_FIFO_CONFIG2, 1000 & 0xFF);
  wr8(REG_FIFO_CONFIG3, (1000 >> 8) & 0x0F);
  // 6) Flush FIFO once
  wr8(REG_SIGNAL_PATH_RESET, 1<<1); delayMicroseconds(50); wr8(REG_SIGNAL_PATH_RESET, 0);

  // Read back and verify; if wrong, re-write once
  uint8_t a0=rd8(REG_ACCEL_CONFIG0);
  uint8_t fc=rd8(REG_FIFO_CONFIG);
  uint8_t f1=rd8(REG_FIFO_CONFIG1);
  if (a0!=0x61 || (fc!=0x01 && fc!=0x40) || (f1&0x41)!=0x41) {
    Serial.printf("Re-write config (a0=%02X fc=%02X f1=%02X)\n", a0, fc, f1);
    wr8(REG_PWR_MGMT0, 0x0F); delay(5);
    wr8(REG_ACCEL_CONFIG0, 0x61);
    wr8(REG_FIFO_CONFIG,  0x01);
    wr8(REG_FIFO_CONFIG1, 0x41);
    wr8(REG_SIGNAL_PATH_RESET, 1<<1); delayMicroseconds(50); wr8(REG_SIGNAL_PATH_RESET, 0);
    a0=rd8(REG_ACCEL_CONFIG0); fc=rd8(REG_FIFO_CONFIG); f1=rd8(REG_FIFO_CONFIG1);
  }

  Serial.printf("ACCEL_CFG0=0x%02X  FIFO_CFG=0x%02X  FIFO_CFG1=0x%02X\n", a0, fc, f1);
  return (a0==0x61) && (fc==0x01 || fc==0x40) && ((f1&0x41)==0x41);
}


void setup(){
  Serial.begin(115200);
  pinMode(PIN_CS, OUTPUT); cs_hi();
  spi.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_CS);

  wifi_up();
  icm_soft_reset();
  imu_ok = icm_init();
  Serial.println(imu_ok ? "ICM FIFO streaming…" : "ICM init failed");
}

void loop(){
  static uint32_t empty_since=0; static bool flipped=false;

  if (!imu_ok) { delay(1000); return; }

  // Latch FIFO count
  uint16_t cnt = (uint16_t(rd8(REG_FIFO_COUNTH))<<8) | rd8(REG_FIFO_COUNTL);
  if (cnt < 8) {
    if (!empty_since) empty_since = millis();
    if (!flipped && millis()-empty_since > 500){
      uint8_t cur = rd8(REG_FIFO_CONFIG);
      uint8_t nxt = (cur==0x01) ? 0x40 : 0x01;
      wr8(REG_FIFO_CONFIG, nxt);
      wr8(REG_SIGNAL_PATH_RESET, 1<<1); delayMicroseconds(50); wr8(REG_SIGNAL_PATH_RESET, 0);
      Serial.printf("Flip FIFO_CONFIG %02X -> %02X (flush)\n", cur, nxt);
      flipped = true;
    }
    return;
  } else {
    empty_since = 0;
  }

  if (cnt > FIFO_BUF_MAX) cnt = FIFO_BUF_MAX;
  rdbuf(REG_FIFO_DATA, fifo_buf, cnt);

  const uint8_t* s = fifo_buf;
  uint16_t usable = cnt;
  static uint16_t fill = 0; // samples currently in pkt_buf

  while (usable >= 8) {
    uint8_t hdr = s[0];
    if (hdr & 0x80) { s+=1; usable-=1; continue; }    // empty MSG
    if (!(hdr & 0x40)) { s+=1; usable-=1; continue; } // no accel tag
    if (usable < 8) break;

    // copy XYZ (6 bytes)
    memcpy(&pkt_buf[fill*SSIZE], s+1, SSIZE);
    fill++;
    s += 8; usable -= 8;

    // when full, send DATA + update parity, maybe send PARITY
    if (fill == NSAMP_MAX) {
      // DATA
      send_data_frame(pkt_buf, NSAMP_MAX);

      sent_samp_sec += NSAMP_MAX;

      // start/accumulate parity
      if (block_count == 0) {
        block_base_seq = seq; // record first DATA seq in block
        memcpy(parity_buf, pkt_buf, NSAMP_MAX*SSIZE);
      } else {
        for (size_t i=0;i<NSAMP_MAX*SSIZE;i++) parity_buf[i] ^= pkt_buf[i];
      }
      block_count++;

      seq++;
      sample_id += NSAMP_MAX;
      fill = 0;

      // PARITY every FEC_K data pkts
      if (block_count == FEC_K) {
        send_parity_frame(parity_buf, block_base_seq);
        seq++;
        block_count = 0;
      }
    }
  }
  uint32_t now = millis();
if (now - last_print >= 1000) {
  last_print = now;
  uint8_t a0 = rd8(REG_ACCEL_CONFIG0);
  uint8_t fc = rd8(REG_FIFO_CONFIG);
  uint8_t f1 = rd8(REG_FIFO_CONFIG1);
  Serial.printf("TX=%lu samp/s   ACCEL_CFG0=%02X  FIFO_CFG=%02X  FIFO_CFG1=%02X\n",
                (unsigned long)sent_samp_sec, a0, fc, f1);
  sent_samp_sec = 0;
}
}
