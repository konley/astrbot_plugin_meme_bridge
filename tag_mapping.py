"""Tag-to-category mapping table (English categories)

Maps smart_imagechat_hub's fine-grained Chinese AI tags to meme_manager's
English category folders. One tag can map to multiple categories.

默认映射内嵌在本文件中，可通过配置项 ``tag_mapping_path`` 指定外部 JSON 文件覆盖。
外部 JSON 格式::

    {
      "tag_to_categories": {
        "开心": ["happy"],
        "猫": ["cat"]
      },
      "category_descriptions": {
        "happy": "Use when ...",
        "cat": "For cat topics..."
      }
    }
"""

from __future__ import annotations

import json
from pathlib import Path


# ===== 默认标签→分类映射 =====

DEFAULT_TAG_TO_CATEGORIES: dict[str, list[str]] = {}


def _register(tags: list[str], categories: list[str]):
    for tag in tags:
        if tag not in DEFAULT_TAG_TO_CATEGORIES:
            DEFAULT_TAG_TO_CATEGORIES[tag] = []
        for cat in categories:
            if cat not in DEFAULT_TAG_TO_CATEGORIES[tag]:
                DEFAULT_TAG_TO_CATEGORIES[tag].append(cat)


# ===== Emotion / Scene =====
_register(["开心", "微笑", "大笑", "闭眼微笑", "眯眼笑", "得意", "欢呼", "兴奋",
           "点赞", "竖大拇指", "握手", "打招呼", "举手", "握拳",
           "激动", "平静", "表情平静", "面无表情"], ["happy"])
_register(["可爱", "呆萌", "萌系", "可爱风", "可爱风格", "可爱萌系", "可爱少女", "卖萌",
           "Q版", "Q版角色", "圆滚滚", "腮红", "可爱治愈", "反差萌",
           "捏脸", "圆润", "圆脸", "萌系角色"], ["cute"])
_register(["搞笑", "搞怪", "恶搞", "幽默", "吐槽", "调侃", "斗图", "聊天斗图",
           "梗图", "熊猫头", "表情包风格", "社交聊天", "日常聊天", "魔性"], ["funny"])
_register(["委屈", "委屈表情", "哭泣", "流泪", "悲伤", "捂脸", "嘟嘴", "撅嘴",
           "捂嘴", "崩溃", "丧", "忧郁", "死鱼眼", "擦眼泪", "委屈哭泣"], ["sad"])
_register(["生气", "愤怒", "愤怒表情", "不满", "瞪眼",
           "竖中指", "怼人", "嘲讽", "嫌弃表情", "抓狂", "不耐烦"], ["angry"])
_register(["害羞", "脸红", "尴尬", "尴尬微笑", "害羞脸红", "害羞微笑", "半睁眼"], ["shy"])
_register(["疑惑", "困惑", "困惑表情", "疑问", "无语", "呆滞", "呆滞表情", "呆滞眼神",
           "面无表情", "尴尬微笑", "思考", "沉思", "好奇", "凝视", "专注", "眉头紧锁"], ["confused"])
_register(["惊讶", "惊讶表情", "震惊", "慌张", "张嘴", "张大嘴", "表情夸张", "夸张表情",
           "惊恐", "焦虑", "紧张"], ["surprised"])
_register(["困倦", "慵懒", "疲惫", "睡觉", "放松", "躺卧", "熬夜冠军",
           "躺平"], ["sleepy"])
_register(["傲娇", "探头", "偷看", "歪头", "躲藏",
           "俏皮", "吐舌头", "比心", "爱心", "撒娇",
           "眨眼", "甜美", "摸头", "拥抱"], ["playful"])
_register(["无奈", "冷淡", "冷漠", "讽刺", "自嘲"], ["helpless"])
_register(["温馨", "治愈", "治愈系", "温馨治愈", "暖色调", "柔和色调"], ["cozy"])

# ===== Content / Style =====
_register(["二次元", "动漫角色", "动漫风格", "游戏角色", "水手服", "女仆装",
           "双马尾", "少女", "白发动漫角色", "金发双马尾", "插画",
           "粉发", "粉色头发", "白发", "银发", "金发", "蓝发", "紫发", "黑发",
           "棕发", "橙发", "绿发", "灰发", "浅色头发", "白毛",
           "紫瞳", "蓝眼", "蓝瞳", "红瞳", "金瞳", "蓝眼睛", "紫色眼睛",
           "粉色", "粉色调", "大眼睛", "大眼", "呆毛",
           "戴眼镜", "耳机", "玫瑰发饰", "学生制服",
           "哆啦A梦"], ["anime"])
_register(["猫", "猫咪", "猫耳", "橘猫", "白猫", "兽耳", "萌宠", "毛茸茸",
           "毛绒玩偶", "毛绒玩具", "小动物",
           "仓鼠", "狗狗", "宠物", "可爱动物",
           "黑猫", "黑白猫", "灰猫", "虎斑猫", "胖猫", "卡通猫", "猫爪", "熊猫人"], ["cat"])
