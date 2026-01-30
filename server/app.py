#!/usr/bin/env python3
"""
High-Speed Accelerometer Data Server
Receives 32 kHz accelerometer data via UDP and provides web API/dashboard
Uses SQLite for persistent storage with batched writes for high-speed operation
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime
import os
import socket
import struct
import math
import time
import threading
import csv
import sqlite3
import queue
import sys
import logging
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional, List

# Setup logging to stdout (captured by systemd)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ===== UDP RECEIVER CONFIGURATION =====
UDP_PORT = 9999
MAGIC = 0xABCD1234
HDR = struct.Struct(">I I H I H H")  # magic, seq, step, first_id, n, ssize
G_PER_LSB = 1.0 / 16384.0  # ±2 g FS → g/LSB
FS = 32000.0  # accel ODR (samples/s)

# Reordering / gap handling
REORDER_MAX = 2048
NO_PROGRESS_MS = 200

# CSV logging
LOG_ENABLE = True
LOG_PATH = "data/accel_stream.csv"
CSV_FLUSH_SEC = 1.0

# Database configuration
DB_PATH = "data/accelerometer.db"
DB_BATCH_SIZE = 5000  # Write every 5000 samples (156ms at 32kHz)
DB_RETENTION_HOURS = 24  # Keep last 24 hours of data (default)
DB_WRITE_QUEUE_MAX = 100000  # Max samples in write queue before backpressure

# ===== DATA STRUCTURES =====
@dataclass
class AccelSample:
    timestamp: float
    sample_id: int
    ax_g: float
    ay_g: float
    az_g: float

@dataclass
class StreamStats:
    mbit_per_sec: float
    samples_per_sec: float
    mean_accel_norm: float
    total_drops: int
    buffer_size: int
    total_samples: int
    uptime_sec: float
    is_receiving: bool

# Database stats cache
db_stats_cache = {
    'total_samples': 0,
    'min_time': 0,
    'max_time': 0,
    'last_update': 0
}
db_stats_lock = threading.Lock()

# ===== GLOBAL STATE =====
# Thread-safe storage for recent samples (last 10 seconds at 32kHz = 320k samples max)
# This provides fast access for real-time API queries
recent_samples = deque(maxlen=320000)
recent_samples_lock = threading.Lock()

# Database write queue (thread-safe queue for batched DB writes)
db_write_queue = queue.Queue(maxsize=DB_WRITE_QUEUE_MAX)
db_thread = None
db_running = False

# Current statistics
current_stats = StreamStats(
    mbit_per_sec=0.0,
    samples_per_sec=0.0,
    mean_accel_norm=0.0,
    total_drops=0,
    buffer_size=0,
    total_samples=0,
    uptime_sec=0.0,
    is_receiving=False
)
stats_lock = threading.Lock()

# UDP receiver state
udp_thread = None
udp_running = False
start_time = None

# ===== HELPER FUNCTIONS =====
def seq_inc(x):
    return (x + 1) & 0xFFFFFFFF

def sdiff32(a, b):
    """Signed 32-bit difference a-b"""
    d = ((a - b) & 0xFFFFFFFF)
    if d & 0x80000000:
        d -= 0x100000000
    return d

# ===== DATABASE FUNCTIONS =====
def init_database():
    """Initialize SQLite database with optimized settings for high-speed writes"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Enable WAL mode for concurrent reads during writes
    cursor.execute("PRAGMA journal_mode=WAL")
    
    # Increase cache size (10 MB)
    cursor.execute("PRAGMA cache_size=-10000")
    
    # Synchronous=NORMAL for better performance (still safe with WAL)
    cursor.execute("PRAGMA synchronous=NORMAL")
    
    # Check if old schema exists and migrate
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='samples'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        # Check if old schema (has timestamp column instead of timestamp_ms)
        cursor.execute("PRAGMA table_info(samples)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'timestamp' in columns and 'timestamp_ms' not in columns:
            print("[DB] Detected old schema, migrating to optimized format...")
            # Drop old table and recreate with new schema
            cursor.execute("DROP TABLE IF EXISTS samples")
            cursor.execute("DROP INDEX IF EXISTS idx_timestamp")
            cursor.execute("DROP INDEX IF EXISTS idx_sample_id")
            conn.commit()
            print("[DB] Old schema dropped")
    
    # Create optimized table with integer storage (preserves 18-bit sensor resolution)
    # Values stored as microunits (value × 1,000,000) to preserve precision
    # timestamp as milliseconds from epoch
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_ms INTEGER NOT NULL,
            sample_id INTEGER NOT NULL,
            ax_micro INTEGER NOT NULL,
            ay_micro INTEGER NOT NULL,
            az_micro INTEGER NOT NULL
        )
    """)
    
    # Index on timestamp for time-range queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp 
        ON samples(timestamp_ms)
    """)
    
    # Index on sample_id for sequence queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sample_id 
        ON samples(sample_id)
    """)
    
    conn.commit()
    conn.close()
    print(f"[DB] Database initialized: {DB_PATH}")
    print(f"[DB] Optimized schema active, batch size: {DB_BATCH_SIZE} samples")

def db_writer_thread():
    """Background thread that batches database writes for optimal performance"""
    global db_running
    
    print("[DB] Writer thread started")
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    batch = []
    last_write = time.time()
    last_cleanup = time.time()
    total_written = 0
    
    while db_running:
        try:
            # Get samples from queue (timeout to allow periodic writes and cleanup)
            try:
                sample = db_write_queue.get(timeout=0.1)
                batch.append((
                    int(sample.timestamp * 1000),  # Convert to milliseconds
                    sample.sample_id,
                    int(sample.ax_g * 1000000),  # Store as microunits (preserves 6 decimals)
                    int(sample.ay_g * 1000000),
                    int(sample.az_g * 1000000)
                ))
            except queue.Empty:
                sample = None
            
            # Write batch if full or timeout reached
            now = time.time()
            should_write = (len(batch) >= DB_BATCH_SIZE or 
                          (len(batch) > 0 and now - last_write > 1.0))
            
            if should_write:
                cursor.executemany(
                    "INSERT INTO samples (timestamp_ms, sample_id, ax_micro, ay_micro, az_micro) VALUES (?, ?, ?, ?, ?)",
                    batch
                )
                conn.commit()
                total_written += len(batch)
                
                if total_written % 50000 == 0:  # Log every 50k samples
                    print(f"[DB] Written {total_written} samples to database")
                
                batch.clear()
                last_write = now
            
            # Periodic cleanup of old data (every 5 minutes)
            if now - last_cleanup > 300:
                cleanup_old_data(cursor, conn)
                last_cleanup = now
                
        except Exception as e:
            print(f"[DB] Error in writer thread: {e}")
            time.sleep(1)
    
    # Flush remaining batch on shutdown
    if batch:
        try:
            cursor.executemany(
                "INSERT INTO samples (timestamp_ms, sample_id, ax_micro, ay_micro, az_micro) VALUES (?, ?, ?, ?, ?)",
                batch
            )
            conn.commit()
            print(f"[DB] Flushed final {len(batch)} samples")
        except Exception as e:
            print(f"[DB] Error flushing final batch: {e}")
    
    conn.close()
    print("[DB] Writer thread stopped")

def cleanup_old_data(cursor, conn):
    """Remove data older than retention period"""
    cutoff_ms = int((time.time() - (DB_RETENTION_HOURS * 3600)) * 1000)
    
    cursor.execute("SELECT COUNT(*) FROM samples WHERE timestamp_ms < ?", (cutoff_ms,))
    count = cursor.fetchone()[0]
    
    if count > 0:
        cursor.execute("DELETE FROM samples WHERE timestamp_ms < ?", (cutoff_ms,))
        conn.commit()
        print(f"[DB] Cleaned up {count} old samples (>{DB_RETENTION_HOURS}h)")
        
        # Optimize database after large deletions
        cursor.execute("VACUUM")
        print("[DB] Database optimized")

def get_db_connection():
    """Get a read-only database connection"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

