"""Tests for the pre-email checks and send bookkeeping, with made-up data. Run: uv run pytest"""
import csv
from datetime import date

import pytest
from openpyxl import load_workbook

import checks
import config
import report
import send_report

DAY = date(2026, 11, 16)


@pytest.fixture
def folders(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROCESSED", str(tmp_path / "processed"))
    monkeypatch.setattr(config, "OUT", str(tmp_path / "out"))
    (tmp_path / "processed").mkdir()
    return tmp_path


def write_day(rows, day=DAY):
    """rows: (time, sender, text). Writes the cleaned CSV and builds the Excel report."""
    with checks.csv_path(DAY).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "time", "sender", "text"])
        for t, sender, text in rows:
            w.writerow([day.isoformat(), t, sender, text])
    report.run(DAY)


GOOD = [
    ("10:00:00", "Ali", "2 up"),                                  # replaced by Ali's EOD post
    ("18:31:00", "Ali", "45 - mobil kontrat\n2 - spbx"),
    ("18:35:10", "Ayşe", "3 - ncst, 1 - sol"),
    ("18:36:00", "Ayşe", "iyi akşamlar"),                         # chatter: not a report
]


def test_all_checks_pass(folders):
    write_day(GOOD)
    assert checks.run(DAY) == []


def test_edited_excel_cell_is_caught(folders):
    write_day(GOOD)
    path = checks.xlsx_path(DAY)
    wb = load_workbook(path)
    wb["Summary"]["B4"] = 99            # Ali's Mobil kontrat
    wb.save(path)
    problems = checks.check_totals(DAY)
    assert any("Ali, Mobil kontrat: Excel says 99" in p for p in problems)


def test_wrong_total_row_is_caught(folders):
    write_day(GOOD)
    path = checks.xlsx_path(DAY)
    wb = load_workbook(path)
    ws = wb["Summary"]
    total_row = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "TOTAL")
    ws.cell(total_row, 2).value = 1
    wb.save(path)
    assert any(p.startswith("TOTAL Mobil kontrat") for p in checks.check_totals(DAY))


def test_missing_rep_row_is_caught(folders):
    write_day(GOOD)
    path = checks.xlsx_path(DAY)
    wb = load_workbook(path)
    wb["Summary"].delete_rows(5)        # Ayşe's row (rows sorted: Ali, Ayşe)
    wb.save(path)
    assert any("Ayşe: posted a report but has no row" in p for p in checks.check_totals(DAY))


def test_quiet_evening_does_not_block(folders):
    write_day([("17:20:00", "Ali", "45 - mobil kontrat")])
    assert checks.check_fresh(DAY) == []


def test_wrong_day_blocks(folders):
    write_day([("18:40:00", "Ali", "1 up")], day=date(2026, 11, 15))
    assert any("not 2026-11-16" in p for p in checks.check_fresh(DAY))


def test_missing_files_block(folders):
    problems = checks.run(DAY)
    assert problems and all("missing" in p for p in problems)


def test_body_has_totals(folders):
    write_day(GOOD)
    body = send_report.body_text(DAY)
    assert "Daily sales report for Monday 16.11.2026 (2 reps reported)." in body
    assert "Mobil kontrat: 45" in body and "NCST: 3" in body and "SOL: 1" in body


def test_previous_sends_by_day_and_address(folders, monkeypatch):
    monkeypatch.setattr(send_report, "SENT_LOG", folders / "out" / "sent_log.csv")
    assert send_report.previous_sends(DAY, "me@example.com") == []
    send_report.log_send(DAY, "me@example.com")
    assert len(send_report.previous_sends(DAY, "me@example.com")) == 1
    assert send_report.previous_sends(DAY, "tl@example.com") == []           # other recipient
    assert send_report.previous_sends(date(2026, 11, 17), "me@example.com") == []


def test_live_mode_needs_tl_address(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_TEST_MODE", False)
    monkeypatch.setattr(config, "EMAIL_TO", "")
    with pytest.raises(SystemExit):
        send_report.recipient()


def test_test_mode_goes_to_tester(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_TEST_MODE", True)
    monkeypatch.setattr(config, "EMAIL_TEST_TO", "me@example.com")
    monkeypatch.setattr(config, "EMAIL_TO", "tl@example.com")
    assert send_report.recipient() == ("me@example.com", "[TEST] ")
