# app/database.py
import os
import sqlite3
import json
import numpy as np
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

from .config import settings

logger = logging.getLogger(__name__)
DB_PATH = settings.DATABASE


@contextmanager
def get_db_connection():
    """
    数据库连接上下文管理器
    - 自动提交事务（无异常时）
    - 异常时回滚并记录日志
    - 确保连接关闭
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"数据库事务回滚: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def init_db():
    """初始化数据库：创建所有表、索引和执行迁移"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # ---- 用户表 ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ---- 物品表（已包含 reject_reason 列） ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK (type IN ('lost', 'found')),
                title TEXT NOT NULL,
                description TEXT,
                category TEXT,
                image_path TEXT,
                image_vector TEXT,
                text_vector TEXT,
                contact TEXT,
                location TEXT,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'claimed', 'done', 'rejected', 'closed')),
                user_id INTEGER NOT NULL,
                review_status TEXT DEFAULT 'pending' CHECK (review_status IN ('pending', 'approved', 'rejected')),
                reviewer_id INTEGER,
                review_time TIMESTAMP,
                reject_reason TEXT,                -- 新增字段
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (reviewer_id) REFERENCES users(id)
            )
        ''')

        # ---- 匹配记录表 ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lost_item_id INTEGER NOT NULL,
                found_item_id INTEGER NOT NULL,
                similarity_score REAL NOT NULL,
                is_confirmed INTEGER DEFAULT 0,
                confirmed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lost_item_id) REFERENCES items(id),
                FOREIGN KEY (found_item_id) REFERENCES items(id)
            )
        ''')

        # ---- 消息通知表 ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                link TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ---------- 迁移：为已有 items 表添加 reject_reason（如果不存在） ----------
        cursor.execute("PRAGMA table_info(items)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'reject_reason' not in columns:
            cursor.execute("ALTER TABLE items ADD COLUMN reject_reason TEXT")
            logger.info("迁移成功：items 表已添加 reject_reason 列")

        # ---------- 迁移：为已有 users 表添加 avatar_path（如果不存在） ----------
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [row['name'] for row in cursor.fetchall()]
        if 'avatar_path' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN avatar_path TEXT")
            logger.info("迁移成功：users 表已添加 avatar_path 列")

        # ---- 统计计数表（持久化计数器，不受物品删除影响） ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats_counters (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            )
        ''')
        # 初始化 claimed 计数器（若不存在则从现有数据计算）
        cursor.execute("INSERT OR IGNORE INTO stats_counters (key, value) VALUES ('total_claimed', 0)")
        # 同步：将已有 claimed 物品数纳入（首次运行或数据恢复时）
        cursor.execute("SELECT COUNT(*) as c FROM items WHERE status='claimed'")
        historical = cursor.fetchone()["c"]
        cursor.execute("UPDATE stats_counters SET value = MAX(value, ?) WHERE key='total_claimed'", (historical,))

        # ---- 公告表 ----
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                is_pinned INTEGER DEFAULT 0,
                target_role TEXT DEFAULT 'all',
                admin_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES users(id)
            )
        ''')
        # 迁移：已有公告表加 target_role 列
        cursor.execute("PRAGMA table_info(announcements)")
        ann_cols = [r['name'] for r in cursor.fetchall()]
        if 'target_role' not in ann_cols:
            cursor.execute("ALTER TABLE announcements ADD COLUMN target_role TEXT DEFAULT 'all'")
            logger.info("迁移成功：announcements 表已添加 target_role 列")

        # ---- 目录准备 ----
        os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(os.path.join(settings.UPLOAD_FOLDER, "avatars"), exist_ok=True)

        # ---- 索引 ----
        # 复合索引（覆盖 user_id + is_read 查询）
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read)')
        # 其他必要索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_user_id ON items(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_type ON items(type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_status ON items(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_review_status ON items(review_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_matches_lost_item ON matches(lost_item_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_matches_found_item ON matches(found_item_id)')
        # 注意：不再需要单独 idx_notifications_user_id 和 idx_notifications_is_read，复合索引已覆盖

        logger.info("数据库初始化/迁移完成")


# ---------- 向量序列化工具（保留 JSON 方式，可后续优化为 BLOB） ----------
def vector_to_json(vector: Optional[np.ndarray]) -> Optional[str]:
    """将 numpy 向量转换为 JSON 字符串"""
    if vector is None:
        return None
    if not isinstance(vector, np.ndarray):
        raise TypeError("vector 必须是 numpy.ndarray 类型")
    return json.dumps(vector.tolist())


def json_to_vector(json_str: Optional[str]) -> Optional[np.ndarray]:
    """将 JSON 字符串转换为 numpy 向量"""
    if not json_str:
        return None
    try:
        arr = json.loads(json_str)
        return np.array(arr)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"JSON 反序列化失败: {e}")
        return None


# ---------- 通知操作函数（统一使用上下文管理器） ----------
def add_notification(user_id: int, title: str, content: str, link: Optional[str] = None) -> None:
    """添加站内消息"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO notifications (user_id, title, content, link) VALUES (?, ?, ?, ?)',
            (user_id, title, content, link)
        )


def get_unread_count(user_id: int) -> int:
    """获取未读消息数量"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0', (user_id,))
        return cursor.fetchone()[0]


def get_unread_notifications(
    user_id: int,
    limit: int = 20,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    分页获取未读消息列表（按时间倒序）
    - limit: 每页条数（默认20）
    - offset: 偏移量（默认0）
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, title, content, link, created_at
            FROM notifications
            WHERE user_id = ? AND is_read = 0
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            ''',
            (user_id, limit, offset)
        )
        return [dict(row) for row in cursor.fetchall()]


def mark_notification_read(notification_id: int, user_id: int) -> None:
    """标记消息为已读（需验证用户ID，防止越权）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
            (notification_id, user_id)
        )
        # 可检查 rowcount 判断是否更新成功，此处省略


# ---------- 计数操作 ----------
def increment_counter(key: str, delta: int = 1) -> None:
    """持久化计数器 +delta（用于 claimed 总数等不受删除影响的统计）"""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO stats_counters (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = value + ?",
            (key, delta, delta)
        )


def get_counter(key: str) -> int:
    """读取持久化计数器"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM stats_counters WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else 0


# ---------- 常量 ----------
CATEGORIES = ['电子产品', '证件卡片', '包袋箱包', '书籍文具', '服装配饰', '钥匙门禁', '其他']