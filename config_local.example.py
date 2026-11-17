"""Personal settings: copy this file to config_local.py and fill it in.

config_local.py is not committed to git, so your group name, your name and your
reps' ids stay on your Mac. Anything set here overrides config.py.
"""

# The WhatsApp group the reps post in, exactly as WhatsApp shows it (emojis included).
# See all your groups with:  uv run fetch_chat.py --list
CHAT_NAME = "My Sales Team"

# Your own messages appear as "You". Put your name here to show that in the report instead.
SELF_NAME = ""

# Reps who aren't in your phone contacts show up as "Unknown <id>". Name them here, or save
# them as contacts (easier), or generate these lines from a phone export:
#   uv run fetch_chat.py --learn-names ~/Downloads/_chat.txt
SENDER_NAMES = {
    # "123456789@lid": "Ali Veli",
}

# Email. Test mode sends to EMAIL_TEST_TO only; set EMAIL_TEST_MODE = False to email EMAIL_TO.
EMAIL_TEST_MODE = True
EMAIL_TEST_TO = "you@example.com"
EMAIL_TO = ""             # the team leader
