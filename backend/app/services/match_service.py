# app/services/match_service.py
from ..database import get_db_connection, json_to_vector, add_notification
from ..clip_service import clip_service
from ..utils.email_utils import send_match_notification
from ..logger import logger
from ..config import settings


def auto_match_and_notify(new_item_id: int, item_type: str) -> None:
    """
    新物品审核通过后自动匹配并推送通知
    """
    # 灰度总开关：重嵌入完成前/灰度期置 false，直接短路，不产生任何匹配与推送。
    if not settings.AUTO_MATCH_ENABLED:
        logger.info(f"自动匹配已关闭（AUTO_MATCH_ENABLED=false），跳过物品 {new_item_id}")
        return
    try:
        from datetime import datetime, timezone

        # 1. 获取新物品信息（含类别、位置、时间）
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, title, category, location, created_at, image_vector, text_vector, color_vector, image_path
                FROM items WHERE id = ?
            ''', (new_item_id,))
            new_item = cursor.fetchone()
            if not new_item:
                logger.warning(f"物品 {new_item_id} 不存在，跳过匹配")
                return

            # 2. 确定匹配目标类型
            target_type = 'found' if item_type == 'lost' else 'lost'

            # 3. 查询所有已审核且状态为 active 的目标物品
            cursor.execute('''
                SELECT id, user_id, title, category, location, created_at, image_vector, text_vector, color_vector, image_path
                FROM items
                WHERE type = ? AND status = 'active' AND review_status = 'approved'
            ''', (target_type,))
            target_items = cursor.fetchall()

        if not target_items:
            logger.info(f"新物品 {new_item_id} 没有可匹配的目标物品")
            return

        # 4. 计算相似度（五阶段+颜色优化）
        new_img_vec = json_to_vector(new_item['image_vector']) if new_item['image_vector'] else None
        new_text_vec = json_to_vector(new_item['text_vector']) if new_item['text_vector'] else None
        now = datetime.now(timezone.utc)
        # 颜色特征：优先取库中持久化的 color_vector（R4，免重复磁盘 IO）；
        # 缺失（NULL，老数据尚未回填）时才回退实时计算。
        new_color_vec = json_to_vector(new_item['color_vector']) if new_item['color_vector'] else None
        if new_color_vec is None and new_item['image_path']:
            try:
                new_color_vec = clip_service.get_color_histogram(new_item['image_path'])
            except Exception as e:
                logger.warning(f"物品 {new_item_id} 颜色直方图回退计算失败: {e}")
                new_color_vec = None

        # R2 维度预检：新物品向量维度 ≠ 库中目标向量维度 → 记 ERROR 并跳过。
        # 否则「切模型未重嵌入」会在后台被静默吞成「未找到高相似度匹配」，与真实无命中混淆。
        new_dim = None
        if new_img_vec is not None:
            new_dim = len(new_img_vec)
        elif new_text_vec is not None:
            new_dim = len(new_text_vec)
        if new_dim is not None:
            for target in target_items:
                mismatch_dim = None
                for col in ("image_vector", "text_vector"):
                    vec = json_to_vector(target[col]) if target[col] else None
                    if vec is not None and len(vec) != new_dim:
                        mismatch_dim = len(vec)
                        break
                if mismatch_dim is not None:
                    logger.error(
                        f"自动匹配跳过（物品 {new_item_id}）：向量维度不匹配"
                        f"（库中 {mismatch_dim} 维 / 当前模型 {new_dim} 维），"
                        "请先运行 scripts/reembed_all_vectors.py 重嵌入"
                    )
                    return

        matches = []
        for target in target_items:
            target_img_vec = json_to_vector(target['image_vector']) if target['image_vector'] else None
            target_text_vec = json_to_vector(target['text_vector']) if target['text_vector'] else None
            # 颜色特征：优先取库，缺失回退实时计算
            target_color_vec = json_to_vector(target['color_vector']) if target['color_vector'] else None
            if target_color_vec is None and target['image_path']:
                try:
                    target_color_vec = clip_service.get_color_histogram(target['image_path'])
                except Exception as e:
                    logger.warning(f"物品 {target['id']} 颜色直方图回退计算失败: {e}")
                    target_color_vec = None

            # 计算目标物品已发布天数（时间衰减）
            try:
                target_date = datetime.fromisoformat(str(target['created_at']).replace('Z', '+00:00'))
                days_old = max(0, (now - target_date).days)
            except Exception:
                days_old = 0

            similarity = clip_service.compute_weighted_similarity(
                new_img_vec, new_text_vec,
                target_img_vec, target_text_vec,
                cat1=new_item['category'] or '',
                cat2=target['category'] or '',
                loc1=new_item['location'] or '',
                loc2=target['location'] or '',
                days_old=days_old,
                color1=new_color_vec, color2=target_color_vec,
            )

            if similarity >= settings.MATCH_THRESHOLD_AUTO:
                matches.append({
                    'lost_item_id': new_item_id if item_type == 'lost' else target['id'],
                    'found_item_id': new_item_id if item_type == 'found' else target['id'],
                    'similarity': similarity,
                    'target_user_id': target['user_id'],
                    'target_title': target['title'],
                    'new_item_title': new_item['title'],
                })

        if not matches:
            logger.info(f"新物品 {new_item_id} 未找到高相似度匹配 (阈值 {settings.MATCH_THRESHOLD_AUTO})")
            return

        # 按相似度降序，只保留 Top-N
        matches.sort(key=lambda m: m['similarity'], reverse=True)
        if len(matches) > settings.MAX_AUTO_MATCH_NOTIFICATIONS:
            logger.info(
                f"新物品 {new_item_id} 匹配到 {len(matches)} 条，"
                f"超过上限 {settings.MAX_AUTO_MATCH_NOTIFICATIONS}，仅推送 Top {settings.MAX_AUTO_MATCH_NOTIFICATIONS}"
            )
            matches = matches[:settings.MAX_AUTO_MATCH_NOTIFICATIONS]

        logger.info(f"新物品 {new_item_id} 推送 {len(matches)} 条匹配通知")

        # 5. 批量插入匹配记录（事务）
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for match in matches:
                cursor.execute('''
                    INSERT INTO matches (lost_item_id, found_item_id, similarity_score)
                    VALUES (?, ?, ?)
                ''', (match['lost_item_id'], match['found_item_id'], match['similarity']))
            # 插入完成后自动提交

        # 6. 获取所有相关用户信息（用于双向通知）
        # 收集新物品发布者和所有匹配目标用户
        notified_user_ids = {new_item['user_id']} | {m['target_user_id'] for m in matches}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(notified_user_ids))
            cursor.execute(f'''
                SELECT id, username, email FROM users WHERE id IN ({placeholders})
            ''', list(notified_user_ids))
            users = {row['id']: dict(row) for row in cursor.fetchall()}

        # 7. 发送双向通知
        new_item_owner = users.get(new_item['user_id'])
        for match in matches:
            # --- 通知目标物品的拥有者（已有物品被匹配） ---
            try:
                target_title = f"[匹配通知] 您的物品 '{match['target_title']}' 有新匹配"
                target_content = f"与新发布的物品 '{match['new_item_title']}' 相似度 {match['similarity']:.2%}"
                target_link = f"/items/{new_item_id}"
                add_notification(match['target_user_id'], target_title, target_content, target_link)

                target_user = users.get(match['target_user_id'])
                if target_user and target_user.get('email') and match['similarity'] >= settings.MATCH_THRESHOLD_EMAIL:
                    send_match_notification(
                        email=target_user['email'],
                        username=target_user['username'],
                        item_title=match['target_title'],
                        similarity=match['similarity'],
                        link=f"{settings.BASE_URL}{target_link}"
                    )
            except Exception as e:
                logger.error(f"处理匹配通知失败 (目标用户 {match['target_user_id']}): {e}")

            # --- 通知新物品的发布者（自己的物品匹配到了已有物品） ---
            try:
                new_title = f"[匹配通知] 您新发布的 '{match['new_item_title']}' 找到匹配"
                new_content = f"与已有物品 '{match['target_title']}' 相似度 {match['similarity']:.2%}"
                # 链接到匹配到的目标物品（非自己的那个）
                if item_type == 'lost':
                    new_link = f"/items/{match['found_item_id']}"
                else:
                    new_link = f"/items/{match['lost_item_id']}"
                add_notification(new_item['user_id'], new_title, new_content, new_link)

                if new_item_owner and new_item_owner.get('email') and match['similarity'] >= settings.MATCH_THRESHOLD_EMAIL:
                    send_match_notification(
                        email=new_item_owner['email'],
                        username=new_item_owner['username'],
                        item_title=match['new_item_title'],
                        similarity=match['similarity'],
                        link=f"{settings.BASE_URL}{new_link}"
                    )
            except Exception as e:
                logger.error(f"处理匹配通知失败 (新物品发布者 {new_item['user_id']}): {e}")

        logger.info(f"已为物品 {new_item_id} 发送 {len(matches)} 条通知")

    except Exception as e:
        logger.error(f"自动匹配失败 (物品 {new_item_id}): {str(e)}", exc_info=True)