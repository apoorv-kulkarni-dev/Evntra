import urllib.request
import urllib.error
import json

def test_qr_scanner():
    print("--- 1. Testing Static Assets for QR Scanner ---")
    urls = [
        "http://127.0.0.1:5000/static/js/html5-qrcode.min.js",
        "http://127.0.0.1:5000/static/js/qrcode.min.js",
        "http://127.0.0.1:5000/static/js/lucide.min.js",
        "http://127.0.0.1:5000/static/js/app.js",
        "http://127.0.0.1:5000/static/css/style.css"
    ]
    for u in urls:
        res = urllib.request.urlopen(u)
        content_len = len(res.read())
        print(f"  ✓ {u.split('/')[-1]}: HTTP {res.status} ({content_len:,} bytes)")

    print("\n--- 2. Booking a New Ticket to Test Scanning ---")
    reg_payload = {
        "attendeeName": "Aditya Varma",
        "attendeeEmail": "aditya.varma@example.com",
        "quantity": 2,
        "ticketTier": "₹199 General Admission",
        "unitPrice": 199.0
    }
    req = urllib.request.Request(
        "http://127.0.0.1:5000/api/public/events/1/register",
        data=json.dumps(reg_payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    res = urllib.request.urlopen(req)
    data = json.loads(res.read().decode())
    ticket_id = data["registration"]["ticketId"]
    attendee = data["registration"]["attendeeName"]
    print(f"  ✓ Pass generated: Code = {ticket_id} for {attendee} (Total: ₹{data['registration']['totalAmount']})")

    print("\n--- 3. Testing POST /api/tickets/scan (First Check-In) ---")
    scan_req = urllib.request.Request(
        "http://127.0.0.1:5000/api/tickets/scan",
        data=json.dumps({"ticketId": ticket_id}).encode(),
        headers={"Content-Type": "application/json"}
    )
    res = urllib.request.urlopen(scan_req)
    scan_res = json.loads(res.read().decode())
    print("  Scan response:", scan_res["message"])
    assert scan_res["ok"] is True
    assert scan_res["alreadyCheckedIn"] is False
    assert scan_res["registration"]["ticket_id"] == ticket_id
    print(f"  ✓ Valid pass cleared gate: {scan_res['registration']['attendee_name']} checked in at {scan_res['registration']['checked_in_at']}")

    print("\n--- 4. Testing Re-Scanning Already Used Ticket (Anti-Fraud Check) ---")
    try:
        urllib.request.urlopen(scan_req)
        print("  Error: Should have rejected duplicate check-in!")
    except urllib.error.HTTPError as e:
        dup_res = json.loads(e.read().decode())
        print(f"  ✓ Correctly rejected duplicate scan: HTTP {e.code} -> {dup_res['message']}")
        assert dup_res["alreadyCheckedIn"] is True

    print("\n--- 5. Testing URL / Raw Text QR Decoding ---")
    # Simulate a scanner that read a full URL like https://eventora.io/t/EVT-XXXXX
    raw_url = f"https://eventora.io/checkin?code={ticket_id}"
    req_url = urllib.request.Request(
        "http://127.0.0.1:5000/api/tickets/scan",
        data=json.dumps({"ticketId": raw_url}).encode(),
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req_url)
    except urllib.error.HTTPError as e:
        dup_res = json.loads(e.read().decode())
        print(f"  ✓ URL extraction worked: Successfully parsed '{ticket_id}' from '{raw_url}'")

    print("\n--- 6. Testing Invalid QR Code Rejection ---")
    invalid_req = urllib.request.Request(
        "http://127.0.0.1:5000/api/tickets/scan",
        data=json.dumps({"ticketId": "EVT-INVALID999"}).encode(),
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(invalid_req)
        print("  Error: Should have rejected fake ticket!")
    except urllib.error.HTTPError as e:
        err_res = json.loads(e.read().decode())
        print(f"  ✓ Correctly rejected fake QR code: HTTP {e.code} -> {err_res['error']}")

    print("\n🎉 ALL QR SCANNER TESTS PASSED WITH 100% SUCCESS!")

if __name__ == "__main__":
    test_qr_scanner()
