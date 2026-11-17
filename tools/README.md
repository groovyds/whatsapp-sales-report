# wa-snapshot: the only part of this project allowed to read WhatsApp's data

| File | What it is |
|---|---|
| `wa_snapshot.c` | The source code (about 150 lines, comments included). Read it to see exactly what the program does. |
| `wa-snapshot` | The compiled program that `daily.sh` runs. This is the file that gets Full Disk Access. It isn't in git: build it from the source with the `clang` command under "Good to know" below. |

## Why it exists

The daily report reads the group chat from the WhatsApp Mac app's databases, in
`~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/`. macOS protects other apps' data
folders. Whenever a program reads one, macOS shows a permission pop-up, and clicking Allow doesn't
stick for this kind of request. The only permanent fix is **Full Disk Access**, which is given to
one program at a time.

The obvious choice would be to give it to `uv`, which runs the Python scripts. But uv also runs
every Python package it downloads, so a bad or hijacked package could then silently read Mail,
Messages, Photos and the rest of your protected data.

So the access goes to this helper instead:

- **It does one fixed thing.** It copies three WhatsApp databases into the project. It has no
  options, so nothing can ask it to read anything else or write somewhere else.
- **It's checked by its exact contents.** macOS identifies a program by a fingerprint of its
  code. If the file is modified or replaced, the fingerprint changes and the access is lost
  automatically.
- **uv and Python stay without Full Disk Access.** They only read the copy.

## How a daily run uses it

```
18:40  launchd starts daily.sh
         │
         ├─ tools/wa-snapshot                     ← the only program with Full Disk Access
         │     reads (read-only) ~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/
         │        ChatStorage.sqlite   messages and groups
         │        ContactsV2.sqlite    contact names (how reps get their names)
         │        LID.sqlite           links WhatsApp ids to phone numbers
         │     writes copies to  <project>/.wa_snapshot/   (folder and files readable only by you)
         │
         ├─ uv run fetch_chat.py                  ← reads .wa_snapshot/ (WA_DATA_DIR), not WhatsApp
         │     writes inbox/chat_YYYY-MM-DD.txt
         ├─ uv run daily.py                       ← CSV and Excel report, as before
         │
         └─ on exit (success, failure or "Not now"): .wa_snapshot/ is deleted
```

If a run fails, the Retry dialog makes a **new** copy on every attempt, so a Retry after WhatsApp
has synced sees the new messages.

### How it copies

It uses SQLite's backup function rather than a plain file copy. WhatsApp keeps writing to these
databases while it runs (recent changes sit in `-wal` side files), and copying the files one by
one could catch them half-updated. The backup function reads through SQLite itself, so each copy
is a consistent snapshot. It opens WhatsApp's files read-only and never changes them.

Two details make this work whether or not WhatsApp is open:

- **WhatsApp open:** the side files exist, and the read-only copy includes changes still waiting
  in `-wal`.
- **WhatsApp closed:** SQLite has merged everything into the main file and removed the side files.
  A normal read-only open would fail at this point, so the helper reads the main file as-is.
  It only does this when no `-wal` file exists, so unsaved changes can't be skipped.

Each copy is then turned into a plain single-file database, so Python can open it read-only
without side files.

## One-time setup: give it Full Disk Access

1. Open **System Settings → Privacy & Security → Full Disk Access**.
2. Click **+** and enter your Mac password if asked.
3. Press **Cmd + Shift + G**, paste the program's full path and press Return. To get the path,
   run this from the project folder: `echo "$PWD/tools/wa-snapshot"`
4. Click **Open** and make sure the **wa-snapshot** switch is on.

To check it, run the scheduled job once and read the newest block at the bottom of `out/daily.log`:

```bash
launchctl kickstart gui/$(id -u)/com.salestracker.daily
```

It should start with `wa-snapshot: copied 3 WhatsApp databases …` and show no pop-up.

**Note:** running `tools/wa-snapshot` or `./daily.sh` from Terminal, or from Claude, can still
show a pop-up. macOS then treats Terminal or Claude as the app asking, and those don't have Full
Disk Access, which is intended. The access only takes effect when the scheduled job runs it.

## Good to know

- **What's left exposed.** For the few seconds a run takes, `.wa_snapshot/` holds a copy of your
  WhatsApp chats inside the project, readable only by your user account. A bad Python package
  running at exactly that moment could read your WhatsApp chats. It could not read Mail,
  Messages, Photos or anything else protected, and that's the difference from giving uv access.
- **Rebuilding resets the access.** Any recompile changes the fingerprint, so macOS treats it as
  a new program. Only rebuild if you change the code, then turn its Full Disk Access off and on
  again (or remove it and add it back):
  ```bash
  clang -O2 -Wall -o tools/wa-snapshot tools/wa_snapshot.c -lsqlite3
  ```
- **Moving the project folder** means removing the old entry and adding the program again from
  its new path, and running `./launchd/install.sh` again so the schedule points at the new
  folder. The copy always goes to `.wa_snapshot/` next to the `tools/` folder.
- **If a WhatsApp update renames these databases,** the helper fails with
  `cannot read …: unable to open database file`, the run stops with the Retry dialog, and
  `wa_snapshot.c` needs updating.
- **To undo all of it:** switch wa-snapshot off in Full Disk Access, or remove it from the list.
  The program then can't read anything, and runs fail with "authorization denied" until access is
  given again.
