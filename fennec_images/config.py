"""Constants of the Fennec Images app, plus a re-export of the shared GUI layer's classes, so
app code writes config.LayoutConfig / config.StyleConfig after one `from fennec_images import
config`, exactly as the Fennec bookkeeping apps do."""
import os
from pathlib import Path

from shared.config import (AppConfig, ClaudeModels, ClaudeRun, CommonUIStrings,  # noqa: F401
                           LayoutConfig, LayoutProfiles, PromptsLog, PromptsState,
                           RepoPaths, SashConfig as _SharedSash, StyleConfig)


class ImagesConfig:
    TITLE = 'Fennec Images'
    APP_ID = 'Fennec.Images'
    STATE_DIR = 'fennec_images'
    LOG_PREFIX = 'fennec_images'
    ICON_FILE = RepoPaths.FILE_ICON_IMAGES
    LAUNCH_LOG_FILE = RepoPaths.FILE_LAUNCH_LOG_IMAGES
    MAX_RECENT_PROJECTS = 10
    # Where the downloaded model and the classification cache live -- per machine, not in git
    path_dir_local = Path(os.environ.get('LOCALAPPDATA', Path.home())) / STATE_DIR
    FILE_CLASS_CACHE = 'classify_cache.json'


class ImagesState:
    """state.json keys the Classify and Albums tabs own."""
    KEY_CLASSIFY_DIR = 'classify_dir'
    KEY_CLASSIFY_COLS = 'classify_col_widths'
    KEY_CLASSIFY_PREVIEW = 'classify_preview_frac'
    KEY_USE_MODEL = 'classify_use_model'
    KEY_USE_OCR = 'classify_use_ocr'
    KEY_POLICY = 'classify_policy'
    KEY_ALBUM_SOURCE = 'albums_source'
    KEY_ALBUM_OUT = 'albums_out'
    KEY_ALBUM_COUNT = 'albums_count'
    KEY_ALBUM_PAGE = 'albums_page'
    KEY_ALBUM_COLS = 'albums_col_widths'


class SashConfig(_SharedSash):
    KEY_CLASSIFY_LOG = 'classify_log_frac'
    KEY_CLASSIFY_HORIZ = 'classify_horiz_frac'
    KEY_ALBUMS_LOG = 'albums_log_frac'
    KEY_ALBUMS_HORIZ = 'albums_horiz_frac'


class ClassifyClasses:
    """The labels the Classify tab writes into its Class column. Photos split by WHAT
    HAPPENED (trip / party / everyday), text-bearing images and documents by WHAT THEY SAY."""
    TRIP = 'Trip'
    PARTY = 'Party'
    OTHER = 'Other photo'
    ADVERT = 'Advertisement'
    SCHOOL = 'School message'
    NOTICE = 'Notification'
    DOCUMENT = 'Document'
    UNKNOWN = 'Unreadable'
    PHOTOS = [TRIP, PARTY, OTHER]
    TEXTS = [ADVERT, SCHOOL, NOTICE, DOCUMENT]
    ALL = PHOTOS + TEXTS + [UNKNOWN]


class ClassifyFiles:
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif',
                  '.gif'}
    PDF_EXTS = {'.pdf'}
    DOCX_EXTS = {'.docx'}
    HTML_EXTS = {'.html', '.htm', '.mhtml'}
    TEXT_EXTS = {'.txt', '.csv', '.md', '.vcf'}
    XLSX_EXTS = {'.xlsx'}
    # Below this many characters a pdf's text layer counts as absent and its pages are OCR'd
    PDF_MIN_TEXT = 40
    PDF_OCR_PAGES = 2
    PDF_OCR_DPI = 200


