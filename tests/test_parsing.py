"""Parser tests with made-up data. Run: uv run pytest"""
from datetime import date, time

import pytest

import preprocess
import report


# ---- headers / dates -------------------------------------------------------

def test_mac_english_header():
    msgs = preprocess.read_messages("[11/8/26, 4:17:37 PM] Ali Veli: 45 - Mobil kontrat\n2 - spbx")
    assert len(msgs) == 1
    assert msgs[0]["date"] == date(2026, 11, 8)
    assert msgs[0]["time"] == time(16, 17, 37)
    assert msgs[0]["lines"] == ["45 - Mobil kontrat", "2 - spbx"]


def test_mac_turkish_header_is_day_first():
    msgs = preprocess.read_messages("[5.11.2026, 18:31:02] Ayşe: 3 - ncst")
    assert msgs[0]["date"] == date(2026, 11, 5)
    assert msgs[0]["time"] == time(18, 31, 2)


def test_invisible_marks_and_encryption_line():
    raw = ("Messages and calls are end-to-end encrypted.\n"
           "[11/8/26, 4:17:37 PM] ‎Ali: ‎1 - sol")
    msgs = preprocess.read_messages(raw)
    assert len(msgs) == 1 and msgs[0]["lines"] == ["1 - sol"]


# ---- cleaning ----------------------------------------------------------------

def test_turkish_lowercase():
    assert preprocess.clean_text(["İKİ", "ISPARTA"]) == "iki\nısparta"


@pytest.mark.parametrize("lines", [
    ["https://www.instagram.com/reel/abc"],
    ["<sticker omitted>"],
    ["This message was deleted."],
    ["   "],
])
def test_noise_dropped(lines):
    assert preprocess.clean_text(lines) == ""


def test_edited_marker_removed():
    assert preprocess.clean_text(["2 - up <This message was edited>"]) == "2 - up"


# ---- product matching ------------------------------------------------------

@pytest.mark.parametrize("spelling, product", [
    ("mobil kontrat", "Mobil kontrat"),
    ("Up", "Mobil kontrat"),
    ("upcell", "Mobil kontrat"),
    ("UPSELL", "Mobil kontrat"),
    ("spbx", "SPBX"),
    ("SPBX up", "SPBX"),
    ("spbx upcell", "SPBX"),
    ("spbx upsell", "SPBX"),
    ("süperbox sözleşmesi", "SPBX"),
    ("Superbox kontrat", "SPBX"),
    ("online superbox", "SOL"),
    ("online süperbox 💞", "SOL"),
    ("online fiber", "SOL"),
    ("sol", "SOL"),
    ("ncst", "NCST"),
    ("NCST.", "NCST"),
    ("online aktivasyon", "Online aktivasyon"),
    ("onl akt", "Online aktivasyon"),
    ("Paycell POS ✨", "Paycell POS"),
])
def test_aliases(spelling, product):
    counts, problems = report.parse_report(f"3 - {spelling}")
    assert counts == {product: 3} and problems == []


def test_full_eod_message():
    text = "45 - mobil kontrat\n2 - spbx\n1 - online aktivasyon\n10 - up\n2 - spbx up"
    counts, problems = report.parse_report(text)
    assert counts == {"Mobil kontrat": 55, "SPBX": 4, "Online aktivasyon": 1}
    assert problems == []


def test_dash_optional_and_plus_sign():
    counts, _ = report.parse_report("45 mobil kontrat\n+2 ncst")
    assert counts == {"Mobil kontrat": 45, "NCST": 2}


def test_commas_and_bullets():
    counts, _ = report.parse_report("- 1 - sol, 2 - ncst; 3 - up")
    assert counts == {"SOL": 1, "NCST": 2, "Mobil kontrat": 3}


def test_ignored_item_not_counted_or_flagged():
    counts, problems = report.parse_report("2 - ncst\n4 - aktivite")
    assert counts == {"NCST": 2} and problems == []


def test_unknown_product_in_report_is_flagged():
    counts, problems = report.parse_report("2 - ncst\n1 - tablet")
    assert counts == {"NCST": 2}
    assert len(problems) == 1 and "tablet" in problems[0]


def test_same_line_twice_is_summed_and_flagged():
    counts, problems = report.parse_report("2 - ncst\n1 - ncst")
    assert counts == {"NCST": 3} and len(problems) == 1


def test_chatter_is_ignored():
    assert report.parse_report("günaydın") == ({}, [])
    assert report.parse_report("2 dk oldu") == ({}, [])


def test_unknown_dash_line_flagged_even_without_known_product():
    counts, problems = report.parse_report("5 - tablet")
    assert counts == {} and len(problems) == 1


def test_product_first_report_is_flagged_not_dropped():
    counts, problems = report.parse_report("mobil kontrat: 45\nncst 3")
    assert counts == {}
    assert len(problems) == 2 and "'45 - mobil kontrat'" in problems[0]


def test_product_first_line_flagged_next_to_counted_lines():
    counts, problems = report.parse_report("2 - ncst\nup 4")
    assert counts == {"NCST": 2}
    assert len(problems) == 1 and "Number after the product" in problems[0]


def test_chatter_ending_in_a_number_is_still_ignored():
    assert report.parse_report("saat 5") == ({}, [])


# ---- names written by fetch_chat.py ----------------------------------------

@pytest.mark.parametrize("name", [
    "Ali: Kadıköy",
    "~ Mehmet | Turkcell Bayi Kadıköy Merkez Mağaza Satış Danışmanı 2026",
])
def test_awkward_sender_names_keep_their_own_message(name):
    import fetch_chat
    raw = (f"[2026-11-18, 17:00:00] Ayşe: 3 - up\n"
           f"[2026-11-18, 17:05:00] {fetch_chat.safe_name(name)}: 2 - ncst")
    msgs = preprocess.read_messages(raw)
    assert len(msgs) == 2
    assert msgs[1]["lines"] == ["2 - ncst"] and msgs[1]["sender"][:5] == name.replace(":", "")[:5]


# ---- whole day -------------------------------------------------------------

def test_latest_report_replaces_earlier():
    msgs = [(time(18, 0), "Ali", "5 - ncst\n2 - sol"),
            (time(18, 20), "Ali", "6 - ncst"),
            (time(18, 5), "Ayşe", "1 - up"),
            (time(12, 0), "Ayşe", "günaydın")]
    latest, issues = report.build_report(msgs)
    assert latest["Ali"] == ("18:20", {"NCST": 6})
    assert latest["Ayşe"] == ("18:05", {"Mobil kontrat": 1})
    assert any("latest one used" in note for _, _, note in issues)
