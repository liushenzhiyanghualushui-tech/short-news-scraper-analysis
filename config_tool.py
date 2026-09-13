"""
可视化配置启动工具
新闻数据采集系统 - 管理面板

功能：
1. 虚拟环境配置
2. 检查并安装依赖
3. 数据库配置
4. 服务器配置
5. 启动服务并打开网页
"""

import os
import sys
import subprocess
import threading
import webbrowser
import traceback
from datetime import datetime
from tkinter import *
from tkinter import ttk, messagebox
import tkinter as tk
import json


class ConfigTool:
    """配置工具主类"""

    def __init__(self, root):
        self.root = root
        self.root.title("新闻数据采集系统 - 配置工具")
        self.root.geometry("600x800")
        self.root.resizable(True, True)
        self.root.minsize(500, 700)

        # 当前状态
        self.server_process = None
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(self.project_root, "config.json")
        self.venv_path = os.path.join(self.project_root, ".venv")

        # 加载配置
        self.config = self.load_config()

        # 虚拟环境 Python 路径
        self.venv_python = self.get_venv_python()

        # 创建界面
        self.create_widgets()

        # 绑定鼠标滚轮滚动
        self.root.bind("<MouseWheel>", self.on_mousewheel)
        self.root.bind("<Up>", self.on_mousewheel)
        self.root.bind("<Down>", self.on_mousewheel)

        # 绑定关闭窗口事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 自动检查虚拟环境状态
        self.root.after(500, self.check_venv_status)

    def get_venv_python(self):
        """获取虚拟环境 Python 路径"""
        if sys.platform == "win32":
            python_path = os.path.join(self.venv_path, "Scripts", "python.exe")
        else:
            python_path = os.path.join(self.venv_path, "bin", "python")
        return python_path if os.path.exists(python_path) else None

    def validate_venv(self):
        """检查虚拟环境是否完整可用"""
        self.venv_python = self.get_venv_python()

        if not self.venv_python:
            return False, "未找到虚拟环境解释器"

        cfg_path = os.path.join(self.venv_path, "pyvenv.cfg")
        if not os.path.exists(cfg_path):
            return False, "缺少 pyvenv.cfg"

        return True, ""

    def is_in_venv(self):
        """检查是否在虚拟环境中运行"""
        return getattr(sys, 'real_prefix', None) is not None or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

    def load_config(self):
        """加载配置文件"""
        def deep_merge(target, src):
            if not isinstance(target, dict) or not isinstance(src, dict):
                return target
            for key, value in src.items():
                if isinstance(target.get(key), dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value
            return target

        default_config = {
            'database': {
                'host': 'localhost',
                'port': 3306,
                'username': 'root',
                'password': '',
                'name': 'news_scraper',
                'charset': 'utf8mb4',
                'table_prefix': 'scraper_'
            },
            'server': {
                'host': '0.0.0.0',
                'port': 5000
            },
            'venv': {
                'enabled': True
            },
            'hf': {
                'endpoint': 'https://hf-mirror.com',
                'model_id': 'bert-base-chinese',
                'output_dir': os.path.join('saved_models', 'pretrained', 'bert-base-chinese'),
                'timeout': 120,
                'force': False
            }
        }

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    deep_merge(default_config, saved_config)
            except:
                pass

        return default_config

    def save_config(self):
        """保存配置文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    def create_widgets(self):
        """创建界面组件"""

        # 标题区域
        title_frame = ttk.Frame(self.root)
        title_frame.pack(fill=X, padx=20, pady=15)

        ttk.Label(title_frame, text="新闻数据采集系统", font=('Microsoft YaHei', 16, 'bold')).pack()
        ttk.Label(title_frame, text="配置启动工具 v1.1 (支持虚拟环境)", foreground='#666').pack()

        # 主内容区域 (带滚动条)
        self.canvas = Canvas(self.root)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True, padx=(20, 0))

        self.scrollbar = ttk.Scrollbar(self.root, orient=VERTICAL, command=self.canvas.yview)
        self.scrollbar.pack(side=RIGHT, fill=Y)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        main_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=main_frame, anchor="nw")

        # 0. 虚拟环境配置区域
        venv_frame = ttk.LabelFrame(main_frame, text=" 0. 虚拟环境 ")
        venv_frame.pack(fill=X, pady=(0, 12), padx=20)

        venv_inner = ttk.Frame(venv_frame)
        venv_inner.pack(fill=X, padx=15, pady=12)

        self.venv_status = StringVar(value="未检测")
        ttk.Label(venv_inner, text="虚拟环境状态:").grid(row=0, column=0, sticky=W, pady=5)
        self.lbl_venv = ttk.Label(venv_inner, textvariable=self.venv_status, foreground='gray')
        self.lbl_venv.grid(row=0, column=1, sticky=E)

        # 虚拟环境路径显示
        self.lbl_venv_path = ttk.Label(venv_inner, text="", foreground='#888', font=('', 8))
        self.lbl_venv_path.grid(row=1, column=0, columnspan=2, sticky=W, pady=(0, 5))

        # 按钮行
        self.btn_create_venv = ttk.Button(venv_inner, text="创建虚拟环境", command=self.create_venv)
        self.btn_create_venv.grid(row=2, column=0, sticky=W, pady=8)

        self.btn_check_venv = ttk.Button(venv_inner, text="重新检测", command=self.check_venv_status)
        self.btn_check_venv.grid(row=2, column=1, sticky=E)

        venv_inner.columnconfigure(1, weight=1)

        # 使用虚拟环境复选框
        self.use_venv_var = BooleanVar(value=self.config.get('venv', {}).get('enabled', True))
        self.chk_use_venv = ttk.Checkbutton(venv_inner, text="启动服务时使用虚拟环境",
                                            variable=self.use_venv_var,
                                            command=self.on_use_venv_changed)
        self.chk_use_venv.grid(row=3, column=0, columnspan=2, sticky=W, pady=(8, 0))

        # 1. 依赖检查区域
        deps_frame = ttk.LabelFrame(main_frame, text=" 1. 依赖检查 ")
        deps_frame.pack(fill=X, pady=(0, 12), padx=20)

        deps_inner = ttk.Frame(deps_frame)
        deps_inner.pack(fill=X, padx=15, pady=12)

        self.deps_status = StringVar(value="未检查")
        ttk.Label(deps_inner, text="Python 依赖状态:").grid(row=0, column=0, sticky=W, pady=5)
        self.lbl_deps = ttk.Label(deps_inner, textvariable=self.deps_status, foreground='gray')
        self.lbl_deps.grid(row=0, column=1, sticky=E)

        ttk.Button(deps_inner, text="检查依赖", command=self.check_dependencies).grid(row=1, column=0, sticky=W, pady=8)
        self.btn_install = ttk.Button(deps_inner, text="安装依赖", command=self.install_dependencies, state=NORMAL)
        self.btn_install.grid(row=1, column=1, sticky=E)

        deps_inner.columnconfigure(1, weight=1)

        # 1.5 模型资源（Hugging Face）
        hf_frame = ttk.LabelFrame(main_frame, text=" 1.5 模型资源 (Hugging Face) ")
        hf_frame.pack(fill=X, pady=(0, 12), padx=20)

        hf_inner = ttk.Frame(hf_frame)
        hf_inner.pack(fill=X, padx=15, pady=12)

        hf_cfg = self.config.get('hf', {}) or {}
        self.hf_status = StringVar(value="未检查")
        ttk.Label(hf_inner, text="模型资源状态:").grid(row=0, column=0, sticky=W, pady=5)
        self.lbl_hf = ttk.Label(hf_inner, textvariable=self.hf_status, foreground='gray')
        self.lbl_hf.grid(row=0, column=1, sticky=E)

        self.lbl_hf_model = ttk.Label(hf_inner, text=f"模型: {hf_cfg.get('model_id', 'bert-base-chinese')}", foreground='#666', font=('', 8))
        self.lbl_hf_model.grid(row=1, column=0, columnspan=2, sticky=W, pady=(0, 2))

        self.lbl_hf_endpoint = ttk.Label(hf_inner, text=f"镜像: {hf_cfg.get('endpoint', 'https://hf-mirror.com')}", foreground='#666', font=('', 8))
        self.lbl_hf_endpoint.grid(row=2, column=0, columnspan=2, sticky=W, pady=(0, 2))

        self.lbl_hf_output = ttk.Label(hf_inner, text=f"输出: {hf_cfg.get('output_dir', os.path.join('saved_models', 'pretrained', 'bert-base-chinese'))}", foreground='#666', font=('', 8))
        self.lbl_hf_output.grid(row=3, column=0, columnspan=2, sticky=W, pady=(0, 6))

        self.hf_force_var = BooleanVar(value=bool(hf_cfg.get('force', False)))
        self.chk_hf_force = ttk.Checkbutton(
            hf_inner,
            text="强制重新下载",
            variable=self.hf_force_var,
            command=self.on_hf_force_changed
        )
        self.chk_hf_force.grid(row=4, column=0, columnspan=2, sticky=W, pady=(0, 6))

        ttk.Button(hf_inner, text="校验本地模型", command=self.check_hf_model).grid(row=5, column=0, sticky=W, pady=8)
        self.btn_hf_download = ttk.Button(hf_inner, text="下载 bert-base-chinese", command=self.download_hf_bert_assets)
        self.btn_hf_download.grid(row=5, column=1, sticky=E)

        hf_inner.columnconfigure(1, weight=1)

        # 2. 数据库配置
        db_frame = ttk.LabelFrame(main_frame, text=" 2. 数据库配置 ")
        db_frame.pack(fill=X, pady=(0, 12), padx=20)

        db_inner = ttk.Frame(db_frame)
        db_inner.pack(fill=X, padx=15, pady=12)

        # Host
        ttk.Label(db_inner, text="主机地址:").grid(row=0, column=0, sticky=W, pady=4)
        self.entry_db_host = ttk.Entry(db_inner)
        self.entry_db_host.insert(0, self.config['database']['host'])
        self.entry_db_host.grid(row=0, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Port
        ttk.Label(db_inner, text="端口:").grid(row=1, column=0, sticky=W, pady=4)
        self.entry_db_port = ttk.Entry(db_inner, width=10)
        self.entry_db_port.insert(0, str(self.config['database']['port']))
        self.entry_db_port.grid(row=1, column=1, sticky=W, pady=4, padx=(10, 0))

        # Username
        ttk.Label(db_inner, text="用户名:").grid(row=2, column=0, sticky=W, pady=4)
        self.entry_db_user = ttk.Entry(db_inner)
        self.entry_db_user.insert(0, self.config['database']['username'])
        self.entry_db_user.grid(row=2, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Password
        ttk.Label(db_inner, text="密码:").grid(row=3, column=0, sticky=W, pady=4)
        self.entry_db_pass = ttk.Entry(db_inner, show="*")
        self.entry_db_pass.insert(0, self.config['database']['password'])
        self.entry_db_pass.grid(row=3, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Database Name
        ttk.Label(db_inner, text="数据库名:").grid(row=4, column=0, sticky=W, pady=4)
        self.entry_db_name = ttk.Entry(db_inner)
        self.entry_db_name.insert(0, self.config['database']['name'])
        self.entry_db_name.grid(row=4, column=1, sticky=EW, pady=4, padx=(10, 0))

        # 测试连接按钮
        self.btn_test_db = ttk.Button(db_inner, text="测试连接", command=self.test_db_connection)
        self.btn_test_db.grid(row=5, column=0, sticky=W, pady=10)

        self.lbl_db_status = ttk.Label(db_inner, text="", foreground='gray')
        self.lbl_db_status.grid(row=5, column=1, sticky=E)

        # 数据库操作按钮
        db_ops_frame = ttk.Frame(db_inner)
        db_ops_frame.grid(row=6, column=0, columnspan=2, sticky=E, pady=(8, 0))

        self.btn_init_db = ttk.Button(db_ops_frame, text="初始化数据库", command=self.init_db)
        self.btn_init_db.pack(side=RIGHT, padx=(8, 0))

        self.btn_migrate_db = ttk.Button(db_ops_frame, text="迁移/更新数据", command=self.migrate_db)
        self.btn_migrate_db.pack(side=RIGHT, padx=(8, 0))

        self.btn_save_db = ttk.Button(db_ops_frame, text="保存数据库配置", command=self.save_db_config)
        self.btn_save_db.pack(side=RIGHT, padx=(8, 0))

        db_inner.columnconfigure(1, weight=1)

        # 3. 服务器配置
        server_frame = ttk.LabelFrame(main_frame, text=" 3. 服务器配置 ")
        server_frame.pack(fill=X, pady=(0, 12), padx=20)

        server_inner = ttk.Frame(server_frame)
        server_inner.pack(fill=X, padx=15, pady=12)

        ttk.Label(server_inner, text="绑定地址:").grid(row=0, column=0, sticky=W, pady=4)
        self.entry_server_host = ttk.Entry(server_inner)
        self.entry_server_host.insert(0, self.config['server']['host'])
        self.entry_server_host.grid(row=0, column=1, sticky=EW, pady=4, padx=(10, 0))

        ttk.Label(server_inner, text="端口号:").grid(row=1, column=0, sticky=W, pady=4)
        self.entry_server_port = ttk.Entry(server_inner, width=10)
        self.entry_server_port.insert(0, str(self.config['server']['port']))
        self.entry_server_port.grid(row=1, column=1, sticky=W, pady=4, padx=(10, 0))

        ttk.Label(server_inner, text="建议: 0.0.0.0", foreground='gray', font=('', 8)).grid(row=0, column=2, sticky=W, padx=(20, 0))
        ttk.Label(server_inner, text="默认: 5000", foreground='gray', font=('', 8)).grid(row=1, column=2, sticky=W, padx=(20, 0))

        server_inner.columnconfigure(1, weight=1)

        # 4. 控制区域
        control_frame = ttk.LabelFrame(main_frame, text=" 4. 服务控制 ")
        control_frame.pack(fill=X, pady=(0, 20), padx=20)

        control_inner = ttk.Frame(control_frame)
        control_inner.pack(fill=X, padx=15, pady=12)

        # 启动按钮
        self.btn_start = ttk.Button(control_inner, text="启动服务", command=self.start_server)
        self.btn_start.pack(side=LEFT, padx=(0, 8))

        # 停止按钮
        self.btn_stop = ttk.Button(control_inner, text="停止服务", command=self.stop_server, state=DISABLED)
        self.btn_stop.pack(side=LEFT, padx=(0, 8))

        # 进入网页按钮 (醒目样式)
        self.btn_browser = tk.Button(control_inner, text="进入网页", command=self.open_browser, 
                                     state=DISABLED, bg="#2196F3", fg="white", font=('Microsoft YaHei', 9, 'bold'),
                                     relief=FLAT, padx=10, pady=2)
        self.btn_browser.pack(side=LEFT, padx=(0, 8))

        # 保存配置按钮
        ttk.Button(control_inner, text="保存配置", command=self.save_all_config).pack(side=RIGHT)

        # 状态日志
        log_frame = ttk.Frame(control_inner)
        log_frame.pack(fill=X, pady=(12, 0))

        ttk.Label(log_frame, text="运行日志:").pack(anchor=W)

        self.log_text = Text(log_frame, height=8, font=('Consolas', 9), state=DISABLED)
        self.log_text.pack(fill=X, pady=(4, 0))

        control_inner.columnconfigure(0, weight=1)

    def log(self, message, level='INFO'):
        """添加日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        colors = {'INFO': '#333', 'SUCCESS': '#10b981', 'ERROR': '#ef4444', 'WARNING': '#f59e0b'}

        self.log_text.config(state=NORMAL)
        self.log_text.insert(END, f"[{timestamp}] [{level}] {message}\n")
        self.log_text.see(END)
        self.log_text.config(state=DISABLED)

    def log_from_thread(self, message, level='INFO'):
        """在后台线程中安全写日志"""
        self.root.after(0, lambda msg=message, lvl=level: self.log(msg, lvl))

    def format_exception(self, exc):
        """格式化异常信息，避免出现空字符串或 None"""
        msg = str(exc).strip()
        return msg if msg else repr(exc)

    def on_use_venv_changed(self):
        """虚拟环境使用选项改变"""
        self.config['venv'] = {'enabled': self.use_venv_var.get()}
        self.save_config()
        status = "启用" if self.use_venv_var.get() else "禁用"
        self.log(f"虚拟环境已{status}")

    def check_venv_status(self):
        """检查虚拟环境状态"""
        is_valid, reason = self.validate_venv()

        if is_valid:
            self.venv_status.set("✓ 已创建")
            self.lbl_venv.config(foreground='#10b981')
            self.lbl_venv_path.config(text=f"路径: {self.venv_path}")
            self.btn_create_venv.config(text="重建虚拟环境")
            self.log("虚拟环境检测成功", 'SUCCESS')
        elif os.path.isdir(self.venv_path):
            self.venv_status.set(f"⚠ 已损坏 ({reason})")
            self.lbl_venv.config(foreground='#ef4444')
            self.lbl_venv_path.config(text=f"路径: {self.venv_path}")
            self.btn_create_venv.config(text="重建虚拟环境")
            self.log(f"检测到虚拟环境损坏: {reason}，请点击“重建虚拟环境”", 'ERROR')
        else:
            self.venv_status.set("✗ 未创建")
            self.lbl_venv.config(foreground='#ef4444')
            self.lbl_venv_path.config(text="")
            self.btn_create_venv.config(text="创建虚拟环境")
            self.log("虚拟环境未创建，建议创建以隔离依赖")

    def create_venv(self):
        """创建虚拟环境"""
        self.log("正在创建虚拟环境...", 'WARNING')
        self.btn_create_venv.config(state=DISABLED)

        def create():
            try:
                # 如果虚拟环境已存在，先删除
                if os.path.exists(self.venv_path):
                    self.log_from_thread("删除现有虚拟环境...")
                    import shutil
                    import time
                    max_retries = 3
                    for i in range(max_retries):
                        try:
                            shutil.rmtree(self.venv_path)
                            break
                        except PermissionError:
                            if i < max_retries - 1:
                                self.log_from_thread(f"尝试 {i+1}/{max_retries}: 文件被锁定，等待重试...")
                                time.sleep(2)
                            else:
                                raise

                # 创建虚拟环境
                result = subprocess.run(
                    [sys.executable, '-m', 'venv', self.venv_path],
                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120
                )

                if result.returncode == 0:
                    is_valid, reason = self.validate_venv()
                    if not is_valid:
                        self.root.after(0, lambda: self.log(f"虚拟环境创建后校验失败: {reason}", 'ERROR'))
                        return
                    self.root.after(0, lambda: self.log("虚拟环境创建成功!", 'SUCCESS'))
                    self.root.after(0, lambda: self.check_venv_status())
                    self.root.after(0, lambda: self.log("正在安装依赖...", 'WARNING'))
                    self.root.after(0, lambda: self.install_dependencies())
                else:
                    self.root.after(0, lambda: self.log(f"创建失败: {result.stderr}", 'ERROR'))
            except Exception as e:
                err_msg = self.format_exception(e)
                self.root.after(0, lambda msg=err_msg: self.log(f"创建错误: {msg}", 'ERROR'))
            finally:
                self.root.after(0, lambda: self.btn_create_venv.config(state=NORMAL))

        threading.Thread(target=create, daemon=True).start()

    def get_python_executable(self):
        """获取要使用的 Python 解释器"""
        if self.use_venv_var.get():
            is_valid, reason = self.validate_venv()
            if is_valid:
                return self.venv_python
            self.log(f"虚拟环境不可用: {reason}。请先点击“重建虚拟环境”", 'ERROR')
            return None
        return sys.executable

    def check_dependencies(self):
        """检查依赖"""
        self.log("正在检查 Python 依赖...")
        self.btn_install.config(state=DISABLED)

        def check():
            try:
                import re
                python_exe = self.get_python_executable()
                if not python_exe:
                    self.root.after(0, lambda: self.deps_status.set("⚠ 虚拟环境不可用"))
                    self.root.after(0, lambda: self.lbl_deps.config(foreground='#ef4444'))
                    return
                
                script_dir = os.path.dirname(os.path.abspath(__file__))
                req_path = os.path.join(script_dir, 'requirements.txt')

                pkg_to_import = {
                    'flask-cors': 'flask_cors',
                    'pyyaml': 'yaml',
                    'beautifulsoup4': 'bs4',
                    'python-dateutil': 'dateutil',
                    'webdriver-manager': 'webdriver_manager',
                    'scikit-learn': 'sklearn',
                    'apscheduler': 'apscheduler',
                    'prometheus-client': 'prometheus_client',
                }

                modules = []
                if os.path.exists(req_path):
                    with open(req_path, 'r', encoding='utf-8') as f:
                        for raw in f:
                            line = raw.strip()
                            if not line or line.startswith('#'):
                                continue
                            line = line.split('#', 1)[0].strip()
                            if not line or line.startswith('-'):
                                continue
                            line = line.split(';', 1)[0].strip()
                            pkg = re.split(r'[<>=!~]', line, 1)[0].strip()
                            if not pkg:
                                continue
                            pkg_norm = pkg.lower().replace('_', '-')
                            modules.append(pkg_to_import.get(pkg_norm, pkg_norm.replace('-', '_')))
                else:
                    modules = [
                        'requests', 'bs4', 'lxml', 'pymysql', 'yaml', 'aiohttp', 'httpx', 'apscheduler', 'prometheus_client',
                        'flask', 'flask_cors',
                        'pandas', 'numpy', 'dateutil', 'chardet',
                        'scrapy', 'w3lib', 'fake_useragent',
                        'selenium', 'webdriver_manager',
                        'jieba',
                        'sklearn', 'tensorflow',
                        'matplotlib', 'seaborn',
                        'transformers', 'torch', 'accelerate', 'openai',
                        'colorlog',
                    ]

                seen = set()
                modules = [m for m in modules if m and not (m in seen or seen.add(m))]
                
                # 构建检查脚本（用 find_spec，避免导入 torch/tensorflow 等导致超时）
                check_script = f"""
import sys
import importlib.util

modules = {modules!r}
missing = []

for module in modules:
    try:
        spec = importlib.util.find_spec(module)
        if spec is None:
            missing.append(module)
    except Exception:
        missing.append(module)

if missing:
    print("\\n".join(missing))
    sys.exit(1)
sys.exit(0)
"""

                # 运行检查脚本
                result = subprocess.run(
                    [python_exe, '-c', check_script],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )

                if result.returncode == 0:
                    self.root.after(0, lambda: self.deps_status.set("✓ 已安装"))
                    self.root.after(0, lambda: self.lbl_deps.config(foreground='#10b981'))
                    self.root.after(0, lambda: self.log("依赖检查完成 - 所有包已安装", 'SUCCESS'))
                else:
                    missing_all = [x.strip() for x in (result.stdout or "").splitlines() if x.strip()]
                    if not missing_all:
                        missing_all = ["未知依赖"]
                    label = missing_all[0]
                    if len(missing_all) > 1:
                        label = f"{label} (+{len(missing_all) - 1})"
                    self.root.after(0, lambda txt=label: self.deps_status.set(f"✗ 缺少: {txt}"))
                    self.root.after(0, lambda: self.lbl_deps.config(foreground='#ef4444'))
                    msg = ", ".join(missing_all[:30])
                    if len(missing_all) > 30:
                        msg = f"{msg} ... (共{len(missing_all)}个)"
                    self.root.after(0, lambda txt=msg: self.log(f"缺少依赖: {txt}", 'ERROR'))

                # 检查驱动
                self.check_driver()

            except Exception as e:
                err_msg = self.format_exception(e)
                self.root.after(0, lambda msg=err_msg: self.log(f"检查失败: {msg}", 'ERROR'))
            finally:
                # 无论结果如何，都允许用户点击安装（可能是为了更新）
                self.root.after(0, lambda: self.btn_install.config(state=NORMAL))

        threading.Thread(target=check, daemon=True).start()

    def check_driver(self):
        """检查并修复 WebDriver 配置"""
        try:
            driver_name = "msedgedriver.exe"
            driver_path = os.path.join(self.project_root, driver_name)
            
            if os.path.exists(driver_path):
                self.root.after(0, lambda: self.log(f"发现驱动程序: {driver_name}", 'SUCCESS'))
                self.update_driver_config_if_needed(driver_name) # 使用相对路径以保持可移植性
            else:
                self.root.after(0, lambda: self.log(f"未找到驱动程序: {driver_name} (请将其放置在项目根目录)", 'WARNING'))
        except Exception as e:
            err_msg = self.format_exception(e)
            self.root.after(0, lambda msg=err_msg: self.log(f"驱动检查失败: {msg}", 'WARNING'))

    def update_driver_config_if_needed(self, driver_path):
        """更新配置文件中的驱动路径"""
        yaml_path = os.path.join(self.project_root, 'scrapers', 'config.yaml')
        if not os.path.exists(yaml_path):
            return

        try:
            # 简单读取检查，避免不必要的 yaml 解析错误
            with open(yaml_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 如果包含绝对路径的旧配置，则更新
            # 简单的字符串替换可能更安全，不破坏注释
            if 'c:\\Users\\' in content or 'C:\\Users\\' in content:
                import yaml
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                if not isinstance(config, dict):
                    return
                
                updated = False
                
                # 检查 xinhua
                if 'xinhua' in config and isinstance(config.get('xinhua'), dict) and 'crawl' in config['xinhua'] and isinstance(config['xinhua'].get('crawl'), dict):
                    current = config['xinhua']['crawl'].get('driver_path', '')
                    if current and (os.path.isabs(current) and not os.path.exists(current)):
                        config['xinhua']['crawl']['driver_path'] = driver_path
                        updated = True
                
                # 检查 cankaoxiaoxi
                if 'cankaoxiaoxi' in config:
                    current = config['cankaoxiaoxi'].get('driver_path', '')
                    if current and (os.path.isabs(current) and not os.path.exists(current)):
                        config['cankaoxiaoxi']['driver_path'] = driver_path
                        updated = True
                
                if updated:
                    with open(yaml_path, 'w', encoding='utf-8') as f:
                        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
                    self.root.after(0, lambda: self.log("已自动修正 config.yaml 中的驱动路径为相对路径", 'SUCCESS'))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"自动修复配置失败: {e}", 'WARNING'))

    def read_db_config_from_entries(self):
        db_port_raw = self.entry_db_port.get()
        return {
            'host': self.entry_db_host.get().strip(),
            'port': int(db_port_raw),
            'username': self.entry_db_user.get().strip(),
            'password': self.entry_db_pass.get(),
            'name': self.entry_db_name.get().strip(),
            'charset': self.config.get('database', {}).get('charset', 'utf8mb4'),
            'table_prefix': self.config.get('database', {}).get('table_prefix', 'scraper_'),
        }

    def save_db_config(self):
        """保存数据库配置"""
        try:
            self.config['database'] = self.read_db_config_from_entries()
        except Exception as e:
            err_msg = self.format_exception(e)
            self.log(f"保存数据库配置失败: {err_msg}", 'ERROR')
            messagebox.showerror("错误", f"保存数据库配置失败：{err_msg}")
            return

        try:
            self.save_config()
            self.update_yaml_config(update_password=True)
            self.log("数据库配置已保存!", 'SUCCESS')
            messagebox.showinfo("成功", "数据库配置已保存!\n\n提示：修改数据库配置后需要重启服务生效。")
        except Exception as e:
            err_msg = self.format_exception(e)
            self.log(f"保存数据库配置失败: {err_msg}", 'ERROR')
            messagebox.showerror("错误", f"保存数据库配置失败：{err_msg}")

    def install_dependencies(self):
        """安装依赖"""
        self.log("正在安装依赖，请稍候...", 'WARNING')
        self.btn_install.config(state=DISABLED)

        def install():
            try:
                python_exe = self.get_python_executable()
                if not python_exe:
                    return
                
                # 获取脚本所在目录
                script_dir = os.path.dirname(os.path.abspath(__file__))
                req_path = os.path.join(script_dir, 'requirements.txt')
                
                if not os.path.exists(req_path):
                     self.root.after(0, lambda: self.log(f"错误: 未找到 requirements.txt 文件\n路径: {req_path}", 'ERROR'))
                     return

                self.log_from_thread(f"使用 Python: {python_exe}")
                self.log_from_thread(f"安装依赖文件: {req_path}")

                # 1. 升级 pip
                self.root.after(0, lambda: self.log("正在升级 pip..."))
                pip_upgrade = subprocess.run(
                    [python_exe, '-m', 'pip', 'install', '--upgrade', 'pip'],
                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120,
                    cwd=script_dir
                )

                pip_upgrade_error = (pip_upgrade.stderr or pip_upgrade.stdout or "").strip()
                if pip_upgrade.returncode != 0 and "No pyvenv.cfg file" in pip_upgrade_error:
                    self.root.after(0, lambda: self.log("检测到虚拟环境损坏（缺少 pyvenv.cfg），请先点击“重建虚拟环境”", 'ERROR'))
                    self.root.after(0, lambda: self.check_venv_status())
                    return
                if pip_upgrade.returncode != 0:
                    self.root.after(0, lambda err=pip_upgrade_error: self.log(f"pip 升级失败，继续安装依赖: {err[:300] or '未知错误'}", 'WARNING'))

                # 2. 安装依赖
                self.root.after(0, lambda: self.log("正在安装库文件 (含大型ML库，可能需要较长时间)..."))
                result = subprocess.run(
                    [python_exe, '-m', 'pip', 'install', '-r', 'requirements.txt',
                     '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple',
                     '--trusted-host', 'pypi.tuna.tsinghua.edu.cn'],
                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3600,  # 大型ML包需要更长时间
                    cwd=script_dir
                )

                if result.returncode == 0:
                    self.root.after(0, lambda: self.deps_status.set("✓ 安装成功"))
                    self.root.after(0, lambda: self.lbl_deps.config(foreground='#10b981'))
                    self.root.after(0, lambda: self.log("依赖安装成功!", 'SUCCESS'))
                else:
                    error_output = (result.stderr or result.stdout or "").strip()
                    if "No pyvenv.cfg file" in error_output:
                        self.root.after(0, lambda: self.log("检测到虚拟环境损坏（缺少 pyvenv.cfg），请先点击“重建虚拟环境”", 'ERROR'))
                        self.root.after(0, lambda: self.check_venv_status())
                        return
                    self.root.after(0, lambda err=error_output: self.log(f"安装失败: {(err or '未知错误')[:500]}", 'ERROR'))
            except Exception as e:
                err_msg = self.format_exception(e)
                tb_last = traceback.format_exc().strip().splitlines()[-1] if traceback.format_exc().strip() else ""
                if tb_last:
                    err_msg = f"{err_msg} | {tb_last}"
                self.root.after(0, lambda msg=err_msg: self.log(f"安装错误: {msg}", 'ERROR'))
            finally:
                self.root.after(0, lambda: self.btn_install.config(state=NORMAL))

        threading.Thread(target=install, daemon=True).start()

    def on_hf_force_changed(self):
        hf_cfg = self.config.get('hf', {}) or {}
        hf_cfg['force'] = bool(self.hf_force_var.get())
        self.config['hf'] = hf_cfg
        self.save_config()

    def get_hf_settings(self):
        hf_cfg = self.config.get('hf', {}) or {}
        model_id = str(hf_cfg.get('model_id', 'bert-base-chinese')).strip() or 'bert-base-chinese'
        endpoint = str(hf_cfg.get('endpoint', 'https://hf-mirror.com')).strip() or 'https://hf-mirror.com'
        output_dir = hf_cfg.get('output_dir', os.path.join('saved_models', 'pretrained', model_id))
        timeout = int(hf_cfg.get('timeout', 120) or 120)
        force = bool(hf_cfg.get('force', False))

        if os.path.isabs(str(output_dir)):
            output_dir_abs = str(output_dir)
            output_dir_rel = os.path.relpath(output_dir_abs, self.project_root)
        else:
            output_dir_rel = os.path.normpath(str(output_dir))
            output_dir_abs = os.path.normpath(os.path.join(self.project_root, output_dir_rel))

        return {
            'model_id': model_id,
            'endpoint': endpoint,
            'output_dir_abs': output_dir_abs,
            'output_dir_rel': output_dir_rel,
            'timeout': timeout,
            'force': force,
        }

    def validate_local_hf_model(self, model_dir: str):
        required_files = ['config.json']
        tokenizer_files = ['vocab.txt', 'tokenizer.json']
        weight_files = ['model.safetensors', 'pytorch_model.bin']

        missing = [name for name in required_files if not os.path.exists(os.path.join(model_dir, name))]
        if missing:
            return False, f"缺少必要文件: {', '.join(missing)}"

        if not any(os.path.exists(os.path.join(model_dir, name)) for name in tokenizer_files):
            return False, '缺少分词器文件 vocab.txt 或 tokenizer.json'

        if not any(os.path.exists(os.path.join(model_dir, name)) for name in weight_files):
            return False, '缺少模型权重文件 model.safetensors 或 pytorch_model.bin'

        return True, '模型文件完整'

    def check_hf_model(self):
        settings = self.get_hf_settings()
        model_dir = settings['output_dir_abs']
        ok, message = self.validate_local_hf_model(model_dir)
        if ok:
            self.hf_status.set("✓ 已就绪")
            self.lbl_hf.config(foreground='#10b981')
            self.log(f"Hugging Face 模型已可用: {settings['output_dir_rel']}", 'SUCCESS')
            self.log(message, 'SUCCESS')
        else:
            self.hf_status.set("✗ 未就绪")
            self.lbl_hf.config(foreground='#ef4444')
            self.log(f"Hugging Face 模型未就绪: {settings['output_dir_rel']}", 'WARNING')
            self.log(message, 'WARNING')

    def update_yaml_nlp_embedding_model(self, local_path_rel: str):
        yaml_path = os.path.join(self.project_root, 'scrapers', 'config.yaml')
        if not os.path.exists(yaml_path):
            self.log(f"未找到 config.yaml: {yaml_path}", 'WARNING')
            return

        try:
            import yaml
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                config = {}
            if not isinstance(config.get('nlp'), dict):
                config['nlp'] = {}
            config['nlp']['embedding_model'] = local_path_rel

            with open(yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False)
            self.log(f"已同步更新 config.yaml: nlp.embedding_model = {local_path_rel}", 'SUCCESS')
        except Exception as e:
            self.log(f"更新 config.yaml 失败: {e}", 'WARNING')

    def download_hf_bert_assets(self):
        settings = self.get_hf_settings()
        python_exe = self.get_python_executable()
        if not python_exe:
            return

        self.log("正在下载 Hugging Face 模型资源...", 'WARNING')
        self.btn_hf_download.config(state=DISABLED)

        def run():
            try:
                os.makedirs(settings['output_dir_abs'], exist_ok=True)
                ok, _ = self.validate_local_hf_model(settings['output_dir_abs'])
                if ok and not settings['force']:
                    self.root.after(0, self.check_hf_model)
                    return

                script_path = os.path.join(self.project_root, 'scripts', 'download_bert_assets.py')
                if not os.path.exists(script_path):
                    self.root.after(0, lambda: self.log(f"未找到下载脚本: {script_path}", 'ERROR'))
                    return

                cmd = [
                    python_exe,
                    script_path,
                    '--model-id', settings['model_id'],
                    '--output-dir', settings['output_dir_abs'],
                    '--timeout', str(settings['timeout']),
                ]
                if settings['force']:
                    cmd.append('--force')

                env = os.environ.copy()
                env['HF_ENDPOINT'] = settings['endpoint']
                env.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
                env.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
                env['HF_HUB_DOWNLOAD_TIMEOUT'] = str(settings['timeout'])

                self.log_from_thread(f"HF_ENDPOINT: {settings['endpoint']}")
                self.log_from_thread(f"输出目录: {settings['output_dir_rel']}")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=max(300, int(settings['timeout']) * 10),
                    cwd=self.project_root,
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )

                std = (result.stdout or '').strip()
                err = (result.stderr or '').strip()
                if std:
                    for line in std.splitlines()[:80]:
                        self.log_from_thread(line.strip())
                if err:
                    self.log_from_thread(err[:800], 'WARNING')

                if result.returncode != 0:
                    self.root.after(0, lambda: self.log("模型下载失败，请检查网络/镜像或先安装依赖。", 'ERROR'))
                    return

                ok, message = self.validate_local_hf_model(settings['output_dir_abs'])
                if not ok:
                    self.root.after(0, lambda msg=message: self.log(f"下载后校验失败: {msg}", 'ERROR'))
                    return

                self.update_yaml_nlp_embedding_model(settings['output_dir_rel'])
                self.root.after(0, self.check_hf_model)
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self.log("模型下载超时，可在 config.json 的 hf.timeout 调大后重试。", 'ERROR'))
            except Exception as e:
                err_msg = self.format_exception(e)
                self.root.after(0, lambda msg=err_msg: self.log(f"模型下载错误: {msg}", 'ERROR'))
            finally:
                self.root.after(0, lambda: self.btn_hf_download.config(state=NORMAL))

        threading.Thread(target=run, daemon=True).start()

    def test_db_connection(self):
        """测试数据库连接"""
        self.log("正在测试数据库连接...")
        self.btn_test_db.config(state=DISABLED)

        def test():
            try:
                import pymysql
                conn = pymysql.connect(
                    host=self.entry_db_host.get(),
                    port=int(self.entry_db_port.get()),
                    user=self.entry_db_user.get(),
                    password=self.entry_db_pass.get(),
                    database=self.entry_db_name.get(),
                    autocommit=True,
                    connect_timeout=5
                )
                conn.close()
                self.root.after(0, lambda: self.lbl_db_status.config(text="✓ 连接成功"))
                self.root.after(0, lambda: self.lbl_db_status.config(foreground='#10b981'))
                self.root.after(0, lambda: self.log("数据库连接成功!", 'SUCCESS'))
            except Exception as e:
                error_msg = str(e)[:25]
                self.root.after(0, lambda msg=error_msg: self.lbl_db_status.config(text=f"✗ {msg}..."))
                self.root.after(0, lambda msg=str(e): self.lbl_db_status.config(foreground='#ef4444'))
                self.root.after(0, lambda msg=str(e): self.log(f"数据库连接失败: {msg}", 'ERROR'))
            finally:
                self.root.after(0, lambda: self.btn_test_db.config(state=NORMAL))

        threading.Thread(target=test, daemon=True).start()

    def execute_sql_file(self, db, file_path):
        """执行 SQL 文件"""
        if not os.path.exists(file_path):
            self.root.after(0, lambda: self.log(f"SQL文件不存在: {file_path}", 'WARNING'))
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            statements = sql_content.split(';')
            with db.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    for statement in statements:
                        if statement.strip():
                            try:
                                cursor.execute(statement)
                            except Exception as e:
                                # 忽略部分错误，如表已存在
                                pass
                conn.commit()
            self.root.after(0, lambda: self.log(f"已执行SQL脚本: {os.path.basename(file_path)}", 'SUCCESS'))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"执行SQL脚本失败: {str(e)}", 'ERROR'))

    def init_db(self):
        """初始化数据库"""
        self.log("正在初始化数据库 (先删除旧库，再创建新库)...", 'WARNING')
        self.btn_init_db.config(state=DISABLED)

        def init():
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import pymysql
                from scrapers.db import DBHandler
                from scrapers.init import init_sources

                # 获取配置
                db_host = self.entry_db_host.get()
                db_port = int(self.entry_db_port.get())
                db_user = self.entry_db_user.get()
                db_pass = self.entry_db_pass.get()
                db_name = self.entry_db_name.get()

                # 1. 先连接服务器（不指定数据库），删除并重建数据库
                try:
                    conn = pymysql.connect(
                        host=db_host,
                        port=db_port,
                        user=db_user,
                        password=db_pass,
                        connect_timeout=5
                    )
                    with conn.cursor() as cursor:
                        # 删除并创建数据库
                        cursor.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
                        self.root.after(0, lambda: self.log(f"已删除旧数据库: {db_name}"))
                        
                        cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                        self.root.after(0, lambda: self.log(f"已创建新数据库: {db_name}", 'SUCCESS'))
                    conn.close()
                except Exception as db_err:
                    err_msg = str(db_err)
                    self.root.after(0, lambda msg=err_msg: self.log(f"数据库操作失败: {msg}", 'ERROR'))
                    raise

                # 2. 连接数据库并初始化表结构
                db_config = {
                    'host': db_host,
                    'port': db_port,
                    'username': db_user,
                    'password': db_pass,
                    'name': db_name,
                    'charset': 'utf8mb4',
                    'table_prefix': 'scraper_'
                }
                db = DBHandler(db_config)

                if not db.get_connection():
                    self.root.after(0, lambda: self.log("数据库连接失败，请检查配置", 'ERROR'))
                    return

                # 初始化表结构
                if db.init_database():
                    self.root.after(0, lambda: self.log("数据库表结构初始化成功", 'SUCCESS'))
                else:
                    self.root.after(0, lambda: self.log("数据库表结构初始化失败", 'ERROR'))
                    return

                # 执行新华网初始化脚本
                self.execute_sql_file(db, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scrapers', 'xinhua_init.sql'))

                # 初始化来源数据
                init_sources(db)
                self.root.after(0, lambda: self.log("数据库初始化完成!", 'SUCCESS'))

            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self.log(f"初始化错误: {msg}", 'ERROR'))
            finally:
                self.root.after(0, lambda: self.btn_init_db.config(state=NORMAL))

        threading.Thread(target=init, daemon=True).start()

    def migrate_db(self):
        """迁移/更新数据库"""
        self.log("正在执行数据迁移...", 'WARNING')
        self.btn_migrate_db.config(state=DISABLED)

        def migrate():
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import pymysql
                from scrapers.db import DBHandler
                from scrapers.init import init_sources

                # 获取配置
                db_host = self.entry_db_host.get()
                db_port = int(self.entry_db_port.get())
                db_user = self.entry_db_user.get()
                db_pass = self.entry_db_pass.get()
                db_name = self.entry_db_name.get()

                # 1. 先确保数据库存在
                try:
                    conn = pymysql.connect(
                        host=db_host,
                        port=db_port,
                        user=db_user,
                        password=db_pass,
                        connect_timeout=5
                    )
                    with conn.cursor() as cursor:
                        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    conn.close()
                except Exception as db_err:
                    self.root.after(0, lambda: self.log(f"检查数据库失败: {str(db_err)}", 'ERROR'))
                    raise

                # 2. 连接并更新
                db_config = {
                    'host': db_host,
                    'port': db_port,
                    'username': db_user,
                    'password': db_pass,
                    'name': db_name,
                    'charset': 'utf8mb4',
                    'table_prefix': 'scraper_'
                }
                db = DBHandler(db_config)

                if not db.get_connection():
                    self.root.after(0, lambda: self.log("数据库连接失败，请检查配置", 'ERROR'))
                    return

                # 确保表存在
                if db.init_database():
                    self.root.after(0, lambda: self.log("数据库表结构检查完成", 'SUCCESS'))

                # 执行新华网初始化脚本
                self.execute_sql_file(db, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scrapers', 'xinhua_init.sql'))

                # 重新初始化来源数据（包含更新）
                init_sources(db)
                self.root.after(0, lambda: self.log("数据迁移/更新完成!", 'SUCCESS'))

            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self.log(f"迁移错误: {msg}", 'ERROR'))
            finally:
                self.root.after(0, lambda: self.btn_migrate_db.config(state=NORMAL))

        threading.Thread(target=migrate, daemon=True).start()

    def save_all_config(self):
        """保存所有配置"""
        try:
            self.config['database'] = self.read_db_config_from_entries()
            self.config['server']['host'] = self.entry_server_host.get().strip()
            self.config['server']['port'] = int(self.entry_server_port.get())
            self.config['venv'] = {'enabled': self.use_venv_var.get()}
        except Exception as e:
            err_msg = self.format_exception(e)
            self.log(f"保存配置失败: {err_msg}", 'ERROR')
            messagebox.showerror("错误", f"保存配置失败：{err_msg}")
            return

        self.save_config()
        self.update_yaml_config(update_password=False)
        self.log("配置已保存!", 'SUCCESS')
        messagebox.showinfo("成功", "配置已保存!\n\n提示：修改数据库配置后需要重启服务生效。")

    def update_yaml_config(self, update_password: bool = True):
        """更新 config.yaml 文件"""
        yaml_path = os.path.join(self.project_root, 'scrapers', 'config.yaml')
        if not os.path.exists(yaml_path):
            self.log(f"未找到 config.yaml: {yaml_path}", 'WARNING')
            return

        try:
            import yaml
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                config = {}
            if not isinstance(config.get('database'), dict):
                config['database'] = {}

            config['database']['host'] = self.entry_db_host.get().strip()
            config['database']['port'] = int(self.entry_db_port.get())
            config['database']['username'] = self.entry_db_user.get().strip()
            password = self.entry_db_pass.get()
            if update_password:
                config['database']['password'] = password
            else:
                if password:
                    config['database']['password'] = password
            config['database']['name'] = self.entry_db_name.get().strip()

            with open(yaml_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False)
            self.log("已同步更新 config.yaml")
        except Exception as e:
            self.log(f"更新 config.yaml 失败: {e}", 'WARNING')

    def start_server(self):
        """启动服务器"""
        host = self.entry_server_host.get()
        port = self.entry_server_port.get()
        python_exe = self.get_python_executable()
        if not python_exe:
            return

        venv_note = " (虚拟环境)" if self.venv_python and self.use_venv_var.get() else ""
        self.log(f"正在启动服务 {host}:{port}{venv_note}...")

        # 获取当前脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))

        def run():
            try:
                cmd = [python_exe, 'app.py', '--host', host, '--port', port]
                env = os.environ.copy()
                env.setdefault('PYTHONUTF8', '1')
                env.setdefault('PYTHONIOENCODING', 'utf-8')
                self.server_process = subprocess.Popen(
                    cmd,
                    cwd=script_dir,  # 在正确的目录下执行
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    env=env,
                    bufsize=1
                )
                for line in iter(self.server_process.stdout.readline, ''):
                    if not line: break
                    self.root.after(0, lambda l=line: self.log(l.strip()))
            except Exception as e:
                err_msg = self.format_exception(e)
                self.root.after(0, lambda msg=err_msg: self.log(f"启动失败: {msg}", 'ERROR'))

        threading.Thread(target=run, daemon=True).start()
        self.btn_start.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)
        self.btn_browser.config(state=NORMAL)
        
        # 3秒后自动打开浏览器
        self.root.after(3000, lambda: self.open_browser())
        self.root.after(3000, lambda: self.log("服务已启动，正在打开浏览器...", 'SUCCESS'))

    def stop_server(self):
        """停止服务器"""
        if self.server_process:
            self.server_process.terminate()
            self.server_process = None
            self.log("服务已停止", 'WARNING')
        self.btn_start.config(state=NORMAL)
        self.btn_stop.config(state=DISABLED)
        self.btn_browser.config(state=DISABLED)

    def on_mousewheel(self, event):
        """鼠标滚轮滚动事件"""
        if sys.platform == 'win32':
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        else:
            if event.delta < 0:
                self.canvas.yview_scroll(1, "units")
            elif event.delta > 0:
                self.canvas.yview_scroll(-1, "units")

    def open_browser(self):
        """打开浏览器"""
        host = self.entry_server_host.get()
        port = self.entry_server_port.get()
        url = f"http://{host}:{port}"
        self.log(f"正在打开浏览器: {url}")
        webbrowser.open(url)

    def on_close(self):
        """关闭窗口"""
        if self.server_process:
            if messagebox.askyesno("确认", "服务正在运行，是否停止服务并退出？"):
                self.stop_server()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    root = Tk()
    app = ConfigTool(root)
    root.mainloop()


if __name__ == '__main__':
    main()
