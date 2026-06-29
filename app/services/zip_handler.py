"""
Zip 上传处理服务 - 解压、目录结构识别、方法名提取、翻译解析

支持的 Zip 结构：
  study.zip
  ├── amusement/          ← 一级：情感类别（自动检测）
  │   ├── prompt_A/      ← 二级：prompt 名称
  │   │   ├── sd.png     ← 图片文件
  │   │   └── sdxl.png
  │   └── prompt_B/
  │       └── ...
  ├── anger/
  │   └── ...
  └── ...
"""
import os
import re
import time
import uuid
import zipfile
import shutil
from pathlib import Path
from typing import Optional

from PIL import Image

from app.config import get_settings
from app.services import translation_db

# 支持的图片格式
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# 安全限制
MAX_EXTRACTED_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
MAX_FILE_COUNT = 10000
MAX_ZIP_SIZE = 500 * 1024 * 1024  # 500MB

# 情感中文名默认映射
EMOTION_CN_MAP = {
    "amusement": "愉悦",
    "anger": "生气",
    "awe": "敬畏",
    "contentment": "满足",
    "disgust": "厌恶",
    "excitement": "激动",
    "fear": "恐惧",
    "sadness": "悲伤",
}


class ZipHandler:
    """Zip 上传处理器"""

    def __init__(self):
        settings = get_settings()
        self.upload_dir = settings.upload_path
        self.temp_dir = self.upload_dir / "_temp"

    def process_upload(self, zip_file_path: str, emotion: str = None) -> dict:
        """
        处理上传的 zip 文件，返回分析结果。

        两阶段模式：
        1. emotion=None → 仅解压并检测情感类别，返回 {upload_id, emotions, ...}
        2. emotion=指定值 → 分析该情感下的 prompt 结构，返回完整分析

        Args:
            zip_file_path: 已保存的 zip 文件路径
            emotion: 情感类别（可选，不传则仅检测）

        Returns:
            分析结果 dict
        """
        upload_id = str(uuid.uuid4())
        extract_dir = self.temp_dir / upload_id
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 验证并解压
            self._validate_and_extract(zip_file_path, str(extract_dir))

            # 从一级子目录检测情感类别
            detected_emotions = self._detect_emotions(str(extract_dir))

            if not detected_emotions:
                raise ValueError(
                    "Zip 中未检测到任何情感类别目录。\n\n"
                    "请确保压缩包结构为：\n"
                    "  study.zip\n"
                    "  ├── amusement/        ← 情感类别\n"
                    "  │   ├── prompt_A/     ← prompt 文件夹\n"
                    "  │   │   ├── sd.png\n"
                    "  │   │   └── sdxl.png\n"
                    "  │   └── prompt_B/\n"
                    "  └── anger/\n"
                    "      └── ..."
                )

            # 阶段 1：仅检测情感类别
            if emotion is None:
                return {
                    "upload_id": upload_id,
                    "emotions": detected_emotions,
                    "emotion_cn_map": {
                        e: EMOTION_CN_MAP.get(e, e) for e in detected_emotions
                    },
                }

            # 阶段 2：验证指定情感是否存在，分析该子树
            if emotion not in detected_emotions:
                raise ValueError(
                    f"Zip 中未找到情感类别 '{emotion}'。"
                    f"检测到的类别: {', '.join(detected_emotions)}"
                )

            # 在该情感子目录下分析 prompt 结构
            emotion_dir = str(extract_dir / emotion)
            structure = self._analyze_structure(emotion_dir)

            if not structure:
                raise ValueError(
                    f"情感类别 '{emotion}' 下未找到有效的 prompt 目录。\n\n"
                    "请确保每个情感目录下包含 prompt 子文件夹，"
                    "每个 prompt 文件夹内包含方法对应的图片。"
                )

            # 提取方法名
            method_analysis = self._extract_methods(structure)
            if not method_analysis["candidates"]:
                per_prompt = method_analysis.get("per_prompt_candidates", {})
                debug_lines = []
                for pname, cands in sorted(per_prompt.items()):
                    cands_str = ", ".join(sorted(cands)) if cands else "(无)"
                    debug_lines.append(f"  {pname}: [{cands_str}]")
                debug_info = "\n".join(debug_lines) if debug_lines else "无 prompt 信息"
                raise ValueError(
                    f"未能识别出任何跨 prompt 一致的方法名。\n\n"
                    f"Prompt 总数: {len(structure)}，要求方法出现在 ≥{max(int(len(structure)*0.4),1)} 个 prompt 中。\n"
                    f"各 prompt 候选方法名:\n{debug_info}\n\n"
                    f"提示：请确保各 prompt 目录下的图片以相同的方法名命名。"
                )

            # 构建返回数据
            result = {
                "upload_id": upload_id,
                "emotion": emotion,
                "emotion_cn": EMOTION_CN_MAP.get(emotion, emotion),
                "detected_emotions": detected_emotions,
                "prompt_count": len(structure),
                "prompts": structure,
                "method_analysis": method_analysis,
                "total_size_mb": round(
                    sum(
                        img["size_bytes"] for p in structure for img in p["images"]
                    )
                    / (1024 * 1024),
                    1,
                ),
            }
            return result

        except Exception:
            # 清理临时文件
            if extract_dir.exists():
                shutil.rmtree(str(extract_dir), ignore_errors=True)
            raise

    def analyze_emotion(self, upload_id: str, emotion: str) -> dict:
        """
        对已解压的 zip 分析指定情感类别（不重新解压）。

        Args:
            upload_id: 已存在的上传会话 ID
            emotion: 要分析的情感类别

        Returns:
            完整分析结果 dict
        """
        extract_dir = self.temp_dir / upload_id
        if not extract_dir.exists():
            raise ValueError("上传会话已过期，请重新上传")

        detected_emotions = self._detect_emotions(str(extract_dir))

        if emotion not in detected_emotions:
            raise ValueError(
                f"Zip 中未找到情感类别 '{emotion}'。"
                f"检测到的类别: {', '.join(detected_emotions)}"
            )

        emotion_dir = str(extract_dir / emotion)
        structure = self._analyze_structure(emotion_dir)

        if not structure:
            raise ValueError(
                f"情感类别 '{emotion}' 下未找到有效的 prompt 目录。"
            )

        method_analysis = self._extract_methods(structure)
        if not method_analysis["candidates"]:
            # 构建详细错误信息，帮助用户排查
            per_prompt = method_analysis.get("per_prompt_candidates", {})
            debug_lines = []
            for pname, cands in sorted(per_prompt.items()):
                cands_str = ", ".join(sorted(cands)) if cands else "(无)"
                debug_lines.append(f"  {pname}: [{cands_str}]")
            debug_info = "\n".join(debug_lines) if debug_lines else "无 prompt 信息"
            raise ValueError(
                f"未能识别出任何跨 prompt 一致的方法名。\n\n"
                f"Prompt 总数: {len(structure)}，要求方法出现在 ≥{max(int(len(structure)*0.4),1)} 个 prompt 中。\n"
                f"各 prompt 候选方法名:\n{debug_info}\n\n"
                f"提示：请确保各 prompt 目录下的图片以相同的方法名命名"
                f"（如 sd.png, sdxl.png），不要附加 prompt 相关的后缀。"
            )

        return {
            "upload_id": upload_id,
            "emotion": emotion,
            "emotion_cn": EMOTION_CN_MAP.get(emotion, emotion),
            "detected_emotions": detected_emotions,
            "prompt_count": len(structure),
            "prompts": structure,
            "method_analysis": method_analysis,
            "total_size_mb": round(
                sum(
                    img["size_bytes"] for p in structure for img in p["images"]
                )
                / (1024 * 1024),
                1,
            ),
        }

    def analyze_emotions(self, upload_id: str, emotions: list[str]) -> list[dict]:
        """
        批量分析多个情感类别（不重新解压）。

        Args:
            upload_id: 已存在的上传会话 ID
            emotions: 要分析的情感类别列表

        Returns:
            每个情感的分析结果列表
        """
        extract_dir = self.temp_dir / upload_id
        if not extract_dir.exists():
            raise ValueError("上传会话已过期，请重新上传")

        detected_emotions = self._detect_emotions(str(extract_dir))
        results = []
        all_prompt_names = set()

        # 第一遍：分析每个情感的结构
        for emotion in emotions:
            if emotion not in detected_emotions:
                results.append({
                    "emotion": emotion,
                    "_error": f"Zip 中未找到情感类别 '{emotion}'。检测到的类别: {', '.join(detected_emotions)}",
                })
                continue

            emotion_dir = str(extract_dir / emotion)
            structure = self._analyze_structure(emotion_dir)

            if not structure:
                results.append({
                    "emotion": emotion,
                    "_error": f"情感类别 '{emotion}' 下未找到有效的 prompt 目录。",
                })
                continue

            method_analysis = self._extract_methods(structure)
            if not method_analysis["candidates"]:
                per_prompt = method_analysis.get("per_prompt_candidates", {})
                debug_lines = []
                for pname, cands in sorted(per_prompt.items()):
                    cands_str = ", ".join(sorted(cands)) if cands else "(无)"
                    debug_lines.append(f"  {pname}: [{cands_str}]")
                debug_info = "\n".join(debug_lines) if debug_lines else "无 prompt 信息"
                results.append({
                    "emotion": emotion,
                    "_error": (
                        f"未能识别出任何跨 prompt 一致的方法名。\n\n"
                        f"Prompt 总数: {len(structure)}，要求方法出现在 ≥{max(int(len(structure)*0.4),1)} 个 prompt 中。\n"
                        f"各 prompt 候选方法名:\n{debug_info}\n\n"
                        f"提示：请确保各 prompt 目录下的图片以相同的方法名命名"
                        f"（如 sd.png, sdxl.png），不要附加 prompt 相关的后缀。"
                    ),
                })
                continue

            # 收集所有 prompt 名称用于统一翻译
            for p in structure:
                all_prompt_names.add(p["name"])

            results.append({
                "emotion": emotion,
                "emotion_cn": EMOTION_CN_MAP.get(emotion, emotion),
                "detected_emotions": detected_emotions,
                "prompt_count": len(structure),
                "prompts": structure,
                "method_analysis": method_analysis,
                "total_size_mb": round(
                    sum(
                        img["size_bytes"] for p in structure for img in p["images"]
                    )
                    / (1024 * 1024),
                    1,
                ),
                })

        return results, list(all_prompt_names)

    def get_preview_image(
        self, upload_id: str, emotion: str, prompt: str, filename: str
    ) -> Optional[Path]:
        """获取预览缩略图"""
        file_path = self.temp_dir / upload_id / emotion / prompt / filename
        if not file_path.exists():
            return None
        return file_path

    def get_temp_dir(self, upload_id: str, emotion: str = None) -> Path:
        """
        获取临时目录路径。
        如果指定 emotion，返回该情感子目录。
        """
        base = self.temp_dir / upload_id
        if emotion:
            return base / emotion
        return base

    def cleanup_temp(self, upload_id: str) -> None:
        """清理临时文件"""
        temp_path = self.temp_dir / upload_id
        if temp_path.exists():
            shutil.rmtree(str(temp_path), ignore_errors=True)

    def cleanup_stale_temp(self, max_age_hours: float = 1.0) -> int:
        """
        清理超过指定时间的遗留临时目录。
        返回清理的目录数量。
        """
        if not self.temp_dir.exists():
            return 0

        now = time.time()
        max_age_seconds = max_age_hours * 3600
        cleaned = 0

        for item in self.temp_dir.iterdir():
            if not item.is_dir():
                continue
            try:
                mtime = item.stat().st_mtime
                if now - mtime > max_age_seconds:
                    shutil.rmtree(str(item), ignore_errors=True)
                    cleaned += 1
            except OSError:
                pass

        return cleaned

    # ============== 内部方法 ==============

    def _detect_emotions(self, extract_dir: str) -> list[str]:
        """从解压后的根目录检测情感类别（一级子目录）"""
        root = Path(extract_dir)
        emotions = []
        for item in sorted(root.iterdir()):
            if item.is_dir():
                emotions.append(item.name)
        return emotions

    def _validate_and_extract(self, zip_path: str, extract_to: str) -> None:
        """验证 zip 文件安全性并解压"""
        # 检查文件大小
        file_size = os.path.getsize(zip_path)
        if file_size > MAX_ZIP_SIZE:
            raise ValueError(f"文件大小超过限制（最大 {MAX_ZIP_SIZE // (1024*1024)}MB）")

        with zipfile.ZipFile(zip_path, "r") as zf:
            # 检查文件数量
            info_list = zf.infolist()
            if len(info_list) > MAX_FILE_COUNT:
                raise ValueError("压缩包内文件数量过多")

            # 检查解压后总大小
            total_size = sum(info.file_size for info in info_list)
            if total_size > MAX_EXTRACTED_SIZE:
                raise ValueError("解压后文件总大小超过限制（最大 2GB）")

            # 检查压缩比（Zip bomb 检测）
            if file_size > 0 and total_size / file_size > 100:
                raise ValueError("压缩比异常，疑似压缩炸弹攻击")

            # 逐文件解压，防止路径穿越
            for info in info_list:
                # 跳过目录条目
                if info.is_dir():
                    continue

                # 路径穿越防护
                extracted_path = os.path.normpath(os.path.join(extract_to, info.filename))
                if not extracted_path.startswith(os.path.normpath(extract_to) + os.sep):
                    raise ValueError(f"检测到路径穿越攻击: {info.filename}")

                # 创建父目录
                os.makedirs(os.path.dirname(extracted_path), exist_ok=True)

                # 解压文件
                with zf.open(info) as src, open(extracted_path, "wb") as dst:
                    # 分块读取，防止单文件 OOM
                    while True:
                        chunk = src.read(1024 * 1024)  # 1MB chunks
                        if not chunk:
                            break
                        dst.write(chunk)

    def _analyze_structure(self, extract_dir: str) -> list[dict]:
        """
        分析目录结构（子目录 = prompt）
        返回格式：
        [
            {
                "name": "A house in a garden",
                "file_count": 4,
                "images": [
                    {
                        "filename": "house_sd.png",
                        "size_bytes": 245678,
                        "width": 1024,
                        "height": 1024
                    },
                    ...
                ]
            },
            ...
        ]
        """
        root = Path(extract_dir)
        if not root.exists():
            return []
        prompts = []

        # 遍历一级子目录（即各个 prompt）
        for item in sorted(root.iterdir()):
            if not item.is_dir():
                continue

            # 收集该子目录下的所有图片
            images = []
            for img_file in sorted(item.iterdir()):
                if not img_file.is_file():
                    continue

                ext = img_file.suffix.lower()
                if ext not in SUPPORTED_IMAGE_EXTENSIONS:
                    continue

                size_bytes = img_file.stat().st_size
                width, height = 0, 0

                # 尝试获取图片尺寸
                try:
                    if ext != ".svg":
                        with Image.open(img_file) as img:
                            width, height = img.size
                except Exception:
                    pass  # 损坏的图片，尺寸留 0

                images.append(
                    {
                        "filename": img_file.name,
                        "size_bytes": size_bytes,
                        "width": width,
                        "height": height,
                    }
                )

            if images:
                prompts.append(
                    {
                        "name": item.name,
                        "file_count": len(images),
                        "images": images,
                    }
                )

        return prompts

    def _extract_methods(self, structure: list[dict]) -> dict:
        """
        从目录结构中提取方法名（跨 prompt 一致性校验）。

        策略：
        1. 每个 prompt 内从文件名提取方法名：
           - 有 _ 的文件：最后一段即方法名（如 ours, db, emogen）
           - 无 _ 的文件：用 prompt 目录名定位边界提取（如 sdxl, ti）
        2. 跨所有 prompt 统计：同一方法名出现的 prompt 数
        3. 仅保留在 ≥40% prompt 中出现的方法名
        4. 变体检测也做跨 prompt 验证

        Args:
            structure: _analyze_structure 的返回结果

        Returns:
            {candidates: [...], missing_matrix: {...}}
        """
        prompt_count = len(structure)
        if prompt_count == 0:
            return {"candidates": [], "missing_matrix": {}}

        # 第一步：每个 prompt 提取候选方法名，然后归一化
        # prompt_candidates[prompt_name] = set of NORMALIZED candidate strings
        # prompt_raw_candidates[prompt_name] = set of ORIGINAL candidate strings
        prompt_candidates: dict[str, set[str]] = {}
        prompt_raw_candidates: dict[str, set[str]] = {}

        for prompt in structure:
            prompt_name = prompt["name"]
            stems = [Path(img["filename"]).stem for img in prompt["images"]]

            if not stems:
                prompt_candidates[prompt_name] = set()
                prompt_raw_candidates[prompt_name] = set()
                continue

            # 提取方法名：
            # - 有 _ 的：最后一段即方法名  (55-house-amusement_ours → ours)
            # - 无 _ 的：用 prompt 目录名定位边界 (sdxl-house-sdxl → sdxl)
            extracted = set()
            for s in stems:
                if "_" in s:
                    method = s.rsplit("_", 1)[1]
                else:
                    idx = s.find(prompt_name)
                    if idx >= 0:
                        after = s[idx + len(prompt_name):]
                        method = after.lstrip("-").lstrip("_")
                    else:
                        method = s.rsplit("-", 1)[-1]

                if method:
                    extracted.add(method)

            prompt_raw_candidates[prompt_name] = extracted

            # 归一化：剥离变体后缀 (sdlora → sd, etc.)
            normalized = {_normalize_name(c) for c in extracted}
            prompt_candidates[prompt_name] = normalized

        # 第二步：跨 prompt 统计归一化后的方法名，找出在 ≥50% prompt 中出现的方法
        candidate_appearances: dict[str, int] = {}
        for candidates_in_prompt in prompt_candidates.values():
            for c in candidates_in_prompt:
                candidate_appearances[c] = candidate_appearances.get(c, 0) + 1

        # 阈值 40%，方法需在 ≥40% 的 prompt 中出现（如 5 prompt 至少 2 个）
        min_presence = max(int(prompt_count * 0.4), 1)

        # 第三步：构建结果
        candidates = []
        seen_methods: set[str] = set()  # 避免变体检测重复

        # 先按出现次数降序排，让高频的排在前面作为 base method
        sorted_candidates = sorted(
            candidate_appearances.items(),
            key=lambda x: (-x[1], x[0]),
        )

        for c_name, presence in sorted_candidates:
            if presence < min_presence:
                continue

            # 检测是否为已知方法的变体（c_name 以 "已知方法_" 或 "已知方法-" 开头）
            method = c_name
            variant = None
            confidence = "high" if presence >= prompt_count * 0.9 else "medium"

            for base_name in sorted(seen_methods, key=len, reverse=True):
                if c_name.startswith(base_name + "_"):
                    method = base_name
                    variant = c_name[len(base_name):].lstrip("_")
                    confidence = "uncertain"
                    break
                if c_name.startswith(base_name + "-"):
                    method = base_name
                    variant = c_name[len(base_name):].lstrip("-")
                    confidence = "uncertain"
                    break

            seen_methods.add(c_name)
            candidates.append(
                {
                    "source": c_name,
                    "method": method,
                    "variant": variant,
                    "confidence": confidence,
                    "present_in": presence,
                }
            )

        # 第四步：构建缺失矩阵（基于 candidates 中的 source）
        missing_matrix: dict[str, list[str]] = {}
        candidate_sources = {c["source"] for c in candidates}
        # 包括方法名本身，因为变体名也会在 source 中
        for c in candidates:
            candidate_sources.add(c["method"])

        for prompt_name, pc_set in prompt_candidates.items():
            missing_in_prompt = []
            for c in candidates:
                # 检查该 prompt 是否有这个候选（或其任何变体）
                found = False
                for pc in pc_set:
                    if pc == c["source"] or pc == c["method"]:
                        found = True
                        break
                    # 也检查变体关系
                    if c["variant"] and pc.startswith(c["method"] + "_"):
                        found = True
                        break
                if not found:
                    missing_in_prompt.append(c["source"])
            if missing_in_prompt:
                missing_matrix[prompt_name] = missing_in_prompt

        return {
            "candidates": candidates,
            "missing_matrix": missing_matrix,
            "per_prompt_candidates": prompt_raw_candidates,
        }


def _normalize_name(name: str) -> str:
    """方法名归一化（目前保留原名，避免误剥方法名内的数字/字母）。"""
    return name


def _longest_common_prefix(strings: list[str]) -> str:
    """找字符串列表的最长公共前缀"""
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix
