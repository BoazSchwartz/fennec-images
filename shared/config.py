"""Constants of the shared GUI layer (copied from fennec-bookkeeping's shared/, kept in step
with it so the General and Prompts tabs stay identical across the Fennec repos).

The app's own config (fennec_images/config.py) RE-EXPORTS the classes below next to its own,
so app code writes `config.LayoutConfig` after a single `from fennec_images import config`.
"""
from pathlib import Path


class RepoPaths:
    """Repo-level paths -- the same for BOTH apps. shared/ sits one folder under the repo
    root, so the root is this file's grandparent."""
    path_dir_root = Path(__file__).resolve().parent.parent
    path_dir_docs = path_dir_root / 'docs'
    # The development log both apps' Prompts tab reads and writes (shared/prompts_log.py)
    path_file_prompts = path_dir_docs / 'prompts.csv'
    # Repo-level log folder (gitignored); holds the prompt text of the last Claude run
    path_dir_log = path_dir_root / 'log'
    # The app icons (scripts/make_icons.py draws them); one per app, so the two
    # windows are told apart on the taskbar. Each app's config names its own file.
    path_dir_assets = path_dir_root / 'assets'
    FILE_ICON_IMAGES = 'fennec-images.ico'
    FILE_CLAUDE_PROMPT = 'claude_prompt.txt'
    # A Chat turn writes its prompt to a file of its own, so the last CODE prompt stays
    # readable beside it (a chat is sent far more often than a run)
    FILE_CLAUDE_CHAT = 'claude_chat.txt'
    # Where a launch's console output lands: each app's run_gui.vbs redirects its .bat
    # into this file, and a silent RESTART writes to the same one (see LAUNCHING in
    # CLAUDE.md) -- overwritten at each launch, so a start-up traceback is always on disk
    FILE_LAUNCH_LOG_IMAGES = 'launch_images.log'
    BAK_SUFFIX = '.bak'
    # The guides a Claude run is told to follow; named here, never spelled out in a prompt
    FILE_GUIDE = 'CLAUDE.md'
    FILE_GUIDE_GENERAL = 'CLAUDE_GENERAL.md'


class AppConfig:
    """Restart plumbing -- identical in both apps. Each app's config subclasses this to add
    its own identity (TITLE / STATE_DIR / data-file prefix)."""
    RESTART_MODE_SILENT = 'Silent'
    RESTART_MODE_CONSOLE = 'Visible Console'
    RESTART_MODES = {
        RESTART_MODE_SILENT:  ('DETACHED_PROCESS', 'CREATE_NEW_PROCESS_GROUP'),
        RESTART_MODE_CONSOLE: ('CREATE_NEW_CONSOLE', 'CREATE_NEW_PROCESS_GROUP'),
    }
    DEFAULT_RESTART_MODE = RESTART_MODE_SILENT
    # The interpreter a SILENT restart spawns. DETACHED_PROCESS does not stop a console
    # app from opening a console of its own -- python.exe detached comes up with a visible
    # black box -- and pythonw.exe, being GUI-subsystem, can never have one.
    PYTHON_GUI_EXE = 'pythonw.exe'


class LayoutConfig:
    COL_RESTORE_DELAY_MS = 600
    MIN_COL_WIDTH = 40
    SASH_MIN_PX = 20
    MIN_FONT_SIZE = 8
    MAX_FONT_SIZE = 22


