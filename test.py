import subprocess
import sys
import time
import requests
from datetime import date, timedelta

BASE_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@finance.com"
ADMIN_PASSWORD = "admin123"
ANALYST_EMAIL = "analyst@test.com"
ANALYST_PASSWORD = "analyst123"
VIEWER_EMAIL = "viewer@test.com"
VIEWER_PASSWORD = "viewer123"

passed = 0
failed = 0


def report(name, ok, detail=""):
    global passed, failed
    icon = "✅" if ok else "❌"
    label = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    suffix = f"  —  {detail}" if detail else ""
    print(f"  {icon} {label}  {name}{suffix}")


def login(email, password):
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise Exception(f"Login failed for {email}: {resp.status_code} {resp.text}")
    data = resp.json()
    return {"token": data["access_token"], "user": data["user"]}


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def make_record(token, **kw):
    payload = {"amount": 1500.0, "type": "income", "category": "Salary", "record_date": str(date.today()), "description": "Test"}
    payload.update(kw)
    return requests.post(f"{BASE_URL}/api/records", json=payload, headers=hdr(token))


def start_server():
    print("\n🚀 Starting server...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--lifespan", "on"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                print("✅ Server ready\n")
                return proc
        except Exception:
            time.sleep(1)
    print("❌ Server failed to start")
    proc.terminate()
    sys.exit(1)


def stop_server(proc):
    print("\n🛑 Stopping server...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("✅ Stopped\n")


def test_health():
    print("━━━ Health ━━━")
    r = requests.get(f"{BASE_URL}/health")
    d = r.json()
    report("Returns 200", r.status_code == 200)
    report("Status healthy", d.get("status") == "healthy")
    report("DB connected", d.get("database") == "connected")
    report("Has version", "version" in d)
    print()


def test_auth(admin_tok):
    print("━━━ Authentication ━━━")
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    report("Admin login 200", r.status_code == 200)
    d = r.json()
    report("Has access_token", "access_token" in d)
    report("Token type bearer", d.get("token_type") == "bearer")
    report("Role is admin", d.get("user", {}).get("role") == "admin")
    report("expires_in > 0", d.get("expires_in", 0) > 0)

    report("Wrong password -> 401",
           requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "x"}).status_code == 401)
    report("Unknown email -> 401",
           requests.post(f"{BASE_URL}/api/auth/login", json={"email": "x@x.com", "password": "x"}).status_code == 401)
    report("Missing field -> 422",
           requests.post(f"{BASE_URL}/api/auth/login", json={"email": ""}).status_code == 422)
    report("No token /me -> 401", requests.get(f"{BASE_URL}/api/auth/me").status_code == 401)
    report("Bad token /me -> 401",
           requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": "Bearer x.y.z"}).status_code == 401)

    r = requests.get(f"{BASE_URL}/api/auth/me", headers=hdr(admin_tok))
    report("Valid /me -> 200", r.status_code == 200)
    report("Correct email", r.json().get("email") == ADMIN_EMAIL)
    print()


def test_user_mgmt(admin_tok):
    print("━━━ User Management ━━━")
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": ANALYST_EMAIL, "name": "Analyst", "password": ANALYST_PASSWORD, "role": "analyst"
    }, headers=hdr(admin_tok))
    report("Register analyst -> 201", r.status_code == 201)
    report("Role set analyst", r.json().get("role") == "analyst")

    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": VIEWER_EMAIL, "name": "Viewer", "password": VIEWER_PASSWORD, "role": "viewer"
    }, headers=hdr(admin_tok))
    report("Register viewer -> 201", r.status_code == 201)
    viewer_id = r.json().get("id")

    report("Duplicate email -> 409",
           requests.post(f"{BASE_URL}/api/auth/register", json={
               "email": ANALYST_EMAIL, "name": "Dup", "password": "pass123", "role": "viewer"
           }, headers=hdr(admin_tok)).status_code == 409)
    report("Bad email -> 422",
           requests.post(f"{BASE_URL}/api/auth/register", json={
               "email": "bad", "name": "X", "password": "pass123", "role": "viewer"
           }, headers=hdr(admin_tok)).status_code == 422)
    report("Short password -> 422",
           requests.post(f"{BASE_URL}/api/auth/register", json={
               "email": "x@x.com", "name": "X", "password": "ab", "role": "viewer"
           }, headers=hdr(admin_tok)).status_code == 422)

    r = requests.get(f"{BASE_URL}/api/users", headers=hdr(admin_tok))
    report("List users -> 200", r.status_code == 200)
    report("Total >= 3", r.json().get("total", 0) >= 3)

    r = requests.get(f"{BASE_URL}/api/users/{viewer_id}", headers=hdr(admin_tok))
    report("Get by ID -> 200", r.status_code == 200)
    report("Correct email", r.json().get("email") == VIEWER_EMAIL)

    report("Missing user -> 404",
           requests.get(f"{BASE_URL}/api/users/99999", headers=hdr(admin_tok)).status_code == 404)

    r = requests.put(f"{BASE_URL}/api/users/{viewer_id}/role", json={"role": "analyst"}, headers=hdr(admin_tok))
    report("Update role -> 200", r.status_code == 200)
    report("Role changed", r.json().get("role") == "analyst")

    requests.put(f"{BASE_URL}/api/users/{viewer_id}/role", json={"role": "viewer"}, headers=hdr(admin_tok))

    r = requests.patch(f"{BASE_URL}/api/users/{viewer_id}/status", headers=hdr(admin_tok))
    report("Deactivate -> 200", r.status_code == 200)
    report("Is inactive", r.json().get("user", {}).get("is_active") is False)
    report("Inactive login -> 401",
           requests.post(f"{BASE_URL}/api/auth/login", json={"email": VIEWER_EMAIL, "password": VIEWER_PASSWORD}).status_code == 401)

    r = requests.patch(f"{BASE_URL}/api/users/{viewer_id}/status", headers=hdr(admin_tok))
    report("Reactivate -> 200", r.status_code == 200)
    report("Is active", r.json().get("user", {}).get("is_active") is True)
    print()


