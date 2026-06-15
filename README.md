# Mumble 转写 AI 机器人

常驻 Mumble 频道的中文语音机器人：持续把每个人的话转写成**带墙钟时间戳的滚动记录**，并在三种触发下用一个有角色感的声音回灌频道——①有人说唤醒短语；②机器人自己把握时机插话（v1 只做"未应答提问"）；③点名召回历史。

## 技术栈
- **收音/出音**：Python 3.12 + `pymumble`（每用户 PCM 回调；注音回灌）
- **STT**：阿里 DashScope `paraformer-realtime-v2`（流式、词+句级时间戳；48k→16k 重采样）
- **TTS**：Fish Audio OpenAudio `s2-pro`（流式、克隆角色音）
- **LLM**：经 **OpenRouter** 路由 `deepseek/deepseek-v4-flash` 到快速 Western provider（Fireworks→DeepInfra→…，关思考）；可切 DeepSeek 直连或 Gemini 兜底
- **工具/技能**：LLM function-calling 驱动的 agentic 循环——倒计时、操作点歌bot、语音自我屏蔽（可扩展）
- **存储**：内存 `deque` 滚动缓冲 + SQLite(WAL) 持久化
- **部署**：Docker（homelab / Oracle ARM）

## 快速开始（Docker）
```bash
cp .env.example .env            # 填 API key / Mumble 密码
cp config.example.yaml config.yaml   # 改 mumble.host、voice_id、wake_regex 等
# 把 Mumble 客户端证书放到 ./certs/bot.pem（决定身份，务必固定）

docker compose up -d            # 连真实 Mumble 服务器
docker compose logs -f bot
```
本地集成测试（自带一个 Mumble 服务器）：
```bash
docker compose --profile testing up
```

## 频道内命令（走 Mumble 文字聊天）
命令前缀默认 **`,`**（不是 `!`），以避开点歌bot 等 `!` 命令的命名空间冲突；可在 `behavior.command_prefix` 改。
| 命令 | 作用 | 权限 |
|---|---|---|
| `,who` | 列当前人：序号｜原始名｜当前称呼｜状态 | 全员 |
| `,whoami` | 私聊返回你的稳定键（填进 `admin_keys` 用） | 全员 |
| `,me <名字>` | 自助绑定本会话称呼 | 全员 |
| `,bind <序号> <名字> [--save]` | 绑定；`--save` 按稳定键存档 | 管理员 |
| `,exclude <序号\|名字> [--save]` | 除名（不转写） | 管理员 |
| `,include <序号\|名字>` | 取消除名 | 管理员 |
| `,forget <名字>` | 删除某人的存档映射 | 管理员 |
| `,pause` / `,resume` | 暂停 / 恢复转写 | 管理员 |
| `,shutup <分钟>` | 让机器人闭嘴 N 分钟（停回话+插话） | 全员 |

管理员 = `config.yaml` 里 `behavior.admin_keys` 白名单。首次用 `,whoami` 获取自己的键填进去再重启。
> 点歌bot（botamusique）的 `!play`/`!pause`/`!skip` 等仍由它自己处理；我们的 bot 只认 `,` 前缀，两者不再打架。

## 技能 / 工具（语音触发，先叫唤醒词）
唤醒后说自然语言，LLM 自己决定要不要调工具：
| 你说（先叫「小特」） | AI 调用 | 效果 |
|---|---|---|
| 「倒计时 30 分钟」「番茄钟 25 分钟」 | `set_timer` | 到点机器人主动开口提醒 |
| 「点一首晴天」「切歌」「暂停」 | `music_control` | 给频道发点歌bot的命令（`external_bots.music` 里配命令模板） |
| 「蒙住耳朵十分钟」「别听了 5 分钟」 | `mute_ears` | 暂停收听+转写，到点自动恢复，快结束前提醒 |

- 操作点歌bot：在 `config.yaml` 的 `external_bots.music.commands` 配你那台 bot 的真实命令（如 `play: "!play {query}"`）。
- 新技能：继承 `mumble_bot/skills/base.py` 的 `Skill`，在 `main.py` 里 `registry.register(...)` 即可。
- 复杂任务想用更强模型：`openrouter.tool_model` 设成 `deepseek/deepseek-v4-pro`。

## 音色（Fish voice_id）
角色音 = Fish 上某个音色的 **Model ID**，填到 `config.yaml` 的 `fish.voice_id`（代码作为 `reference_id` 传给 Fish 的 `client.tts.stream`）。
- **用现成音色**：在 [fish.audio](https://fish.audio) 挑好音色 → 进它的页面，URL 形如 `fish.audio/m/<MODEL_ID>`，或页面上「复制 Model ID / Use API」→ 把那串 ID 填进 `voice_id`。
- **用自己克隆的**：上传你有权使用的参考音克隆，得到的 Model ID 同样填进去。
- 想试你物色的几个音色：改 `fish.voice_id` 换一个、重启即可（本设计锁定一个固定角色音）。
- 模型档 `fish.model` 默认 `s2-pro`（也可 `s1` / `speech-1.6` 等更便宜）。

## Web 管理界面
浏览器打开 `http://<宿主机>:8080`（Docker 默认只映射到宿主机本机；要 LAN 访问把 compose 端口映射改成 `8080:8080` 并设 `WEB_PASSWORD`）。
- **换音色**：设置 → 音色，改 Model ID 保存即时生效；状态页「试听」让它当场用新音色在频道里说一句——挑音色一键试。
- 改 人设 / 唤醒词 / 命令前缀 / 主动插话阈值 / 外部bot命令 / 记忆窗口 / 管理员键——即时生效；LLM、Mumble、STT 改动标「需重启」。
- 看 在线状态、频道成员（可绑定名字 / 除名）、最近转写、计时器；一键 暂停/恢复转写、闭嘴 N 分钟。
- **密钥不在这里改**（留在 `.env`），界面只显示是否已配置。可选 `WEB_PASSWORD` 登录保护。

## 开发与测试
纯逻辑模块（重采样/身份/唤醒/编排 prompt/插话门控）不依赖 Mumble，可在任意机器跑单测：
```bash
pip install -r requirements-dev.txt
pytest
```
> 注意：用 Python 3.12（3.13 移除了重采样备选、且 pymumble 未验证）。完整收音/出音链路依赖系统 `libopus`，建议直接走 Docker。

## 隐私
持续转写全员并上云——**务必告知频道成员**。进频道有公告；`,pause` 可随时停转写。

## 许可证
本项目以 **[GPL-3.0-or-later](LICENSE)** 发布。
核心依赖 `pymumble` 为 GPLv3，结合作品须沿用兼容的 copyleft 许可，故整体采用 GPLv3。
