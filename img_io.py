# -*- coding: utf-8 -*-
"""图片读写：兼容中文/非 ASCII 路径。

OpenCV 的 cv2.imread / cv2.imwrite 在 Windows 上无法处理非 ASCII 路径——
imread 返回 None、imwrite 返回 False（实测确认），且不会抛异常，
调用方很容易把它当成"处理失败"而不知道真正原因。

这里统一走 imdecode + np.fromfile / imencode + 二进制写入，
两者对中文路径都正常工作。所有需要读写图片的工具都应使用本模块。
"""
import os

import cv2
import numpy as np


def imread(path, flags=cv2.IMREAD_COLOR):
    """读取图片，支持中文路径。失败返回 None（与 cv2.imread 行为一致）"""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
        if buf.size == 0:
            return None
        return cv2.imdecode(buf, flags)
    except Exception:
        return None


def imwrite(path, img, ext=None):
    """保存图片，支持中文路径。成功返回 True，失败返回 False。

    ext 为 None 时按目标路径的扩展名推断（如 .jpg/.png）。
    """
    path = str(path)
    if ext is None:
        ext = os.path.splitext(path)[1]
    if not ext:
        raise ValueError("无法从路径推断图片格式，请显式传入 ext: %s" % path)
    try:
        ok, buf = cv2.imencode(ext, img)
        if not ok:
            return False
        # 目录不存在时补建，避免因缺目录而静默失败
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as f:
            f.write(buf.tobytes())
        return True
    except Exception:
        return False
