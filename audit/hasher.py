import hashlib
import json

def hash_violation(payload: dict) ->str:
    canonical_json=json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical_json.encode()).hexdigest()