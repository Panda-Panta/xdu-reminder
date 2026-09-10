import os
import random

def generate_ids_browser_fingerprint() -> str:
    """Generates a random 32-char uppercase hex string (16 random bytes)."""
    return bytes(random.getrandbits(8) for _ in range(16)).hex().upper()

def get_or_create_ids_browser_fingerprint(data_dir: str) -> str:
    """Reads from file data_dir/fingerprint.txt, creates if missing."""
    file_path = os.path.join(data_dir, 'fingerprint.txt')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            fingerprint = f.read().strip()
            if len(fingerprint) == 32 and all(c in '0123456789ABCDEF' for c in fingerprint):
                return fingerprint
    
    fingerprint = generate_ids_browser_fingerprint()
    os.makedirs(data_dir, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(fingerprint)
    
    return fingerprint
