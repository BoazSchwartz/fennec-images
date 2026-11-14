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
    KEY_CLASSIFY_SUBDIRS = 'classify_subdirs'
    KEY_FIND_PEOPLE = 'classify_find_people'
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
    HAPPENED (trip / party) or WHERE (home, restaurant, car, street, nature, work, else
    everyday), text-bearing images and documents by what they say."""
    TRIP = 'Trip'
    PARTY = 'Party'
    HOME = 'Home'
    RESTAURANT = 'Restaurant'
    CAR = 'Car'
    STREET = 'Street'
    NATURE = 'Nature'
    WORK = 'Work'
    OTHER = 'Other photo'
    ADVERT = 'Advertisement'
    SCHOOL = 'School message'
    NOTICE = 'Notification'
    DOCUMENT = 'Document'
    UNKNOWN = 'Unreadable'
    EVENTS = [TRIP, PARTY]              # the classes an event's photos share (event smoothing)
    SCENES = [HOME, RESTAURANT, CAR, STREET, NATURE, WORK]
    PHOTOS = EVENTS + SCENES + [OTHER]
    TEXTS = [ADVERT, SCHOOL, NOTICE, DOCUMENT]
    ALL = PHOTOS + TEXTS + [UNKNOWN]
    # The photo classes by their score key (Result.scores, ClipModel.PROMPTS, the sheet)
    GROUPS = {'trip': TRIP, 'party': PARTY, 'home': HOME, 'restaurant': RESTAURANT, 'car': CAR,
              'street': STREET, 'nature': NATURE, 'work': WORK, 'other': OTHER}


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
    # Subfolders a recursive listing skips: an album folder (it holds this marker file) and
    # the app's own output (ClassifySheet.DIR_OUT, the class folders of Copy to Class Folders)
    ALBUM_MARK = 'album.json'


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
    COL_FACES = 'Faces'
    COL_PEOPLE = 'People'
    COL_REASON = 'Reason'
    COL_SCORES = 'Scores'
    COL_TEXT = 'Text'
    COLUMNS = [COL_NAME, COL_SIZE, COL_MODIFIED, COL_KIND, COL_CLASS, COL_CONF, COL_MANUAL,
               COL_METHOD, COL_WORDS, COL_FACES, COL_PEOPLE, COL_REASON, COL_SCORES, COL_TEXT]
    WIDTHS = {COL_NAME: 40, COL_SIZE: 12, COL_MODIFIED: 17, COL_KIND: 10, COL_CLASS: 16,
              COL_CONF: 7, COL_MANUAL: 8, COL_METHOD: 16, COL_WORDS: 7, COL_FACES: 7,
              COL_PEOPLE: 24, COL_REASON: 50, COL_SCORES: 30, COL_TEXT: 80}
    PEOPLE_SEP = ', '
    METHOD_FACES = '+faces'     # in Method when the face pass ran (the sheet drops it: no embeddings)


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
    # Several phrasings per group; a group scores the best of its prompts. The photo groups
    # are ClassifyClasses.GROUPS (trip / party by the event, the rest by the place), 'text'
    # the text-bearing images.
    PROMPTS = {
        'trip': ['a photo of a family trip in nature', 'a landscape photo taken on vacation',
                 'a photo of people hiking outdoors', 'a photo of a beach on a holiday',
                 'a photo of tourists sightseeing in a city', 'a photo of a picnic in a park',
                 'a photo of kids playing outdoors on a trip', 'a photo of mountains and a view'],
        'party': ['a photo of a birthday party', 'a photo of people celebrating at a party',
                  'a photo of a wedding celebration', 'a photo of kids at a party with balloons',
                  'a photo of a birthday cake with candles', 'a photo of people dancing at an event',
                  'a photo of a festive holiday dinner with family'],
        'home': ['a photo taken in a living room at home', 'a photo of a kitchen at home',
                 'a photo of a child playing at home', 'a photo of a bedroom',
                 'a photo of a family on a sofa at home', 'a photo of a backyard of a house'],
        'restaurant': ['a photo of people eating at a restaurant', 'a photo of a table at a cafe',
                       'a photo of a restaurant interior', 'a photo of a meal served at a restaurant'],
        'car': ['a photo taken inside a car', 'a photo of a child in a car seat',
                'a photo of a car on the road', 'a photo of a parking lot with cars'],
        'street': ['a photo of a city street', 'a photo of a sidewalk with shops',
                   'a photo of buildings in a city', 'a photo of people walking in the street',
                   'a photo of a town square'],
        'nature': ['a photo of trees and plants', 'a photo of flowers', 'a landscape photo of a field',
                   'a photo of a forest', 'a photo of the sea', 'a photo of a river or a lake',
                   'a photo of a wild animal'],
        'work': ['a photo of an office', 'a photo of people in a meeting',
                 'a photo of a desk with a computer', 'a photo of a conference presentation',
                 'a photo of a workshop with tools', 'a photo of a construction site'],
        'other': ['a selfie', 'a photo of food on a plate', 'a casual everyday photo of a person',
                  'a photo of a pet', 'a photo of an object', 'a portrait of a child'],
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


class FaceModel:
    """Finding people: OpenCV's YuNet face detector and SFace face recognizer, two small onnx
    files of the opencv_zoo (0.2 + 37 MB) run by cv2 on the CPU, about 60 ms a photo. Faces
    the user names in the Tag People window are kept, as embeddings, in
    ImagesConfig.path_dir_local/people.json; every face found is matched against them."""
    NAME = 'opencv-face'
    URL_BASE = 'https://github.com/opencv/opencv_zoo/raw/main/models/'
    FILE_DET = 'face_detection_yunet_2023mar.onnx'
    FILE_REC = 'face_recognition_sface_2021dec.onnx'
    FILES = {FILE_DET: 'face_detection_yunet/' + FILE_DET,
             FILE_REC: 'face_recognition_sface/' + FILE_REC}
    path_dir = ImagesConfig.path_dir_local / 'models' / NAME
    FILE_PEOPLE = 'people.json'
    MAX_SIDE = 1024         # the photo is reduced to this before detection
    SCORE_MIN = 0.8         # YuNet's confidence that a box is a face
    NMS = 0.3
    TOP_K = 50
    MIN_FACE = 20           # pixels, after the reduction; smaller faces embed badly
    # Cosine similarity to a named face that makes it the same person (OpenCV's own figure for
    # SFace is 0.363; different faces of the 2010 test folder stay under 0.35, same ones 0.65+)
    MATCH_SIM = 0.40
    EMB_DECIMALS = 4
    CROP_PX = 110           # the face thumbnails of the Tag People window
    CROP_MARGIN = 0.35      # of the box, added around it


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
    COL_PEOPLE = 'People'
    FMT_FACES = '{n} face(s)'           # the People cell: faces found, none of them named
    FMT_FACES_MORE = ' +{n}'            # ... after the names, the faces not named
    LBL_UNKNOWN_FACES = 'Unknown faces'
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
    BTN_DOWNLOAD_MODEL = 'Download Models'
    BTN_TAG_PEOPLE = 'Tag People'
    TITLE_TAG = 'Tag People'
    LBL_TAG_HINT = 'Name each face (leave a stranger empty); the names are matched in every photo'
    LBL_TAG_FINDING = 'Finding the faces…'
    LBL_TAG_NONE = 'No face found in this image'
    BTN_SAVE = 'Save'
    STATUS_LOADING = 'loading the models…'
    STATUS_PROGRESS = 'completed {done}/{total} files ({pct}%){extra}'
    STATUS_FROM_CACHE = ', {n} from the cache'
    STATUS_DONE = 'done: {done}/{total} files in {secs:.1f} s{extra}'
    STATUS_STOPPED = 'stopped: {done}/{total} files in {secs:.1f} s{extra}'
    STATUS_SMOOTHED = ', {n} moved to their event'
    LBL_POLICY = 'If exists'
    LBL_FILTER = 'Show'
    LBL_ALL_CLASSES = 'All classes'
    LBL_MODEL_ON = 'Model: CLIP (local) ready'
    LBL_MODEL_OFF = 'Model: not downloaded, heuristics only'
    LBL_OCR_ON = 'OCR: Tesseract (heb+eng)'
    LBL_OCR_OFF = 'OCR: Tesseract not found'
    LBL_FACES_ON = 'Faces: YuNet + SFace (local) ready'
    LBL_FACES_OFF = 'Faces: not downloaded'
    CHK_USE_MODEL = 'Use CLIP model'
    CHK_USE_OCR = 'Use OCR'
    CHK_FIND_PEOPLE = 'Find people'
    CHK_RECLASSIFY = 'Ignore cache'
    CHK_SUBDIRS = 'Subfolders'

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
