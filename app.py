"""
Flask Web 应用入口

新闻数据采集系统 - Web 管理平台
"""

import os
import logging
from flask import Flask, render_template
from flask_cors import CORS

from scrapers.config import load_config as load_scraper_config
from scrapers.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def create_app():
    """应用工厂函数"""
    setup_logging(load_scraper_config())
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')
    
    # 启用跨域支持（前后端分离开发需要）
    CORS(app)
    
    # 应用配置
    app.config['SECRET_KEY'] = os.urandom(24)
    app.config['JSON_SORT_KEYS'] = False
    
    # 注册蓝图
    from api.routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # 主页路由
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/dashboard')
    def dashboard():
        return render_template('index.html')
    
    @app.route('/news')
    def news():
        return render_template('index.html')
    
    @app.route('/logs')
    def logs():
        return render_template('index.html')
    
    # 404 错误处理
    @app.errorhandler(404)
    def not_found(error):
        return render_template('index.html'), 404
    
    # 500 错误处理
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"服务器错误: {error}")
        return {'error': '服务器内部错误'}, 500
    
    logger.info("Flask 应用初始化完成")
    return app


# 创建应用实例
app = create_app()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='新闻采集系统 Web 管理平台')
    parser.add_argument('--host', default='0.0.0.0', help='绑定地址')
    parser.add_argument('--port', type=int, default=5000, help='端口号')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    
    args = parser.parse_args()
    
    app.run(host=args.host, port=args.port, debug=args.debug)