class StyleConfig:
    LOG_BG = '#1e1e1e'
    LOG_FG = '#d4d4d4'
    DEFAULT_ACCENT = 'Blue'
    FONT_FAMILY = 'Segoe UI'
    ROW_EVEN_BG = '#ffffff'
    ROW_ODD_BG = '#f2f2f2'
    ROW_ODD_BLUE_BG = '#dbeafe'
    ACCENT_COLORS = {
        'Default': None,
        'Blue': '#1d4ed8',
        'Teal': '#0f766e',
        'Green': '#15803d',
        'Orange': '#c2410c',
        'Purple': '#4c1d95',
        'Gray': '#374151',
    }
    # A pending request in the Prompts tab (no executed stamp)
    PROMPT_PENDING_BG = '#fff8ec'
    # The General tab's Save & Apply button: an Action button carrying the app's own
    # text size instead of the Action bump, in a box shortened vertically to match.
    # A dotted name, so ttk resolves everything else from 'Action.TButton'.
    STYLE_SAVE_APPLY = 'SaveApply.Action.TButton'
    # The General tab's Application row is ONE row of buttons, so the three wear the same
    # height: same font size, same vertical padding, same border. Restart App keeps its
    # accent (a dotted name off Action.TButton), Open Config Folder stays a plain button.
    STYLE_RESTART_APP = 'Restart.Action.TButton'
    STYLE_OPEN_CONFIG = 'OpenConfig.TButton'
    # (left, top/bottom) of all three -- the vertical half is what gives the row its height
    GENERAL_BTN_PADDING = (10, 6)
    # The Prompts tab's two runs, each in its own color so which one is about to start is
    # read without looking twice: Code writes code (orange), Chat only answers (purple).
    # DOTTED names off 'TButton', so ttk resolves the font, the padding and the relief
    # from it -- which is also why a font-size change needs no repaint here: the two
    # styles set colors only, and the size follows the plain button they hang off.
    # Configured by the tab itself (shared/prompts_tab.py), not by an app's
    # _configure_style: the buttons are the shared tab's own, in both apps.
    STYLE_BTN_CODE = 'Code.TButton'
    STYLE_BTN_CHAT = 'Chat.TButton'
    CODE_BTN_BG = '#f97316'
    CODE_BTN_FG = 'black'        # orange is too light to carry white letters
    CODE_BTN_ACTIVE = '#fb923c'
    CODE_BTN_PRESSED = '#c2410c'
    CHAT_BTN_BG = '#c084fc'      # light purple, so the two runs are told apart at a glance
    CHAT_BTN_FG = 'black'        # light purple carries black letters, as the orange does
    CHAT_BTN_ACTIVE = '#d8b4fe'
    CHAT_BTN_PRESSED = '#9333ea'
    # DISABLED keeps each button's OWN hue, only washed out: both are disabled for as long
    # as a run goes, and a gray pair says nothing about which button starts what. The
    # letters go gray too, which is what still reads as "not now".
    CODE_BTN_DISABLED = '#fde3cc'
    CHAT_BTN_DISABLED = '#eddcfb'
    BTN_DISABLED_FG = '#7a7a7a'
    # What every OTHER colored button washes out to while disabled -- the shade both apps'
    # own Action/Delete styles already use
    BTN_DISABLED_BG = '#888888'
    # The Chat window's transcript is a log pane (LOG_BG/LOG_FG), so the two speakers
    # are told apart by color: the question in light blue, the answer in the pane's own
    # foreground, and the tool calls dim beside it.
    CHAT_FG_YOU = '#7dd3fc'
    CHAT_FG_META = '#9a9a9a'


class SashConfig:
    """Default sash fractions, shared. The state.json KEYS a sash is stored under are
    per-app, so each app's config subclasses this and adds its own KEY_* names."""
    LOG_FRAC = 0.70
    HORIZ_HALF = 0.50
    # The Prompts tab is identical in both apps (as the General tab is), so its key is
    # shared too; each app still stores it in its OWN state.json.
    KEY_PROMPTS_LOG = 'prompts_log_frac'
    # Same reason: the General tab's log pane is the same tab in both apps.
    KEY_GENERAL_LOG = 'general_log_frac'


