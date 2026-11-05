"""The development log docs/prompts.csv -- read, written and turned into a Claude prompt.

Pure logic, no tkinter, used by the Prompts tab (shared/prompts_tab.py). The log
is repo-level: one csv, one row per request, the row NUMBER (header not counted) being
the request id a prompt names as "csv row N".

A request is PENDING while its executed column is empty. compose_prompt() builds what a
run is sent: the general prompt (invariant, editable in the tab) followed by the numbered
request lines and the stamp the run should write back into each row it finishes.
"""
from __future__ import annotations

import csv
import datetime
import shutil
from pathlib import Path

from shared.config import PromptsLog, RepoPaths

_H = PromptsLog.HEADERS
I_REQUESTED = _H.index(PromptsLog.COL_REQUESTED)
I_EXECUTED = _H.index(PromptsLog.COL_EXECUTED)
I_CATEGORY = _H.index(PromptsLog.COL_CATEGORY)
I_REQUEST = _H.index(PromptsLog.COL_REQUEST)
I_NOTES = _H.index(PromptsLog.COL_NOTES)
I_FILES = _H.index(PromptsLog.COL_FILES)


def one_line(text: str) -> str:
    return ' '.join((text or '').split())


def clip(text: str, n: int) -> str:
    text = one_line(text)
    return text if len(text) <= n else text[:n - 1] + '…'


def now_stamp() -> str:
    return datetime.datetime.now().strftime(PromptsLog.DATETIME_FORMAT)


def stamp_key(text: str) -> float:
    """Sort key of a logged datetime; an empty one (a pending request) reads newest."""
    text = (text or '').strip()
    if not text:
        return float('inf')
    for fmt in PromptsLog.DATETIME_FORMATS_READ:
        try:
            return datetime.datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    return float('-inf')


def row_key(row: list) -> float:
    """Sort key of a request: when it was made, or when it was worked if it carries no
    requested stamp (a row written before that column existed has both)."""
    return stamp_key(row[I_REQUESTED].strip() or row[I_EXECUTED])


def csv_name(path_file=None) -> str:
    """The csv named the way a prompt should name it -- relative to the repo root."""
    path_file = Path(path_file or RepoPaths.path_file_prompts)
    try:
        return path_file.relative_to(RepoPaths.path_dir_root).as_posix()
    except ValueError:
        return path_file.name


