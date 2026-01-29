# Production Deployment with Nginx + Gunicorn

This document explains the production-grade setup using Nginx as a reverse proxy and Gunicorn as the WSGI server.

## Deployment Profile

**Target Use Case**: Private network deployment
- **Sensors**: 1-3 ESP32 devices
- **Users**: Handful of simultaneous users (typically 2-5)
- **Network**: Internal/private network (optional internet exposure with VPN/auth)
- **Configuration**: Optimized for reliability over maximum throughput

## Architecture

```
ESP32 (UDP:9999) ──┐
                   │
                   ├──> Python UDP Receiver (Background Thread)
                   │           │
                   │           ├──> SQLite Database
                   │           └──> In-Memory Buffer
                   │
Client (HTTP) ──> Nginx (Port 80/443) ──> Gunicorn (Port 8000) ──> Flask App
                   │                              │
                   └──> Rate Limiting              └──> 4 Workers + 2 Threads each
```

## Why Nginx + Gunicorn?

### Gunicorn Benefits
- **Production WSGI server** - Flask's dev server is not suitable for production
- **Process-based workers** - Better CPU utilization on multi-core systems
- **Graceful restarts** - Zero-downtime deployments
- **Worker timeout protection** - Automatic restart of stuck workers
- **Better performance** - 2-3x throughput vs Flask dev server

### Nginx Benefits
- **Reverse proxy** - Load balancing, SSL termination
- **Static file serving** - Efficiently serves static assets
- **Rate limiting** - Prevents API abuse (100 req/s default)
- **Compression** - Automatic gzip compression
- **Security** - DDoS protection, request filtering
- **SSL/TLS** - Easy Let's Encrypt integration

## Configuration

### Gunicorn Settings
Located in: `/etc/systemd/system/esp32-sensor-server.service`

```ini
ExecStart=/opt/esp32-sensor/server/venv/bin/gunicorn \
    --bind 127.0.0.1:8000 \     # Listen on localhost only
    --workers 1 \                # MUST be 1 (UDP receiver limitation)
    --threads 4 \                # 4 threads (sufficient for handful of users)
    --worker-class gthread \     # Threaded worker class
    --timeout 120 \              # 120s timeout
    --access-logfile /var/log/esp32-sensor-server/access.log \
    --error-logfile /var/log/esp32-sensor-server/error.log \
    app:app
```

**⚠️ CRITICAL: Why Only 1 Worker?**

The UDP receiver runs as a background thread that binds to port 9999. Gunicorn's multi-process model means each worker is a **separate process** with its own:
- Thread pool
- Memory space
- UDP socket binding attempt

If we use multiple workers:
- ❌ Only ONE worker can bind to UDP port 9999 (others fail)
- ❌ No shared memory between workers (data not accessible across processes)
- ❌ Multiple database writer threads compete for locks
- ❌ `recent_samples` deque is duplicated per worker (not shared)

With 1 worker + 4 threads (for this private deployment):
- ✅ UDP receiver binds successfully
- ✅ All HTTP requests share the same data structures
- ✅ 4 concurrent HTTP requests (more than enough for 2-5 users)
- ✅ High-speed UDP reception unaffected
- ✅ Lower resource usage

**Thread Configuration:**
- **Worker**: 1 (required for UDP receiver)
- **Threads**: 4 (sufficient for handful of internal users)
- **Total capacity**: 4 concurrent HTTP requests
- **UDP reception**: Unaffected, runs at full 32 kHz

### Nginx Settings
Located in: `/etc/nginx/sites-available/esp32-sensor-server`

**Rate Limiting:**
- API endpoints: 500 requests/second (relaxed for internal network)
- Download endpoints: 50 requests/second
- Health check: No limit

These limits are intentionally relaxed since this is a private deployment. If you expose the server to the internet, consider tightening these limits.

**Timeouts:**
- Standard requests: 60 seconds
- API queries: 120 seconds
- Large exports: 300 seconds

**Security Headers:**
```nginx
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
```

## Performance Tuning

### Adjusting Thread Count

For your use case (handful of users), the default 4 threads is optimal. Only adjust if needed:

Edit `/etc/systemd/system/esp32-sensor-server.service`:

```bash
sudo systemctl stop esp32-sensor-server
sudo nano /etc/systemd/system/esp32-sensor-server.service
```

**For Minimal Load (1-2 users):**
```ini
ExecStart=... --workers 1 --threads 2 ...
```

**For Normal Load (2-5 users):**
```ini
ExecStart=... --workers 1 --threads 4 ...  # Default - recommended
```