_register(["小猪", "猪"], ["pig"])
_register(["兔子", "兔耳", "白兔"], ["rabbit"])
_register(["像素风", "简笔画", "简约", "简约风格", "卡通", "卡通风格", "卡通角色",
           "3D渲染", "3D动画", "动画截图", "手绘", "手绘风格", "黑白线条",
           "卡通插画", "卡通形象"], ["cartoon"])
_register(["照片", "中年男性", "室内", "图片", "男性", "西装", "天安门"], ["photo"])
_register(["天安门"], ["photo"])


# ===== 默认分类描述 =====

DEFAULT_CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "happy": "Use when the conversation involves joy, success, celebration, or positive feedback (e.g., problem solved, achievement unlocked)",
    "cute": "For adorable interactions, softening tone, or moe scenarios (e.g., pet topics, comforting, acting cute)",
    "funny": "When the conversation has humor, teasing, parody, or meme battles (e.g., jokes, pranks, reaction memes)",
    "sad": "For sadness, crying, apologizing, or comforting (e.g., setbacks, bad news, being criticized)",
    "angry": "When the conversation involves complaints, criticism, or frustration (e.g., user complaints, arguments, anger)",
    "shy": "For privacy topics or receiving praise (e.g., personal stories, appearance comments, embarrassment)",
    "confused": "For requesting clarification or expressing puzzlement (e.g., unclear concepts, logical contradictions)",
    "surprised": "For unexpected information, shock, or panic (e.g., major discoveries, plot twists, emergencies)",
    "sleepy": "For rest, fatigue, staying up late, or bedtime scenarios (e.g., tiredness, sleep, relaxation)",
    "playful": "For teasing, flirting, peeking, or tsundere behavior (e.g., winking,撒娇, heart gestures)",
    "helpless": "For resignation, speechlessness, or sarcasm (e.g., repeated issues, awkward situations, sighing)",
    "cozy": "For healing, warmth, gratitude, or comfort (e.g., warm interactions, thanks, gentle atmosphere)",
    "anime": "For anime, game, or 2D art style content (e.g., anime characters, cosplay, illustration)",
    "cat": "For cat or pet topics (e.g., cats, furry animals, pet interactions)",
    "pig": "For pig-related content (e.g., pig memes, anthropomorphic pig characters)",
    "rabbit": "For rabbit or bunny-related content (e.g., rabbit memes, bunny ear characters)",
    "photo": "For real photos or screenshots (e.g., real people, life scene screenshots)",
    "cartoon": "For pixel art, cartoons, or hand-drawn style (e.g., minimalist, sketch, cartoon style)",
    "other": "Fallback for uncategorizable memes",
}


# ===== 兼容旧版的模块级符号 =====

TAG_TO_CATEGORIES = DEFAULT_TAG_TO_CATEGORIES
CATEGORY_DESCRIPTIONS = DEFAULT_CATEGORY_DESCRIPTIONS


def get_default_all_categories() -> list[str]:
    """返回默认全部分类名列表。"""
    return list(DEFAULT_CATEGORY_DESCRIPTIONS.keys())


def load_mapping_from_json(path: str | Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """从外部 JSON 文件加载标签映射与分类描述。

    Args:
        path: JSON 文件路径。

    Returns:
        (tag_to_categories, category_descriptions) 元组。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: JSON 结构不合法。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"标签映射文件不存在: {p}")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("JSON 顶层必须是对象")

    raw_tags = data.get("tag_to_categories", {})
    if not isinstance(raw_tags, dict):
        raise ValueError("tag_to_categories 必须是对象")

    tag_to_categories: dict[str, list[str]] = {}
    for tag, cats in raw_tags.items():
        if not isinstance(tag, str) or not isinstance(cats, list):
            raise ValueError(f"非法条目: {tag!r} -> {cats!r}")
        cleaned = [str(c).strip() for c in cats if c]
        if cleaned:
            tag_to_categories[tag] = cleaned

    raw_desc = data.get("category_descriptions", {})
    if not isinstance(raw_desc, dict):
        raise ValueError("category_descriptions 必须是对象")

    category_descriptions: dict[str, str] = {
        str(k): str(v) for k, v in raw_desc.items() if v
    }

    return tag_to_categories, category_descriptions


def get_categories_for_tags(
    tags: list[str],
    mapping: dict[str, list[str]] | None = None,
) -> set[str]:
    """Return matched categories for a list of tags.

    Args:
        tags: 待匹配的中文标签列表。
        mapping: 标签→分类映射表，为 None 时使用默认映射。
    """
    table = mapping if mapping is not None else DEFAULT_TAG_TO_CATEGORIES
    matched: set[str] = set()
    for tag in tags:
        cats = table.get(tag)
        if cats:
            matched.update(cats)
    return matched