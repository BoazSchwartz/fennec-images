"""CLIP zero-shot on the local CPU: onnxruntime + numpy + Pillow, no torch.

The quantized ViT-B/32 export of Xenova/clip-vit-base-patch32 is downloaded ONCE into
ClipModel.path_dir (download_model); after that nothing leaves the machine. The tokenizer is
CLIP's byte-level BPE, implemented here over the model's own vocab.json / merges.txt."""
from __future__ import annotations

import json
import re
import urllib.request
from functools import lru_cache

import numpy as np
from PIL import Image

from fennec_images.config import ClipModel as _CM

_SOT, _EOT = '<|startoftext|>', '<|endoftext|>'
_PAT = re.compile(r"<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[^\W\d_]+|\d|[^\s\w]+",
                  re.IGNORECASE)


def model_ready() -> bool:
    return all((_CM.path_dir / f).is_file() for f in _CM.FILES)


def download_model(log=print) -> bool:
    _CM.path_dir.mkdir(parents=True, exist_ok=True)
    for name, rel in _CM.FILES.items():
        dst = _CM.path_dir / name
        if dst.is_file() and dst.stat().st_size > 0:
            continue
        log(f'[MODEL] downloading {rel} ...\n')
        tmp = dst.with_suffix(dst.suffix + '.part')
        urllib.request.urlretrieve(_CM.URL_BASE + rel, tmp)
        tmp.replace(dst)
    log(f'[MODEL] ready in {_CM.path_dir}\n')
    return model_ready()


@lru_cache()
def _bytes_to_unicode() -> dict:
    bs = list(range(ord('!'), ord('~') + 1)) + list(range(ord('¡'), ord('¬') + 1)) + \
        list(range(ord('®'), ord('ÿ') + 1))
    cs, n = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


class _Tokenizer:
    def __init__(self):
        self.encoder = json.loads((_CM.path_dir / _CM.FILE_VOCAB).read_text(encoding='utf-8'))
        lines = (_CM.path_dir / _CM.FILE_MERGES).read_text(encoding='utf-8').split('\n')
        merges = [tuple(m.split()) for m in lines if m and not m.startswith('#version')]
        self.ranks = {m: i for i, m in enumerate(merges) if len(m) == 2}
        self.byte_enc = _bytes_to_unicode()
        self.cache = {}

    def _bpe(self, token: str) -> list:
        if token in self.cache:
            return self.cache[token]
        word = list(token[:-1]) + [token[-1] + '</w>']
        while len(word) > 1:
            pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
            best = min(pairs, key=lambda p: self.ranks.get(p, 1e12))
            if best not in self.ranks:
                break
            out, i = [], 0
            while i < len(word):
                if i < len(word) - 1 and (word[i], word[i + 1]) == best:
                    out.append(word[i] + word[i + 1])
                    i += 2
                else:
                    out.append(word[i])
                    i += 1
            word = out
        self.cache[token] = word
        return word

    def encode(self, text: str) -> np.ndarray:
        text = ' '.join(text.lower().split())
        ids = [self.encoder[_SOT]]
        for tok in _PAT.findall(text):
            tok = ''.join(self.byte_enc[b] for b in tok.encode('utf-8'))
            ids += [self.encoder[t] for t in self._bpe(tok) if t in self.encoder]
        ids = ids[:_CM.CONTEXT - 1] + [self.encoder[_EOT]]
        ids += [self.encoder[_EOT]] * (_CM.CONTEXT - len(ids))   # causal mask: padding after EOT is inert
        return np.array(ids, dtype=np.int64)


class ClipZeroShot:
    def __init__(self):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        prov = ['CPUExecutionProvider']
        self.vision = ort.InferenceSession(str(_CM.path_dir / _CM.FILE_VISION), opts, providers=prov)
        self.text = ort.InferenceSession(str(_CM.path_dir / _CM.FILE_TEXT), opts, providers=prov)
        self.tok = _Tokenizer()
        self._text_cache = {}

    def embed_texts(self, texts: list) -> np.ndarray:
        missing = [t for t in texts if t not in self._text_cache]
        if missing:
            ids = np.stack([self.tok.encode(t) for t in missing])
            emb = self.text.run(None, {'input_ids': ids})[0]
            emb /= np.linalg.norm(emb, axis=1, keepdims=True)
            self._text_cache.update(zip(missing, emb))
        return np.stack([self._text_cache[t] for t in texts])

    def embed_image(self, im: Image.Image) -> np.ndarray:
        s = _CM.SIZE
        w, h = im.size
        k = s / min(w, h)
        im = im.convert('RGB').resize((max(s, round(w * k)), max(s, round(h * k))), Image.BICUBIC)
        w, h = im.size
        left, top = (w - s) // 2, (h - s) // 2
        im = im.crop((left, top, left + s, top + s))
        x = (np.asarray(im, dtype=np.float32) / 255.0 - _CM.MEAN) / _CM.STD
        x = x.transpose(2, 0, 1)[None].astype(np.float32)
        emb = self.vision.run(None, {'pixel_values': x})[0][0]
        return emb / np.linalg.norm(emb)

    def group_probs(self, img_emb: np.ndarray, groups: dict) -> dict:
        """{group: probability}; each group scores the best of its prompts, then a softmax."""
        names = list(groups)
        best = []
        for g in names:
            sims = self.embed_texts(groups[g]) @ img_emb
            best.append(float(sims.max()))
        logits = np.array(best) * _CM.LOGIT_SCALE
        p = np.exp(logits - logits.max())
        p /= p.sum()
        return dict(zip(names, p.tolist()))
