"""简单的数据库验证脚本"""

import pymysql
import yaml
import os

# 加载配置
project_root = os.path.dirname(os.path.dirname(__file__))
config_path = os.path.join(project_root, 'scrapers', 'config.yaml')

with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

db_config = config.get('database', {})

# 表前缀（默认空，表名不带前缀）
table_prefix = db_config.get('table_prefix', '')

print("=" * 50)
print("数据库验证工具")
print("=" * 50)
print(f"数据库: {db_config.get('name')}")
print(f"主机: {db_config.get('host')}")
print(f"端口: {db_config.get('port')}")
print(f"表前缀: '{table_prefix}'")
print("=" * 50)

try:
    conn = pymysql.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 3306),
        user=db_config.get('username', 'root'),
        password=db_config.get('password', ''),
        database=db_config.get('name', 'news_scraper'),
        charset=db_config.get('charset', 'utf8mb4')
    )

    with conn.cursor() as cursor:
        # 1. 验证 category 列
        cursor.execute(f'SHOW COLUMNS FROM {table_prefix}raw_articles LIKE "category"')
        result = cursor.fetchone()
        if result:
            print('[OK] category 列存在')
        else:
            print('[ERROR] category 列不存在')

        # 2. 检查记录数
        cursor.execute(f'SELECT COUNT(*) FROM {table_prefix}raw_articles')
        count = cursor.fetchone()[0]
        print(f'\n数据库总记录数: {count}')

        # 3. 检查带标签的记录
        cursor.execute(f'''
        SELECT COUNT(*) FROM {table_prefix}raw_articles 
        WHERE category IS NOT NULL AND category != ""
        ''')
        labeled_count = cursor.fetchone()[0]
        print(f'带分类标签的记录: {labeled_count}')

        # 4. 显示分类分布
        if labeled_count > 0:
            cursor.execute(f'''
            SELECT category, COUNT(*) as count 
            FROM {table_prefix}raw_articles 
            WHERE category IS NOT NULL AND category != "" 
            GROUP BY category
            ''')
            categories = cursor.fetchall()
            print('\n分类分布:')
            for cat in categories:
                print(f'  {cat[0]}: {cat[1]} 条')
        else:
            print('\n[WARNING] 没有带分类标签的数据')

    conn.close()
    print('\n' + '=' * 50)
    print('验证完成!')
    print('=' * 50)

except Exception as e:
    print(f'\n[ERROR] 错误: {e}')