class LayoutProfiles:
    """The General tab's Screen setting: two named arrangements of the same GUI, so one
    machine keeps a big-screen layout and a laptop keeps its own (aligned with
    C:\\vc\\resolight\\resolight-app, core/config.py LAYOUT_PROFILES).

    A profile holds every piece of geometry the app already remembers -- the font size,
    the window size, every sash fraction and every table's column widths -- under one
    entry of state.json's KEY_STATE dict. The app works from the FLAT keys as it always
    did; shared/layout_profiles.py is what copies the active profile onto them and back.
    Shared because the General tab is identical in both apps."""

    LARGE = 'Large screen'
    SMALL = 'Small screen'
    NAMES = [LARGE, SMALL]
    DEFAULT = LARGE
    # state.json: the profiles themselves ({name: {geometry key: value}}), and which one
    # is in use. The active name is NOT inside a profile -- it says which one to read.
    KEY_STATE = 'screen_profiles'
    KEY_ACTIVE = 'screen_profile'
    # The two flat keys that belong to a profile whatever app it is; each app adds its
    # own sash and column-width keys (they are the same names it already stores).
    KEY_FONT_SIZE = 'font_size'
    KEY_WINDOW = 'window_geometry'
    # What a profile that was never shaped starts from. The font goes with the screen:
    # the size that reads well on a 24 inch monitor wastes half a laptop panel.
    FONT_DEFAULT = {LARGE: 12, SMALL: 9}
    WINDOW_DEFAULT = {LARGE: '1880x1120', SMALL: '1280x820'}


class PromptsLog:
    """The development log docs/prompts.csv -- its column order and its category list.
    Read by shared/prompts_log.py and the Prompts tab (shared/prompts_tab.py), so both
    walk the same columns. The log is REPO-level: one file, shown by both apps.
    Two datetime columns answering different questions: requested is stamped when the
    request is written, executed when the run that solved it was sent. A row with no
    executed stamp is a PENDING request -- that is what marks one."""

    COL_REQUESTED = 'requested'
    COL_EXECUTED = 'executed'
    COL_CATEGORY = 'category'
    COL_REQUEST = 'request'
    COL_NOTES = 'notes'
    COL_WORK = 'work'
    COL_FILES = 'files'
    HEADERS = [COL_REQUESTED, COL_EXECUTED, COL_CATEGORY, COL_REQUEST, COL_NOTES,
               COL_WORK, COL_FILES]
    # What the NEW REQUEST / Edit dialog offers: the log's SUBJECTS, each at most two
    # words -- the cross-cutting ones first, then one entry per TAB ('%s Tab', the shape
    # CATEGORY_TAB makes of a right-click's tab).
    CATEGORIES = ['GUI', 'Classify', 'Albums', 'Data', 'Refactor',
                  'Classify Tab', 'Albums Tab', 'Prompts Tab', 'General Tab']
    # How a tab's name becomes a category: the shape every entry above already has.
    # A request written by right-clicking a tab is filed under it (prompts_log.
    # tab_category), so a tab with no entry of its own still files itself correctly.
    CATEGORY_TAB = '%s Tab'
    # The stamp written into both datetime columns
    DATETIME_FORMAT = '%d/%m/%Y %H:%M'
    # Stamps a hand-edited cell may also hold; accepted when sorting
    DATETIME_FORMATS_READ = ('%d/%m/%Y %H:%M', '%d/%m/%Y', '%Y-%m-%d %H:%M', '%Y-%m-%d')


class PromptsState:
    """state.json keys the Prompts tab owns (its sash key is SashConfig.KEY_PROMPTS_LOG).
    Each app keeps its own copy in its own state.json."""

    KEY_COL_WIDTHS = 'prompts_col_widths'
    KEY_CLAUDE_SESSION = 'claude_session_id'
    KEY_CLAUDE_MODEL = 'claude_model'
    KEY_CLAUDE_PERMISSION = 'claude_permission_mode'
    KEY_CLAUDE_GENERAL = 'claude_general_prompt'
    KEY_CLAUDE_ADD_DIRS = 'claude_add_dirs'
    KEY_CLAUDE_EXTRA = 'claude_extra_args'


