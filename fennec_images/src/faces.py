"""Finding people in photos, on this machine: OpenCV's YuNet detects the faces and SFace turns
each into a 128-number embedding (two small onnx files, FaceModel, downloaded once). The user
names faces in the Tag People window; those are kept in people.json (name: its embeddings) and
every face found is matched against them by cosine similarity. No tkinter."""
from __future__ import annotations

import json
import threading
import urllib.request

import numpy as np

from fennec_images.config import FaceModel as _FM


def model_ready() -> bool:
    return all((_FM.path_dir / f).is_file() for f in _FM.FILES)


def download_model(log=print) -> bool:
    _FM.path_dir.mkdir(parents=True, exist_ok=True)
    for name, rel in _FM.FILES.items():
        dst = _FM.path_dir / name
        if dst.is_file() and dst.stat().st_size > 0:
            continue
        log(f'[MODEL] downloading {rel} ...\n')
        tmp = dst.with_suffix(dst.suffix + '.part')
        urllib.request.urlretrieve(_FM.URL_BASE + rel, tmp)
        tmp.replace(dst)
    log(f'[MODEL] faces ready in {_FM.path_dir}\n')
    return model_ready()


# ── The people file ───────────────────────────────────────────────────────────

def people_file():
    return _FM.path_dir.parent.parent / _FM.FILE_PEOPLE


def load_people() -> dict:
    """{name: [{'emb': [...], 'src': path, 'box': [x, y, w, h]}]}."""
    try:
        return json.loads(people_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_people(people: dict) -> None:
    f = people_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix('.tmp')
    tmp.write_text(json.dumps(people, ensure_ascii=False), encoding='utf-8')
    tmp.replace(f)


def forget_face(people: dict, src: str, box: list) -> None:
    """Drop the stored face of this photo and box, whatever its name."""
    for name in list(people):
        people[name] = [f for f in people[name] if not (f['src'] == src and f['box'] == box)]
        if not people[name]:
            del people[name]


def add_face(people: dict, name: str, face: dict, src: str) -> None:
    forget_face(people, src, face['box'])
    people.setdefault(name, []).append({'emb': face['emb'], 'src': src, 'box': face['box']})


def match(people: dict, emb: list) -> tuple[str, float]:
    """The best named face: (name, similarity), ('', best) when no one is close enough."""
    best, who = -1.0, ''
    v = np.asarray(emb, dtype=np.float32)
    for name, faces in people.items():
        if faces:
            s = float(np.max(np.stack([f['emb'] for f in faces]).astype(np.float32) @ v))
            if s > best:
                best, who = s, name
    return (who if best >= _FM.MATCH_SIM else ''), best


def name_faces(faces: list, people: dict) -> list:
    """Match every face against the named ones (each gets its 'name', '' for a stranger);
    returns the names found, sorted, each once."""
    for f in faces:
        f['name'], f['sim'] = match(people, f['emb']) if f.get('emb') else ('', 0.0)
        f['sim'] = round(f['sim'], 3)
    return sorted({f['name'] for f in faces if f['name']})


# ── The models ────────────────────────────────────────────────────────────────

class FaceFinder:
    """One YuNet + SFace pair, used under a lock (cv2's sessions are not thread-safe)."""

    def __init__(self):
        import cv2
        self._cv2 = cv2
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)   # a harmless dnn WARN
        self.det = cv2.FaceDetectorYN.create(str(_FM.path_dir / _FM.FILE_DET), '', (320, 320),
                                             _FM.SCORE_MIN, _FM.NMS, _FM.TOP_K)
        self.rec = cv2.FaceRecognizerSF.create(str(_FM.path_dir / _FM.FILE_REC), '')
        self._lock = threading.Lock()

    def find(self, im) -> list:
        """[{'box': [x, y, w, h] in the photo's pixels, 'score', 'emb'}] of the faces."""
        cv2 = self._cv2
        im = im.convert('RGB')
        w, h = im.size
        k = min(1.0, _FM.MAX_SIDE / max(w, h))
        if k < 1.0:
            im = im.resize((max(1, round(w * k)), max(1, round(h * k))))
        bgr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
        out = []
        with self._lock:
            self.det.setInputSize((bgr.shape[1], bgr.shape[0]))
            _n, dets = self.det.detect(bgr)
            for d in (dets if dets is not None else []):
                if min(d[2], d[3]) < _FM.MIN_FACE:
                    continue
                emb = self.rec.feature(self.rec.alignCrop(bgr, d)).flatten().astype(np.float32)
                emb /= np.linalg.norm(emb) or 1.0
                out.append({'box': [int(round(float(v) / k)) for v in d[:4]],
                            'score': round(float(d[14]), 3),
                            'emb': [round(float(v), _FM.EMB_DECIMALS) for v in emb]})
        return out