def test_rbac(admin_tok):
    print("━━━ Access Control ━━━")
    a_tok = login(ANALYST_EMAIL, ANALYST_PASSWORD)["token"]
    v_tok = login(VIEWER_EMAIL, VIEWER_PASSWORD)["token"]

    report("Viewer reg -> 403",
           requests.post(f"{BASE_URL}/api/auth/register", json={"email": "a@b.com", "name": "X", "password": "pass123"}, headers=hdr(v_tok)).status_code == 403)
    report("Analyst reg -> 403",
           requests.post(f"{BASE_URL}/api/auth/register", json={"email": "b@c.com", "name": "X", "password": "pass123"}, headers=hdr(a_tok)).status_code == 403)
    report("Viewer list users -> 403", requests.get(f"{BASE_URL}/api/users", headers=hdr(v_tok)).status_code == 403)
    report("Analyst list users -> 403", requests.get(f"{BASE_URL}/api/users", headers=hdr(a_tok)).status_code == 403)
    report("Viewer create record -> 403", make_record(v_tok, amount=100).status_code == 403)
    report("Viewer list records -> 403", requests.get(f"{BASE_URL}/api/records", headers=hdr(v_tok)).status_code == 403)
    report("Viewer summary -> 200", requests.get(f"{BASE_URL}/api/dashboard/summary", headers=hdr(v_tok)).status_code == 200)
    report("Viewer categories -> 200", requests.get(f"{BASE_URL}/api/dashboard/categories", headers=hdr(v_tok)).status_code == 200)
    report("Viewer recent -> 200", requests.get(f"{BASE_URL}/api/dashboard/recent", headers=hdr(v_tok)).status_code == 200)
    report("Viewer trends -> 403", requests.get(f"{BASE_URL}/api/dashboard/trends", headers=hdr(v_tok)).status_code == 403)
    report("Analyst create record -> 201", make_record(a_tok, amount=200, category="Freelance").status_code == 201)
    report("Analyst list records -> 200", requests.get(f"{BASE_URL}/api/records", headers=hdr(a_tok)).status_code == 200)
    report("Analyst trends -> 200", requests.get(f"{BASE_URL}/api/dashboard/trends", headers=hdr(a_tok)).status_code == 200)
    report("Analyst update -> 403",
           requests.put(f"{BASE_URL}/api/records/1", json={"amount": 999}, headers=hdr(a_tok)).status_code == 403)
    report("Analyst delete -> 403",
           requests.delete(f"{BASE_URL}/api/records/1", headers=hdr(a_tok)).status_code == 403)
    report("Admin create record -> 201", make_record(admin_tok, amount=5000, category="Investment").status_code == 201)
    print()


