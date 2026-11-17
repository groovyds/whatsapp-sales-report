/*
 * wa-snapshot: copy the WhatsApp Mac app's databases into this project, and nothing else.
 *
 * Why it exists: macOS asks permission whenever a program reads another app's data folder.
 * Giving that permission (Full Disk Access) to uv or Python would let every package they run
 * read all your data. Instead, only this small program gets Full Disk Access, and all it can
 * do is the copy below. See tools/README.md for the full explanation.
 *
 * What it does, every time, with no options:
 *   1. Opens three WhatsApp databases READ-ONLY (it never changes WhatsApp's data):
 *        ~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/
 *            ChatStorage.sqlite   messages and groups
 *            ContactsV2.sqlite    your contact names
 *            LID.sqlite           WhatsApp id -> phone number links
 *   2. Copies each one with SQLite's backup function, which gives a consistent snapshot even
 *      while WhatsApp is writing (a plain file copy could catch it half-written).
 *   3. Writes the copies to <project>/.wa_snapshot/ (folder 0700, files 0600: only you).
 *      The destination is fixed relative to this program, so it can't be pointed elsewhere.
 *
 * Exit codes: 0 = all copied, 1 = could not read WhatsApp data (usually: no Full Disk Access,
 * or the app isn't installed), 2 = could not write the snapshot.
 *
 * Build (done once; rebuilding changes the program, so macOS will need permission again):
 *   clang -O2 -Wall -o tools/wa-snapshot tools/wa_snapshot.c -lsqlite3
 */
#include <errno.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <pwd.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* Relative to your home folder. Fixed at build time; the -D override is only for test builds. */
#ifndef WA_SOURCE_DIR
#define WA_SOURCE_DIR "Library/Group Containers/group.net.whatsapp.WhatsApp.shared"
#endif
static const char *SOURCE_DIR = WA_SOURCE_DIR;
static const char *FILES[] = {"ChatStorage.sqlite", "ContactsV2.sqlite", "LID.sqlite"};

/* <project>/.wa_snapshot, found from this program's own location (<project>/tools/wa-snapshot). */
static int snapshot_dir(char *out, size_t size) {
    char exe[PATH_MAX], real[PATH_MAX];
    uint32_t len = sizeof exe;
    if (_NSGetExecutablePath(exe, &len) != 0 || !realpath(exe, real)) return -1;
    char *tools = dirname(real);              /* <project>/tools */
    char project[PATH_MAX];
    strlcpy(project, tools, sizeof project);
    char *proj = dirname(project);            /* <project> */
    return snprintf(out, size, "%s/.wa_snapshot", proj) < (int)size ? 0 : -1;
}

static int probe(const char *uri, sqlite3 **db) {
    if (*db) { sqlite3_close(*db); *db = NULL; }
    return sqlite3_open_v2(uri, db, SQLITE_OPEN_READONLY | SQLITE_OPEN_URI, NULL) == SQLITE_OK &&
           sqlite3_exec(*db, "SELECT count(*) FROM sqlite_master", NULL, NULL, NULL) == SQLITE_OK;
}

/* Open read-only. While WhatsApp runs, its -wal/-shm side files exist and a normal read-only
 * open sees the latest data. When WhatsApp is closed, SQLite removes them, and a read-only open
 * then fails (it would have to create -shm). In that case the main file holds everything, so it
 * is opened as "immutable" (read as a plain file). Only done when no -wal file exists, so
 * unsaved changes can never be skipped. */
static int readable(const char *path, sqlite3 **db) {
    char uri[PATH_MAX + 32], wal[PATH_MAX];
    snprintf(uri, sizeof uri, "file:%s?mode=ro", path);
    if (probe(uri, db)) return 1;
    snprintf(wal, sizeof wal, "%s-wal", path);
    if (access(path, F_OK) != 0 || access(wal, F_OK) == 0) return 0;
    snprintf(uri, sizeof uri, "file:%s?immutable=1", path);
    return probe(uri, db);
}

/* Copy one database: 0 ok, 1 can't read the source, 2 can't write the copy. */
static int copy_db(const char *src_path, const char *dst_path) {
    sqlite3 *src = NULL, *dst = NULL;
    int rc = 1;
    if (!readable(src_path, &src)) {
        fprintf(stderr, "wa-snapshot: cannot read %s: %s\n", src_path,
                src ? sqlite3_errmsg(src) : "out of memory");
        goto done;
    }

    char tmp[PATH_MAX];
    snprintf(tmp, sizeof tmp, "%s.tmp", dst_path);
    unlink(tmp);
    rc = 2;
    if (sqlite3_open_v2(tmp, &dst, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, NULL) != SQLITE_OK) {
        fprintf(stderr, "wa-snapshot: cannot create %s: %s\n", tmp, sqlite3_errmsg(dst));
        goto done;
    }
    sqlite3_backup *b = sqlite3_backup_init(dst, "main", src, "main");
    if (!b) {
        fprintf(stderr, "wa-snapshot: backup failed: %s\n", sqlite3_errmsg(dst));
        goto done;
    }
    int step, tries = 0;
    while ((step = sqlite3_backup_step(b, -1)) == SQLITE_BUSY || step == SQLITE_LOCKED) {
        if (++tries > 50) break;              /* WhatsApp busy writing: wait up to ~5 s */
        sqlite3_sleep(100);
    }
    sqlite3_backup_finish(b);
    if (step != SQLITE_DONE) {
        fprintf(stderr, "wa-snapshot: copying %s failed: %s\n", src_path, sqlite3_errstr(step));
        goto done;
    }
    /* The copy inherits WhatsApp's WAL mode; make it a plain single file so it can be opened
     * read-only later without side files. */
    sqlite3_exec(dst, "PRAGMA journal_mode=DELETE", NULL, NULL, NULL);
    sqlite3_close(dst);
    dst = NULL;
    chmod(tmp, 0600);
    if (rename(tmp, dst_path) != 0) {
        fprintf(stderr, "wa-snapshot: cannot write %s: %s\n", dst_path, strerror(errno));
        goto done;
    }
    rc = 0;
done:
    if (dst) sqlite3_close(dst);
    if (src) sqlite3_close(src);
    return rc;
}

int main(void) {
    /* Home folder from the user database, not $HOME, so the source can't be redirected. */
    struct passwd *pw = getpwuid(getuid());
    char out_dir[PATH_MAX];
    if (!pw || snapshot_dir(out_dir, sizeof out_dir) != 0) {
        fprintf(stderr, "wa-snapshot: cannot work out folders\n");
        return 2;
    }
    if (mkdir(out_dir, 0700) != 0 && errno != EEXIST) {
        fprintf(stderr, "wa-snapshot: cannot create %s: %s\n", out_dir, strerror(errno));
        return 2;
    }
    chmod(out_dir, 0700);

    for (size_t i = 0; i < sizeof FILES / sizeof *FILES; i++) {
        char src[PATH_MAX], dst[PATH_MAX];
        snprintf(src, sizeof src, "%s/%s/%s", pw->pw_dir, SOURCE_DIR, FILES[i]);
        snprintf(dst, sizeof dst, "%s/%s", out_dir, FILES[i]);
        int rc = copy_db(src, dst);
        if (rc) {
            if (rc == 1)
                fprintf(stderr, "wa-snapshot: if this says 'authorization denied', give this program "
                                "Full Disk Access (see tools/README.md).\n");
            return rc;
        }
    }
    printf("wa-snapshot: copied %zu WhatsApp databases to %s\n", sizeof FILES / sizeof *FILES, out_dir);
    return 0;
}
