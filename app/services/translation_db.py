"""
翻译词库管理服务 - 读写 prompt_translations.json
"""
import json
import os
from pathlib import Path
from typing import Dict, Optional


# 词库文件路径（放在 uploads 目录下，避免 sandbox 权限问题）
TRANSLATION_DB_FILE = Path(__file__).resolve().parent.parent.parent / "uploads" / "prompt_translations.json"


def _ensure_db_file() -> None:
    """确保词库文件存在"""
    if not TRANSLATION_DB_FILE.exists():
        TRANSLATION_DB_FILE.write_text("{}", encoding="utf-8")


def load_translation_db() -> Dict[str, str]:
    """加载全部翻译词条"""
    _ensure_db_file()
    try:
        data = json.loads(TRANSLATION_DB_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_translation_db(translations: Dict[str, str]) -> None:
    """全量保存翻译词条"""
    TRANSLATION_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_DB_FILE.write_text(
        json.dumps(translations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_translation(prompt: str) -> Optional[str]:
    """获取单个 prompt 的中文翻译"""
    db = load_translation_db()
    return db.get(prompt)


def batch_get_translations(prompts: list[str]) -> Dict[str, str]:
    """批量获取翻译（已有的返回，没有的返回空字符串）"""
    db = load_translation_db()
    return {p: db.get(p, "") for p in prompts}


def add_translation(prompt: str, chinese: str) -> None:
    """添加或更新一条翻译"""
    db = load_translation_db()
    db[prompt] = chinese
    save_translation_db(db)


def batch_add_translations(translations: Dict[str, str]) -> None:
    """批量添加/更新翻译"""
    if not translations:
        return
    db = load_translation_db()
    db.update(translations)
    save_translation_db(db)


def delete_translation(prompt: str) -> bool:
    """删除一条翻译"""
    db = load_translation_db()
    if prompt in db:
        del db[prompt]
        save_translation_db(db)
        return True
    return False


def get_db_stats() -> dict:
    """获取词库统计信息"""
    db = load_translation_db()
    return {"total": len(db), "translations": db}
