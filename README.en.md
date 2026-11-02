# PeekTodo

A todo panel that lives on the right edge of your screen. Move your mouse to the far right of the primary display and it slides out with what you should be doing right now; move away and it slides back. Click it to pin, drag a corner to resize. Tray-resident, doesn't steal focus unless you click it, optional autostart.

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

Requires Python 3.10+ and Windows 10/11. The first launch opens the settings panel: pick a source, click a node in the structure tree to use as root, choose a mode, save. No document yet? Hit “新建 Markdown 文档” — it writes a sample template and opens it for editing. Reopen it any time from the tray menu; refresh interval, accent colour, autostart and the desktop shortcut live there too.

![settings](docs/screenshot-settings.png)

Afterwards (when launched from a terminal it moves itself to the background, so closing the terminal does not kill it):

```bash
peektodo                 # normal use (tray resident)
peektodo --setup         # reconfigure
peektodo --force-shown   # keep the panel open, for tweaking styles
peektodo --force         # start another instance even if one is already running
peektodo --doctor        # print what the parser understood (stays in the foreground)
peektodo --no-detach     # stay in the foreground for logs
```

Installed as a package, config lives in `%APPDATA%\PeekTodo\`. Running from source keeps it in the repo root (portable).

No terminal needed: double-click `start.cmd`, which launches it via `pythonw` in the background.

### Desktop shortcut

Saving the settings for the first time drops a `PeekTodo` shortcut on your Desktop (app icon, starts in the background with no console). Uncheck “桌面快捷方式” in the settings to remove it. To recreate it by hand:

```bash
powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1
```

### Updating

Already have a copy? Update **inside the folder you originally cloned**, don't clone again:

```bash
cd PeekTodo
git pull
python -m pip install --no-build-isolation --force-reinstall .   # skip if you installed with pip install -e .
```

Then quit from the tray icon and start it again. `config.json` and `.state.json` are gitignored, so updating leaves your settings and checked items alone.

## Using it

| Action | Result |
|---|---|
| Mouse to the far right edge | panel slides out |
| Move away | slides back |
| **Click the panel** | pins it: takes focus and stays while the mouse moves away |
| **Drag the top-left / bottom-left corner** | resizes the panel, text scales with it; dragging outside the panel doesn't retract it |
| Click a checkbox | tick/untick (local to the panel, never touches the source file) |
| Double-click a row's text | open the source file in your default editor |
| Click far from the panel / Esc | unpin and retract |

The size you drag to is remembered (`panel.width` / `panel.height` in `config.json`).

## Three modes

| Mode | Direct children of the root | Panel shows | Good for |
|---|---|---|---|
| **Week plan** | time slots (`Mon afternoon`) | current slot on top, today below | class/work schedules |
| **Deadline** | dates (`Nov 3`) | overdue + due today on top, upcoming below | assignments, deliverables |
| **Memo** | items directly, no grouping | everything, no filtering | this-week lists, long-term reminders |

The first two share the same shape (root → groups → items); only the **interpretation of the group title** differs — a time slot of the week, or a calendar date. Memo has no groups.

<table>
<tr>
<td width="33%"><b>Week plan</b>: current slot on top, today below<br><img src="docs/screenshot-panel.png"></td>
<td width="33%"><b>Deadline</b>: overdue in red, rest by date<br><img src="docs/screenshot-due.png"></td>
<td width="33%"><b>Memo</b>: one standing list<br><img src="docs/screenshot-memo.png"></td>
</tr>
</table>

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
├─ shortcut.py      desktop shortcut
├─ opener.py        open the source file
├─ template.py      template used by "new Markdown document"
├─ win32.py         pywin32 loading fallback, window styles, key state
├─ app.py           entry point: window, tray, polling
├─ assets/          tray icon and app icon
├─ sources/
│  ├─ markdown.py   headings + list items
│  └─ mubu.py       local Mubu backup
└─ ui/
   ├─ panel.py      the panel (with drag-to-resize)
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