# ===== UDP RECEIVER THREAD =====
def udp_receiver_thread():
    """High-speed UDP receiver running in background thread"""
    global udp_running, current_stats, recent_samples, start_time
    
    logger.info(f"UDP Starting receiver on port {UDP_PORT}...")
    
    # Setup socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)
    sock.settimeout(1.0)  # 1 second timeout to allow clean shutdown
    sock.bind(("0.0.0.0", UDP_PORT))
    
    logger.info(f"UDP Listening on UDP/{UDP_PORT}")
    
    # CSV logging
    csvf = None
    csvw = None
    log_batch = []
    last_csv_flush = time.time()
    
    if LOG_ENABLE:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        csvf = open(LOG_PATH, "w", newline="")
        csvw = csv.writer(csvf)
        csvw.writerow(["t_wall_s", "sample_id", "ax_g", "ay_g", "az_g"])
    
    # Reorder buffers & stats
    reorder = {}
    parity_seen = set()
    expected_seq = None
    expected_id = None
    drops = 0
    
    bytes_in = samp_in = 0
    acc_norm_sum = 0.0
    acc_norm_n = 0
    last_stat_t = time.time()
    last_log_t = time.time()  # Separate timer for logging
    last_emit_t = time.time()
    
    # Rolling window for smoothed rate calculations (1 second window)
    rate_window_size = 30  # 30 samples at 30 Hz = 1 second
    rate_window_bytes = deque(maxlen=rate_window_size)
    rate_window_samples = deque(maxlen=rate_window_size)
    rate_window_times = deque(maxlen=rate_window_size)
    
    # Sample-time base for timestamps
    t0_wall = None
    emitted_total = 0
    total_samples_global = 0
    
    start_time = time.time()
    
    def process_packet(first_id, n, ssize, payload):
        """Consume one in-order DATA packet"""
        nonlocal expected_id, drops, bytes_in, samp_in
        nonlocal acc_norm_sum, acc_norm_n, last_emit_t
        nonlocal t0_wall, emitted_total, log_batch, total_samples_global
        
        need = n * ssize
        if len(payload) < need:
            return
        
        if expected_id is None:
            expected_id = first_id
        
        # True gap in sample IDs → count as drops
        d = sdiff32(first_id, expected_id)
        if d > 0:
            drops += d
            expected_id = first_id
        
        # Overlap trim
        trim = sdiff32(expected_id, first_id)
        if trim >= n:
            return
        off0 = trim * ssize
        new_samples = n - trim
        
        bytes_in += HDR.size + need
        samp_in += new_samples
        
        if t0_wall is None:
            t0_wall = time.time()
            emitted_total = 0
        
        # Process samples
        idx0 = emitted_total
        samples_to_add = []
        
        for i in range(new_samples):
            x, y, z = struct.unpack_from(">hhh", payload, off0 + i * ssize)
            ax = x * G_PER_LSB
            ay = y * G_PER_LSB
            az = z * G_PER_LSB
            acc_norm_sum += math.sqrt(ax * ax + ay * ay + az * az)
            acc_norm_n += 1
            
            t = t0_wall + (idx0 + i) / FS
            sid = (expected_id + i) & 0xFFFFFFFF
            
            # Store sample
            sample = AccelSample(
                timestamp=t,
                sample_id=sid,
                ax_g=ax,
                ay_g=ay,
                az_g=az
            )
            samples_to_add.append(sample)
            
            # Queue for database write (non-blocking)
            try:
                db_write_queue.put_nowait(sample)
            except queue.Full:
                # Queue full - this means DB writer can't keep up
                # Skip this sample for DB (it's still in memory buffer)
                pass
            
            # CSV logging
            if LOG_ENABLE:
                log_batch.append((f"{t:.6f}", int(sid), f"{ax:.6f}", f"{ay:.6f}", f"{az:.6f}"))
        
        # Add samples to recent buffer (thread-safe)
        with recent_samples_lock:
            recent_samples.extend(samples_to_add)
        
        emitted_total += new_samples
        total_samples_global += new_samples
        expected_id = (expected_id + new_samples) & 0xFFFFFFFF
        last_emit_t = time.time()
    
    def fast_forward_if_stuck():
        """If no progress and buffered packets exist, skip ahead"""
        nonlocal expected_seq, drops, last_emit_t
        if expected_seq is None or not reorder:
            return False
        if (time.time() - last_emit_t) * 1000.0 < NO_PROGRESS_MS:
            return False
        
        ahead = sorted(reorder.keys(), key=lambda k: (k - expected_seq) & 0xFFFFFFFF)
        head = ahead[0]
        fi, nn, ss, pl = reorder.pop(head)
        drops += nn
        process_packet(fi, nn, ss, pl)
        expected_seq = seq_inc(head)
        return True
    
    # Main receiver loop
    print("[UDP] Receiver ready")
    
    while udp_running:
        try:
            pkt, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except Exception as e:
            if udp_running:
                print(f"[UDP] Socket error: {e}")
            break
        
        if len(pkt) < HDR.size:
            continue
        
        try:
            magic, seq, step, first_id, n, ssize = HDR.unpack_from(pkt, 0)
        except:
            continue
        
        if magic != MAGIC or ssize not in (6, 12):
            continue
        
        payload = pkt[HDR.size:]
        if len(payload) < n * ssize:
            continue
        
        if step == 1:  # DATA
            reorder[seq] = (first_id, n, ssize, payload)
        elif step == 2:  # PARITY
            parity_seen.add(seq)
        else:
            continue
        
        if expected_seq is None:
            expected_seq = seq
            last_emit_t = time.time()
        
        # Emit in order
        while True:
            if expected_seq in reorder:
                fi, nn, ss, pl = reorder.pop(expected_seq)
                process_packet(fi, nn, ss, pl)
                expected_seq = seq_inc(expected_seq)
                continue
            if expected_seq in parity_seen:
                parity_seen.discard(expected_seq)
                expected_seq = seq_inc(expected_seq)
                continue
            break
        
        # Queue overflow protection
        if len(reorder) > REORDER_MAX:
            ahead = sorted(reorder.keys(), key=lambda k: (k - expected_seq) & 0xFFFFFFFF)
            head = ahead[0]
            fi, nn, ss, pl = reorder.pop(head)
            drops += nn
            process_packet(fi, nn, ss, pl)
            expected_seq = seq_inc(head)
        
        # Opportunistic fast-forward
        fast_forward_if_stuck()
        
        # Update stats every 33ms (30 Hz) for smoother UI updates
        now = time.time()
        if now - last_stat_t >= 0.033:
            dt = now - last_stat_t
            
            # Add current interval to rolling window
            rate_window_bytes.append(bytes_in)
            rate_window_samples.append(samp_in)
            rate_window_times.append(dt)
            
            # Calculate smoothed rates over the entire window (1 second)
            total_bytes = sum(rate_window_bytes)
            total_samples = sum(rate_window_samples)
            total_time = sum(rate_window_times)
            
            mbit = (total_bytes * 8.0) / total_time / 1e6 if total_time > 0 else 0.0
            sps = total_samples / total_time if total_time > 0 else 0.0
            mean_norm = (acc_norm_sum / acc_norm_n) if acc_norm_n else 0.0
            
            with stats_lock:
                current_stats.mbit_per_sec = mbit
                current_stats.samples_per_sec = sps
                current_stats.mean_accel_norm = mean_norm
                current_stats.total_drops = drops
                current_stats.buffer_size = len(reorder)
                current_stats.total_samples = total_samples_global
                current_stats.uptime_sec = now - start_time
                current_stats.is_receiving = True
                
                # Emit stats update via WebSocket (30 Hz for smoother graphs)
                socketio.emit('stats_update', asdict(current_stats))
            
            # Get latest sample for real-time display
            with recent_samples_lock:
                if recent_samples:
                    latest = asdict(recent_samples[-1])
                    socketio.emit('sample_update', latest)
            
            # Log to console every second (keep logging at 1 Hz to avoid spam)
            if now - last_log_t >= 1.0:
                logger.info(f"UDP {mbit:5.2f} Mbit/s  {sps:7.0f} samp/s  |a|={mean_norm:.4f} g  "
                      f"drops={drops}  buf={len(reorder)}")
                last_log_t = now
            
            bytes_in = samp_in = 0
            acc_norm_sum = 0.0
            acc_norm_n = 0
            last_stat_t = now
            
            # CSV flush
            if LOG_ENABLE and log_batch and (now - last_csv_flush >= CSV_FLUSH_SEC):
                csvw.writerows(log_batch)
                log_batch.clear()
                csvf.flush()
                last_csv_flush = now
    
    # Cleanup
    sock.close()
    if csvf:
        if log_batch:
            csvw.writerows(log_batch)
        csvf.close()
    print("[UDP] Receiver stopped")

