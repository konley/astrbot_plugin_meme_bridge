"""
meme_bridge - 表情包桥接插件
自动将 smart_imagechat_hub 收集的表情包同步到 meme_manager 分类目录。
"""
import asyncio
import base64
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain

from .tag_mapping import CATEGORY_DESCRIPTIONS, ALL_CATEGORIES, get_categories_for_tags

# LLM classification prompt (English for better LLM compatibility)
_LLM_CLASSIFY_PROMPT = """You are a meme classifier. Look at the image and select 1-3 categories that best fit it.

Available categories:
{categories}

Output ONLY the category names, separated by commas. Do not output anything else.
Categories:"""


@register(
    "meme_bridge",
    "BoxAI",
    "表情包桥接插件 - 自动同步 smart_imagechat_hub 表情包到 meme_manager",
    "v1.0.0",
)
class MemeBridgePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
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
        self.target_memes_dir = self.target_dir / "memes"
        self.target_data_path = self.target_dir / "memes_data.json"

        # 同步状态文件
        self.sync_state_path = plugin_data / "meme_bridge" / "sync_state.json"
        self.sync_state_path.parent.mkdir(parents=True, exist_ok=True)

        # 加载已同步状态
        self.sync_state = self._load_sync_state()

        # 定时任务
        self._sync_task = None

    def _load_sync_state(self) -> dict:
        """加载已同步图片 ID 集合"""
        if self.sync_state_path.exists():
            try:
                with open(self.sync_state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"synced_ids": {}, "total_synced": 0, "last_sync_time": 0}

    def _save_sync_state(self):
        """保存同步状态"""
        try:
            with open(self.sync_state_path, "w", encoding="utf-8") as f:
                json.dump(self.sync_state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存同步状态失败: {e}")

    async def initialize(self):
        """插件初始化时启动定时任务"""
        if self.config.get("enable_sync", True):
            interval = self.config.get("sync_interval", 600)
            self._sync_task = asyncio.create_task(self._sync_loop(interval))
            logger.info(f"meme_bridge 定时同步已启动，间隔 {interval} 秒")

    async def terminate(self):
        """插件卸载时停止定时任务"""
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

    # ===== 定时同步 =====

    async def _sync_loop(self, interval: int):
        """定时扫描循环"""
        while True:
            try:
                await asyncio.sleep(interval)
                await self._do_sync(auto=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"meme_bridge 同步异常: {e}")
                await asyncio.sleep(60)  # 出错后等 1 分钟再重试

    # ===== 核心同步逻辑 =====

    async def _do_sync(self, auto: bool = False) -> dict:
        """执行一次同步，返回统计信息

        Returns:
            dict with keys: total_new, categories (dict), llm_count, skipped, failed, total_library
        """
        index_path = self.source_dir / "image_index.json"
        if not index_path.exists():
            logger.warning(f"源插件 image_index.json 不存在: {index_path}")
            return {"error": "image_index.json 不存在"}

        # 读取索引
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception as e:
            logger.error(f"读取 image_index.json 失败: {e}")
            return {"error": f"读取失败: {e}"}

        images: dict = index_data.get("images", {})
        synced_ids: dict = self.sync_state.get("synced_ids", {})

        # 找出需要同步的新图
        new_images = []
        for img_id, img_info in images.items():
            if img_id in synced_ids:
                continue
            # 只同步已完成 caption 的图片
            caption_status = img_info.get("caption_status", "")
            if caption_status != "done":
                continue
            new_images.append((img_id, img_info))

        if not new_images:
            # 无新图
            total_library = self._count_library()
            self.sync_state["last_sync_time"] = int(asyncio.get_event_loop().time())
            self._save_sync_state()
            return {
                "total_new": 0,
                "total_library": total_library,
            }

        # 确保目标目录存在
        self.target_memes_dir.mkdir(parents=True, exist_ok=True)

        # 同步统计
        stats = {
            "total_new": 0,
            "categories": defaultdict(int),
            "llm_count": 0,
            "skipped": 0,
            "failed": 0,
        }

        for img_id, img_info in new_images:
            tags = img_info.get("tags", [])
            rel_path = img_info.get("rel_path", "")
            filename = img_info.get("filename", "")

            if not filename or not rel_path:
                stats["failed"] += 1
                continue

            src_path = self.source_dir / rel_path
            if not src_path.exists():
                logger.warning(f"源文件不存在: {src_path}")
                stats["skipped"] += 1
                continue

            # 标签映射
            matched = get_categories_for_tags(tags)

            # LLM 辅助分类
            if not matched and self.config.get("enable_llm_fallback", True):
                llm_cats = await self._llm_classify_image(src_path)
                if llm_cats:
                    matched = set(llm_cats)
                    stats["llm_count"] += 1

            # 兜底
            if not matched:
                matched = {"other"}

            # 复制到每个分类
            for category in matched:
                cat_dir = self.target_memes_dir / category
                cat_dir.mkdir(parents=True, exist_ok=True)
                dst_path = cat_dir / filename
                if not dst_path.exists():
                    try:
                        shutil.copy2(str(src_path), str(dst_path))
                    except Exception as e:
                        logger.warning(f"复制失败 {src_path} -> {dst_path}: {e}")
                        stats["failed"] += 1
                        continue
                stats["categories"][category] += 1

            stats["total_new"] += 1
            synced_ids[img_id] = {
                "filename": filename,
                "categories": list(matched),
                "synced_at": int(asyncio.get_event_loop().time()),
            }

        # 更新 memes_data.json（合并新分类描述）
        self._update_memes_data(stats["categories"])

        # 保存同步状态
        self.sync_state["synced_ids"] = synced_ids
        self.sync_state["total_synced"] = len(synced_ids)
        self.sync_state["last_sync_time"] = int(asyncio.get_event_loop().time())
        self._save_sync_state()

        # 统计图库总量
        stats["total_library"] = self._count_library()

        return dict(
            total_new=stats["total_new"],
            categories=dict(stats["categories"]),
            llm_count=stats["llm_count"],
            skipped=stats["skipped"],
            failed=stats["failed"],
            total_library=stats["total_library"],
        )

    def _update_memes_data(self, new_categories: dict):
        """将新分类描述合并到 memes_data.json"""
        existing = {}
        if self.target_data_path.exists():
            try:
                with open(self.target_data_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        updated = False
        for cat in new_categories:
            if cat not in existing and cat in CATEGORY_DESCRIPTIONS:
                existing[cat] = CATEGORY_DESCRIPTIONS[cat]
                updated = True

        if updated:
            try:
                with open(self.target_data_path, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"更新 memes_data.json 失败: {e}")

    def _count_library(self) -> int:
        """统计目标图库总文件数"""
        if not self.target_memes_dir.exists():
            return 0
        total = 0
        for _ in self.target_memes_dir.rglob("*"):
            if _.is_file():
                total += 1
        return total

    # ===== LLM 视觉分类 =====

    async def _llm_classify_image(self, image_path: Path) -> list[str]:
        """调用视觉 LLM 对图片进行分类

        Returns:
            分类名列表，失败时返回空列表
        """
        try:
            # 获取 provider
            provider_id = self.config.get("llm_provider_id", "")
            if provider_id:
                provider = self.context.get_provider(provider_id)
            else:
                provider = self.context.get_using_provider()

            if provider is None:
                logger.warning("LLM Provider 不可用，跳过 LLM 分类")
                return []

            # 读取图片转 base64
            with open(image_path, "rb") as f:
                img_data = f.read()
            img_b64 = base64.b64encode(img_data).decode("utf-8")

            # 构建 prompt
            categories_str = "\n".join(
                f"- {cat}: {desc}" for cat, desc in CATEGORY_DESCRIPTIONS.items()
            )
            prompt = _LLM_CLASSIFY_PROMPT.format(categories=categories_str)

            # 调用 LLM
            resp = await provider.text_chat(
                prompt=prompt,
                session_id="meme_bridge_classify",
                contexts=[],
                image_urls=[f"data:image/jpeg;base64,{img_b64}"],
            )

            if not resp:
                return []

            # 解析响应
            result = resp.strip()
            cats = [c.strip() for c in result.split(",")]
            # 过滤非法分类
            valid = [c for c in cats if c in ALL_CATEGORIES]
            return valid[:3]

        except Exception as e:
            logger.warning(f"LLM 分类失败: {e}")
            return []

    # ===== 指令 =====

    @filter.command("表情包同步", alias={"同步表情包", "meme_sync"})
    async def cmd_sync(self, event):
        """立即执行一次同步"""
        yield event.plain_result("正在同步表情包...")

        stats = await self._do_sync()

        if "error" in stats:
            yield event.plain_result(f"[表情包同步] 失败 ❌\n{stats['error']}")
            return

        msg = self._format_sync_result(stats)
        yield event.plain_result(msg)

    @filter.command("同步状态", alias={"meme_status"})
    async def cmd_status(self, event):
        """查看同步统计信息"""
        total_synced = self.sync_state.get("total_synced", 0)
        total_library = self._count_library()
        last_time = self.sync_state.get("last_sync_time", 0)

        lines = [
            "[表情包同步状态]",
            f"已同步图片: {total_synced} 张",
            f"当前图库: {total_library} 张",
            f"自动同步: {'开启' if self.config.get('enable_sync', True) else '关闭'}",
            f"扫描间隔: {self.config.get('sync_interval', 600)} 秒",
            f"LLM 辅助: {'开启' if self.config.get('enable_llm_fallback', True) else '关闭'}",
        ]
        yield event.plain_result("\n".join(lines))

    # ===== 格式化输出 =====

    def _format_sync_result(self, stats: dict) -> str:
        """格式化同步结果为用户友好的文案"""
        total_new = stats.get("total_new", 0)
        total_library = stats.get("total_library", 0)
        categories = stats.get("categories", {})
        llm_count = stats.get("llm_count", 0)
        skipped = stats.get("skipped", 0)
        failed = stats.get("failed", 0)

        has_issues = skipped > 0 or failed > 0

        if total_new == 0:
            return f"[表情包同步] 完成 ✅ 未发现新表情包，当前图库共 {total_library} 张"

        lines = ["[表情包同步] 完成 ✅"]

        # 分类统计
        sorted_cats = sorted(categories.items(), key=lambda x: -x[1])
        if len(sorted_cats) > 6:
            top = sorted_cats[:6]
            rest_count = len(sorted_cats) - 6
            cat_str = "  " + "  ".join(f"{c}: {n}" for c, n in top)
            cat_str += f"\n  等共 {len(sorted_cats)} 个分类"
        else:
            cat_str = "  " + "  ".join(f"{c}: {n}" for c, n in sorted_cats)

        lines.append(f"本次同步 {total_new} 张新表情，归入 {len(categories)} 个分类：")
        lines.append(cat_str)

        if llm_count > 0:
            lines.append(f"其中 LLM 辅助分类: {llm_count} 张")

        lines.append(f"当前图库总计: {total_library} 张")

        if has_issues:
            lines.append(f"⚠️ {skipped + failed} 张图片源文件{'丢失' if skipped else ''}{'，' if skipped and failed else ''}{'复制失败' if failed else ''}，已跳过")

        return "\n".join(lines)
