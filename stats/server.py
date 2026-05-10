#!/usr/bin/env python3
"""Lightweight stats API — reads /proc and /sys, serves JSON on port 8080.
Logs CPU temp every second to /logs/temp.log and returns 15-min min/max."""

from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import deque
import json, os, time, socket, struct


LOG_FILE      = '/logs/temp.log'
HISTORY_SEC   = 15 * 60       # 15 minutes in-memory
HISTORY_24H   = 24 * 3600     # 24 hours on disk


# ── In-memory history: deque of (unix_timestamp, temp_celsius) ──────────────

temp_history = deque()


def load_history():
    """Populate in-memory history from log file on startup."""
    if not os.path.exists(LOG_FILE):
        return
    cutoff = time.time() - HISTORY_SEC
    try:
        with open(LOG_FILE) as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 2:
                    ts, temp = float(parts[0]), float(parts[1])
                    if ts >= cutoff:
                        temp_history.append((ts, temp))
    except Exception:
        pass


def append_log(temp):
    if temp is None:
        return
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(f"{time.time():.1f},{temp}\n")
    except Exception:
        pass


def trim_history():
    """Drop entries older than 15 minutes from the in-memory deque."""
    cutoff = time.time() - HISTORY_SEC
    while temp_history and temp_history[0][0] < cutoff:
        temp_history.popleft()


def history_stats():
    trim_history()
    values = [t for _, t in temp_history]
    if not values:
        return None, None
    return round(min(values), 1), round(max(values), 1)


# ── System stats readers ─────────────────────────────────────────────────────

def cpu_percent():
    def read_stat():
        with open('/host/proc/stat') as f:
            parts = f.readline().split()[1:]
        vals = list(map(int, parts))
        return vals[3], sum(vals)  # idle, total

    idle1, total1 = read_stat()
    time.sleep(0.1)
    idle2, total2 = read_stat()
    delta_total = total2 - total1
    if delta_total == 0:
        return 0.0
    return round(100 * (1 - (idle2 - idle1) / delta_total), 1)


def mem_info():
    info = {}
    with open('/host/proc/meminfo') as f:
        for line in f:
            key, val = line.split(':')
            info[key.strip()] = int(val.strip().split()[0])
    total     = info['MemTotal']
    available = info['MemAvailable']
    used      = total - available
    return {
        'total_mb': total // 1024,
        'used_mb':  used  // 1024,
        'percent':  round(100 * used / total, 1),
    }


def cpu_temp():
    try:
        base = '/host/sys/class/hwmon'
        for hwmon in os.listdir(base):
            name_file = os.path.join(base, hwmon, 'name')
            if not os.path.exists(name_file):
                continue
            with open(name_file) as f:
                name = f.read().strip()
            if name in ('k10temp', 'coretemp'):
                temp_file = os.path.join(base, hwmon, 'temp1_input')
                if os.path.exists(temp_file):
                    with open(temp_file) as f:
                        return round(int(f.read().strip()) / 1000, 1)
        return None
    except Exception:
        return None


def history_24h():
    """Read log file, return 1-per-minute averages for the last 24 h."""
    if not os.path.exists(LOG_FILE):
        return []
    cutoff  = time.time() - HISTORY_24H
    buckets = {}  # minute_boundary -> [temps]
    try:
        with open(LOG_FILE) as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) != 2:
                    continue
                ts, temp = float(parts[0]), float(parts[1])
                if ts < cutoff:
                    continue
                minute = int(ts // 60) * 60
                buckets.setdefault(minute, []).append(temp)
    except Exception:
        return []
    return [[ts, round(sum(v) / len(v), 1)] for ts, v in sorted(buckets.items())]


# ── Minecraft server list ping ───────────────────────────────────────────────

def _varint(n):
    buf = b''
    while True:
        part = n & 0x7F
        n >>= 7
        if n:
            part |= 0x80
        buf += bytes([part])
        if not n:
            break
    return buf

def _read_varint(sock):
    n, shift = 0, 0
    while True:
        b = sock.recv(1)
        if not b:
            raise EOFError()
        b = b[0]
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n
        shift += 7

def mc_ping(host='minecraft', port=25565, timeout=3):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        host_b = host.encode()
        handshake = (
            _varint(0x00) +
            _varint(-1) +                   # protocol version (any)
            _varint(len(host_b)) + host_b +
            struct.pack('>H', port) +
            _varint(1)                       # next state: status
        )
        s.sendall(_varint(len(handshake)) + handshake)
        s.sendall(b'\x01\x00')              # status request

        length = _read_varint(s)
        data = b''
        while len(data) < length:
            chunk = s.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        s.close()

        # skip packet id varint, then read string length varint
        i = 0
        while data[i] & 0x80:
            i += 1
        i += 1
        n, shift = 0, 0
        while True:
            b = data[i]; i += 1
            n |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7

        info = json.loads(data[i:i + n])
        return {
            'online': True,
            'players_online': info.get('players', {}).get('online', 0),
            'players_max':    info.get('players', {}).get('max', 0),
        }
    except Exception:
        return {'online': False, 'players_online': 0, 'players_max': 0}


# ── HTTP handler ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # suppress access logs

    def _send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith('/minecraft'):
            self._send_json(mc_ping())
            return

        if self.path.endswith('/history24h'):
            self._send_json(history_24h())
            return

        if self.path.endswith('/history'):
            trim_history()
            self._send_json([[round(ts, 1), t] for ts, t in temp_history])
            return

        temp     = cpu_temp()
        temp_min, temp_max = history_stats()

        # Log and store reading
        if temp is not None:
            temp_history.append((time.time(), temp))
            append_log(temp)
            trim_history()

        self._send_json({
            'cpu_percent':  cpu_percent(),
            'memory':       mem_info(),
            'cpu_temp':     temp,
            'temp_min_15m': temp_min,
            'temp_max_15m': temp_max,
        })


if __name__ == '__main__':
    load_history()
    print(f"Stats API running on :8080 — logging temps to {LOG_FILE}")
    HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