class ClaudeRun:
    """How the Prompts tab runs the claude CLI: headless (--print), output streamed as
    json lines into the tab's log pane, the session id captured from the stream so the
    next run can continue the same conversation with --resume. The permission mode is
    what lets a headless run act at all -- it cannot ask, so whatever the mode would ask
    about is denied. The list is the installed CLI's own (claude --help)."""

    EXE = 'claude'
    OUTPUT_FORMAT = 'stream-json'
    PERMISSION_MODES = ['auto', 'acceptEdits', 'dontAsk', 'bypassPermissions',
                        'plan', 'manual']
    DEFAULT_PERMISSION_MODE = 'auto'
    # The Chat button asks a question, so its run is read-only BY CONSTRUCTION: 'plan'
    # is the mode that answers and changes nothing, and the chat prompt says so too --
    # a chat can never edit a file or the log it is asking about.
    CHAT_PERMISSION_MODE = 'plan'
    # Separator of the Add dirs field
    DIR_SEP = ';'
    # Characters of a request shown per checkbox line in the run dialog
    REQUEST_CLIP = 110


class ClaudeModels:
    """Which model the Prompts tab may point a run at. The dialog sends one of these
    KEYS and never a command line, so nothing reaches the argument list except by being
    on this list already. An empty model leaves --model off -- the CLI's own default."""

    LIST = [
        {'key': 'default', 'label': 'Default', 'model': ''},
        {'key': 'fable', 'label': 'Fable 5.1', 'model': 'claude-fable-5-1'},
        {'key': 'opus', 'label': 'Opus 5.5', 'model': 'claude-opus-5-5'},
        {'key': 'sonnet', 'label': 'Sonnet 5.5', 'model': 'claude-sonnet-5-5'},
        {'key': 'haiku', 'label': 'Haiku 5.5', 'model': 'claude-haiku-5-5'},
    ]
    DEFAULT_KEY = 'default'

    @staticmethod
    def entry(key):
        """The row of LIST with this key, or None -- an unknown key is refused."""
        for m in ClaudeModels.LIST:
            if m['key'] == key:
                return m
        return None