class ClassifySheet:
    """The classification written into the classified folder itself:
    <folder>\\fennec_images\\classification.xlsx, one row per file, rewritten after every run,
    Set Class and full-text read. On load it restores the rows the local cache lacks."""
    DIR_OUT = 'fennec_images'
    FILE_XLSX = 'classification.xlsx'
    SHEET = 'Classification'
    TEXT_MAX = 32000            # an Excel cell holds at most 32767 characters
    COL_NAME = 'Name'
    COL_SIZE = 'Size (bytes)'
    COL_MODIFIED = 'Modified'
    COL_KIND = 'Kind'
    COL_CLASS = 'Class'
    COL_CONF = 'Conf.'
    COL_MANUAL = 'Manual'
    COL_METHOD = 'Method'
    COL_WORDS = 'Words'
    COL_REASON = 'Reason'
    COL_SCORES = 'Scores'
    COL_TEXT = 'Text'
    COLUMNS = [COL_NAME, COL_SIZE, COL_MODIFIED, COL_KIND, COL_CLASS, COL_CONF, COL_MANUAL,
               COL_METHOD, COL_WORDS, COL_REASON, COL_SCORES, COL_TEXT]
    WIDTHS = {COL_NAME: 40, COL_SIZE: 12, COL_MODIFIED: 17, COL_KIND: 10, COL_CLASS: 16,
              COL_CONF: 7, COL_MANUAL: 8, COL_METHOD: 16, COL_WORDS: 7, COL_REASON: 50,
              COL_SCORES: 30, COL_TEXT: 80}


