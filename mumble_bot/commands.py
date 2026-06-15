"""频道文字命令处理（走 Mumble 文字聊天）。

序号来自 !who 的列表顺序（按 session 排序，稳定）。管理员 = config.behavior.admin_keys 白名单。
依赖通过构造注入（resolver / privacy / 发送与列人回调），便于单测。
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class CommandHandler:
    def __init__(self, *, resolver, privacy, admin_keys, list_users, reply, reply_private,
                 speaker=None, prefix: str = ","):
        self._resolver = resolver
        self._privacy = privacy
        self._admin_keys = admin_keys
        self._list_users = list_users      # () -> 排好序的 user 列表（不含 bot）
        self._reply = reply                # (text) -> 发到频道
        self._reply_private = reply_private  # (user, text) -> 私信
        self._speaker = speaker
        self._prefix = prefix              # 独立前缀，避开点歌bot 的 ! 命名空间

    def set_prefix(self, prefix: str) -> None:
        self._prefix = prefix

    def set_admin_keys(self, admin_keys) -> None:
        self._admin_keys = admin_keys

    def handle(self, actor, text: str) -> bool:
        """返回是否被当作命令处理。非本前缀（如点歌bot 的 !pause）一律不接管。"""
        text = text.strip()
        if not text.startswith(self._prefix):
            return False
        rest = text[len(self._prefix):].strip()
        if not rest:
            return False
        toks = rest.split()
        cmd = toks[0].lower()
        args = toks[1:]
        method = getattr(self, f"_cmd_{cmd}", None)
        if method is None:
            return False
        try:
            method(actor, args)
        except Exception:
            log.exception("命令处理异常：%s", text)
            self._reply("命令出错了。")
        return True

    # ---------- 权限 ----------
    def _is_admin(self, actor) -> bool:
        return self._resolver.is_admin(actor, self._admin_keys)

    def _require_admin(self, actor) -> bool:
        if not self._is_admin(actor):
            self._reply("需要管理员权限。")
            return False
        return True

    def _user_by_index(self, idx_str):
        if not idx_str.isdigit():
            return None
        users = self._list_users()
        idx = int(idx_str)
        return users[idx] if 0 <= idx < len(users) else None

    # ---------- 命令 ----------
    def _cmd_help(self, actor, args):
        p = self._prefix
        self._reply(
            f"命令（前缀 {p}）：{p}who 列人 ｜ {p}whoami 看自己的键 ｜ {p}me <名字> 自报 ｜ "
            f"{p}bind <序号> <名字> [--save] ｜ {p}exclude <序号|名字> [--save] ｜ "
            f"{p}include <序号|名字> ｜ {p}forget <名字> ｜ {p}pause/{p}resume 转写 ｜ "
            f"{p}shutup [分钟] 闭嘴 ｜ {p}comeback 取消闭嘴"
        )

    def _cmd_who(self, actor, args):
        users = self._list_users()
        if not users:
            self._reply("当前没有其他人。")
            return
        lines = ["序号｜原始名｜当前称呼｜状态"]
        for i, u in enumerate(users):
            canon = self._resolver.resolve(u)
            if canon is None:
                cur, status = u.get("name"), "除名"
            else:
                cur = canon
                status = "未绑定" if self._resolver.is_unbound(u) else "已绑定"
            lines.append(f"{i}｜{u.get('name')}｜{cur}｜{status}")
        self._reply("\n".join(lines))

    def _cmd_whoami(self, actor, args):
        key = self._resolver.stable_key(actor)
        is_admin = "是" if self._is_admin(actor) else "否"
        self._reply_private(
            actor,
            f"你的稳定键：{key}（管理员：{is_admin}）。把它加入 config 的 behavior.admin_keys 即可成为管理员。",
        )

    def _cmd_me(self, actor, args):
        if not args:
            self._reply("用法：!me 你的名字")
            return
        name = " ".join(args).strip()
        self._resolver.bind_session(actor.get("session"), name)
        self._reply(f"好的，本次会话叫你「{name}」。")

    def _cmd_bind(self, actor, args):
        if not self._require_admin(actor):
            return
        save = "--save" in args
        args = [a for a in args if a != "--save"]
        if len(args) < 2 or not args[0].isdigit():
            self._reply("用法：!bind <序号> <名字> [--save]")
            return
        u = self._user_by_index(args[0])
        if u is None:
            self._reply("序号超范围，先 !who 看序号。")
            return
        name = " ".join(args[1:]).strip()
        self._resolver.bind_session(u.get("session"), name)
        if save:
            self._resolver.archive(self._resolver.stable_key(u), name)
        self._reply(f"已绑定 {u.get('name')} → {name}{'（已存档）' if save else ''}。")

    def _cmd_exclude(self, actor, args):
        if not self._require_admin(actor):
            return
        save = "--save" in args
        args = [a for a in args if a != "--save"]
        if not args:
            self._reply("用法：!exclude <序号|名字> [--save]")
            return
        if args[0].isdigit():
            u = self._user_by_index(args[0])
            if u is None:
                self._reply("序号超范围。")
                return
            self._resolver.exclude(self._resolver.stable_key(u), save=save)
            self._resolver.clear_session(u.get("session"))
            self._reply(f"已除名 {u.get('name')}{'（已存档）' if save else ''}。")
        else:
            name = " ".join(args).strip()
            self._resolver.exclude(name, save=save)
            self._reply(f"已除名「{name}」{'（已存档）' if save else ''}。")

    def _cmd_include(self, actor, args):
        if not self._require_admin(actor):
            return
        if not args:
            self._reply("用法：!include <序号|名字>")
            return
        if args[0].isdigit():
            u = self._user_by_index(args[0])
            if u is None:
                self._reply("序号超范围。")
                return
            self._resolver.include(self._resolver.stable_key(u))
            self._reply(f"已取消除名 {u.get('name')}。")
        else:
            name = " ".join(args).strip()
            self._resolver.include(name)
            self._reply(f"已取消除名「{name}」。")

    def _cmd_forget(self, actor, args):
        if not self._require_admin(actor):
            return
        if not args:
            self._reply("用法：!forget <名字>")
            return
        name = " ".join(args).strip()
        n = self._resolver.forget_name(name)
        self._reply(f"已删除 {n} 条「{name}」的存档映射。")

    def _cmd_pause(self, actor, args):
        if not self._require_admin(actor):
            return
        self._privacy.pause()
        self._reply("已暂停转写。")

    def _cmd_resume(self, actor, args):
        if not self._require_admin(actor):
            return
        self._privacy.resume()
        self._reply("已恢复转写。")

    def _cmd_shutup(self, actor, args):
        mins = 5.0
        if args:
            try:
                mins = float(args[0])
            except ValueError:
                pass
        if mins <= 0:
            self._privacy.unmute()
            self._reply("好，我继续说话。")
        else:
            self._privacy.shutup(mins)
            self._reply(f"好，我闭嘴 {mins:g} 分钟。")

    def _cmd_comeback(self, actor, args):
        self._privacy.unmute()
        self._reply("我回来了。")
