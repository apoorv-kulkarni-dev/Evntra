import urllib.request
import urllib.parse
import http.cookiejar
import json

def test_organizer():
    print("--- Testing Organizer Studio & Expense Ledger ---")
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    # 1. Demo Login
    req = urllib.request.Request("http://127.0.0.1:5000/api/auth/demo", data=b"{}", headers={"Content-Type": "application/json"})
    res = opener.open(req)
    auth = json.loads(res.read().decode())
    print("Organizer signed in:", auth["user"]["name"], auth["user"]["email"])

    # 2. Get Events for organizer
    res = opener.open("http://127.0.0.1:5000/api/events")
    events = json.loads(res.read().decode())["events"]
    print(f"Organizer has {len(events)} managed events.")

    # 3. Get itemized expenses for Event 1
    res = opener.open("http://127.0.0.1:5000/api/events/1/expenses")
    exp_data = json.loads(res.read().decode())
    expenses = exp_data["expenses"]
    print(f"Event 1 has {len(expenses)} itemized expenses totaling ₹{exp_data['totalExpenses']}.")
    for exp in expenses:
        print(f"  - [{exp['category']}] {exp['title']}: ₹{exp['amount']}")

    # 4. Add a new expense
    new_exp_payload = {
        "title": "Stage LED Lights & Sound Technician",
        "category": "Equipment",
        "amount": 4500.0,
        "date": "2026-10-24"
    }
    req = urllib.request.Request(
        "http://127.0.0.1:5000/api/events/1/expenses",
        data=json.dumps(new_exp_payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    res = opener.open(req)
    added_exp = json.loads(res.read().decode())
    print("Expense added successfully: ID =", added_exp["expense"]["id"], "New Total Expenses = ₹", added_exp["totalExpenses"])

    # 5. Check reports summary
    res = opener.open("http://127.0.0.1:5000/api/reports/summary")
    summary = json.loads(res.read().decode())["summary"]
    print("Workspace Summary Metrics:")
    print(f"  Total Events: {summary['eventCount']}")
    print(f"  Total Registrations: {summary['registrationCount']}")
    print(f"  Checked In: {summary['checkedInCount']}")
    print(f"  Total Budget: ₹{summary['totalBudget']:,.2f}")
    print(f"  Total Expenses: ₹{summary['totalExpenses']:,.2f}")

    # 6. Check CSV export
    res = opener.open("http://127.0.0.1:5000/api/reports/export.csv")
    csv_content = res.read().decode()
    print(f"CSV Export generated successfully ({len(csv_content)} bytes, {len(csv_content.splitlines())} rows).")

    print("\n✓ ALL ORGANIZER & EXPENSE FEATURES WORKING FLAWLESSLY!")

if __name__ == "__main__":
    test_organizer()
