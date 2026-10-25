import urllib.request
import json

def test():
    print("--- 1. Testing GET /api/public/events ---")
    res = urllib.request.urlopen("http://127.0.0.1:5000/api/public/events")
    data = json.loads(res.read().decode())
    events = data.get("events", [])
    print(f"Total events found: {len(events)}")
    for e in events:
        print(f"  [{e['id']}] {e['title']} | Price: ₹{e['ticket_price']} | Category: {e['category']}")

    print("\n--- 2. Testing Ticket Booking (₹199 per person, 2 tickets) ---")
    payload = {
        "name": "Priya Deshmukh",
        "email": "priya.deshmukh@example.com",
        "phone": "+91 98765 43210",
        "quantity": 2,
        "ticket_tier": "General Access"
    }
    req = urllib.request.Request(
        "http://127.0.0.1:5000/api/public/events/1/register",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    res = urllib.request.urlopen(req)
    booking_resp = json.loads(res.read().decode())
    booking = booking_resp["registration"]
    print("Booking response:", booking)
    assert booking["quantity"] == 2, "Quantity mismatch"
    assert booking["totalAmount"] == 398.0, "Total amount mismatch"
    code = booking["ticketId"]

    print(f"\n--- 3. Testing Find-My-Ticket with Code: {code} ---")
    res = urllib.request.urlopen(f"http://127.0.0.1:5000/api/public/tickets/lookup?query={code}")
    lookup_resp = json.loads(res.read().decode())
    ticket = lookup_resp["tickets"][0]
    print("Ticket retrieved:", ticket["ticket_id"], ticket["attendee_name"], ticket["event_title"], f"₹{ticket['total_amount']}")

    print("\n--- 4. Testing Event Detail & Schedule Timeline for Event 1 ---")
    res = urllib.request.urlopen("http://127.0.0.1:5000/api/public/events/1")
    detail = json.loads(res.read().decode())
    evt = detail["event"]
    print("Event Title:", evt["title"])
    print("Schedule items count:", len(evt.get("schedule", [])))
    print("Reviews count:", len(detail.get("reviews", [])))

    print("\n--- 5. Testing Review Submission ---")
    rev_payload = {
        "authorName": "Rohan Mehra",
        "rating": 5,
        "comment": "Had an unforgettable time! Best ₹199 spent this entire month."
    }
    req = urllib.request.Request(
        "http://127.0.0.1:5000/api/public/events/1/reviews",
        data=json.dumps(rev_payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    res = urllib.request.urlopen(req)
    rev_resp = json.loads(res.read().decode())
    print("Review response:", rev_resp)

    print("\n✓ ALL ENDPOINTS WORKING PERFECTLY!")

if __name__ == "__main__":
    test()
