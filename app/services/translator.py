"""
自动翻译服务 — 使用 MyMemory 免费翻译 API

无需 API Key，匿名 5000 字符/天，注册后 50000/天。
因 Google Translate 在国内无法访问，使用 MyMemory 作为替代方案。
"""

import logging
import re
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

MYMEMORY_API = "https://api.mymemory.translated.net/get"

# 匿名模式频率限制（MyMemory 建议间隔）
_MIN_REQ_INTERVAL = 0.5  # 秒
_last_request_time: float = 0.0

# MyMemory 翻译记忆库中有脏数据的词（永远返回原文），提供硬编码兜底
_FALLBACK_DICT: Dict[str, str] = {
    "cake": "蛋糕",
    "cat": "猫",
    "cats": "猫",
    "dog": "狗",
    "dogs": "狗",
    "branch": "树枝",
    "branches": "树枝",
    "bird": "鸟",
    "bridge": "桥",
    "castle": "城堡",
    "sunset": "日落",
    "house": "房屋",
    "car": "汽车",
    "tree": "树",
    "mountain": "山",
    "river": "河流",
    "beach": "海滩",
    "happy": "愉快的",
    "sadness": "悲伤",
}


def _rate_limited_get(
    params: dict, timeout: int = 10, max_retries: int = 3
) -> Optional[dict]:
    """带频率限制和重试的 MyMemory API 请求"""
    global _last_request_time

    last_error = None
    for attempt in range(max_retries):
        elapsed = time.time() - _last_request_time
        if elapsed < _MIN_REQ_INTERVAL:
            time.sleep(_MIN_REQ_INTERVAL - elapsed)

        try:
            resp = requests.get(MYMEMORY_API, params=params, timeout=timeout)
            _last_request_time = time.time()
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            last_error = e
            if attempt < max_retries - 1:
                backoff = (attempt + 1) * 1.0  # 1s, 2s, 3s 指数退避
                logger.debug(
                    f"MyMemory 请求失败（第 {attempt + 1}/{max_retries} 次），"
                    f"{backoff}s 后重试: {e}"
                )
                time.sleep(backoff)

    logger.warning(f"MyMemory 请求全部 {max_retries} 次失败: {last_error}")
    return None


def _clean_translation(text: str) -> str:
    """
    清理翻译结果中的噪声：
    - 去掉圆括号及括号内的内容，如 "蛋糕（甜点）" → "蛋糕"
    - 【】方头括号是中文正常标点（如【分部】），保留不删
    - 去掉多余空格
    """
    # 只去掉英文圆括号和中文全角括号内容（不碰【】）
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    # 去掉多余空格
    text = re.sub(r"\s+", " ", text).strip()
    return text


def translate_text(text: str) -> Optional[str]:
    """
    翻译单个文本（EN → zh-CN）。
    失败时返回 None。
    """
    if not text or not text.strip():
        return None

    text = text.strip()
    params = {
        "q": text,
        "langpair": "en|zh-CN",
        "mt": "1",  # 启用机器翻译回退
    }

    data = _rate_limited_get(params)
    if not data:
        return None

    translated = (data.get("responseData") or {}).get("translatedText")
    if not translated:
        return None

    # 去除首尾空格后与原文比较，排除 MyMemory 返回原文的脏数据
    translated_stripped = translated.strip()
    if not translated_stripped or translated_stripped.lower() == text.lower():
        # 翻译记忆库有错误记录时会返回原文（如 cake → cake / cat → "cat "）
        # 尝试内置兜底词典
        fallback = _FALLBACK_DICT.get(text.lower())
        if fallback:
            logger.debug(f"MyMemory 返回原文，使用内置词典: {text!r} -> {fallback!r}")
            return fallback
        logger.debug(f"MyMemory 返回原文，无内置词典兜底: {text!r}")
        return None

    cleaned = _clean_translation(translated_stripped)
    if not cleaned or cleaned.lower() == text.lower():
        return None

    return cleaned


def batch_translate_texts(texts: List[str]) -> Dict[str, str]:
    """
    批量翻译。返回 {原文: 译文} 字典（仅成功项）。
    逐个翻译以避免单次失败影响整批，同时遵守频率限制。
    """
    results: Dict[str, str] = {}
    for text in texts:
        translation = translate_text(text)
        if translation:
            results[text] = translation
    return results


class AutoTranslator:
    """
    自动翻译器，封装 MyMemory 免费 API。
    支持结果缓存以避免重复请求。
    """

    def __init__(self):
        self._cache: Dict[str, str] = {}

    def translate(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            return None
        text = text.strip()
        if text in self._cache:
            return self._cache[text]
        result = translate_text(text)
        if result:
            self._cache[text] = result
        return result

    def batch_translate(self, texts: List[str]) -> Dict[str, str]:
        results: Dict[str, str] = {}
        for text in texts:
            translation = self.translate(text)
            if translation:
                results[text] = translation
        return results


# 模块级单例
_translator_instance: Optional[AutoTranslator] = None


def get_translator() -> AutoTranslator:
    """获取翻译器单例"""
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = AutoTranslator()
    return _translator_instance
