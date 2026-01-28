#!/usr/bin/env python3
import socket, time, struct, math, csv, os

# ===== runtime config =====
PORT = 9999
MAGIC = 0xABCD1234
HDR   = struct.Struct(">I I H I H H")   # magic, seq, step, first_id, n, ssize
G_PER_LSB = 1.0/16384.0                 # ±2 g FS → g/LSB
FS = 32000.0                            # accel ODR (samples/s)

# Reordering / gap handling
REORDER_MAX = 2048
NO_PROGRESS_MS = 200

# CSV logging
LOG_ENABLE = True
LOG_PATH   = "icm_accel_stream.csv"     # new file each run
CSV_FLUSH_SEC = 1.0

# ===== socket =====
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32*1024*1024)
sock.bind(("0.0.0.0", PORT))
print(f"Listening on UDP/{PORT} …")

# ===== helpers =====
def seq_inc(x): return (x + 1) & 0xFFFFFFFF
def sdiff32(a, b):
    """signed 32-bit difference a-b"""
    d = ((a - b) & 0xFFFFFFFF)
    if d & 0x80000000: d -= 0x100000000
    return d

# ===== reorder buffers & stats =====
reorder = {}             # seq -> (first_id, n, ssize, payload)
parity_seen = set()      # for step==2 if you later re-enable parity
expected_seq = None
expected_id  = None
drops = 0

bytes_in = samp_in = 0
acc_norm_sum = 0.0
acc_norm_n   = 0
last_stat_t  = time.time()
dumped = 0
last_emit_t = time.time()

# sample-time base for CSV timestamps
t0_wall = None
emitted_total = 0  # total samples emitted since t0

# CSV
csvf = None
csvw = None
log_batch = []
last_csv_flush = time.time()

if LOG_ENABLE:
    csvf = open(LOG_PATH, "w", newline="")
    csvw = csv.writer(csvf)
    csvw.writerow(["t_wall_s", "sample_id", "ax_g", "ay_g", "az_g"])

def process_packet(first_id, n, ssize, payload):
    """Consume one in-order DATA packet, trim overlap, update stats & CSV."""
    global expected_id, drops, bytes_in, samp_in
    global acc_norm_sum, acc_norm_n, dumped, last_emit_t
    global t0_wall, emitted_total, log_batch

    need = n * ssize
    if len(payload) < need:
        return

    if expected_id is None:
        expected_id = first_id

    # true (forward) gap in sample IDs → count as drops
    d = sdiff32(first_id, expected_id)
    if d > 0:
        drops += d
        expected_id = first_id

    # overlap trim
    trim = sdiff32(expected_id, first_id)
    if trim >= n:
        return
    off0 = trim * ssize
    new_samples = n - trim

    bytes_in += HDR.size + need
    samp_in  += new_samples

    if dumped < 1:
        dumped += 1
        print(f"first frame: n={n} ssize={ssize} first_id={first_id} step=1")
        for i in range(min(3, n)):
            x,y,z = struct.unpack_from(">hhh", payload, i*ssize)
            print(f"  s[{i}] = ({x},{y},{z})")

    if t0_wall is None:
        t0_wall = time.time()
        emitted_total = 0

    # accumulate stats + CSV rows
    idx0 = emitted_total
    for i in range(new_samples):
        x,y,z = struct.unpack_from(">hhh", payload, off0 + i*ssize)
        ax = x*G_PER_LSB; ay = y*G_PER_LSB; az = z*G_PER_LSB
        acc_norm_sum += math.sqrt(ax*ax+ay*ay+az*az)
        acc_norm_n   += 1

        if LOG_ENABLE:
            t = t0_wall + (idx0 + i)/FS
            sid = (expected_id + i) & 0xFFFFFFFF
            log_batch.append((f"{t:.6f}", int(sid), f"{ax:.6f}", f"{ay:.6f}", f"{az:.6f}"))

    emitted_total += new_samples
    expected_id = (expected_id + new_samples) & 0xFFFFFFFF
    last_emit_t = time.time()

def fast_forward_if_stuck():
    """If no emit for NO_PROGRESS_MS and we buffered future packets, skip the head."""
    global expected_seq, drops, last_emit_t
    if expected_seq is None or not reorder:
        return False
    if (time.time() - last_emit_t) * 1000.0 < NO_PROGRESS_MS:
        return False
    # pick nearest available seq ahead (modulo)
    ahead = sorted(reorder.keys(), key=lambda k: (k - expected_seq) & 0xFFFFFFFF)
    head = ahead[0]
    fi, nn, ss, pl = reorder.pop(head)
    drops += nn                      # we skipped exactly one data packet
    process_packet(fi, nn, ss, pl)   # emit it
    expected_seq = seq_inc(head)
    return True

# ===== main loop =====
while True:
    pkt,_ = sock.recvfrom(65535)
    if len(pkt) < HDR.size:
        continue

    magic, seq, step, first_id, n, ssize = HDR.unpack_from(pkt, 0)
    if magic != MAGIC or ssize not in (6,12):
        continue
    payload = pkt[HDR.size:]
    if len(payload) < n*ssize:
        continue

    if step == 1:          # DATA
        reorder[seq] = (first_id, n, ssize, payload)
    elif step == 2:        # PARITY (unused for now)
        parity_seen.add(seq)
    else:
        continue

    if expected_seq is None:
        expected_seq = seq
        last_emit_t = time.time()

    # emit in order, skipping any parity seqs
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

    # if queue too large, fast-forward
    if len(reorder) > REORDER_MAX:
        ahead = sorted(reorder.keys(), key=lambda k: (k - expected_seq) & 0xFFFFFFFF)
        head = ahead[0]
        fi, nn, ss, pl = reorder.pop(head)
        drops += nn
        process_packet(fi, nn, ss, pl)
        expected_seq = seq_inc(head)

    # opportunistic fast-forward if stuck
    fast_forward_if_stuck()

    # 1 Hz stats + CSV flush
    now = time.time()
    if now - last_stat_t >= 1.0:
        mbit = (bytes_in*8.0)/(now-last_stat_t)/1e6
        sps  = samp_in/(now-last_stat_t) if (now-last_stat_t)>0 else 0.0
        mean_norm = (acc_norm_sum/acc_norm_n) if acc_norm_n else 0.0
        print(f"{mbit:5.2f} Mbit/s  {sps:7.0f} samp/s  |a|={mean_norm:.4f} g  drops={drops}  buf={len(reorder)}")
        bytes_in = samp_in = 0
        acc_norm_sum = 0.0; acc_norm_n = 0
        last_stat_t = now

        if LOG_ENABLE and log_batch and (now - last_csv_flush >= CSV_FLUSH_SEC):
            csvw.writerows(log_batch)
            log_batch.clear()
            csvf.flush()   # avoid fsync to reduce SD wear
            last_csv_flush = now
