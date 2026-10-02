"""End-to-end API test: auth, upload, ML profiling, live status, progress update, annexure printing."""
import io
import time
from datetime import datetime, timedelta

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.main import app


def _workbook() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Order summary"
    ws.append(["ORDER NUM", "Custom Code", "Order date", "ETD", "Item", "Order Qty", "Issued Qty", "Coating Qty",
               "Reject Qty", "Despatch Date", "Despatch Qty", "Stock", "Request"])
    d0 = datetime(2026, 4, 1)
    for i in range(1, 121):
        done = i <= 80
        issued, coat = 10, (10 if done else None)
        desp = 10 if done else None
        ws.append([i, 2301 + i % 4, d0 + timedelta(days=i), d0 + timedelta(days=i + 21), f"S{i % 9}Q SCLCR 0{i % 5}", 10,
                   issued, coat, issued - (coat or 0), (d0 + timedelta(days=i + 30 + i % 11)) if done else None, desp,
                   (coat or 0) - (desp or 0), "Emergency" if i % 10 == 0 else "Regular"])
    led = wb.create_sheet("SUMMARY")
    led.append(["SL. NO.", "ISSUE DATE", "VENDOR NAME", "ITEM NO", "QTY", "DESCRIPTION", "ORDER NO", "OPERATION",
                "UNIT COST", "VALUE OF GOODS", "HRC", "INWARD DATE", "HRC CHECKED"])
    for i in range(1, 121):
        led.append([i, d0 + timedelta(days=i + 3), ["GLOBE-TECH FORTUNE", "RAPID TOOLING SOLUTION"][i % 2], "EN-19", 10,
                    f"S{i % 9}Q SCLCR", f"{i}" if i % 15 else f"{i}/{(i + 1) % 100:02d}", ["HEAT TREATMENT", "GRINDING"][i % 2],
                    [15, 45][i % 2], 1000, "42-46", (d0 + timedelta(days=i + 6)) if i <= 100 else None,
                    "43-44" if i % 2 == 0 and i <= 100 else None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "Test@12345"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_requires_auth(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_full_flow(client, auth):
    r = client.post("/api/files", headers=auth, files={"file": ("book.xlsx", _workbook(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    for _ in range(120):
        f = client.get(f"/api/files/{fid}", headers=auth).json()
        if f["status"] != "processing":
            break
        time.sleep(1)
    assert f["status"] == "ready", f
    roles = {t["sheet"]: t["role"] for t in f["tables"]}
    assert roles["Order summary"] == "orders" and roles["SUMMARY"] == "job_work_ledger"

    # a re-saved copy of the same workbook is caught before it can double-count orders
    dup = client.post("/api/files", headers=auth, files={"file": ("book.xlsx", _workbook(), "x")})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "possible_new_version"

    o = client.get("/api/orders/5", headers=auth).json()
    assert o["status"] == "completed"
    live = client.get("/api/orders/100", headers=auth).json()
    assert live["status"] == "live"
    line = live["lines"][0]
    assert line["job_work"], "ledger entry should link to the order"
    # multi-reference '15/16' links to both orders
    assert any(e["raw_ref"] == "15/16" for e in client.get("/api/orders/16", headers=auth).json()["lines"][0]["job_work"])

    r = client.patch(f"/api/orders/line/{line['id']}", headers=auth,
                     json={"values": {"coating_qty": 10, "despatch_qty": 10, "despatch_date": "2026-10-01"}})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed", [(l["order_no"], l["row_no"], l["status"]) for l in r.json()["lines"]]
    rec = r.json()["lines"][0]["record"]
    assert rec["Reject Qty"] == 0 and rec["Stock"] == 0          # derived columns recomputed

    a = client.get("/api/annexure/100", headers=auth).json()
    assert a["rows"] and {"issue_date", "operation", "unit_cost", "value_of_goods", "hrc_result"} <= set(a["rows"][0])
    s = client.post("/api/annexure/100/submit", headers=auth, json={}).json()
    assert s["doc_no"].startswith("ANX/")
    pdf = client.get(s["pdf_url"], headers=auth)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get("/api/annexure/100/download?format=xlsx", headers=auth).content[:2] == b"PK"

    ask = client.post("/api/ask", headers=auth, json={"q": "status of 100"}).json()
    assert ask["kind"] == "navigate" and ask["order_no"] == "100"
    d = client.get("/api/dashboard", headers=auth).json()
    assert d["kpi"]["total_lines"] == 120
