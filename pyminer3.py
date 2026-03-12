#!/usr/bin/env python3
"""
pyminer3 — Minimal Python 3 CPU Bitcoin miner (Stratum v1)

Educational / hobby use only. CPU mining Bitcoin is not profitable.
Based on the public pyminer concept by Jeff Garzik (GPL v2+).

Usage:
  python3 pyminer3.py --pool stratum+tcp://POOL:PORT --user WALLET.WORKER --pass x
"""

import argparse
import hashlib
import json
import socket
import struct
import sys
import threading
import time
from multiprocessing import Process, Event, Value


# ---------------------------------------------------------------------------
# Stratum client
# ---------------------------------------------------------------------------

class StratumClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.msg_id = 0
        self._lock = threading.Lock()
        self._buf = b""

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        self.sock.settimeout(600)

    def close(self):
        if self.sock:
            self.sock.close()

    def _send(self, msg):
        with self._lock:
            self.sock.sendall((json.dumps(msg) + "\n").encode())

    def _readline(self):
        while b"\n" not in self._buf:
            data = self.sock.recv(4096)
            if not data:
                raise ConnectionError("Pool closed connection")
            self._buf += data
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line.decode())

    def call(self, method, params):
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method, "params": params}
        self._send(msg)
        # read until we get our response (skip notifications)
        while True:
            resp = self._readline()
            if resp.get("id") == self.msg_id:
                return resp
            # queue mining.notify / mining.set_difficulty as side-effects
            if resp.get("method"):
                yield resp  # caller can iterate if needed
                continue
            return resp

    def subscribe(self):
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": "mining.subscribe", "params": ["pyminer3/0.1"]}
        self._send(msg)
        return self._readline()

    def authorize(self, user, password):
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": "mining.authorize", "params": [user, password]}
        self._send(msg)
        return self._readline()

    def submit(self, worker, job_id, extranonce2, ntime, nonce):
        self.msg_id += 1
        msg = {
            "id": self.msg_id,
            "method": "mining.submit",
            "params": [worker, job_id, extranonce2, ntime, nonce],
        }
        self._send(msg)

    def recv(self):
        return self._readline()


# ---------------------------------------------------------------------------
# Mining helpers
# ---------------------------------------------------------------------------

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def swap32(data: bytes) -> bytes:
    """Swap endianness of each 32-bit word."""
    return b"".join(
        struct.pack("<I", struct.unpack(">I", data[i : i + 4])[0])
        for i in range(0, len(data), 4)
    )


def build_merkle_root(coinbase_hash: bytes, merkle_branches: list[str]) -> bytes:
    root = coinbase_hash
    for branch in merkle_branches:
        root = sha256d(root + bytes.fromhex(branch))
    return root


def build_block_header(
    version: str,
    prev_hash: str,
    merkle_root: bytes,
    ntime: str,
    nbits: str,
) -> bytes:
    header = b""
    header += struct.pack("<I", int(version, 16))
    header += swap32(bytes.fromhex(prev_hash))
    header += merkle_root
    header += struct.pack("<I", int(ntime, 16))
    header += struct.pack("<I", int(nbits, 16))
    return header  # 76 bytes; nonce (4 bytes) appended during search


def target_from_difficulty(difficulty: float) -> int:
    """Convert pool difficulty to a 256-bit target."""
    max_target = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
    return int(max_target / difficulty)


# ---------------------------------------------------------------------------
# Nonce grinding (runs in a subprocess)
# ---------------------------------------------------------------------------

