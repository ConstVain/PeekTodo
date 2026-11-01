# PeekTodo

A todo panel that lives on the right edge of your screen. Move your mouse to the far right of the primary display and it slides out with what you should be doing right now; move away and it slides back. Tray-resident, never steals focus, optional autostart.

[中文说明](README.md)

![panel](docs/screenshot-panel.png)

## What it solves

You have a weekly plan, but you are not going to open your notes app just to check what's next.
PeekTodo pins it to the screen edge — one flick of the mouse and you know.

**Sources**: local Markdown (`- [ ]` lists) or a Mubu document.
**Read-only**: it never modifies your files. Checkboxes on the panel are local and expire after 7 days.

## Quick start

```bash
git clone https://github.com/ConstVain/PeekTodo.git
cd PeekTodo
pip install .
peektodo
```

Or run straight from source:

```bash
pip install -r requirements.txt
python -m peek_todo
```

Requires Python 3.10+ and Windows 10/11. The first launch opens the settings panel: pick a source, click a node in the structure tree to use as root, choose a mode, save. No document yet? Hit “新建 Markdown 文档” — it writes a sample template and opens it for editing. Reopen it any time from the tray menu; refresh interval, accent colour and autostart live there too.

![settings](docs/screenshot-settings.png)

Afterwards (when launched from a terminal it moves itself to the background, so closing the terminal does not kill it):

```bash
peektodo                 # normal use (tray resident)
peektodo --setup         # reconfigure
peektodo --force-shown   # keep the panel open, for tweaking styles
peektodo --doctor        # print what the parser understood (stays in the foreground)
peektodo --no-detach     # stay in the foreground for logs
```

Installed as a package, config lives in `%APPDATA%\PeekTodo\`. Running from source keeps it in the repo root (portable).

No terminal needed: double-click `start.cmd`, which launches it via `pythonw` in the background.

## Three modes

| Mode | Direct children of the root | Panel shows | Good for |
|---|---|---|---|
| **Week plan** | time slots (`Mon afternoon`) | current slot on top, today below | class/work schedules |
| **Deadline** | dates (`Nov 3`) | overdue + due today on top, upcoming below | assignments, deliverables |
| **Memo** | items directly, no grouping | everything, no filtering | this-week lists, long-term reminders |

The first two share the same shape (root → groups → items); only the **interpretation of the group title** differs — a time slot of the week, or a calendar date. Memo has no groups.

Dates understood: `11月2日`, `11月3号`, `2026-11-02`, `11/2`, `今天`(today), `明天`(tomorrow), `后天`(day after).
Time slots: `周一下午`, `星期二上午`, `礼拜三`, `周7 早上` — or add your own aliases under `vocabulary` in `config.json`.

Pick the wrong mode and you won't get an empty panel: week-plan mode will suggest switching when all titles are dates, and a flat list automatically falls back to memo.

## Why no fixed syntax

People write things differently (`周一下午` / `礼拜一下午` / `下午`). PeekTodo doesn't ask you to change your document:

- Time words are recognised through a configurable vocabulary (`vocabulary` in `config.json`)
- Titles it can't parse are **still displayed** — they just don't take part in time filtering, and the panel flags them
- `--doctor` prints exactly what the parser understood, so a mismatch is visible at a glance

```
source  docs/sample-plan.md
root    周计划
mode    Week plan
──────────────────────────────────────────────
✓ 周一下午                  Monday afternoon  ·  4 items (2 levels)
! 待定                      no time found     ·  1 item
──────────────────────────────────────────────
8 items, 1 done
```

## Layout

```
peek_todo/
├─ model.py         Node / Task / Group
├─ vocabulary.py    time-slot and date recognition (vocabulary configurable)
├─ structure.py     root node + three modes
├─ selection.py     slices by current time
├─ state.py         local checkboxes (never touches the source)
├─ edge.py          edge-hotzone detector
├─ report.py        parse report
├─ doctor.py        CLI diagnostics
├─ autostart.py     autostart via HKCU Run
├─ app.py           entry point: window, tray, polling
├─ assets/          tray icon and app icon
├─ sources/
│  ├─ markdown.py   headings + list items
│  └─ mubu.py       local Mubu backup
└─ ui/
   ├─ panel.py      the panel
   └─ settings.py   settings panel (also first run)
```

## Development

```bash
pip install -r requirements.txt
python -m pytest tests -q
```

`verify.cmd` runs the tests plus a diagnostic on both bundled sample sources.

## Notes and limitations

- **Read-only**: never writes to your Markdown or Mubu document. Checkboxes are local.
- **No network**: the app makes no network requests.
- **Mubu source** reads the desktop client's local cache, an undocumented format that may break with client updates. On failure it keeps the last good data and shows a warning instead of going blank.
- Windows 10/11 only (relies on Win32 `WS_EX_NOACTIVATE` and cursor polling).

## License

GPL-3.0 — see [LICENSE](LICENSE). PyQt5 is GPL/commercially dual-licensed, so the project is released under GPL.