# ===== FLASK ROUTES =====
@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/settings')
def settings():
    """Render the settings page"""
    return render_template('settings.html')

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get current stream statistics"""
    with stats_lock:
        return jsonify({
            'status': 'success',
            'stats': asdict(current_stats)
        }), 200

@app.route('/api/samples/recent', methods=['GET'])
def get_recent_samples():
    """Get recent samples (last N seconds)"""
    try:
        seconds = request.args.get('seconds', default=1.0, type=float)
        seconds = max(0.1, min(seconds, 10.0))  # Clamp 0.1-10 seconds
        
        now = time.time()
        cutoff = now - seconds
        
        with recent_samples_lock:
            # Filter samples within time window
            filtered = [s for s in recent_samples if s.timestamp >= cutoff]
            
            # Downsample if too many points (max 10000 points for web display)
            if len(filtered) > 10000:
                step = len(filtered) // 10000
                filtered = filtered[::step]
            
            samples_dict = [asdict(s) for s in filtered]
        
        return jsonify({
            'status': 'success',
            'seconds': seconds,
            'count': len(samples_dict),
            'samples': samples_dict
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/samples/latest', methods=['GET'])
def get_latest_sample():
    """Get the most recent sample"""
    try:
        with recent_samples_lock:
            if not recent_samples:
                return jsonify({
                    'status': 'success',
                    'sample': None
                }), 200
            
            latest = recent_samples[-1]
        
        return jsonify({
            'status': 'success',
            'sample': asdict(latest)
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/samples/export', methods=['GET'])
def export_samples():
    """Export recent samples as CSV"""
    try:
        seconds = request.args.get('seconds', default=10.0, type=float)
        seconds = max(0.1, min(seconds, 3600.0))  # Max 1 hour
        
        now = time.time()
        cutoff = now - seconds
        
        # Try database first for larger exports
        if seconds > 10.0:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cutoff_ms = int(cutoff * 1000)
                cursor.execute(
                    "SELECT timestamp_ms, sample_id, ax_micro, ay_micro, az_micro FROM samples WHERE timestamp_ms >= ? ORDER BY timestamp_ms",
                    (cutoff_ms,)
                )
                rows = cursor.fetchall()
                conn.close()
                
                csv_lines = ["timestamp,sample_id,ax_g,ay_g,az_g"]
                for row in rows:
                    # Convert back from integer storage to floats
                    timestamp = row['timestamp_ms'] / 1000.0
                    ax_g = row['ax_micro'] / 1000000.0
                    ay_g = row['ay_micro'] / 1000000.0
                    az_g = row['az_micro'] / 1000000.0
                    csv_lines.append(f"{timestamp:.6f},{row['sample_id']},{ax_g:.6f},{ay_g:.6f},{az_g:.6f}")
                
            except Exception as e:
                print(f"[API] Database export failed, using memory: {e}")
                # Fallback to memory
                with recent_samples_lock:
                    filtered = [s for s in recent_samples if s.timestamp >= cutoff]
                
                csv_lines = ["timestamp,sample_id,ax_g,ay_g,az_g"]
                for s in filtered:
                    csv_lines.append(f"{s.timestamp:.6f},{s.sample_id},{s.ax_g:.6f},{s.ay_g:.6f},{s.az_g:.6f}")
        else:
            # Use memory for short exports
            with recent_samples_lock:
                filtered = [s for s in recent_samples if s.timestamp >= cutoff]
            
            csv_lines = ["timestamp,sample_id,ax_g,ay_g,az_g"]
            for s in filtered:
                csv_lines.append(f"{s.timestamp:.6f},{s.sample_id},{s.ax_g:.6f},{s.ay_g:.6f},{s.az_g:.6f}")
        
        csv_data = "\n".join(csv_lines)
        
        from flask import Response
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=accel_export_{int(now)}.csv"}
        )
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/samples/history', methods=['GET'])
def get_sample_history():
    """Query historical samples from database with time range and downsampling"""
    try:
        # Parse query parameters
        start_time = request.args.get('start_time', type=float)
        end_time = request.args.get('end_time', type=float)
        max_points = request.args.get('max_points', default=10000, type=int)
        
        if not start_time or not end_time:
            return jsonify({
                'status': 'error',
                'message': 'start_time and end_time required'
            }), 400
        
        max_points = max(100, min(max_points, 100000))  # Clamp 100-100k
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get total count in range
        cursor.execute(
            "SELECT COUNT(*) FROM samples WHERE timestamp >= ? AND timestamp <= ?",
            (start_time, end_time)
        )
        total_count = cursor.fetchone()[0]
        
        # Calculate downsampling factor
        if total_count > max_points:
            # Use every Nth sample
            step = total_count // max_points
            cursor.execute(
                f"""SELECT timestamp_ms, sample_id, ax_micro, ay_micro, az_micro 
                   FROM samples 
                   WHERE timestamp_ms >= ? AND timestamp_ms <= ? 
                   AND (rowid % {step}) = 0
                   ORDER BY timestamp_ms""",
                (int(start_time * 1000), int(end_time * 1000))
            )
        else:
            cursor.execute(
                "SELECT timestamp_ms, sample_id, ax_micro, ay_micro, az_micro FROM samples WHERE timestamp_ms >= ? AND timestamp_ms <= ? ORDER BY timestamp_ms",
                (int(start_time * 1000), int(end_time * 1000))
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        # Convert from integer storage to float values
        samples = []
        for row in rows:
            samples.append({
                'timestamp': row['timestamp_ms'] / 1000.0,
                'sample_id': row['sample_id'],
                'ax_g': row['ax_micro'] / 1000000.0,
                'ay_g': row['ay_micro'] / 1000000.0,
                'az_g': row['az_micro'] / 1000000.0
            })
        
        return jsonify({
            'status': 'success',
            'start_time': start_time,
            'end_time': end_time,
            'total_in_range': total_count,
            'returned': len(samples),
            'samples': samples
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/database/stats', methods=['GET'])
def get_database_stats():
    """Get database statistics (cached for performance)"""
    try:
        # Check if we should refresh the cache (every 10 seconds)
        now = time.time()
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        with db_stats_lock:
            cache_age = now - db_stats_cache['last_update']
            
            # Use cached data if less than 10 seconds old and not force refresh
            if cache_age < 10 and not force_refresh and db_stats_cache['last_update'] > 0:
                total_samples = db_stats_cache['total_samples']
                min_time = db_stats_cache['min_time']
                max_time = db_stats_cache['max_time']
            else:
                # Need to query database
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Use faster approximate count for large tables
                # For SQLite, we can use a faster method
                cursor.execute("SELECT COUNT(*) FROM samples")
                total_samples = cursor.fetchone()[0]
                
                # Time range - this is relatively fast with index
                cursor.execute("SELECT MIN(timestamp_ms), MAX(timestamp_ms) FROM samples")
                row = cursor.fetchone()
                min_time = (row[0] / 1000.0) if row[0] else 0
                max_time = (row[1] / 1000.0) if row[1] else 0
                
                conn.close()
                
                # Update cache
                db_stats_cache['total_samples'] = total_samples
                db_stats_cache['min_time'] = min_time
                db_stats_cache['max_time'] = max_time
                db_stats_cache['last_update'] = now
        
        # Database file size (fast operation)
        db_size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        
        # Queue status
        queue_size = db_write_queue.qsize()
        
        return jsonify({
            'status': 'success',
            'database': {
                'total_samples': total_samples,
                'min_timestamp': min_time,
                'max_timestamp': max_time,
                'time_span_hours': (max_time - min_time) / 3600 if max_time > min_time else 0,
                'size_mb': db_size_bytes / (1024 * 1024),
                'retention_hours': DB_RETENTION_HOURS,
                'write_queue_size': queue_size,
                'write_queue_max': DB_WRITE_QUEUE_MAX,
                'batch_size': DB_BATCH_SIZE
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/settings/retention', methods=['GET', 'POST'])
def manage_retention():
    """Get or set data retention period"""
    global DB_RETENTION_HOURS
    
    if request.method == 'GET':
        return jsonify({
            'status': 'success',
            'retention_hours': DB_RETENTION_HOURS
        }), 200
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            hours = data.get('retention_hours')
            
            if hours is None:
                return jsonify({'status': 'error', 'message': 'retention_hours required'}), 400
            
            hours = float(hours)
            if hours < 0:
                return jsonify({'status': 'error', 'message': 'retention_hours must be >= 0'}), 400
            
            DB_RETENTION_HOURS = hours
            logger.info(f"Data retention updated to {hours} hours")
            
            return jsonify({
                'status': 'success',
                'retention_hours': DB_RETENTION_HOURS,
                'message': f'Retention period set to {hours} hours'
            }), 200
            
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/database/diagnostics', methods=['GET'])
def database_diagnostics():
    """Get detailed database diagnostics to investigate size issues"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Basic stats
        total_samples = cursor.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        
        # Check for duplicate sample_ids
        duplicates = cursor.execute("""
            SELECT sample_id, COUNT(*) as count 
            FROM samples 
            GROUP BY sample_id 
            HAVING count > 1 
            LIMIT 10
        """).fetchall()
        
        # Get all indexes
        indexes = cursor.execute("""
            SELECT name, sql FROM sqlite_master 
            WHERE type='index' AND tbl_name='samples'
        """).fetchall()
        
        # Get all tables
        tables = cursor.execute("""
            SELECT name, sql FROM sqlite_master WHERE type='table'
        """).fetchall()
        
        # Check time span and calculate expected vs actual rate
        time_span = cursor.execute("""
            SELECT 
                MIN(timestamp_ms) / 1000.0 as min_ts,
                MAX(timestamp_ms) / 1000.0 as max_ts,
                (MAX(timestamp_ms) - MIN(timestamp_ms)) / 1000.0 as span_seconds
            FROM samples
        """).fetchone()
        
        # Page count and page size
        page_count = cursor.execute("PRAGMA page_count").fetchone()[0]
        page_size = cursor.execute("PRAGMA page_size").fetchone()[0]
        
        # Database size breakdown
        db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        
        # Check for WAL and SHM files
        wal_path = DB_PATH + "-wal"
        shm_path = DB_PATH + "-shm"
        wal_size_mb = os.path.getsize(wal_path) / (1024 * 1024) if os.path.exists(wal_path) else 0
        shm_size_mb = os.path.getsize(shm_path) / (1024 * 1024) if os.path.exists(shm_path) else 0
        
        conn.close()
        
        # Calculate expected size with optimized schema
        # New format: id(8) + timestamp_ms(8) + sample_id(4) + 3×accel(4 each) = 32 bytes per row
        bytes_per_row = 32
        expected_size_mb = (total_samples * bytes_per_row) / (1024 * 1024)
        
        avg_rate = total_samples / time_span[2] if time_span[2] > 0 else 0
        
        return jsonify({
            'success': True,
            'total_samples': total_samples,
            'duplicate_sample_ids': len(duplicates),
            'duplicate_examples': [{'sample_id': d[0], 'count': d[1]} for d in duplicates],
            'indexes': [{'name': idx[0], 'sql': idx[1]} for idx in indexes],
            'tables': [{'name': t[0], 'sql': t[1]} for t in tables],
            'time_span': {
                'min_timestamp': time_span[0],
                'max_timestamp': time_span[1],
                'span_seconds': time_span[2],
                'span_hours': round(time_span[2] / 3600, 2) if time_span[2] else 0
            },
            'sample_rate': {
                'average_hz': round(avg_rate, 0),
                'expected_hz': 32000
            },
            'file_sizes': {
                'db_mb': round(db_size_mb, 2),
                'wal_mb': round(wal_size_mb, 2),
                'shm_mb': round(shm_size_mb, 2),
                'total_mb': round(db_size_mb + wal_size_mb + shm_size_mb, 2)
            },
            'size_analysis': {
                'expected_raw_mb': round(expected_size_mb, 2),
                'actual_mb': round(db_size_mb, 2),
                'overhead_factor': round(db_size_mb / expected_size_mb, 2) if expected_size_mb > 0 else 0
            },
            'sqlite_internals': {
                'page_count': page_count,
                'page_size': page_size,
                'calculated_size_mb': round((page_count * page_size) / (1024 * 1024), 2)
            }
        })
        
    except Exception as e:
        logger.error(f"Diagnostics error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/database/cleanup', methods=['POST'])
def manual_cleanup():
    """Manually trigger database cleanup and optimization"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Count old data
        cutoff_ms = int((time.time() - (DB_RETENTION_HOURS * 3600)) * 1000)
        cursor.execute("SELECT COUNT(*) FROM samples WHERE timestamp_ms < ?", (cutoff_ms,))
        old_count = cursor.fetchone()[0]
        
        # Get total count before
        cursor.execute("SELECT COUNT(*) FROM samples")
        total_before = cursor.fetchone()[0]
        
        # Get file size before
        size_before = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        
        if old_count > 0:
            # Delete old data
            cursor.execute("DELETE FROM samples WHERE timestamp_ms < ?", (cutoff_ms,))
            conn.commit()
            logger.info(f"Cleanup: Deleted {old_count} old samples (>{DB_RETENTION_HOURS}h)")
        
        # Always run VACUUM to reclaim space
        cursor.execute("VACUUM")
        conn.commit()
        logger.info("Cleanup: VACUUM completed")
        
        # Get stats after
        cursor.execute("SELECT COUNT(*) FROM samples")
        total_after = cursor.fetchone()[0]
        
        conn.close()
        
        # Get file size after
        size_after = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        
        return jsonify({
            'status': 'success',
            'message': f'Cleanup complete',
            'samples_deleted': old_count,
            'samples_before': total_before,
            'samples_after': total_after,
            'size_before_mb': size_before / (1024 * 1024),
            'size_after_mb': size_after / (1024 * 1024),
            'space_reclaimed_mb': (size_before - size_after) / (1024 * 1024)
        }), 200
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/database/clear', methods=['POST'])
def clear_database():
    """Delete all data from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get count before deletion
        cursor.execute("SELECT COUNT(*) FROM samples")
        count_before = cursor.fetchone()[0]
        
        # Delete all samples
        cursor.execute("DELETE FROM samples")
        conn.commit()
        
        # Vacuum to reclaim space
        cursor.execute("VACUUM")
        
        conn.close()
        
        logger.info(f"Database cleared: {count_before} samples deleted")
        
        return jsonify({
            'status': 'success',
            'message': f'Deleted {count_before} samples',
            'samples_deleted': count_before
        }), 200
        
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/esp32/command', methods=['POST'])
def send_esp32_command():
    """Send command to ESP32 and return response"""
    try:
        import requests
        
        data = request.get_json()
        esp_ip = data.get('esp_ip')
        endpoint = data.get('endpoint', '/status')
        method = data.get('method', 'GET').upper()
        body = data.get('body')
        
        if not esp_ip:
            return jsonify({'status': 'error', 'message': 'esp_ip required'}), 400
        
        # Construct URL
        url = f"http://{esp_ip}{endpoint}"
        
        # Send request to ESP32
        if method == 'GET':
            response = requests.get(url, timeout=5)
        elif method == 'POST':
            response = requests.post(url, json=body, timeout=5)
        else:
            return jsonify({'status': 'error', 'message': f'Unsupported method: {method}'}), 400
        
        # Return ESP32 response
        try:
            response_json = response.json()
        except:
            response_json = {'raw_response': response.text}
        
        return jsonify({
            'status': 'success',
            'esp_status_code': response.status_code,
            'esp_response': response_json
        }), 200
        
    except requests.exceptions.Timeout:
        return jsonify({'status': 'error', 'message': 'ESP32 connection timeout'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'error', 'message': 'Cannot connect to ESP32'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    with stats_lock:
        is_healthy = current_stats.is_receiving
    
    return jsonify({
        'status': 'healthy' if is_healthy else 'degraded',
        'udp_receiver': 'running' if udp_running else 'stopped',
        'db_writer': 'running' if db_running else 'stopped',
        'db_queue_size': db_write_queue.qsize(),
        'timestamp': datetime.now().isoformat()
    }), 200

# ===== STARTUP/SHUTDOWN =====
def start_db_writer():
    """Start the database writer thread"""
    global db_thread, db_running
    
    if db_running:
        print("[Server] DB writer already running")
        return
    
    # Initialize database
    init_database()
    
    db_running = True
    db_thread = threading.Thread(target=db_writer_thread, daemon=True)
    db_thread.start()
    print("[Server] Database writer thread started")

def stop_db_writer():
    """Stop the database writer thread"""
    global db_running
    
    if not db_running:
        return
    
    print("[Server] Stopping database writer...")
    db_running = False
    if db_thread:
        db_thread.join(timeout=5.0)
    print("[Server] Database writer stopped")
def start_udp_receiver():
    """Start the UDP receiver thread"""
    global udp_thread, udp_running
    
    if udp_running:
        print("[Server] UDP receiver already running")
        return
    
    udp_running = True
    udp_thread = threading.Thread(target=udp_receiver_thread, daemon=True)
    udp_thread.start()
    print("[Server] UDP receiver thread started")

def stop_udp_receiver():
    """Stop the UDP receiver thread"""
    global udp_running
    
    if not udp_running:
        return
    
    print("[Server] Stopping UDP receiver...")
    udp_running = False
    if udp_thread:
        udp_thread.join(timeout=3.0)
    print("[Server] UDP receiver stopped")

# Initialize database and start background threads when module is loaded
# This ensures they start even when running under Gunicorn
init_database()
start_db_writer()
start_udp_receiver()
logger.info(f"Server Background threads started (UDP port {UDP_PORT}, DB batch size {DB_BATCH_SIZE})")

if __name__ == '__main__':
    # Get configuration from environment variables
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    print("========================================")
    print("High-Speed Accelerometer Data Server")
    print("========================================")
    print(f"Flask HTTP API: http://{host}:{port}")
    print(f"UDP Receiver:   UDP/{UDP_PORT}")
    print(f"Database:       {DB_PATH}")
    print(f"  - Batch size: {DB_BATCH_SIZE} samples")
    print(f"  - Retention:  {DB_RETENTION_HOURS} hours")
    print(f"Debug mode:     {debug}")
    print(f"CSV Logging:    {LOG_ENABLE} -> {LOG_PATH if LOG_ENABLE else 'disabled'}")
    print("========================================")
    
    try:
        app.run(host=host, port=port, debug=debug, use_reloader=False)
    except KeyboardInterrupt:
        print("\n[Server] Shutting down...")
    finally:
        stop_udp_receiver()
        stop_db_writer()