**For Higher Load (5-10 users):**
```ini
ExecStart=... --workers 1 --threads 8 ...
```

**⚠️ Never increase workers beyond 1** - this will break UDP reception!

Reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl start esp32-sensor-server
```

### Future: Separate UDP Receiver Service

For true scalability with multiple Gunicorn workers, the UDP receiver should run as a separate service:

**Architecture:**
```
UDP Receiver Service (dedicated) → Redis/ZMQ → Multiple Gunicorn Workers
```

This would require:
1. Separate systemd service for UDP receiver
2. Shared state via Redis or message queue
3. Multiple Gunicorn workers for HTTP API

**Benefits:**
- Scale HTTP API independently
- UDP receiver isolation
- Better fault tolerance

**Implementation complexity:** Moderate (requires Redis/ZMQ setup)

## SSL/HTTPS Setup

### When to Enable HTTPS

- **Internal network only**: HTTPS optional (HTTP is fine)
- **Exposing to internet**: HTTPS strongly recommended
- **VPN access**: HTTPS optional (VPN provides encryption)

### Option 1: Let's Encrypt (For Internet-Exposed Servers)

Install certbot:
```bash
sudo apt-get install certbot python3-certbot-nginx
```

Obtain certificate (requires domain name):
```bash
sudo certbot --nginx -d your-domain.com
```

Certbot automatically:
- Updates Nginx configuration
- Sets up auto-renewal
- Configures HTTP → HTTPS redirect

### Option 2: Self-Signed Certificate

Generate certificate:
```bash
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/esp32-sensor.key \
    -out /etc/ssl/certs/esp32-sensor.crt
```

Edit `/etc/nginx/sites-available/esp32-sensor-server`:
```nginx
# Uncomment the HTTPS server block
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name _;
    
    ssl_certificate /etc/ssl/certs/esp32-sensor.crt;
    ssl_certificate_key /etc/ssl/private/esp32-sensor.key;
    
    # Rest of configuration...
}
```

Restart Nginx:
```bash
sudo systemctl restart nginx
```

### Option 3: Basic Authentication (For Internet Exposure)

If you expose the server to the internet without a VPN, add basic authentication:

Install htpasswd:
```bash
sudo apt-get install apache2-utils
```

Create user credentials:
```bash
sudo htpasswd -c /etc/nginx/.htpasswd username
# Enter password when prompted
```

Add more users:
```bash
sudo htpasswd /etc/nginx/.htpasswd another_user
```

Edit `/etc/nginx/sites-available/esp32-sensor-server`, add to server block:
```nginx
server {
    listen 80;
    
    # Add authentication
    auth_basic "ESP32 Sensor Platform";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    # Rest of configuration...
}
```

Restart Nginx:
```bash
sudo systemctl restart nginx
```

Now users must enter username/password to access the site.

### Recommended Setup for Internet Exposure

**Best**: VPN (WireGuard, OpenVPN) - Most secure, no authentication needed
**Good**: HTTPS + Basic Auth - Requires domain and SSL certificate  
**Minimum**: Basic Auth over HTTP - Simple but credentials sent in clear text

For your team's access, a VPN is the most secure and user-friendly option.

## Monitoring & Debugging

### Check Services Status

```bash
# Gunicorn backend
sudo systemctl status esp32-sensor-server

# Nginx
sudo systemctl status nginx
```

### View Logs

```bash
# Gunicorn access log
sudo tail -f /var/log/esp32-sensor-server/access.log

# Gunicorn error log
sudo tail -f /var/log/esp32-sensor-server/error.log

# Nginx access log
sudo tail -f /var/log/nginx/esp32-sensor-access.log

# Nginx error log
sudo tail -f /var/log/nginx/esp32-sensor-error.log

# Combined view
sudo journalctl -u esp32-sensor-server -u nginx -f
```

### Test Nginx Configuration

```bash
sudo nginx -t
```

### Reload Nginx (no downtime)

```bash
sudo systemctl reload nginx
```

### Graceful Restart Gunicorn

```bash
sudo systemctl reload esp32-sensor-server
```

## Performance Metrics

### Monitor Gunicorn Workers

```bash
# See worker processes
ps aux | grep gunicorn

# Monitor resource usage
htop -p $(pgrep -d',' -f gunicorn)
```

### Monitor Nginx

```bash
# Active connections
sudo netstat -an | grep :80 | wc -l