class CommonUIStrings:
    """Display strings both apps use VERBATIM -- the General tab (identical in both) plus
    the few labels every tab repeats. Each app's UIStrings subclasses this and adds its own
    tab names / headers."""

    TAB_GENERAL = '  General  '
    TAB_PROMPTS = '  Prompts  '

    SEC_APPLICATION = 'Application'
    SEC_SUMMARY = 'Summary'
    SEC_PROJECT = 'Project'

    LBL_PROJECT_ROOT = 'Project Root'
    LBL_RECENT = 'Recent Projects'
    LBL_FONT_SIZE = 'Font size'
    LBL_ACCENT = 'Accent'
    LBL_RESTART_MODE = 'Restart mode'
    LBL_SCREEN = 'Screen'
    # What the log says when the Screen setting picks the other arrangement
    MSG_SCREEN_SWITCHED = ('[SCREEN] "{name}" now in use, font {font}. Drag any sash or '
                           'column to shape it; Save & Apply keeps it for this screen.\n')
    # Row counter shown next to each table's All/None buttons.
    LBL_ROW_COUNT = '{n} items'
    # Header of a tab's log pane -- the General tab carries one like every other tab.
    HDR_LOG = 'Log'

    BTN_SAVE_APPLY = 'Save & Apply'
    BTN_RESTART_APP = 'Restart App'
    BTN_OPEN_CONFIG = 'Open Config Folder'

    # Prompts tab -- identical in both apps, as the General tab is.
    PRM_COL_ID = 'ID'
    PRM_COL_REQUESTED = 'Requested at'
    PRM_COL_EXECUTED = 'Executed at'
    PRM_COL_CATEGORY = 'Category'
    PRM_COL_REQUEST = 'Request'
    PRM_COL_NOTES = 'Notes'
    PRM_COL_WORK = 'Work'
    PRM_COL_FILES = 'Files'
    PRM_FILTER = 'Filter'
    PRM_ALL_CATEGORIES = 'All categories'
    PRM_STATE_ALL = 'All'
    PRM_STATE_PENDING = 'Pending'
    PRM_STATE_DONE = 'Done'
    PRM_COUNT = '{shown} / {total} requests, {pending} pending'
    PRM_BTN_REFRESH = 'Refresh'
    PRM_BTN_ADD = 'Add'
    PRM_BTN_EDIT = 'Edit'
    PRM_BTN_DELETE = 'Delete'
    # The two runs: Code works the pending requests, Chat only answers about the repo
    PRM_BTN_CODE = 'Code'
    PRM_BTN_CHAT = 'Chat'
    PRM_BTN_STOP = 'Stop'
    PRM_BTN_SAVE = 'Save'
    PRM_BTN_CANCEL = 'Cancel'
    PRM_BTN_CLEAR = 'Clear'
    PRM_BTN_CLOSE = 'Close'
    PRM_BTN_SEND = 'Send'
    PRM_HDR_LOG = 'Claude Log'
    PRM_NO_SELECTION = 'Select a request in the table first.'
    PRM_ADD_TITLE = 'New request'
    PRM_ADD_HINT = ('The whole box is one request, newlines and all. Notes are what the run '
                    'should know before it starts, not a comment about the request.')
    PRM_EDIT_TITLE = 'Request #{n}'
    PRM_DEL_TITLE = 'Delete request'
    PRM_DEL_ASK = ('Delete request #{n}?\n\n{text}\n\nEvery later request is renumbered, '
                   'and the previous log is kept as prompts.csv.bak.')
    PRM_DLG_TITLE = 'Start Claude'
    PRM_DLG_REQUESTS = 'Pending requests'
    PRM_DLG_NONE = 'No pending request in the log.'
    PRM_DLG_GENERAL = 'General prompt'
    PRM_DLG_RESET = 'Reset to default'
    PRM_DLG_MODEL = 'Model'
    PRM_DLG_CONTEXT = 'Context'
    PRM_DLG_CTX_NEW = 'New session'
    PRM_DLG_CTX_CONTINUE = 'Continue last run'
    PRM_DLG_PERMISSIONS = 'Permissions'
    PRM_DLG_ADD_DIRS = 'Add dirs'
    PRM_DLG_EXTRA = 'Extra CLI args'
    PRM_BTN_START = 'Start Claude'
    # The Chat window: a conversation about the repo, answered in the window itself
    PRM_CHAT_TITLE = 'Chat with Claude'
    PRM_CHAT_TRANSCRIPT = 'Chat'
    PRM_CHAT_QUESTION = 'Question'
    PRM_CHAT_HINT = ('A question about the repo, answered here -- nothing is changed and '
                     'nothing is written into the log. Ctrl+Enter sends.')
    PRM_CHAT_YOU = 'You'
    PRM_CHAT_CLAUDE = 'Claude'
    PRM_CHAT_THINKING = 'thinking…'
    PRM_CHAT_EMPTY = 'Type a question first.'
    PRM_CHAT_BUSY = 'A run is already going; Stop it first.'
    PRM_CHAT_SUBJECT = 'a question'
    PRM_TIP_CODE = ('Opens the run dialog: pick the pending requests, edit the general\n'
                    'prompt, choose the model and permissions, and start a headless run\n'
                    'that WRITES the work.')
    PRM_TIP_CHAT = ('Opens a chat window: a question about the repo, answered there.\n'
                    'Read-only -- it changes no file and writes nothing into the log.')
    PRM_TIP_ADD = 'Adds a request with no executed stamp, which is what marks it pending.'
    PRM_TIP_EDIT = ('Opens the selected request with all seven columns editable.\n'
                    'A double-click on a row does the same.')
    PRM_TIP_DELETE = ('Removes the selected request from the log. Every later request is\n'
                      'renumbered, so a prompt that named one now names a different one;\n'
                      'prompts.csv.bak is the undo.')
    PRM_TIP_CONTEXT = ('New session starts a fresh conversation. Continue resumes the\n'
                       'previous run, so it still knows what it just did.')
    PRM_TIP_PERMISSIONS = ('A headless run cannot ask, so whatever the mode would ask\n'
                           'about is denied instead.')
    PRM_TIP_ADD_DIRS = ('Folders outside the repo the run may read, separated by ";" --\n'
                        'the project data root, for instance.')