def test_records_crud(admin_tok, analyst_tok):
    print("━━━ Records CRUD ━━━")
    samples = [
        {"amount": 5000.0, "type": "income", "category": "Salary", "record_date": str(date.today()), "description": "Jan salary"},
        {"amount": 1200.0, "type": "expense", "category": "Housing", "record_date": str(date.today()), "description": "Rent"},
        {"amount": 350.5, "type": "expense", "category": "Food & Dining", "record_date": str(date.today() - timedelta(days=1)), "description": "Groceries"},
        {"amount": 800.0, "type": "income", "category": "Freelance", "record_date": str(date.today() - timedelta(days=2)), "description": "Side project"},
        {"amount": 99.99, "type": "expense", "category": "Entertainment", "record_date": str(date.today() - timedelta(days=3)), "description": "Subscriptions"},
        {"amount": 2500.0, "type": "income", "category": "Investment", "record_date": str(date.today() - timedelta(days=5)), "description": "Dividends"},
    ]
    ids = []
    for i, s in enumerate(samples):
        r = make_record(admin_tok, **s)
        report(f"Create #{i+1} -> 201", r.status_code == 201, f"{s['type']}/{s['category']}")
        if r.status_code == 201:
            ids.append(r.json()["id"])

    report("Negative amount -> 422", make_record(admin_tok, amount=-100, category="Bad").status_code == 422)
    report("Zero amount -> 422", make_record(admin_tok, amount=0, category="Bad").status_code == 422)
    report("Missing fields -> 422",
           requests.post(f"{BASE_URL}/api/records", json={"type": "income"}, headers=hdr(admin_tok)).status_code == 422)

    r = requests.get(f"{BASE_URL}/api/records", headers=hdr(admin_tok))
    report("List -> 200", r.status_code == 200)
    d = r.json()
    report("Has items", d.get("total", 0) > 0)
    report("Pagination fields", all(k in d for k in ["total", "page", "page_size", "total_pages"]))

    if ids:
        r = requests.get(f"{BASE_URL}/api/records/{ids[0]}", headers=hdr(admin_tok))
        report("Get by ID -> 200", r.status_code == 200)
        report("Has expected fields", all(k in r.json() for k in ["id", "amount", "type", "category", "record_date"]))

    r = requests.get(f"{BASE_URL}/api/records?type=income", headers=hdr(admin_tok))
    report("Filter income -> 200", r.status_code == 200)
    report("All income", all(x["type"] == "income" for x in r.json().get("records", [])))

    r = requests.get(f"{BASE_URL}/api/records?category=Salary", headers=hdr(admin_tok))
    report("Filter category -> 200", r.status_code == 200)
    report("All Salary", all(x["category"] == "Salary" for x in r.json().get("records", [])))

    r = requests.get(f"{BASE_URL}/api/records?search=salary", headers=hdr(admin_tok))
    report("Search -> 200", r.status_code == 200)

    if ids:
        r = requests.put(f"{BASE_URL}/api/records/{ids[0]}", json={"amount": 6000.0, "description": "Updated"}, headers=hdr(admin_tok))
        report("Update -> 200", r.status_code == 200)
        report("Amount changed", r.json().get("amount") == 6000.0)
        report("Desc changed", r.json().get("description") == "Updated")

    report("Missing record -> 404",
           requests.get(f"{BASE_URL}/api/records/99999", headers=hdr(admin_tok)).status_code == 404)

    if ids:
        r = requests.delete(f"{BASE_URL}/api/records/{ids[0]}", headers=hdr(admin_tok))
        report("Delete -> 200", r.status_code == 200)
        report("Confirmed deleted", r.json().get("deleted") is True)

        normal = requests.get(f"{BASE_URL}/api/records", headers=hdr(admin_tok)).json().get("records", [])
        report("Gone from normal list", not any(x["id"] == ids[0] for x in normal))

        with_del = requests.get(f"{BASE_URL}/api/records?include_deleted=true", headers=hdr(admin_tok)).json().get("records", [])
        report("Visible with flag", any(x["id"] == ids[0] for x in with_del))

        report("Double delete -> 400",
               requests.delete(f"{BASE_URL}/api/records/{ids[0]}", headers=hdr(admin_tok)).status_code == 400)

    r = requests.get(f"{BASE_URL}/api/records?page=1&page_size=2", headers=hdr(admin_tok))
    report("Pagination limit", len(r.json().get("records", [])) <= 2)
    report("Total pages > 0", r.json().get("total_pages", 0) > 0)
    print()


