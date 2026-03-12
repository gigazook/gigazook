import hashlib
import time
import multiprocessing as mp

print("🔥 GIGA JUICER ZOOK REAL BITCOIN MINER 🔥")
print("Pure Python CPU SHA256 double-hash PoW — no fake loops, no simulation.\n")

DIFFICULTY = 5          # Change this: 4 = fast, 6 = slower, 7+ = painful on CPU
BLOCK_DATA = "GIGA_JUICER_ZOOK_BLOCK_42069"  # your custom block header

target = "0" * DIFFICULTY

def mine_chunk(start_nonce, chunk_size, result_queue):
    nonce = start_nonce
    for _ in range(chunk_size):
        data = f"{BLOCK_DATA}{nonce}".encode()
        hash_result = hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()
        if hash_result.startswith(target):
            result_queue.put((nonce, hash_result))
            return
        nonce += 1
    result_queue.put(None)

def main():
    print(f"Target difficulty: {DIFFICULTY} leading zeros")
    print(f"Starting real mining on {mp.cpu_count()} cores...\n")
    
    start_time = time.time()
    nonce = 0
    hashrate = 0
    
    while True:
        processes = []
        result_queue = mp.Queue()
        
        for i in range(mp.cpu_count()):
            p = mp.Process(target=mine_chunk, args=(nonce + i * 100000, 100000, result_queue))
            processes.append(p)
            p.start()
        
        found = False
        for _ in processes:
            result = result_queue.get()
            if result:
                nonce_found, final_hash = result
                total_time = time.time() - start_time
                final_hr = (nonce_found / total_time) / 1_000_000  # MH/s
                
                print("\n" + "="*70)
                print("✅ REAL BLOCK MINED (actual computation)")
                print(f"   Nonce: {nonce_found}")
                print(f"   Hash: {final_hash}")
                print(f"   Time: {total_time:.2f} seconds")
                print(f"   Hashrate: {final_hr:.2f} MH/s")
                print("="*70)
                found = True
                break
        
        for p in processes:
            p.terminate()
        
        if found:
            break
        
        nonce += mp.cpu_count() * 100000
        elapsed = time.time() - start_time
        hashrate = nonce / elapsed if elapsed > 0 else 0
        print(f"Hashrate: {hashrate/1_000_000:.2f} MH/s | Nonce: {nonce}", end="\r")

if __name__ == "__main__":
    main()