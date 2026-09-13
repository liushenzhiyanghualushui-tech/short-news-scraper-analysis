"""数据库初始化脚本

提供数据初始化功能
"""

def init_sources(db):
    """执行数据库初始化（插入初始数据）

    Args:
        db: DBHandler 实例
    """
    sources = [
        ('domestic', '新浪新闻', 'sina', None),
        ('domestic', '网易新闻', 'netease', None),
        ('domestic', '中新网', 'chinanews', None),
        # 新闻门户爬虫（归类为国内新闻）
        ('domestic', '腾讯新闻', 'tencent', None),
        ('domestic', '凤凰新闻', 'ifeng', None),
        ('domestic', '澎湃新闻', 'pengpai', None),
        ('domestic', '参考消息', 'cankaoxiaoxi', None),
        ('domestic', '新华网', 'xinhua', None),
    ]

    query = f"""
    INSERT INTO {db.get_table_name('sources')} (source_type, name, code, platform_id)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE name = VALUES(name)
    """
    try:
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                for s in sources:
                    cursor.execute(query, s)
            conn.commit()
        db.logger.info(f"已初始化 {len(sources)} 个来源")
    except Exception as e:
        db.logger.error(f"初始化来源失败: {e}")
        raise
