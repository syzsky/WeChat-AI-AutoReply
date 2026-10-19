"""OCR 封装：本地 RapidOCR，支持整图与归一化区域识别。

模型查找顺序：./models → ./_internal/models → 包内置模型。
"""
import os
import sys

_ENGINE = None


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_engine():
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE

    from rapidocr_onnxruntime import RapidOCR

    base = _base_dir()
    for models_dir in (os.path.join(base, "models"),
                       os.path.join(base, "_internal", "models")):
        det = os.path.join(models_dir, "ch_PP-OCRv4_det_infer.onnx")
        rec = os.path.join(models_dir, "ch_PP-OCRv4_rec_infer.onnx")
        cls = os.path.join(models_dir, "ch_ppocr_mobile_v2.0_cls_infer.onnx")
        if os.path.exists(det) and os.path.exists(rec):
            try:
                _ENGINE = RapidOCR(det_model_path=det, cls_model_path=cls, rec_model_path=rec)
                return _ENGINE
            except Exception:
                pass
    _ENGINE = RapidOCR()
    return _ENGINE


def ocr_image(img):
    """整图识别，返回 [(text, (x1,y1,x2,y2), score), ...]。"""
    import numpy as np

    engine = get_engine()
    result, _ = engine(np.asarray(img.convert("RGB")))
    out = []
    for item in result or []:
        box, text, score = item[0], item[1], item[2]
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        out.append((str(text).strip(), (min(xs), min(ys), max(xs), max(ys)), float(score)))
    return out


def ocr_region(img, rect, min_score=0.5):
    """识别归一化区域，坐标换算回整图像素。"""
    from .vision import crop_norm

    crop = crop_norm(img, rect)
    w, h = img.size
    ox, oy = int(rect[0] * w), int(rect[1] * h)
    res = []
    for text, box, score in ocr_image(crop):
        if score < min_score or not text:
            continue
        res.append((text, (box[0] + ox, box[1] + oy, box[2] + ox, box[3] + oy), score))
    return res


def find_text(img, rect, keywords, min_score=0.5):
    """在区域里找包含关键词的文本，返回 [(text, center_x, center_y, score)]。"""
    hits = []
    for text, box, score in ocr_region(img, rect, min_score):
        if any(k and k in text for k in keywords):
            cx = int((box[0] + box[2]) / 2)
            cy = int((box[1] + box[3]) / 2)
            hits.append((text, cx, cy, score))
    return hits


def read_number(img, rect, min_score=0.3):
    """读区域里的第一个数字，失败返回 None。"""
    import re

    for text, _box, score in ocr_region(img, rect, min_score):
        m = re.search(r"\d+", text.replace(",", "").replace("，", ""))
        if m:
            return int(m.group())
    return None