class ClassifyOcr:
    """Tesseract is called as an exe (no pytesseract needed). 'heb+eng' covers the WhatsApp
    traffic of the household."""
    EXE_CANDIDATES = [r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                      r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe']
    LANGS = 'heb+eng'
    MIN_CONF = 60           # a word below this confidence is noise, not text
    MAX_SIDE = 2200         # larger images are reduced first: same words, a fraction of the time
    # An image with at least this many confident words is a text image, whatever CLIP says
    # (real photos of the test folder gave 0-7)
    WORDS_TEXT_SURE = 12
    # ... and with at least this many, it is one when CLIP leans that way (p >= CLIP_TEXT_MAYBE)
    WORDS_TEXT_MAYBE = 5
    CLIP_TEXT_MAYBE = 0.5
    # Stylized Hebrew flyers OCR badly; above this CLIP text probability the words are not needed
    CLIP_TEXT_SURE = 0.9
    TIMEOUT_S = 60


class ClipModel:
    """Zero-shot image classifier, run locally with onnxruntime. Downloaded once (~150 MB)
    into ImagesConfig.path_dir_local/models; without it the classifier falls back to
    heuristics (OCR words, faces, sky and greenery)."""
    NAME = 'clip-vit-base-patch32'
    URL_BASE = 'https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/'
    FILES = {'vocab.json': 'vocab.json', 'merges.txt': 'merges.txt',
             'vision_model_quantized.onnx': 'onnx/vision_model_quantized.onnx',
             'text_model_quantized.onnx': 'onnx/text_model_quantized.onnx'}
    FILE_VISION = 'vision_model_quantized.onnx'
    FILE_TEXT = 'text_model_quantized.onnx'
    FILE_VOCAB = 'vocab.json'
    FILE_MERGES = 'merges.txt'
    SIZE = 224
    MEAN = (0.48145466, 0.4578275, 0.40821073)
    STD = (0.26862954, 0.26130258, 0.27577711)
    LOGIT_SCALE = 100.0
    CONTEXT = 77
    path_dir = ImagesConfig.path_dir_local / 'models' / NAME
    # Several phrasings per group; a group scores the best of its prompts
    PROMPTS = {
        'trip': ['a photo of a family trip in nature', 'a landscape photo taken on vacation',
                 'a photo of people hiking outdoors', 'a photo of a beach on a holiday',
                 'a photo of tourists sightseeing in a city', 'a photo of a picnic in a park',
                 'a photo of kids playing outdoors on a trip', 'a photo of mountains and a view'],
        'party': ['a photo of a birthday party', 'a photo of people celebrating at a party',
                  'a photo of a wedding celebration', 'a photo of kids at a party with balloons',
                  'a photo of a birthday cake with candles', 'a photo of people dancing at an event',
                  'a photo of a festive holiday dinner with family'],
        'other': ['a photo of a child at home', 'a selfie', 'a photo of food on a plate',
                  'a casual everyday photo of a person', 'a photo of a pet',
                  'a photo of a room in a house', 'a photo of an object'],
        'text': ['a flyer with text', 'a poster advertisement', 'a screenshot of a phone',
                 'a screenshot of a chat message', 'a scanned document page', 'a printed letter',
                 'an announcement with hebrew text', 'a page of text', 'a table with text and numbers',
                 'a graphic design with a lot of text'],
    }
    # Tie-breakers among the text classes when the words alone do not decide
    PROMPTS_TEXT = {
        ClassifyClasses.ADVERT: ['a colorful advertisement poster', 'a sale promotion flyer',
                                 'a commercial banner with a logo and a price'],
        ClassifyClasses.SCHOOL: ['a school announcement for parents', 'a kindergarten notice with drawings',
                                 'a school schedule'],
        ClassifyClasses.NOTICE: ['a screenshot of a phone notification', 'a screenshot of a chat message',
                                 'a short announcement message'],
        ClassifyClasses.DOCUMENT: ['a scanned official document', 'a receipt', 'a form to fill out',
                                   'an invoice'],
    }


class ClassifyRules:
    """Words that tell the text classes apart (matched as substrings of the lowercased text).
    Hebrew first -- that is what the household's messages are written in.
    Advertisement = commercial (prices, discounts, bookings); Notification = an announcement
    of an event, a date or a change (community events, seminars, reminders); School message =
    school / kindergarten / parents; Document = forms, receipts, contracts, long text."""
    # Regex signals, each class gaining at most PATTERN_CAP from them
    PATTERNS = {
        ClassifyClasses.NOTICE: [r'\b\d{1,2}:\d{2}\b', r'\b\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\b'],
        ClassifyClasses.ADVERT: [r'\d\s?₪', r'₪\s?\d', r'\d\s?%', r'\d\s?(?:אירו|euro|\$)'],
    }
    PATTERN_CAP = 2
    # Photos of one event (taken within EVENT_GAP_H of each other) share the event's class
    # when their own call is weak: a garden party's outdoor shots are still the party
    EVENT_GAP_H = 2.0
    EVENT_MIN = 3
    EVENT_DOMINANCE = 1.5      # the event's trip/party mass must beat the other by this factor
    EVENT_OWN_CONF = 0.8       # a photo this sure of itself keeps its own class
    EVENT_OTHER_CONF = 0.6     # an 'Other photo' below this joins the event
    KEYWORDS = {
        ClassifyClasses.SCHOOL: [
            'בית ספר', 'בית הספר', 'ביה"ס', 'ביה״ס', 'בי"ס', 'גן ', 'הגן', 'גננת', 'סייעת',
            'הורים', 'ההורים', 'תלמיד', 'כיתה', 'כיתת', 'מחנכ', 'מורה', 'המורה', 'חוזר',
            'שכבת', 'שכבה', 'אסיפת', 'ועד הורים', 'טיול שנתי', 'תשפ"ז', 'תשפ״ז', 'תשפז',
            'שנת הלימודים', 'מנהלת', 'צהרון', 'יום הורים', 'הסעות', 'משרד החינוך', 'פדגוג',
            'school', 'parents', 'kindergarten', 'teacher', 'class ',
        ],
        ClassifyClasses.ADVERT: [
            'מבצע', 'הנחה', '₪', 'ש"ח', 'מחיר', 'להזמנות', 'הזמינו', 'חייגו', 'קופון', 'מכירה',
            'חינם', 'במתנה', 'הרשמה', 'להרשמה', 'סדנ', 'חוג', 'מבצעי', 'קנו', 'רכשו', 'בלעדי',
            'מוגבל', 'www.', '.co.il', 'http', 'מסעדה', 'תפריט', 'פתיחת', 'השקה', 'כרטיסים',
            'השכרה', 'להשכרה', 'מחירים', 'מוזל', 'לילה', 'לילות', 'משלוח', 'אירו',
            'sale', 'discount', 'order now', 'free', 'offer', 'price', 'nights', 'booking',
            'taxes', 'fees', 'refundable',
        ],
        ClassifyClasses.NOTICE: [
            'הודעה', 'תזכורת', 'שימו לב', 'עדכון', 'ביטול', 'בוטל', 'נדחה', 'מחר', 'היום',
            'בשעה', 'עירי', 'תושבים', 'הפסקת', 'חסימ', 'אזעקה', 'פיקוד העורף', 'מועד',
            'נא ', 'אנא', 'לידיעת', 'יתקיים', 'תתקיים', 'ועד הבית', 'קבוצת', 'whatsapp',
            'מפגש', 'אירוע', 'הרצאה', 'הספרייה', 'ספריה', 'יום ראשון', 'יום שני', 'יום שלישי',
            'יום רביעי', 'רביעי', 'יום חמישי', 'יום שישי', 'מוצאי שבת', 'בחירות', 'הצבעה',
            'כתובת', 'מקום', 'הכניסה', 'save the date', 'פורום', 'קהילה', 'קהילתי',
            'reminder', 'notice', 'update', 'cancel', 'seminar', 'lecture', 'meeting',
            'room', 'building', 'university',
        ],
        ClassifyClasses.DOCUMENT: [
            'חשבונית', 'קבלה', 'אישור', 'טופס', 'חוזה', 'הסכם', 'מסמך', 'תעודה', 'דו"ח', 'דוח',
            'חתימה', 'חתימת', 'ת.ז', 'תעודת זהות', 'מספר זהות', 'סעיף', 'פוליסה', 'ביטוח',
            'בנק', 'חשבון', 'מס ', 'מע"מ', 'עמוד', 'נספח', 'הצהרה', 'בקשה',
            'invoice', 'receipt', 'form', 'agreement', 'signature', 'page ',
        ],
    }
    # Long dense text with no decisive word reads as a document, short text as a notice
    DOC_LONG_WORDS = 250


class UIStrings(CommonUIStrings):
    TAB_CLASSIFY = '  Classify  '
    TAB_ALBUMS = '  Albums  '

    LBL_DIR = 'Folder'
    BTN_BROWSE = 'Browse…'
    BTN_RELOAD = 'Reload'
    BTN_ALL = 'All'
    BTN_NONE = 'None'
    SEC_FILES = 'Files'
    SEC_ACTIONS = 'Actions'
    SEC_PREVIEW = 'Preview'
    COL_SEL = ''
    COL_SIZE = 'Size'
    COL_CLASS = 'Class'
    COL_SCORE = 'Conf.'
    COL_NAME = 'Name'
    COL_TEXT = 'Text'
    TITLE_TEXT = 'Text read'
    LBL_TEXT_READING = 'Reading the full text…'
    LBL_TEXT_NONE = '(no text read)'
    BTN_COPY_TEXT = 'Copy'
    BTN_CLOSE = 'Close'
    BTN_CLASSIFY = 'Classify Checked'
    BTN_STOP = 'Stop'
    BTN_SET_CLASS = 'Set Class'
    BTN_COPY = 'Copy to Class Folders'
    BTN_OPEN = 'Open File'
    BTN_DOWNLOAD_MODEL = 'Download Model'
    LBL_POLICY = 'If exists'
    LBL_FILTER = 'Show'
    LBL_ALL_CLASSES = 'All classes'
    LBL_MODEL_ON = 'Model: CLIP (local) ready'
    LBL_MODEL_OFF = 'Model: not downloaded, heuristics only'
    LBL_OCR_ON = 'OCR: Tesseract (heb+eng)'
    LBL_OCR_OFF = 'OCR: Tesseract not found'
    CHK_USE_MODEL = 'Use CLIP model'
    CHK_USE_OCR = 'Use OCR'
    CHK_RECLASSIFY = 'Ignore cache'

    SEC_ALBUM_BUILD = 'Build'
    SEC_ALBUM_EVENTS = 'Events of the album'
    LBL_SOURCE = 'Photos folder'
    LBL_ALBUM_DIR = 'Album folder'
    LBL_COUNT = 'Photos'
    LBL_TITLE = 'Title'
    LBL_PAGE = 'Page size'
    LBL_GAP = 'Gap hours'
    LBL_JUMP = 'Jump km'
    LBL_DIVERSITY = 'Diversity'
    CHK_ENHANCE = 'Auto enhance'
    CHK_GEOCODE = 'Name places (network)'
    BTN_BUILD = 'Build Album'
    BTN_LOAD = 'Load Album'
    BTN_EDITOR = 'Open Editor'
    BTN_EXPORT = 'Export PDF'
    BTN_RELAYOUT = 'Re-layout'
    BTN_OPEN_FOLDER = 'Open Folder'
    COL_EVENT = 'Event'
    COL_COUNT = 'Photos'
    COL_DATE = 'Start'


class OverridePolicy:
    """CLAUDE_GENERAL.md OVERRIDE POLICY -- what a copy does when the target exists."""
    SKIP = 'Skip'
    OVERRIDE = 'Override'
    BAK = 'Bak'
    ALL = [SKIP, OVERRIDE, BAK]
    DEFAULT = SKIP