def read_csv(path_file=None) -> list:
    """Rows of the log, header dropped, every row padded to the seven columns."""
    path_file = Path(path_file or RepoPaths.path_file_prompts)
    if not path_file.is_file():
        return []
    with open(path_file, 'r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    if rows and [c.strip() for c in rows[0]][:1] == _H[:1]:
        rows = rows[1:]
    return [[str(c or '') for c in (r + [''] * len(_H))[:len(_H)]] for r in rows]


def write_csv(rows: list, path_file=None) -> None:
    """Replace the csv, keeping the previous content as prompts.csv.bak -- one undo,
    never a lost log. The caller re-reads first, so a file edited meanwhile is not
    overwritten blindly."""
    path_file = Path(path_file or RepoPaths.path_file_prompts)
    path_file.parent.mkdir(parents=True, exist_ok=True)
    if path_file.is_file():
        shutil.copyfile(path_file, str(path_file) + RepoPaths.BAK_SUFFIX)
    with open(path_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(_H)
        writer.writerows(rows)


def new_row(request: str, category: str = '', notes: str = '') -> list:
    """A fresh request: stamped as requested, executed left empty -- which is what marks
    it pending."""
    row = [''] * len(_H)
    row[I_REQUESTED] = now_stamp()
    row[I_CATEGORY] = category.strip()
    row[I_REQUEST] = request.strip()
    row[I_NOTES] = notes.strip()
    return row


def is_pending(row: list) -> bool:
    return not row[I_EXECUTED].strip()


def pending_rows(rows: list, picked=None) -> list:
    """(index, row) of every request still waiting for work, or of the picked indexes."""
    if picked:
        wanted = {int(i) for i in picked}
        return [(i, r) for i, r in enumerate(rows)
                if i in wanted and any(c.strip() for c in r)]
    return [(i, r) for i, r in enumerate(rows) if is_pending(r)]


def categories(rows: list) -> list:
    """The configured categories plus any the log already uses, sorted -- what the
    tab's category FILTER offers, so a row written under an older category is still
    reachable."""
    return sorted(set(PromptsLog.CATEGORIES) |
                  {r[I_CATEGORY].strip() for r in rows if r[I_CATEGORY].strip()})


def tab_category(tab_text: str) -> str:
    """The category a request written from a tab is filed under -- 'Files Tab' for
    the Files tab, the shape PromptsLog.CATEGORIES already uses. '' for no tab."""
    name = ' '.join((tab_text or '').split())
    if not name:
        return ''
    if name.lower().endswith(' tab'):
        return name
    return PromptsLog.CATEGORY_TAB % name


def dialog_categories(extra: str = '') -> list:
    """What a request may be FILED under: the configured list, plus the one category
    the caller is filing under right now (the tab it was written from).

    Deliberately not the union of everything the log holds -- a dropdown offering
    every category ever used is what made picking one hard, and a category no longer
    configured should not be handed out to new requests. A tab the list does not name
    is still offered, because that is where this request was written."""
    cats = list(PromptsLog.CATEGORIES)
    extra = (extra or '').strip()
    if extra and extra not in cats:
        cats.append(extra)
    return cats


def default_general_prompt(path_file=None) -> str:
    """The invariant part of the prompt -- everything but the request lines. Shown
    editable in the tab, so an edit never has to touch the requests."""
    name_csv = csv_name(path_file)
    return '\n'.join([
        'Work the pending requests of %s listed below, in their order, following %s and '
        'the %s it requires.'
        % (name_csv, RepoPaths.FILE_GUIDE, RepoPaths.FILE_GUIDE_GENERAL),
        'The notes of a request are part of it, not commentary on it: read them before '
        'starting that item.',
        'For each request, when its work is done, write the outcome back into its own row '
        'of %s: stamp the %s column with the stamp given below (leave it empty only if the '
        'request stays open), leave the %s column as it is, give it a category if the row '
        'has none, put one sentence in the work column, the files it landed in in the '
        'files column, and anything worth keeping that surfaced while working it (an error '
        'hit, a path, a constraint) in the notes column, keeping what the notes column '
        'already holds. Edit the csv in place -- it is the log, not a generated view of '
        'one. Keep the column order %s and the rows oldest first, and do not touch the '
        'rows of requests you were not asked to work.'
        % (name_csv, PromptsLog.COL_EXECUTED, PromptsLog.COL_REQUESTED, ','.join(_H)),
        'Update %s when a convention moved with the work, and do not commit and do not '
        'push; leave the work in the working tree.' % RepoPaths.FILE_GUIDE,
    ])


def request_lines(chosen: list, stamp: str = '') -> str:
    """The numbered request list, one block per (index, row) pair. stamp is the datetime
    the run should write into the executed column of each row it finishes; it rides with
    the requests rather than the general prompt, so an edited general prompt still
    carries the value."""
    lines = ['The requests, %d of them:' % len(chosen), '']
    for n, (i, r) in enumerate(chosen, 1):
        cat = r[I_CATEGORY].strip() or 'no category'
        lines.append('[%d] (csv row %d, %s) %s' % (n, i + 1, cat, one_line(r[I_REQUEST])))
        if r[I_NOTES].strip():
            lines.append('    notes: %s' % one_line(r[I_NOTES]))
    if stamp:
        lines += ['', 'The datetime to stamp into the %s column of each of these rows, '
                      'once its work is done, is %s -- the time this run was sent.'
                  % (PromptsLog.COL_EXECUTED, stamp)]
    return '\n'.join(lines)


def compose_prompt(general_text: str, chosen: list, stamp: str = '') -> str:
    return general_text.rstrip() + '\n\n' + request_lines(chosen, stamp)


def default_chat_prompt(path_file=None) -> str:
    """The invariant part of a CHAT turn -- a question to answer, not work to do.

    The Chat window sends this above the message. It says in words what the run's
    permission mode (ClaudeRun.CHAT_PERMISSION_MODE) already enforces, so a chat can
    neither change a file nor write into the log it is asking about."""
    return '\n'.join([
        'Answer the question below about this repo, following %s. Read whatever you '
        'need to read.' % RepoPaths.FILE_GUIDE,
        'This is a question, not a request for work: change no file, write nothing into '
        '%s, and do not commit or push.' % csv_name(path_file),
        'Answer in plain language and keep it short; name a file or a line only where it '
        'is needed to act on the answer.',
    ])


def compose_chat(question: str, general_text: str = '') -> str:
    """One chat turn: the invariant part above, the typed question below."""
    return ((general_text or default_chat_prompt()).rstrip()
            + '\n\nThe question:\n\n' + (question or '').strip())
