"""
meme_bridge - 表情包桥接插件
自动将 smart_imagechat_hub 收集的表情包同步到 meme_manager 分类目录。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register

from .tag_mapping import (
    DEFAULT_CATEGORY_DESCRIPTIONS,
    DEFAULT_TAG_TO_CATEGORIES,
    get_categories_for_tags,
    get_default_all_categories,
    load_mapping_from_json,
)

_LLM_CLASSIFY_PROMPTS: dict[str, str] = {
    "en": """You are a meme classifier. Look at the image and select 1-3 categories that best fit it.

Available categories:
{categories}

Output ONLY the category names, separated by commas. Do not output anything else.
Categories:""",
    "zh": """你是表情包分类器。观察图片，从以下分类中选出 1-3 个最匹配的：

可用分类：
{categories}

只输出分类名，用英文逗号分隔，不要输出其他内容。
分类：""",
}


def _file_sha256(path: Path) -> str:
    """计算文件 SHA256（hex），大文件流式读取。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@register(
    "meme_bridge",
    "konley",
    "表情包桥接插件 - 自动同步 smart_imagechat_hub 表情包到 meme_manager",
    "v1.3.0",
)
class MemeBridgePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}

        # 路径
        data_dir = Path(os.environ.get("ASTRBOT_DATA_DIR", "data"))
        plugin_data = data_dir / "plugin_data"
        self.source_dir = plugin_data / self.config.get(
            "source_plugin_name", "astrbot_plugin_smart_imagechat_hub"
        )
        self.target_dir = plugin_data / self.config.get(
            "target_plugin_name", "meme_manager"
        )
        self.target_memes_dir = self.target_dir / "memes"  # legacy layout fallback
        self.target_data_path = (
            self.target_dir / "memes_data.json"
        )  # legacy layout fallback

        # 同步状态文件
        self.sync_state_path = plugin_data / "meme_bridge" / "sync_state.json"
        self.sync_state_path.parent.mkdir(parents=True, exist_ok=True)

        # 标签映射（支持外部 JSON 覆盖）
        self.tag_to_categories: dict[str, list[str]] = DEFAULT_TAG_TO_CATEGORIES
        self.category_descriptions: dict[str, str] = DEFAULT_CATEGORY_DESCRIPTIONS
        self.all_categories: list[str] = get_default_all_categories()
        self._load_tag_mapping()

        # 已同步状态
        self.sync_state: dict = self._load_sync_state()

        # 上次同步结果（内存缓存，供 /同步状态 查询）
        self.last_sync_stats: dict | None = None

        # 定时任务
        self._sync_task: asyncio.Task | None = None

    # ===== 标签映射加载 =====

    def _load_tag_mapping(self):
        """按配置加载标签映射，外部 JSON > 内置默认。"""
        mapping_path = (self.config.get("tag_mapping_path") or "").strip()
        if not mapping_path:
            return
        try:
            tag_map, desc_map = load_mapping_from_json(mapping_path)
            if tag_map:
                self.tag_to_categories = tag_map
            if desc_map:
                self.category_descriptions = desc_map
            self.all_categories = list(self.category_descriptions.keys())
            logger.info(f"已从外部加载标签映射: {mapping_path}")
        except FileNotFoundError as e:
            logger.warning(f"{e}，回退到内置默认映射")
        except Exception as e:
            logger.warning(f"加载外部标签映射失败: {e}，回退到内置默认")

    # ===== 同步状态 =====

    def _load_sync_state(self) -> dict:
        if self.sync_state_path.exists():
            try:
                with open(self.sync_state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    return self._empty_sync_state()
                # 兼容旧字段
                data.setdefault("synced_ids", {})
                data.setdefault("content_hashes", {})
                data.setdefault("total_synced", 0)
                data.setdefault("last_sync_time", 0)
                data.setdefault("last_sync_stats", None)
                data.setdefault("target_states", {})
                return data
            except Exception as e:
                logger.warning(f"读取同步状态失败，将重置: {e}")
        return self._empty_sync_state()

    @staticmethod
    def _empty_sync_state() -> dict:
        return {
            "synced_ids": {},
            "content_hashes": {},
            "total_synced": 0,
            "last_sync_time": 0,
            "last_sync_stats": None,
            "target_states": {},
        }

    def _pick_target_pack_id(self) -> str | None:
        """解析目标 pack_id。优先级: 配置固定 pack > default 规则 > enabled pack > 常见回退 > 首个目录。"""
        packs_dir = self.target_dir / "packs"
        if not packs_dir.is_dir():
            return None

        configured_pack_id = str(self.config.get("target_pack_id") or "").strip()
        if configured_pack_id:
            if (packs_dir / configured_pack_id).is_dir():
                return configured_pack_id
            logger.warning(
                f"配置的 target_pack_id 不存在: {configured_pack_id}，将自动解析默认包"
            )

        selection_rules_path = self.target_dir / "selection_rules.json"
        if selection_rules_path.is_file():
            try:
                with open(selection_rules_path, "r", encoding="utf-8") as f:
                    selection_rules = json.load(f)
                rules = (
                    selection_rules.get("rules", [])
                    if isinstance(selection_rules, dict)
                    else []
                )
                if isinstance(rules, list):
                    for rule in reversed(rules):
                        if not isinstance(rule, dict):
                            continue
                        if str(rule.get("scope") or "").strip().lower() != "default":
                            continue
                        pack_id = str(rule.get("pack_id") or "").strip()
                        if pack_id and (packs_dir / pack_id).is_dir():
                            return pack_id
            except Exception as e:
                logger.warning(f"读取 selection_rules.json 失败: {e}")

        registry_path = self.target_dir / "registry.json"
        if registry_path.is_file():
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry = json.load(f)
                installed = (
                    registry.get("installed_packs", [])
                    if isinstance(registry, dict)
                    else []
                )
                if isinstance(installed, list):
                    for item in installed:
                        if not isinstance(item, dict):
                            continue
                        if not bool(item.get("enabled", True)):
                            continue
                        pack_id = str(item.get("id") or "").strip()
                        if pack_id and (packs_dir / pack_id).is_dir():
                            return pack_id
            except Exception as e:
                logger.warning(f"读取 registry.json 失败: {e}")

        for fallback_pack_id in ("builtin-default", "legacy-migrated"):
            if (packs_dir / fallback_pack_id).is_dir():
                return fallback_pack_id

        try:
            candidates = sorted(
                path.name for path in packs_dir.iterdir() if path.is_dir()
            )
        except Exception:
            candidates = []
        return candidates[0] if candidates else None

    def _resolve_target_context(self) -> dict[str, Any]:
        """解析目标目录上下文，兼容新旧 meme_manager 存储布局。"""
        pack_id = self._pick_target_pack_id()
        if pack_id:
            pack_dir = self.target_dir / "packs" / pack_id
            return {
                "layout": "pack",
                "pack_id": pack_id,
                "pack_dir": pack_dir,
                "memes_dir": pack_dir / "memes",
                "metadata_path": pack_dir / "memes_data.json",
                "state_key": f"pack:{pack_id}",
            }

        return {
            "layout": "legacy",
            "pack_id": None,
            "pack_dir": self.target_dir,
            "memes_dir": self.target_memes_dir,
            "metadata_path": self.target_data_path,
            "state_key": "legacy:root",
        }

    def _ensure_target_state(self, state_key: str) -> dict:
        """获取目标维度同步状态；兼容迁移旧版（无 target_states）状态结构。"""
        target_states = self.sync_state.setdefault("target_states", {})
        state = target_states.get(state_key)
        if isinstance(state, dict):
            state.setdefault("synced_ids", {})
            state.setdefault("content_hashes", {})
            state.setdefault("total_synced", 0)
            state.setdefault("last_sync_time", 0)
            state.setdefault("last_sync_stats", None)
            return state

        state = {
            "synced_ids": {},
            "content_hashes": {},
            "total_synced": 0,
            "last_sync_time": 0,
            "last_sync_stats": None,
        }

        # 迁移旧版单状态字段，避免升级后第一次同步重复处理历史图片。
        if not target_states and self.sync_state.get("synced_ids"):
            state["synced_ids"] = dict(self.sync_state.get("synced_ids", {}))
            state["content_hashes"] = dict(self.sync_state.get("content_hashes", {}))
            state["total_synced"] = int(self.sync_state.get("total_synced", 0) or 0)
            state["last_sync_time"] = int(self.sync_state.get("last_sync_time", 0) or 0)
            state["last_sync_stats"] = self.sync_state.get("last_sync_stats")

        target_states[state_key] = state
        return state

    def _save_sync_state(self):
        try:
            with open(self.sync_state_path, "w", encoding="utf-8") as f:
                json.dump(self.sync_state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存同步状态失败: {e}")

    def reset_sync_state(self, keep_hashes: bool = False):
        """清空已同步状态。

        Args:
            keep_hashes: True 时保留 content_hashes（用于 dry-run 演练或重分类）。
        """
        if keep_hashes:
            target_states = self.sync_state.get("target_states", {})
            if isinstance(target_states, dict):
                for key, state in list(target_states.items()):
                    if not isinstance(state, dict):
                        target_states[key] = {
                            "synced_ids": {},
                            "content_hashes": {},
                            "total_synced": 0,
                            "last_sync_time": 0,
                            "last_sync_stats": None,
                        }
                        continue
                    state["synced_ids"] = {}
                    state["total_synced"] = 0
                    state["last_sync_stats"] = None
            self.sync_state["synced_ids"] = {}
            self.sync_state["total_synced"] = 0
            self.sync_state["last_sync_stats"] = None
        else:
            self.sync_state = self._empty_sync_state()
        self._save_sync_state()
        logger.info("meme_bridge 同步状态已重置")

    # ===== 生命周期 =====

    async def initialize(self):
        if self.config.get("enable_sync", True):
            interval = max(60, int(self.config.get("sync_interval", 600)))
            self._sync_task = asyncio.create_task(self._sync_loop(interval))
            logger.info(f"meme_bridge 定时同步已启动，间隔 {interval} 秒")
        else:
            logger.info("meme_bridge 自动同步已关闭，仅响应手动指令")

    async def terminate(self):
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

    # ===== 定时同步 =====

    async def _sync_loop(self, interval: int):
        while True:
            try:
                await asyncio.sleep(interval)
                await self._do_sync()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"meme_bridge 同步异常: {e}")
                await asyncio.sleep(60)

    # ===== 核心同步 =====

    async def _do_sync(self) -> dict:
        """执行一次同步。"""
        # 热重载外部标签映射
        self._load_tag_mapping()

        target_ctx = self._resolve_target_context()
        target_memes_dir: Path = target_ctx["memes_dir"]
        target_data_path: Path = target_ctx["metadata_path"]
        target_pack_id = target_ctx.get("pack_id")
        target_state = self._ensure_target_state(str(target_ctx["state_key"]))

        index_path = self.source_dir / "image_index.json"
        if not index_path.exists():
            logger.warning(f"源插件 image_index.json 不存在: {index_path}")
            return {"error": "image_index.json 不存在"}

        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception as e:
            logger.error(f"读取 image_index.json 失败: {e}")
            return {"error": f"读取失败: {e}"}

        images: dict = index_data.get("images", {})
        synced_ids: dict = dict(target_state.get("synced_ids", {}))
        content_hashes: dict = dict(target_state.get("content_hashes", {}))

        new_images: list[tuple[str, dict]] = []
        for img_id, img_info in images.items():
            if img_id in synced_ids:
                continue
            if img_info.get("caption_status") != "done":
                continue
            new_images.append((img_id, img_info))

        stats = {
            "total_new": 0,
            "categories": defaultdict(int),
            "llm_count": 0,
            "skipped": 0,
            "failed": 0,
            "duplicate": 0,
            "target_memes_dir": target_memes_dir,
        }

        if not new_images:
            now_ts = int(time.time())
            target_state["last_sync_time"] = now_ts
            self.sync_state["last_sync_time"] = now_ts
            self._save_sync_state()
            stats["total_library"] = self._count_library(target_memes_dir)
            stats["dry_run"] = self.config.get("dry_run", False)
            stats["target_pack_id"] = target_pack_id
            result = self._build_result(stats)
            self.last_sync_stats = result
            return result

        dry_run = bool(self.config.get("dry_run", False))
        if not dry_run:
            target_memes_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: 校验源文件 + 计算哈希 + 哈希去重
        dedup_hashes = bool(self.config.get("dedup_by_hash", True))
        valid_items: list[tuple[str, dict, Path, str | None, list[str]]] = []
        for img_id, img_info in new_images:
            tags = img_info.get("tags", [])
            rel_path = img_info.get("rel_path", "")
            filename = img_info.get("filename", "")
            if not filename or not rel_path:
                stats["skipped"] += 1
                continue
            src_path = self.source_dir / rel_path
            if not src_path.exists():
                logger.warning(f"源文件不存在: {src_path}")
                stats["skipped"] += 1
                continue

            content_hash: str | None = None
            if dedup_hashes:
                try:
                    content_hash = await asyncio.to_thread(_file_sha256, src_path)
                except Exception as e:
                    logger.warning(f"计算 hash 失败 {src_path}: {e}")

            if content_hash and content_hash in content_hashes:
                stats["duplicate"] += 1
                # 复用先前的分类信息，但不重复复制
                prev = content_hashes[content_hash]
                synced_ids[img_id] = {
                    "filename": filename,
                    "categories": prev.get("categories", []),
                    "content_hash": content_hash,
                    "duplicate_of": prev.get("img_id"),
                    "synced_at": int(time.time()),
                }
                continue

            valid_items.append((img_id, img_info, src_path, content_hash, tags))

        # Step 2: 标签预分类 + 收集需要 LLM 的项
        classifications: dict[str, dict] = {}
        needs_llm: list[tuple[str, Path]] = []
        enable_llm = bool(self.config.get("enable_llm_fallback", True))

        for img_id, img_info, src_path, content_hash, tags in valid_items:
            matched = get_categories_for_tags(tags, self.tag_to_categories)
            if matched:
                classifications[img_id] = {"categories": matched, "llm": False}
            elif enable_llm:
                needs_llm.append((img_id, src_path))
            else:
                classifications[img_id] = {"categories": {"other"}, "llm": False}

        # Step 3: 视觉 LLM 并发分类（信号量限流）
        if needs_llm:
            llm_conc = max(1, int(self.config.get("llm_concurrency", 3)))
            sem = asyncio.Semaphore(llm_conc)

            async def _classify(item: tuple[str, Path]):
                async with sem:
                    cats = await self._llm_classify_image(item[1])
                    return item[0], cats

            results = await asyncio.gather(
                *[_classify(it) for it in needs_llm],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    logger.warning(f"LLM 分类异常: {r}")
                    continue
                img_id, cats = r
                if cats:
                    classifications[img_id] = {"categories": set(cats), "llm": True}
                else:
                    classifications[img_id] = {"categories": {"other"}, "llm": False}

        # Step 4: 拷贝到各分类目录（异步 + dry_run 感知）
        for img_id, img_info, src_path, content_hash, tags in valid_items:
            filename = img_info.get("filename", "")
            cls = classifications.get(img_id)
            if cls is None:
                continue
            matched = cls["categories"]
            llm_used = cls["llm"]
            if not matched:
                matched = {"other"}

            if not dry_run:
                copy_results = await asyncio.gather(
                    *[
                        self._copy_to_category(
                            src_path, target_memes_dir, matched, cat, filename
                        )
                        for cat in matched
                    ]
                )
                for ok, cat in copy_results:
                    if ok:
                        stats["categories"][cat] += 1
                        if llm_used:
                            stats["llm_count"] += 1
                    else:
                        stats["failed"] += 1
            else:
                # dry_run：仅统计，不实际复制
                for cat in matched:
                    stats["categories"][cat] += 1
                if llm_used:
                    stats["llm_count"] += 1
                logger.info(f"[dry-run] 将复制 {src_path.name} -> {matched}")

            stats["total_new"] += 1
            synced_ids[img_id] = {
                "filename": filename,
                "categories": list(matched),
                "content_hash": content_hash,
                "synced_at": int(time.time()),
            }
            if content_hash:
                content_hashes[content_hash] = {
                    "img_id": img_id,
                    "categories": list(matched),
                }

        # Step 5: 更新 memes_data.json + 持久化
        if not dry_run and stats["categories"]:
            self._update_memes_data(target_data_path, stats["categories"])

        now_ts = int(time.time())
        target_state["synced_ids"] = synced_ids
        target_state["content_hashes"] = content_hashes
        target_state["total_synced"] = len(synced_ids)
        target_state["last_sync_time"] = now_ts

        self.sync_state["last_sync_time"] = now_ts
        self.sync_state["total_synced"] = sum(
            len((state or {}).get("synced_ids", {}))
            for state in self.sync_state.get("target_states", {}).values()
            if isinstance(state, dict)
        )

        stats["target_pack_id"] = target_pack_id
        result = self._build_result(stats)
        summary = {
            "total_new": result["total_new"],
            "categories": result["categories"],
            "llm_count": result["llm_count"],
            "skipped": result["skipped"],
            "failed": result["failed"],
            "duplicate": result["duplicate"],
            "dry_run": result["dry_run"],
            "timestamp": now_ts,
            "target_pack_id": target_pack_id,
        }
        target_state["last_sync_stats"] = summary
        self.sync_state["last_sync_stats"] = summary
        self._save_sync_state()

        self.last_sync_stats = result
        return result

    async def _copy_to_category(
        self,
        src_path: Path,
        target_memes_dir: Path,
        matched: set[str],
        category: str,
        filename: str,
    ) -> tuple[bool, str]:
        """异步复制到目标分类目录。"""
        cat_dir = target_memes_dir / category
        try:
            cat_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"创建分类目录失败 {cat_dir}: {e}")
            return False, category

        dst_path = cat_dir / filename
        if dst_path.exists():
            return True, category  # 已存在视为成功，不重复复制

        try:
            await asyncio.to_thread(shutil.copy2, str(src_path), str(dst_path))
            return True, category
        except Exception as e:
            logger.warning(f"复制失败 {src_path} -> {dst_path}: {e}")
            return False, category

    def _build_result(self, stats: dict) -> dict:
        target_memes_dir = stats.get("target_memes_dir")
        if isinstance(target_memes_dir, Path):
            total_library = self._count_library(target_memes_dir)
        else:
            total_library = self._count_library(self.target_memes_dir)
        return {
            "total_new": stats.get("total_new", 0),
            "categories": dict(stats.get("categories", {})),
            "llm_count": stats.get("llm_count", 0),
            "skipped": stats.get("skipped", 0),
            "failed": stats.get("failed", 0),
            "duplicate": stats.get("duplicate", 0),
            "total_library": total_library,
            "dry_run": bool(self.config.get("dry_run", False)),
            "target_pack_id": stats.get("target_pack_id"),
        }

    def _update_memes_data(self, metadata_path: Path, new_categories: dict):
        """将新分类描述合并到 memes_data.json（不覆盖已有条目）。"""
        existing: dict = {}
        if metadata_path.exists():
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        if not isinstance(existing, dict):
            existing = {}

        updated = False
        for cat in new_categories:
            if cat not in existing:
                existing[cat] = self.category_descriptions.get(cat, "请添加描述")
                updated = True

        if updated:
            try:
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"更新 memes_data.json 失败: {e}")

    def _count_library(self, target_memes_dir: Path | None = None) -> int:
        memes_dir = target_memes_dir or self.target_memes_dir
        if not memes_dir.exists():
            return 0
        total = 0
        for p in memes_dir.rglob("*"):
            if p.is_file():
                total += 1
        return total

    # ===== LLM 视觉分类 =====

    async def _llm_classify_image(self, image_path: Path) -> list[str]:
        try:
            provider_id = (self.config.get("llm_provider_id") or "").strip()
            if provider_id:
                provider = self.context.get_provider(provider_id)
            else:
                provider = self.context.get_using_provider()

            if provider is None:
                logger.warning("LLM Provider 不可用，跳过 LLM 分类")
                return []

            with open(image_path, "rb") as f:
                img_data = f.read()
            img_b64 = base64.b64encode(img_data).decode("utf-8")

            categories_str = "\n".join(
                f"- {cat}: {desc}" for cat, desc in self.category_descriptions.items()
            )
            lang = (self.config.get("llm_prompt_language") or "en").lower()
            prompt_template = _LLM_CLASSIFY_PROMPTS.get(
                lang, _LLM_CLASSIFY_PROMPTS["en"]
            )
            prompt = prompt_template.format(categories=categories_str)

            resp = await provider.text_chat(
                prompt=prompt,
                session_id="meme_bridge_classify",
                contexts=[],
                image_urls=[f"data:image/jpeg;base64,{img_b64}"],
            )
            if not resp:
                return []

            cats = [c.strip() for c in resp.strip().split(",")]
            valid = [c for c in cats if c in self.all_categories]
            return valid[:3]
        except Exception as e:
            logger.warning(f"LLM 分类失败: {e}")
            return []

    # ===== 权限校验 =====

    def _is_admin(self, event) -> bool:
        """检查事件发送者是否为 Bot 管理员。"""
        if not self.config.get("manual_sync_admin_only", False):
            return True
        try:
            role = getattr(event, "role", None)
            if isinstance(role, str) and role.lower() in ("owner", "admin"):
                return True
            is_admin = getattr(event, "is_admin", None)
            if callable(is_admin):
                return bool(is_admin())
        except Exception:
            pass
        return False

    # ===== 指令 =====

    @filter.command("表情包同步", alias={"同步表情包", "meme_sync"})
    async def cmd_sync(self, event):
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 此指令仅 Bot 管理员可用")
            return

        if self.config.get("dry_run", False):
            yield event.plain_result("正在演练同步（dry_run，不会复制文件）...")
        else:
            yield event.plain_result("正在同步表情包...")

        stats = await self._do_sync()

        if "error" in stats:
            yield event.plain_result(f"[表情包同步] 失败 ❌\n{stats['error']}")
            return

        yield event.plain_result(self._format_sync_result(stats))

    @filter.command("表情包重扫", alias={"重扫表情包", "meme_resync"})
    async def cmd_resync(self, event):
        """清空已同步状态并立即重新同步。"""
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 此指令仅 Bot 管理员可用")
            return

        yield event.plain_result(
            "⚠️ 即将清空同步状态并重新扫描（已同步图片会重新复制）..."
        )
        self.reset_sync_state(keep_hashes=False)
        stats = await self._do_sync()

        if "error" in stats:
            yield event.plain_result(f"[表情包重扫] 失败 ❌\n{stats['error']}")
            return

        yield event.plain_result(self._format_sync_result(stats))

    @filter.command("同步状态", alias={"meme_status"})
    async def cmd_status(self, event):
        target_ctx = self._resolve_target_context()
        target_state = self._ensure_target_state(str(target_ctx["state_key"]))
        total_synced = int(target_state.get("total_synced", 0) or 0)
        total_library = self._count_library(target_ctx["memes_dir"])
        last_time = int(target_state.get("last_sync_time", 0) or 0)
        last_stats = target_state.get("last_sync_stats") or self.last_sync_stats

        lines = [
            "[表情包同步状态]",
            f"已同步图片: {total_synced} 张",
            f"当前图库: {total_library} 张",
            f"自动同步: {'开启' if self.config.get('enable_sync', True) else '关闭'}",
            f"扫描间隔: {self.config.get('sync_interval', 600)} 秒",
            f"LLM 辅助: {'开启' if self.config.get('enable_llm_fallback', True) else '关闭'}",
            f"LLM 并发: {self.config.get('llm_concurrency', 3)}",
            f"LLM Prompt: {self.config.get('llm_prompt_language', 'en')}",
            f"内容去重: {'开启' if self.config.get('dedup_by_hash', True) else '关闭'}",
            f"Dry-run: {'开启' if self.config.get('dry_run', False) else '关闭'}",
        ]

        lines.append(
            f"目标存储: {'packs/' + str(target_ctx['pack_id']) if target_ctx.get('pack_id') else 'legacy 根目录'}"
        )
        fixed_pack = str(self.config.get("target_pack_id") or "").strip()
        lines.append(
            f"目标 pack 选择: {'固定 ' + fixed_pack if fixed_pack else '自动跟随 default 规则'}"
        )

        mapping_path = (self.config.get("tag_mapping_path") or "").strip()
        lines.append(
            f"标签映射: {'外部 ' + mapping_path if mapping_path else '内置默认'}"
        )

        if last_time and last_time > 1e10:
            from datetime import datetime

            lines.append(
                f"上次同步: {datetime.fromtimestamp(last_time).strftime('%Y-%m-%d %H:%M:%S')}"
            )
        elif last_time:
            lines.append(f"上次同步: 启动后 {int(last_time)} 秒")

        if last_stats:
            lines.append("")
            lines.append("[上次同步结果]")
            lines.append(f"  新增: {last_stats.get('total_new', 0)} 张")
            if last_stats.get("llm_count"):
                lines.append(f"  LLM 辅助: {last_stats.get('llm_count')} 张")
            if last_stats.get("duplicate"):
                lines.append(f"  哈希去重跳过: {last_stats.get('duplicate')} 张")
            if last_stats.get("skipped"):
                lines.append(f"  源文件丢失: {last_stats.get('skipped')} 张")
            if last_stats.get("failed"):
                lines.append(f"  复制失败: {last_stats.get('failed')} 张")

        yield event.plain_result("\n".join(lines))

    # ===== 格式化输出 =====

    def _format_sync_result(self, stats: dict) -> str:
        total_new = stats.get("total_new", 0)
        total_library = stats.get("total_library", 0)
        categories = stats.get("categories", {})
        llm_count = stats.get("llm_count", 0)
        skipped = stats.get("skipped", 0)
        failed = stats.get("failed", 0)
        duplicate = stats.get("duplicate", 0)
        dry_run = stats.get("dry_run", False)
        target_pack_id = stats.get("target_pack_id")

        prefix = (
            "[表情包同步] 完成 ✅"
            if not dry_run
            else "[表情包同步] 演练完成 ✅（dry-run，未复制文件）"
        )

        if total_new == 0:
            target_line = f"（目标表情包: {target_pack_id}）" if target_pack_id else ""
            msg = f"{prefix} 未发现新表情包，当前图库共 {total_library} 张{target_line}"
            extras = self._format_extras(duplicate, skipped, failed)
            return msg + extras

        lines = [prefix]
        if target_pack_id:
            lines.append(f"目标表情包: {target_pack_id}")

        sorted_cats = sorted(categories.items(), key=lambda x: -x[1])
        if len(sorted_cats) > 6:
            top = sorted_cats[:6]
            cat_str = "  " + "  ".join(f"{c}: {n}" for c, n in top)
            cat_str += f"\n  等共 {len(sorted_cats)} 个分类"
        else:
            cat_str = "  " + "  ".join(f"{c}: {n}" for c, n in sorted_cats)

        lines.append(f"本次同步 {total_new} 张新表情，归入 {len(categories)} 个分类：")
        lines.append(cat_str)

        if llm_count > 0:
            lines.append(f"其中 LLM 辅助分类: {llm_count} 张")

        lines.append(f"当前图库总计: {total_library} 张")
        lines.append(self._format_extras(duplicate, skipped, failed).lstrip())

        return "\n".join(lines)

    @staticmethod
    def _format_extras(duplicate: int, skipped: int, failed: int) -> str:
        parts = []
        if duplicate:
            parts.append(f"哈希去重 {duplicate} 张")
        if skipped:
            parts.append(f"源文件丢失 {skipped} 张")
        if failed:
            parts.append(f"复制失败 {failed} 张")
        if not parts:
            return ""
        return "\n⚠️ " + "，".join(parts)