def miner_process(
    proc_id: int,
    header76: bytes,
    target: int,
    start_nonce: int,
    end_nonce: int,
    found_event_flag,      # multiprocessing.Value('b')
    result_nonce,           # multiprocessing.Value('I')
    hashes_done,            # multiprocessing.Value('L')
):
    static_hash = hashlib.sha256(header76)
    count = 0

    for nonce in range(start_nonce, end_nonce):
        if found_event_flag.value:
            break
        h = static_hash.copy()
        h.update(struct.pack("<I", nonce))
        first = h.digest()

        result = hashlib.sha256(first).digest()
        count += 1

        # quick reject: top 4 bytes must be zero for any plausible target
        if result[-4:] != b"\x00\x00\x00\x00":
            continue

        # full check
        val = int.from_bytes(result[::-1], "big")
        if val < target:
            with found_event_flag.get_lock():
                found_event_flag.value = 1
            result_nonce.value = nonce
            break

    with hashes_done.get_lock():
        hashes_done.value += count


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="pyminer3 — minimal Python 3 Stratum CPU miner")
    parser.add_argument("--pool", required=True, help="stratum+tcp://HOST:PORT")
    parser.add_argument("--user", required=True, help="WALLET.worker or pool username")
    parser.add_argument("--pass", dest="password", default="x", help="Pool password (default: x)")
    parser.add_argument("--threads", type=int, default=2, help="Number of mining threads")
    args = parser.parse_args()

    # Parse pool URL
    url = args.pool.replace("stratum+tcp://", "").replace("stratum://", "")
    if ":" not in url:
        print("Pool URL must include port, e.g. stratum+tcp://pool.example.com:3333")
        sys.exit(1)
    pool_host, pool_port = url.rsplit(":", 1)
    pool_port = int(pool_port)

    print(f"pyminer3 — connecting to {pool_host}:{pool_port}")
    print(f"Worker: {args.user} | Threads: {args.threads}\n")

    client = StratumClient(pool_host, pool_port)
    client.connect()

    # Subscribe
    sub = client.subscribe()
    if "error" in sub and sub["error"]:
        print("Subscribe error:", sub["error"])
        sys.exit(1)
    extranonce1 = sub["result"][1]
    extranonce2_size = sub["result"][2]
    print(f"Subscribed — extranonce1={extranonce1}, en2_size={extranonce2_size}")

    # Authorize
    auth = client.authorize(args.user, args.password)
    print(f"Authorize response: {auth}\n")

    # State
    current_job = None
    difficulty = 1.0
    extranonce2_counter = 0
    total_hashes = 0
    start_time = time.time()

    def process_notification(msg):
        nonlocal current_job, difficulty
        method = msg.get("method")
        if method == "mining.notify":
            p = msg["params"]
            current_job = {
                "job_id": p[0],
                "prevhash": p[1],
                "coinb1": p[2],
                "coinb2": p[3],
                "merkle": p[4],
                "version": p[5],
                "nbits": p[6],
                "ntime": p[7],
                "clean": p[8],
            }
            print(f"[{time.strftime('%H:%M:%S')}] New job: {current_job['job_id']}")
        elif method == "mining.set_difficulty":
            difficulty = msg["params"][0]
            print(f"[{time.strftime('%H:%M:%S')}] Difficulty set to {difficulty}")

    # Wait for first job
    while current_job is None:
        msg = client.recv()
        process_notification(msg)

    print("Mining started.\n")

    while True:
        job = current_job

        # Build coinbase
        extranonce2 = format(extranonce2_counter, f"0{extranonce2_size * 2}x")
        extranonce2_counter += 1
        coinbase_bin = bytes.fromhex(job["coinb1"] + extranonce1 + extranonce2 + job["coinb2"])
        coinbase_hash = sha256d(coinbase_bin)

        # Build header
        merkle_root = build_merkle_root(coinbase_hash, job["merkle"])
        header76 = build_block_header(
            job["version"], job["prevhash"], merkle_root, job["ntime"], job["nbits"]
        )
        target = target_from_difficulty(difficulty)

        # Partition nonce space across processes
        nonce_range = 0xFFFFFFFF
        chunk = nonce_range // args.threads
        found_flag = Value("b", 0)
        result_nonce = Value("I", 0)
        hashes_done = Value("L", 0)

        procs = []
        for i in range(args.threads):
            lo = i * chunk
            hi = lo + chunk if i < args.threads - 1 else nonce_range
            p = Process(
                target=miner_process,
                args=(i, header76, target, lo, hi, found_flag, result_nonce, hashes_done),
            )
            procs.append(p)
            p.start()

        # Poll for new work while mining
        client.sock.settimeout(0.5)
        while any(p.is_alive() for p in procs):
            try:
                msg = client.recv()
                process_notification(msg)
                if msg.get("method") == "mining.notify" and msg["params"][8]:
                    # clean jobs — abort current work
                    found_flag.value = 1
                    break
            except (socket.timeout, BlockingIOError):
                pass
            except json.JSONDecodeError:
                pass
            if found_flag.value:
                break
            time.sleep(0.1)

        for p in procs:
            p.join(timeout=2)
            if p.is_alive():
                p.terminate()

        total_hashes += hashes_done.value
        elapsed = time.time() - start_time
        rate = total_hashes / elapsed if elapsed > 0 else 0

        if found_flag.value and result_nonce.value != 0:
            nonce_hex = format(result_nonce.value, "08x")
            print(f"[{time.strftime('%H:%M:%S')}] Share found! nonce={nonce_hex}")
            client.sock.settimeout(30)
            client.submit(args.user, job["job_id"], extranonce2, job["ntime"], nonce_hex)
            # read submit response
            try:
                resp = client.recv()
                accepted = resp.get("result", False)
                print(f"  -> {'Accepted' if accepted else 'Rejected'}: {resp}")
            except Exception:
                pass

        print(f"  Hashrate: {rate / 1000:.1f} kH/s | Total: {total_hashes:,} hashes\n")
        client.sock.settimeout(600)

        # Check for queued notifications
        try:
            client.sock.settimeout(0.1)
            msg = client.recv()
            process_notification(msg)
        except (socket.timeout, BlockingIOError, json.JSONDecodeError):
            pass
        client.sock.settimeout(600)


if __name__ == "__main__":
    main()