# Request rate
sudo tail -f /var/log/nginx/esp32-sensor-access.log | pv -l -i 1 > /dev/null
```

### Benchmark Performance

Using Apache Bench:
```bash
# Install
sudo apt-get install apache2-utils

# Test API endpoint
ab -n 1000 -c 10 http://localhost/api/stats

# Test with rate limiting
ab -n 10000 -c 50 http://localhost/api/stats
```

Expected results (for private deployment with 2-5 users):
- **HTTP requests**: 4 concurrent users handled comfortably
- **API response time**: <100ms for most queries
- **Large exports**: 2-5 seconds for 1 hour of data
- **UDP Reception**: Full 32 kHz unaffected by HTTP load
- **Database writes**: Real-time, no lag

## Troubleshooting

### Port 80 Already in Use

Find what's using it:
```bash
sudo netstat -tulpn | grep :80
sudo lsof -i :80
```

Common culprits:
- Apache2: `sudo systemctl stop apache2 && sudo systemctl disable apache2`
- Another Nginx instance: Check `/etc/nginx/sites-enabled/`

### 502 Bad Gateway

Means Nginx can't connect to Gunicorn.

Check if Gunicorn is running:
```bash
sudo systemctl status esp32-sensor-server
curl http://127.0.0.1:8000/health
```

Check Gunicorn logs:
```bash
sudo journalctl -u esp32-sensor-server -n 50
```

### 504 Gateway Timeout

Request took too long. Increase timeout in Nginx:

```nginx
location /api/ {
    proxy_read_timeout 300s;  # Increase to 5 minutes
    # ...
}
```

### Workers Crashing

Check error log:
```bash
sudo journalctl -u esp32-sensor-server -n 100
```

Common causes:
- Out of memory: Reduce workers
- Database locks: Check database queries
- Timeout: Increase worker timeout

### Rate Limiting Too Strict

Edit `/etc/nginx/sites-available/esp32-sensor-server`:

```nginx
# Increase rate limit
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=200r/s;

# Or remove rate limiting
location /api/ {
    # Comment out: limit_req zone=api_limit burst=20 nodelay;
    # ...
}
```

## Security Best Practices

1. **Always use HTTPS in production**
   ```bash
   sudo certbot --nginx
   ```

2. **Keep software updated**
   ```bash
   sudo apt-get update && sudo apt-get upgrade
   ```

3. **Configure firewall**
   ```bash
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

4. **Limit API access** (already configured via rate limiting)

5. **Regular backups**
   ```bash
   # Backup database
   sudo cp /opt/esp32-sensor/server/data/accelerometer.db ~/backup-$(date +%Y%m%d).db
   ```

6. **Monitor logs for suspicious activity**
   ```bash
   sudo tail -f /var/log/nginx/esp32-sensor-access.log | grep -E "40[34]|50[023]"
   ```

## Advanced Configuration

### Load Balancing (Multiple Gunicorn Instances)

Edit `/etc/nginx/sites-available/esp32-sensor-server`:

```nginx
upstream esp32_backend {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
}
```

### WebSocket Support (for real-time updates)

Already configured in Nginx:
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### Custom Domain

1. Point your domain's A record to your server's IP
2. Update Nginx configuration:
   ```nginx
   server_name yourdomain.com www.yourdomain.com;
   ```
3. Get SSL certificate:
   ```bash
   sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
   ```

## Resource Requirements

### For Your Use Case (1-3 sensors, handful of users)

**Raspberry Pi 3 or higher:**
- **RAM**: 1 GB minimum, 2 GB comfortable
- **Storage**: 16 GB SD card (8 GB for 24h retention)
- **Threads**: 4 (default)
- **Expected load**: 2-5 simultaneous users
- **UDP Reception**: Full 32 kHz per sensor (up to 3 sensors)

**Database Storage (per sensor at 32 kHz):**
- 1 hour: ~460 MB
- 24 hours: ~11 GB
- 1 week: ~77 GB (consider reducing retention)

**Network Requirements:**
- **Per sensor**: ~1.5 Mbps sustained UDP traffic
- **3 sensors**: ~4.5 Mbps total
- **Web users**: Negligible (~100 Kbps per user)

**Note**: UDP data reception is not affected by HTTP load. The 32 kHz sampling runs in a dedicated background thread.

## Support

For issues:
1. Check logs: `sudo journalctl -u esp32-sensor-server -n 100`
2. Test Nginx: `sudo nginx -t`
3. Check connectivity: `curl http://localhost:8000/health`
4. Verify firewall: `sudo ufw status`