def test_dashboard(admin_tok):
    print("━━━ Dashboard Analytics ━━━")
    r = requests.get(f"{BASE_URL}/api/dashboard/summary", headers=hdr(admin_tok))
    report("Summary -> 200", r.status_code == 200)
    s = r.json()
    report("Has income", "total_income" in s)
    report("Has expenses", "total_expenses" in s)
    report("Has balance", "net_balance" in s)
    report("Has count", "total_records" in s)
    report("Income >= 0", s.get("total_income", -1) >= 0)
    report("Expenses >= 0", s.get("total_expenses", -1) >= 0)
    expected_net = s.get("total_income", 0) - s.get("total_expenses", 0)
    report("Balance correct", abs(s.get("net_balance", 0) - expected_net) < 0.01)

    r = requests.get(f"{BASE_URL}/api/dashboard/categories", headers=hdr(admin_tok))
    report("Categories -> 200", r.status_code == 200)
    cats = r.json().get("categories", [])
    report("Not empty", len(cats) > 0)
    if cats:
        report("Has total/count/type", all(k in cats[0] for k in ["total", "count", "type"]))

    r = requests.get(f"{BASE_URL}/api/dashboard/recent?limit=5", headers=hdr(admin_tok))
    report("Recent -> 200", r.status_code == 200)
    report("Limit respected", len(r.json().get("records", [])) <= 5)

    r = requests.get(f"{BASE_URL}/api/dashboard/trends?period_type=monthly", headers=hdr(admin_tok))
    report("Monthly trends -> 200", r.status_code == 200)
    report("Period type correct", r.json().get("period_type") == "monthly")
    t = r.json().get("trends", [])
    if t:
        report("Trend point fields", all(k in t[0] for k in ["period", "income", "expenses", "net"]))

    r = requests.get(f"{BASE_URL}/api/dashboard/trends?period_type=weekly", headers=hdr(admin_tok))
    report("Weekly trends -> 200", r.status_code == 200)
    report("Period type weekly", r.json().get("period_type") == "weekly")
    report("Invalid period -> 422",
           requests.get(f"{BASE_URL}/api/dashboard/trends?period_type=yearly", headers=hdr(admin_tok)).status_code == 422)
    print()


if __name__ == "__main__":
    proc = start_server()
    try:
        admin = login(ADMIN_EMAIL, ADMIN_PASSWORD)
        admin_tok = admin["token"]
        test_health()
        test_auth(admin_tok)
        test_user_mgmt(admin_tok)
        test_rbac(admin_tok)
        test_records_crud(admin_tok, admin_tok)
        test_dashboard(admin_tok)
    except Exception as exc:
        print(f"\n💥 Fatal error: {exc}")
    finally:
        stop_server(proc)

    total = passed + failed
    print("=" * 50)
    print(f"  Total: {total}  |  ✅ Passed: {passed}  |  ❌ Failed: {failed}")
    print(f"  Success Rate: {passed / total * 100:.1f}%" if total else "  No tests ran")
    print("=" * 50)
    sys.exit(0 if failed == 0 else 1)