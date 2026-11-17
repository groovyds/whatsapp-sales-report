"""Settings for the daily sales report. Edit this file, not the scripts.

Personal settings (your group name, your own name, rep ids) go in config_local.py, which
is not committed to git. Copy config_local.example.py to config_local.py to start.
Anything set there overrides the defaults below.
"""

# Products, in the column order of the Excel report.
# Left: column name. Right: other spellings reps use.
# Matching ignores capitals, Turkish letters (ü=u, ş=s, ı=i ...), emojis and punctuation,
# so "Süperbox Upsell 💞" and "superbox upsell" are the same thing. Add spellings in plain lowercase.
PRODUCTS = {
    "Mobil kontrat": [
        "mk", "up", "upp", "upc", "upcell", "upcelll", "upcel", "upsell", "upsel",
    ],
    "SPBX": [
        "spbx up", "spbx upcell", "spbx upsell", "spbx kontrat",
        "sbox", "sbox up", "sbox upp", "sbox upcell", "sbox upsell", "sbox kontrat", "sbox kont",
        "sbx up", "sbxup", "sb upsell",
        "superbox", "superbox up", "superbox upcell", "superbox upsell", "superbox kontrat",
        "superbox sozlesmesi", "spbx rekontrat", "sbox rekontrat",
        "sprbx up", "sprbx upsell", "sprbx kontrat",
    ],
    "Online aktivasyon": ["onl akt", "online akt"],
    "NCST": [],
    "SOL": [
        "online sol", "online superbox", "superbox online", "online sbox", "sbox online", "online spbx",
        "fiber", "online fiber",
    ],
    "Paycell POS": ["paycell", "pos"],
}

# Lines that are known but should not be counted or flagged.
IGNORE = ["aktivite"]

# Your own messages are exported with the sender name "You". Leave empty to keep
# "You" in the report, or put your name here to show that instead.
SELF_NAME = ""             # set yours in config_local.py

# Day/month order for dates written with "/" (e.g. 11/8/26). "MDY" = 8 Nov 2026.
# Dates written with "." (e.g. 8.11.2026) are always read day first.
DATE_ORDER = "MDY"

# Optional, not used in the MVP: rep names exactly as WhatsApp shows them.
# If filled in, the report lists reps who have not reported and names it doesn't recognise.
ROSTER = []

# ---- Automatic export from the WhatsApp Mac app (fetch_chat.py) ----
# Group name exactly as WhatsApp shows it (emojis included). See all groups: uv run fetch_chat.py --list
CHAT_NAME = ""             # set yours in config_local.py

# Reps who are not in your contacts have no readable name in the Mac app's data, only an id
# like "123456789@lid". fetch_chat.py prints any id it can't name; add it in config_local.py.
SENDER_NAMES = {}

INBOX = "inbox"          # raw WhatsApp exports go here
PROCESSED = "processed"  # step 1 output (cleaned CSV)
OUT = "out"              # step 2 output (Excel report)

# Personal overrides, kept out of git.
try:
    from config_local import *  # noqa: F401,F403
except ImportError:
    pass
