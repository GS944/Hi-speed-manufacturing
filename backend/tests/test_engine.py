"""Unit tests for the data pipeline and the ML / rule engine (no external services needed)."""
from datetime import datetime, timedelta

import openpyxl

from app.ingest.reader import read_workbook, segment_sheet
from app.intelligence import canonical, profiler, rules
from app.services.keys import norm_key, parse_refs, to_date
from app.services.workspace import hrc_verdict


def test_parse_refs_expands_abbreviated_and_ranges():
    assert parse_refs("2328/29") == ["2328", "2329"]
    assert parse_refs("2445/46") == ["2445", "2446"]
    assert parse_refs(2374.0) == ["2374"]
    assert parse_refs("1201-03") == ["1201", "1202", "1203"]
    assert parse_refs("LOI") == ["LOI"]
    assert parse_refs(None) == []
    assert norm_key(" 0042 ") == "42"


def test_to_date_formats():
    assert str(to_date("2026-04-02")) == "2026-04-02"
    assert str(to_date("15/05/2026")) == "2026-05-15"
    assert to_date("not a date") is None


def test_rule_language():
    row = {"despatch_qty": 10, "order_qty": 10, "stock_qty": 0, "despatch_date": "2026-01-01"}
    get = row.get
    assert rules.evaluate({"gte": ["despatch_qty", "order_qty"]}, get)
    assert rules.evaluate({"all": [{"gt": ["despatch_qty", 0]}, {"lte": ["stock_qty", 0]}]}, get)
    assert not rules.evaluate({"present": "coating_date"}, get)
    assert rules.evaluate({"not": {"present": "coating_date"}}, get)


def test_canonical_merges_spelling_variants():
    m = canonical.canonical_map(["HI-SPEED SPARES", "Hi-Speed Spares", "Hi-Speed Spares", "WIDIA SPARES"])
    assert m["HI-SPEED SPARES"] == m["Hi-Speed Spares"] == "Hi-Speed Spares"
    assert m["WIDIA SPARES"] == "WIDIA SPARES"


def test_hrc_verdict():
    assert hrc_verdict("42-46", "43-44") == "ok"
    assert hrc_verdict("40-44 hrc", "45-46") == "out_of_spec"
    assert hrc_verdict("42-46", None) is None


def test_discover_derived_finds_spreadsheet_formulas():
    issued = [10, 7, 21, 11, 6, 8, 1, 3] * 6
    coated = [10, 7, None, 10, 6, 5, 1, None] * 6
    desp = [10, 5, None, 10, None, 5, 1, None] * 6
    reject = [i - (c or 0) for i, c in zip(issued, coated)]
    stock = [(c or 0) - (d or 0) for c, d in zip(coated, desp)]
    fields = {"issued_qty": "I", "coating_qty": "C", "despatch_qty": "D", "reject_qty": "R", "stock_qty": "S"}
    rel = profiler.discover_derived(fields, {"I": issued, "C": coated, "D": desp, "R": reject, "S": stock})
    targets = {r["target"]: r for r in rel}
    assert set(targets) == {"reject_qty", "stock_qty"}          # inputs with gaps are never targets
    assert targets["reject_qty"]["plus"] == "issued_qty" and targets["reject_qty"]["minus"] == ["coating_qty"]


def test_segmentation_side_tables_and_prefilled_tail(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Orders"
    ws.append(["ORDER NUM", "Order date", "Item", "Order Qty", "Despatch Qty", None, "Customer list", "name"])
    d0 = datetime(2026, 4, 1)
    for i in range(1, 41):
        ws.append([i, d0 + timedelta(days=i), f"PCLNR 2525 M{i}", i % 7 + 1, None, None,
                   2300 + i if i <= 5 else None, f"Cust {i}" if i <= 5 else None])
    for i in range(41, 120):          # pre-filled template rows: serial + formula defaults only
        ws.append([i, None, None, None, 0])
    p = tmp_path / "book.xlsx"
    wb.save(p)
    tables = segment_sheet(read_workbook(p)[0])
    main = next(t for t in tables if t.columns[0] == "ORDER NUM")
    side = next(t for t in tables if t.columns[0] == "Customer list")
    assert len(main.rows) == 40                                   # filler removed
    assert len(side.rows) == 5 and side.columns == ["Customer list", "name"]
