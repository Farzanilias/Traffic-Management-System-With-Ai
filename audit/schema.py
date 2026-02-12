# audit/schema.py
def canonical_violation_payload(
    violation_id,
    license_plate,
    violation_type,
    fine_amount,
    location,
    timestamp,
    evidence_filename
):
    return {
        "violation_id": violation_id,
        "license_plate": license_plate,
        "violation_type": violation_type,
        "fine_amount": float(fine_amount),
        "location": location,
        "timestamp": timestamp.isoformat(),
        "evidence": evidence_filename
    }
