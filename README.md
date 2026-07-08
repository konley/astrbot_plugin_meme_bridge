<p align="center">
  <img src="logo.png" alt="meme_bridge logo" width="200">
</p>

<h1 align="center">🌉 AstrBot 表情包桥接插件 (meme_bridge)</h1>

<p align="center">自动将 <code>smart_imagechat_hub</code> 收集的表情包同步到 <code>meme_manager</code> 的分类目录，让两个插件各司其职、协同工作。</p>

## 🎯 为什么需要这个插件

AstrBot 生态中有两个优秀的表情包插件，各有优劣：

|                        | [smart_imagechat_hub](https://github.com/QingchenWait/astrbot_plugin_smart_imagechat_hub) | [meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) |
| :--------------------: | :---------------------------------------------------------------------------------------: | :---------------------------------------------------------------------: |
| **自动收集群聊表情包** |                                          ✅ 支持                                          |                                ❌ 不支持                                |
|   **AI 自动打标签**    |                                    ✅ 每张图细粒度标签                                    |                                  ❌ 无                                  |
|        **斗图**        |                                          ✅ 支持                                          |                                ❌ 不支持                                |
|    **主动发表情包**    |                                ✅ 支持，但费 token、频率低                                |                           ✅ 零 token、频率高                           |
|     **Token 消耗**     |                                 高（语义匹配 + LLM 分析）                                 |                     极低（仅 system prompt 多几行）                     |
|      **匹配精度**      |                                   高（细粒度语义匹配）                                    |                         中（分类级 + 随机抽图）                         |
|      **图库管理**      |                                     JSON 索引 + WebUI                                     |                             文件夹 + WebUI                              |

**最佳实践：** 让旧插件负责收集和斗图，让新插件负责日常发图。本桥接插件自动将旧插件收集并打标签的新表情包，按分类同步到新插件的图库目录中。

## 🙏 鸣谢

- **[QingchenWait](https://github.com/QingchenWait)** — 感谢开发了 [astrbot_plugin_smart_imagechat_hub](https://github.com/QingchenWait/astrbot_plugin_smart_imagechat_hub)，提供了强大的表情包自动收集、AI 打标签和斗图功能，本插件依赖其运行时产生的 `image_index.json` 索引数据
- **[anka-afk](https://github.com/anka-afk)** — 感谢开发了 [astrbot_plugin_meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) 表情包管理器，其优秀的分类架构和 WebUI 管理界面是本插件的同步目标

本插件仅为数据桥接工具，不修改上述两个插件的任何源码，不侵犯其著作权。所有表情包图片的版权归原作者所有。

## 📦 前置安装

### 1. 安装旧插件 smart_imagechat_hub

在 AstrBot WebUI 插件管理中安装 `astrbot_plugin_smart_imagechat_hub`。

### 2. 安装新插件 meme_manager

在 AstrBot WebUI 插件管理中安装 `astrbot_plugin_meme_manager`。

### 3. 安装本插件

将 `astrbot_plugin_meme_bridge` 文件夹放到 AstrBot 的 `data/plugins/` 目录下，或通过 WebUI 插件管理安装。

### 4. 配置旧插件

**关键步骤！** 进入旧插件设置，**关闭主动发表情包功能**，只保留自动收集和斗图：

```json
{
  "proactive_emoji_reply": {
    "enabled": false          ← 关闭主动发图，交给 meme_manager
  },
  "auto_image_collection": {
    "enabled": true            ← 保留自动收集
  },
  "meme_combat": {
    "enabled": true            ← 保留斗图（可选）
  }
}
```

> 💡 旧插件的自动收集功能会在群聊中自动收集用户发送的表情包图片，调用 AI 生成细粒度标签（如"可爱"、"二次元"、"猫耳"等），并记录到 `image_index.json` 中。桥接插件读取这份索引来执行同步。

### 5. 配置新插件

确保 `meme_manager` 已正常运行。在新版本多包结构下，桥接插件会自动同步到 `packs/<default_pack_id>/memes/`（或你配置的目标 pack），并自动维护该 pack 下的 `memes_data.json`。

### 6. 配置桥接插件

在本插件的 WebUI 设置页面中配置以下选项（均可后续修改）：

| 配置项                | 类型   | 默认值                               | 说明                                                                             |
| --------------------- | ------ | ------------------------------------ | -------------------------------------------------------------------------------- |
| `enable_sync`         | 布尔   | `true`                               | 启用自动定时同步                                                                 |
| `sync_interval`       | 整数   | `600`                                | 扫描间隔（秒），默认 10 分钟                                                     |
| `llm_provider_id`     | 字符串 | `""`                                 | LLM Provider ID，留空使用框架默认。需支持图片输入                                |
| `enable_llm_fallback` | 布尔   | `true`                               | 标签映射不到时是否调用视觉 LLM 辅助分类                                          |
| `source_plugin_name`  | 字符串 | `astrbot_plugin_smart_imagechat_hub` | 旧插件目录名                                                                     |
| `target_plugin_name`  | 字符串 | `meme_manager`                       | 新插件目录名                                                                     |
| `target_pack_id`      | 字符串 | `""`                                 | 目标 pack_id。留空自动跟随 meme_manager 的 default 规则，填写后固定同步到该 pack |

### 7. 首次迁移（可选）

如果你已经在旧插件中积累了大量表情包，建议在安装桥接插件前先执行一次手动迁移（复制到目标 pack 的 `meme_manager/packs/<pack_id>/memes/` 目录）。桥接插件仅同步**新增量**的图片，不会重复处理已经迁移过的图片。

## 🔄 工作原理

```
群聊表情包 → smart_imagechat_hub 自动收集 → AI 打标签 → image_index.json
                                                         ↓
                                              meme_bridge 定时扫描
                                                         ↓
                                              ┌─ 标签能映射到分类 → 复制文件
                                              │
                                              └─ 标签无法映射 → 调视觉 LLM 选分类 → 复制
                                                         ↓
                                              meme_manager/packs/<pack_id>/memes/{分类}/
                                                         ↓
                                              meme_manager 正常发图（零 token）
```

### 分步说明

1. **旧插件自动收集**：群聊中用户发送的表情包图片被旧插件自动收集，调用 AI 生成细粒度标签
2. **桥接插件扫描**：每隔 N 分钟（默认 10 分钟）扫描旧插件的 `image_index.json`，找出已完成打标签但尚未同步的新图片
3. **标签映射**：将旧插件的细粒度标签（如"粉发"、"猫耳"、"呆萌"）归并到新插件的分类体系（如"可爱"、"猫猫"）
4. **LLM 辅助分类**（可选）：当标签无法映射到任何分类时，将图片和分类描述发送给视觉 LLM，让 LLM 选择 1-3 个最合适的分类
5. **复制文件**：将图片复制到新插件对应的分类文件夹中，一张图可以归入多个分类
6. **更新配置**：自动将新分类的描述写入 `memes_data.json`，让新插件能识别新分类
7. **新插件发图**：新插件在正常对话中根据 LLM 输出的 `&&分类名&&` 标记，从对应文件夹随机抽图发送

### 分类体系

桥接插件维护 19 个英文分类，覆盖表情包的常见情绪和风格：

<details>
<summary>📋 全部分类列表（点击展开）</summary>

| Category    | Description                        | Example Source Tags          |
| ----------- | ---------------------------------- | ---------------------------- |
| `happy`     | Joy, success, celebration          | 开心、大笑、得意、欢呼       |
| `cute`      | Adorable interactions, moe         | 可爱、呆萌、卖萌、Q版        |
| `funny`     | Humor, teasing, meme battles       | 搞笑、恶搞、梗图、熊猫头     |
| `sad`       | Sadness, crying, apologizing       | 委屈、哭泣、流泪、崩溃       |
| `angry`     | Complaints, criticism, frustration | 生气、愤怒、不满、抓狂       |
| `shy`       | Privacy, embarrassment, praise     | 害羞、脸红、尴尬             |
| `confused`  | Clarification, puzzlement          | 疑惑、困惑、无语、思考       |
| `surprised` | Shock, unexpected, panic           | 惊讶、震惊、慌张、惊恐       |
| `sleepy`    | Rest, fatigue, bedtime             | 困倦、慵懒、疲惫、躺平       |
| `playful`   | Teasing, flirting, tsundere        | 傲娇、俏皮、比心、撒娇       |
| `helpless`  | Resignation, speechlessness        | 无奈、冷淡、讽刺、自嘲       |
| `cozy`      | Healing, warmth, comfort           | 温馨、治愈、暖色调           |
| `anime`     | Anime, game, 2D art                | 二次元、动漫角色、粉发、猫耳 |
| `cat`       | Cats, pets, furry animals          | 猫、猫咪、橘猫、毛茸茸       |
| `pig`       | Pig-related content                | 小猪、猪                     |
| `rabbit`    | Rabbit, bunny                      | 兔子、兔耳、白兔             |
| `photo`     | Real photos, screenshots           | 照片、中年男性、室内         |
| `cartoon`   | Pixel art, cartoon, hand-drawn     | 像素风、简笔画、手绘、3D渲染 |
| `other`     | Fallback for uncategorizable       | （无法归入以上分类的图片）   |

</details>

### 标签映射 + LLM 混合策略

桥接插件采用混合分类策略，兼顾效率和精度：

- **方案 A（标签映射，零 token）**：将旧插件的细粒度标签通过内置映射表归并到 19 个分类。覆盖约 90% 的图片。
- **方案 B（LLM 辅助，精准但费 token）**：当标签无法映射时，将图片和分类描述发给视觉 LLM，让 LLM 选择 1-3 个分类。覆盖剩余约 10% 的图片。
- **兜底**：如果 LLM 也无法分类（或未启用），图片归入 `other` 分类。

## 📝 使用指令

| 指令          | 别名                          | 说明                     |
| ------------- | ----------------------------- | ------------------------ |
| `/表情包同步` | `/同步表情包`、`/meme_sync`   | 立即执行一次同步         |
| `/表情包重扫` | `/重扫表情包`、`/meme_resync` | 清空已同步状态后重新同步 |
| `/同步状态`   | `/meme_status`                | 查看同步统计与上次结果   |

> 开启 `manual_sync_admin_only` 后，`/表情包同步` 与 `/表情包重扫` 仅 Bot 管理员可用。

### 同步结果示例

**有新图时：**

```
[表情包同步] 完成 ✅
本次同步 12 张新表情，归入 8 个分类：
  anime: 5  cute: 3  funny: 2  cat: 1  happy: 1
  等共 8 个分类
其中 LLM 辅助分类: 2 张
当前图库总计: 3412 张
⚠️ 哈希去重 2 张，源文件丢失 1 张
```

**无新图时：**

```
[表情包同步] 完成 ✅ 未发现新表情包，当前图库共 3412 张
```

**Dry-run 模式：**

```
[表情包同步] 演练完成 ✅（dry-run，未复制文件）
本次同步 5 张新表情，归入 4 个分类：
  ...
```

## ⚙️ 配置详解

| 配置项                   | 类型   | 默认                                 | 说明                                                               |
| ------------------------ | ------ | ------------------------------------ | ------------------------------------------------------------------ |
| `enable_sync`            | bool   | `true`                               | 启用自动定时同步                                                   |
| `sync_interval`          | int    | `600`                                | 扫描间隔（秒），不低于 60                                          |
| `llm_provider_id`        | string | `""`                                 | 视觉 LLM Provider ID，留空用框架默认                               |
| `enable_llm_fallback`    | bool   | `true`                               | 标签无法映射时调用视觉 LLM 兜底                                    |
| `llm_concurrency`        | int    | `3`                                  | LLM 视觉分类最大并发数                                             |
| `llm_prompt_language`    | string | `en`                                 | `en` / `zh`，国产模型建议改 `zh`                                   |
| `source_plugin_name`     | string | `astrbot_plugin_smart_imagechat_hub` | 源插件目录名                                                       |
| `target_plugin_name`     | string | `meme_manager`                       | 目标插件目录名                                                     |
| `target_pack_id`         | string | `""`                                 | 目标 pack_id。留空自动跟随 default 规则，填写后固定同步到指定 pack |
| `tag_mapping_path`       | string | `""`                                 | 外部标签映射 JSON 绝对路径，留空用内置                             |
| `dedup_by_hash`          | bool   | `true`                               | 内容 SHA256 去重，防止多 ID 重复入库                               |
| `dry_run`                | bool   | `false`                              | 演练模式：只统计不复制                                             |
| `manual_sync_admin_only` | bool   | `false`                              | 手动同步指令仅管理员可用                                           |

### 外部标签映射（v1.2.0 新增）

编辑任意 JSON 文件，按下列格式自定义标签→分类映射，下次同步自动加载：

```json
{
  "tag_to_categories": {
    "开心": ["happy"],
    "猫": ["cat", "cute"]
  },
  "category_descriptions": {
    "happy": "Use when joy/celebration ...",
    "cat": "For cat topics ..."
  }
}
```

在 WebUI 把文件绝对路径填到 `tag_mapping_path` 即可生效，无需重载插件。`category_descriptions` 也会作为 LLM 视觉分类的 prompt 描述，**自定义描述会改变 LLM 分类标准**。

### Dry-run 演练

开启 `dry_run` 后插件不会实际复制任何文件，只统计和打印目标分类。改完标签映射想先看效果时很有用。

### 内容哈希去重

开启 `dedup_by_hash`（默认开）后，每张图同步前会算 SHA256。已同步过的内容直接跳过，避免旧插件因重试产生多 ID 导致重复入库。哈希表存在 `sync_state.json` 的 `content_hashes` 字段。

### 关于 `memes_data.json`

桥接插件只会在 `memes_data.json` 中**追加新分类的描述**（仅当 key 不存在时）。你**手动修改或删除**已有描述不会被覆盖；删除某个分类文件夹后，对应描述条目会保留——这是 meme_manager 容错的需要，删除是安全的。

## 📁 文件结构

```
astrbot_plugin_meme_bridge/
├── main.py                  # 插件主逻辑
├── tag_mapping.py            # 默认标签→分类映射表 + JSON 加载器
├── metadata.yaml             # 插件元数据
├── _conf_schema.json         # 配置项定义（WebUI 可见）
├── __init__.py
└── README.md
```

运行时数据：

```
data/plugin_data/meme_bridge/
└── sync_state.json           # 同步状态（已同步图片 ID + 内容哈希 + 上次结果摘要）
```

## ❓ FAQ

<details>
<summary>桥接插件会影响旧插件或新插件的运行吗？</summary>

不会。桥接插件只**读取**旧插件的 `image_index.json` 索引文件，不修改旧插件的任何数据。对于新插件，只向目标 pack 的 `memes/` 目录**添加**文件并更新该 pack 的 `memes_data.json`，不修改新插件源码。

</details>

<details>
<summary>同一张图片会被同步多次吗？</summary>

不会。桥接插件在 `sync_state.json` 中记录每张已同步图片的 ID，下次扫描时自动跳过。

</details>

<details>
<summary>一张图片只能归入一个分类吗？</summary>

不是。一张图片可以同时归入多个分类。例如一张同时有"可爱"和"猫猫"标签的图片，会被复制到两个分类文件夹中。

</details>

<details>
<summary>LLM 辅助分类会消耗多少 token？</summary>

只有标签映射不到的图片才会调用 LLM（约占 10%）。每次调用发送一张图片和约 500 token 的分类描述 prompt，消耗很小。如果你完全不想消耗 token，可以关闭 `enable_llm_fallback`，无法映射的图片将归入"其他"。

</details>

<details>
<summary>如何修改分类体系？</summary>

两种方式：

- **简单方式**：编辑 `tag_mapping.py` 中的 `DEFAULT_TAG_TO_CATEGORIES` 与 `DEFAULT_CATEGORY_DESCRIPTIONS`，然后**重载插件**。
- **热加载方式（v1.2.0）**：把自定义映射写到 JSON 文件，在 WebUI 的 `tag_mapping_path` 填入绝对路径。下次同步自动生效，无需重载。

已有分类的图片不会自动迁移，仅影响后续新同步的图片。如需对历史图片重新分类，使用 `/表情包重扫`（会清空已同步状态重新复制）。

</details>

<details>
<summary>旧插件卸载后桥接插件还能用吗？</summary>

不能。桥接插件依赖旧插件的 `image_index.json` 作为数据源。如果旧插件卸载，桥接插件将无法同步新图片，但已同步到 `meme_manager` 的图片不受影响。

</details>

## 📜 License

MIT

## 🆕 v1.3.0 更新日志

- **新增**：兼容 `meme_manager` 多表情包存储结构，自动识别并写入 `packs/<pack_id>/memes/`
- **新增**：`target_pack_id` 配置项，支持固定同步到指定 pack
- **新增**：留空 `target_pack_id` 时自动跟随 `selection_rules.json` 的 default 规则
- **新增**：同步状态按目标 pack 隔离存储，避免多 pack 场景相互污染
- **兼容**：保留旧版根目录 `memes/` 布局回退逻辑

## 🆕 v1.2.0 更新日志

- **修复**：`@register` 装饰器作者署名（`BoxAI` → `konley`），版本号与 metadata 同步
- **修复**：磁盘 IO 改为 `asyncio.to_thread`，不再阻塞事件循环
- **新增**：LLM 视觉分类并发限流（`llm_concurrency`，信号量控制）
- **新增**：外部标签映射 JSON 文件支持（`tag_mapping_path`，无需重载插件即可热生效）
- **新增**：内容 SHA256 去重（`dedup_by_hash`，防止旧插件多 ID 重复入库）
- **新增**：Dry-run 演练模式（`dry_run`，只统计不复制）
- **新增**：`/表情包重扫` 指令，清空已同步状态重新同步
- **新增**：手动同步指令可选管理员限制（`manual_sync_admin_only`）
- **新增**：LLM Prompt 双语支持（`llm_prompt_language`: `en` / `zh`）
- **新增**：`time.time()` 替代 `asyncio.get_event_loop().time()`，时间戳可读
- **优化**：`/同步状态` 展示上次同步结果摘要与配置快照
- **优化**：跳过/失败统计分开显示（源文件丢失 vs 复制失败 vs 哈希去重）

## 🔗 相关链接

- [astrbot_plugin_smart_imagechat_hub](https://github.com/QingchenWait/astrbot_plugin_smart_imagechat_hub) — 表情包自动收集与斗图
- [astrbot_plugin_meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) — 表情包管理器 3.0
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) — AstrBot 聊天机器人框架
