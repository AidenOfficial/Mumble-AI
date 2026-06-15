"""身份解析：把"这一刻这个连接"映射到一个 canonical 称呼。

三类身份、三种键：
- stable_map:   稳定键 -> canonical（持久化）。键 = f"reg:{user_id}"（注册用户，跨设备稳定）
                或 user["hash"]（游客的证书哈希，退而求其次）。
- exclude_set:  除名键集合（稳定键 / 原始名 / 固定名如 bot）；持久化。
- session_bind: session_id -> canonical（仅内存，断开即清；网吧小子 !me 自报用）。

resolve() 返回 canonical；None 表示被除名（连 STT 流都不开，省钱）。

user 参数兼容 pymumble 的 User（dict 子类）与测试用的普通 dict，统一走 .get()。
注意：pymumble 的证书哈希字段是 user["hash"]（不是 cert_hash，且未文档化——启动需断言）。
"""

from __future__ import annotations

import threading


class IdentityResolver:
    def __init__(self, db=None, exclude_names=()):
        self._db = db
        self._lock = threading.RLock()
        self._stable_map: dict[str, str] = {}
        self._exclude_set: set[str] = set(exclude_names)
        self._session_bind: dict[int, str] = {}
        if db is not None:
            self._load()

    # ---------- 持久化加载 ----------
    def _load(self) -> None:
        for key, canonical in self._db.query("SELECT stable_key, canonical FROM identity_map"):
            self._stable_map[key] = canonical
        for (key,) in self._db.query("SELECT key FROM excludes"):
            self._exclude_set.add(key)

    # ---------- 键 ----------
    @staticmethod
    def stable_key(user) -> str:
        """注册用户跨设备稳定用 reg:user_id；游客退而求其次用证书哈希；都没有用 session。"""
        uid = user.get("user_id")
        if uid is not None:
            return f"reg:{uid}"
        h = user.get("hash")
        if h:
            return h
        return f"session:{user.get('session')}"

    # ---------- 解析 ----------
    def resolve(self, user) -> str | None:
        """返回 canonical；None = 被除名。"""
        with self._lock:
            key = self.stable_key(user)
            name = user.get("name")
            if key in self._exclude_set or (name and name in self._exclude_set):
                return None
            if key in self._stable_map:
                return self._stable_map[key]
            sess = user.get("session")
            if sess in self._session_bind:
                return self._session_bind[sess]
            return name  # 兜底：原始名（unbound）

    def is_unbound(self, user) -> bool:
        """是否还在用原始名（没存档也没会话绑定）。供 !who 标状态。"""
        with self._lock:
            key = self.stable_key(user)
            return key not in self._stable_map and user.get("session") not in self._session_bind

    # ---------- 绑定 ----------
    def bind_session(self, session: int, canonical: str) -> None:
        with self._lock:
            self._session_bind[session] = canonical

    def archive(self, stable_key: str, canonical: str) -> None:
        """按稳定键存档，下次自动套。"""
        with self._lock:
            self._stable_map[stable_key] = canonical
            if self._db is not None:
                self._db.execute(
                    "INSERT OR REPLACE INTO identity_map(stable_key, canonical) VALUES (?, ?)",
                    (stable_key, canonical),
                )

    def clear_session(self, session: int) -> None:
        with self._lock:
            self._session_bind.pop(session, None)

    # ---------- 除名 ----------
    def exclude(self, key: str, save: bool = False) -> None:
        with self._lock:
            self._exclude_set.add(key)
            if save and self._db is not None:
                self._db.execute("INSERT OR REPLACE INTO excludes(key) VALUES (?)", (key,))

    def include(self, key: str) -> None:
        with self._lock:
            self._exclude_set.discard(key)
            if self._db is not None:
                self._db.execute("DELETE FROM excludes WHERE key=?", (key,))

    def is_excluded(self, key: str) -> bool:
        with self._lock:
            return key in self._exclude_set

    # ---------- 删除存档 ----------
    def forget_name(self, name: str) -> int:
        """删除所有 canonical==name 的存档映射，返回删除条数。"""
        with self._lock:
            keys = [k for k, v in self._stable_map.items() if v == name]
            for k in keys:
                del self._stable_map[k]
                if self._db is not None:
                    self._db.execute("DELETE FROM identity_map WHERE stable_key=?", (k,))
            return len(keys)

    # ---------- 管理员 ----------
    def is_admin(self, user, admin_keys) -> bool:
        key = self.stable_key(user)
        name = user.get("name")
        return key in admin_keys or (name is not None and name in admin_keys)
