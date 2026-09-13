"""
数据清洗模块

提供新闻数据的清洗与预处理功能，包括：
1. 结构化数据处理（去重、缺失值填充、格式统一）
2. 文本预处理（中文分词、词性标注、停用词处理）
3. 特征基础准备

技术栈：Pandas, Numpy, Jieba, NLTK
"""

import re
import os
import sys
import jieba
import jieba.posseg as pseg
import jieba.analyse
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Set
from datetime import datetime
from collections import Counter
import logging

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# 尝试导入 load_config，如果失败则尝试相对导入
try:
    from scrapers.config import load_config
except ImportError:
    try:
        from config import load_config
    except ImportError:
        load_config = None

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('data_cleaner')


class DataCleaner:
    """数据清洗主类"""
    
    def __init__(self, stopwords_file: str = None):
        """
        初始化数据清洗器
        
        Args:
            stopwords_file: 停用词文件路径，默认使用内置停用词
        """
        self.stopwords = self._load_default_stopwords()
        
        # 加载自定义停用词
        if stopwords_file and os.path.exists(stopwords_file):
            self.load_stopwords(stopwords_file)
        
        # 词性过滤 - 保留有意义的词性
        self.allowed_pos = {
            'n', 'nr', 'ns', 'nt', 'nz',  # 名词
            'vn', 'vd',  # 动词
            'adj', 'ad',  # 形容词
            'an',  # 名形词
            'eng',  # 英文
        }
        
        # 新闻分类类别
        self.news_categories = [
            '政治', '经济', '体育', '娱乐', '科技', '教育',
            '军事', '国际', '社会', '文化', '财经', '汽车', '房产', '游戏'
        ]
        
        # 自动打标规则
        self.auto_label_rules = {
            '政治': ['国务院', '习近平', '会议', '政策', '外交部', '改革', '政府', '国家', '党中央'],
            '经济': ['股市', '基金', '银行', '增长', 'GDP', '市场', '投资', '金融', '证券', '经济'],
            '体育': ['比赛', '冠军', '球队', '赢', '输', 'NBA', '足球', '篮球', '奥运会', '体育'],
            '娱乐': ['明星', '电影', '电视剧', '演员', '演唱会', '综艺', '票房', '绯闻', '娱乐'],
            '科技': ['AI', '华为', '芯片', '互联网', '5G', '软件', '人工智能', '科技', '发布会'],
            '教育': ['学校', '考试', '学生', '大学', '教育部', '招生', '高考', '教育'],
            '军事': ['军队', '武器', '导弹', '战机', '演习', '军演', '国防', '军事'],
            '国际': ['美国', '欧洲', '俄乌', '战争', '国际', '总统', '联合国', '外交'],
            '社会': ['事故', '案件', '警方', '救援', '民生', '社区', '交通', '社会'],
            '文化': ['艺术', '博物馆', '历史', '文物', '展览', '文化', '非遗'],
            '财经': ['财经', '理财', '保险', '税务', '财政', '上市'],
            '汽车': ['汽车', '新车', '试驾', '车型', '销量', '车展'],
            '房产': ['房价', '楼市', '房产', '置业', '户型', '楼盘'],
            '游戏': ['游戏', '电竞', '手游', '网游', '攻略', '版本']
        }
    
    def auto_label(self, text: str) -> Optional[str]:
        """
        自动为文本打标
        
        Args:
            text: 输入文本
            
        Returns:
            分类标签 (如果没有匹配则返回 None)
        """
        if not text:
            return None
            
        scores = {}
        for category, keywords in self.auto_label_rules.items():
            count = 0
            for keyword in keywords:
                if keyword in text:
                    count += 1
            
            if count > 0:
                scores[category] = count
        
        if not scores:
            return None
            
        # 返回命中数最多的分类
        return max(scores.items(), key=lambda x: x[1])[0]

    def _load_default_stopwords(self) -> Set[str]:
        """加载默认停用词"""
        # 常用中文停用词
        stopwords = set([
            '的', '是', '了', '在', '和', '有', '就', '不', '这', '也', '都',
            '被', '与', '着', '为', '到', '把', '从', '向', '又', '要', '会',
            '能', '可', '对', '而', '但', '或', '而且', '因为', '所以',
            '如果', '那么', '而且', '或者', '虽然', '但是', '然而',
            '一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
            '我', '你', '他', '她', '它', '我们', '你们', '他们', '它们',
            '这个', '那个', '哪个', '什么', '怎么', '怎样', '如何',
            '啊', '吧', '呢', '吗', '哦', '嗯', '哈', '呀', '哇', '嘛',
            '说', '说', '说', '说',  # 重复的动词
            '表示', '认为', '指出', '报道', '介绍', '表示',
            '记者', '新华社', '人民日报', '央视新闻', '中新社',
            '日', '月', '年', '时', '分', '秒',
            '今天', '昨天', '明天', '后天', '日前', '近日',
            '月日', '年日', '目前', '当前', '现在', '近年来',
            '方面', '问题', '情况', '工作', '发展', '建设',
            '通过', '进行', '完成', '实现', '开展', '加强',
            '相关', '各种', '其他', '另外', '此外', '同时',
            '其中', '包括', '除了', '以及', '及其',
            '约', '大约', '大概', '可能', '应该', '必须',
            '需要', '希望', '可以', '能够', '不得不',
            '第', '多', '全', '各', '本', '该', '此', '其',
            '上', '下', '中', '内', '外', '前', '后', '左', '右',
            '一次', '一些', '一种', '一样', '一起', '一同', '一共',
            '已', '已经', '曾经', '早已', '早已', '向来',
            '将', '将要', '即将', '将要', '马上', '立刻', '立即',
            '还', '再', '又', '也', '都', '已经',
            '比', '像', '跟', '似', '如', '若', '假如',
            '按', '按照', '根据', '依据', '基于', '遵照',
            '之', '于', '对于', '关于', '至于', '由于',
            '即', '就是', '则是', '则是', '那就是',
            '无论', '不论', '不管', '不顾', '尽管',
            '只有', '除非', '即便', '即使', '只要',
            '越来越', '越来', '稍稍', '略微', '稍微',
            '很', '非常', '十分', '特别', '极其', '相当',
            '最', '更', '还', '更加', '格外', '尤其',
            '的确', '确实', '实在', '反正', '反正',
            '到底', '究竟', '难道', '简直', '竟然',
            '忽然', '突然', '猛然', '陡然', '骤然',
            '渐渐', '逐渐', '逐步', '慢慢', '日益',
            '仍旧', '仍然', '还是', '依然', '仍旧',
            '特意', '故意', '一定', '必须', '必定',
        ])
        return stopwords
    
    def load_stopwords(self, filepath: str):
        """加载自定义停用词文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    word = line.strip()
                    if word:
                        self.stopwords.add(word)
            logger.info(f"加载停用词 {len(self.stopwords)} 个")
        except Exception as e:
            logger.error(f"加载停用词文件失败: {e}")
    
    def add_stopwords(self, words: List[str]):
        """添加停用词"""
        self.stopwords.update(words)
    
    def remove_stopwords(self, words: List[str]) -> List[str]:
        """去除停用词"""
        return [w for w in words if w not in self.stopwords and len(w) > 1]
    
    # ==================== 结构化数据处理 ====================
    
    def clean_dataframe(self, df: pd.DataFrame, config: Dict = None) -> pd.DataFrame:
        """
        清洗 DataFrame 数据
        
        Args:
            df: 原始数据 DataFrame
            config: 清洗配置
            
        Returns:
            清洗后的 DataFrame
        """
        if df.empty:
            logger.warning("输入 DataFrame 为空")
            return df
        
        config = config or {}
        cleaned_df = df.copy()
        
        # 1. 去重
        if config.get('remove_duplicates', True):
            before_count = len(cleaned_df)
            cleaned_df = cleaned_df.drop_duplicates()
            logger.info(f"去重: {before_count} -> {len(cleaned_df)} 条数据")
        
        # 2. 缺失值处理 (原去除空值行)
        if config.get('remove_null', True):
            before_count = len(cleaned_df)
            # 仅去除标题为空的数据
            if 'title' in cleaned_df.columns:
                cleaned_df = cleaned_df.dropna(subset=['title'])
            
            # 填充缺失的正文
            if 'content' in cleaned_df.columns:
                cleaned_df['content'] = cleaned_df['content'].fillna('无正文')
            
            logger.info(f"缺失值处理: {before_count} -> {len(cleaned_df)} 条数据")
        
        # 3. 格式统一
        if config.get('normalize_format', True):
            cleaned_df = self._normalize_formats(cleaned_df)
        
        # 4. 过滤无效数据
        if config.get('filter_invalid', True):
            before_count = len(cleaned_df)
            cleaned_df = self._filter_invalid_data(cleaned_df)
            logger.info(f"过滤无效数据: {before_count} -> {len(cleaned_df)} 条数据")

        # 5. 大模型筛选 (新增)
        if config.get('llm_filter', False):
            if OpenAI is None:
                logger.warning("未安装 openai 库，跳过大模型筛选")
            elif load_config is None:
                logger.warning("无法加载配置，跳过大模型筛选")
            else:
                before_count = len(cleaned_df)
                cleaned_df = self._filter_by_llm(cleaned_df)
                logger.info(f"大模型筛选: {before_count} -> {len(cleaned_df)} 条数据")
        
        return cleaned_df
    
    def _filter_by_llm(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        使用大模型筛选非新闻格式数据
        """
        sys_config = load_config()
        llm_config = sys_config.get('llm', {})
        
        if not llm_config.get('enabled', False) and not llm_config.get('api_key'):
             # 如果配置未启用且没有key，尝试直接读取 api_key (兼容简单配置)
             if not llm_config.get('api_key'):
                 logger.warning("LLM 配置未启用或缺少 API Key")
                 return df

        api_key = llm_config.get('api_key')
        base_url = llm_config.get('api_base', "https://api.openai.com/v1")
        model = llm_config.get('model', "gpt-3.5-turbo")
        
        if not api_key or api_key == "sk-...":
            logger.warning("无效的 LLM API Key")
            return df
            
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
        except Exception as e:
            logger.error(f"初始化 OpenAI 客户端失败: {e}")
            return df
            
        keep_indices = []
        
        for idx, row in df.iterrows():
            title = str(row.get('title', ''))
            content = str(row.get('content', ''))
            # 截取一部分内容以节省 token
            text_snippet = f"标题: {title}\n正文: {content[:500]}"
            
            if self._check_is_news(client, model, text_snippet):
                keep_indices.append(idx)
            else:
                logger.info(f"LLM 剔除数据: {title}")
                
        return df.loc[keep_indices]

    def _check_is_news(self, client, model, text) -> bool:
        """调用 LLM 判断是否为新闻"""
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个专业的新闻编辑。请判断以下文本是否符合标准的新闻报道格式。如果是新闻，请回答'YES'；如果是广告、小说、心情随笔、代码片段或其他非新闻内容，请回答'NO'。只回答YES或NO。"},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                max_tokens=10
            )
            answer = response.choices[0].message.content.strip().upper()
            return "YES" in answer
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            # 出错时默认保留，避免误删
            return True

    def _normalize_formats(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一数据格式"""
        df = df.copy()
        
        # 统一时间格式
        if 'publish_time' in df.columns:
            df['publish_time'] = df['publish_time'].apply(self._normalize_time)
        
        # 统一来源格式
        if 'source' in df.columns:
            df['source'] = df['source'].fillna('未知')
            df['source'] = df['source'].apply(self._normalize_source)
        
        # 去除标题和内容的多余空白
        text_columns = ['title', 'content', 'author']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).apply(lambda x: re.sub(r'\s+', ' ', x).strip())
        
        return df
    
    def _normalize_time(self, time_str) -> str:
        """标准化时间格式"""
        if pd.isna(time_str):
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        time_str = str(time_str).strip()
        
        # 尝试解析常见时间格式
        time_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d %H:%M',
            '%Y/%m/%d',
            '%m月%d日 %H:%M',
            '%m月%d日',
        ]
        
        for fmt in time_formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
        
        # 如果无法解析，返回当前时间
        logger.warning(f"无法解析时间格式: {time_str}")
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def _normalize_source(self, source: str) -> str:
        """标准化来源名称"""
        if pd.isna(source):
            return '未知'
        
        source = str(source).strip()
        
        # 来源映射表
        source_mapping = {
            '新浪': '新浪新闻',
            '网易': '网易新闻',
            '腾讯': '腾讯新闻',
            '搜狐': '搜狐新闻',
            '凤凰': '凤凰网',
            '今日头条': '头条',
            '头条': '头条',
        }
        
        for key, value in source_mapping.items():
            if key in source:
                return value
        
        return source
    
    def _filter_invalid_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """过滤无效数据"""
        df = df.copy()
        
        # 过滤标题过短的数据
        if 'title' in df.columns:
            df = df[df['title'].str.len() >= 5]
        
        # 过滤内容过短的数据 (需求: 标题+正文 < 50字)
        if 'content' in df.columns and 'title' in df.columns:
            df['total_len'] = df['title'].str.len().fillna(0) + df['content'].str.len().fillna(0)
            df = df[df['total_len'] >= 50]
            df = df.drop(columns=['total_len'])
        
        # 关键词黑名单过滤 (广告、敏感词、无效页面、后台页)
        invalid_keywords = [
            # 广告与营销
            '推广', '点击购买', '广告', '优惠券', '代购', 
            '特价', '包邮', '限时抢购', '扫码关注', '微信搜索',
            
            # 敏感词
            '赌博', '色情', '暴力', '反动', 
            
            # 无效内容/错误页面
            '[图片]', '正文为空', '404 Not Found', '页面不存在', 
            '系统维护', '访问出错', 'Error 404', '访问被拒绝', '资源不存在',
            
            # 管理员/登录/后台页面
            '用户登录', '后台管理', '请输入密码', '验证码', 
            '忘记密码', '立即注册', '管理员登录', 'System Login',
            'Username', 'Password', '请登录'
        ]
        
        if 'content' in df.columns:
            pattern = '|'.join(invalid_keywords)
            # 过滤掉包含黑名单关键词的行
            df = df[~df['content'].astype(str).str.contains(pattern, na=False, regex=True)]
        
        return df
    
    # ==================== 文本预处理 ====================
    
    def preprocess_text(self, text: str, 
                       do_segmentation: bool = True,
                       do_pos_filtering: bool = True,
                       do_stopword_removal: bool = True) -> Dict:
        """
        预处理单条文本
        
        Args:
            text: 原始文本
            do_segmentation: 是否分词
            do_pos_filtering: 是否进行词性过滤
            do_stopword_removal: 是否去除停用词
            
        Returns:
            预处理结果字典
        """
        if not text or not isinstance(text, str):
            return {
                'original': text,
                'cleaned': '',
                'words': [],
                'keywords': [],
                'pos_filtered': []
            }
        
        result = {
            'original': text,
            'cleaned': '',
            'words': [],
            'keywords': [],
            'pos_filtered': []
        }
        
        # 1. 文本清洗
        cleaned = self._clean_text(text)
        result['cleaned'] = cleaned
        
        # 2. 中文分词
        if do_segmentation:
            words = self.segment(cleaned)
            result['words'] = words
            
            # 3. 词性过滤
            if do_pos_filtering:
                pos_filtered = self.filter_by_pos(words)
                result['pos_filtered'] = pos_filtered
            
            # 4. 停用词处理
            if do_stopword_removal:
                if result.get('pos_filtered'):
                    words = self.remove_stopwords(result['pos_filtered'])
                else:
                    words = self.remove_stopwords(words)
                result['words'] = words
        
        # 5. 关键词提取
        result['keywords'] = self.extract_keywords(cleaned, top_k=10)
        
        return result
    
    def _clean_text(self, text: str) -> str:
        """清洗文本"""
        if not text:
            return ''
        
        # 去除 URL
        text = re.sub(r'http[s]?://\S+', '', text)
        # 去除 HTML 标签
        text = re.sub(r'<[^>]+>', '', text)
        # 去除特殊字符，保留中文、英文、数字
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def segment(self, text: str) -> List[str]:
        """
        中文分词
        
        Args:
            text: 输入文本
            
        Returns:
            分词后的词语列表
        """
        if not text:
            return []
        
        # 使用 jieba 分词
        words = jieba.cut(text)
        
        # 过滤单个字符
        words = [w for w in words if len(w) > 1]
        
        return list(words)
    
    def segment_with_pos(self, text: str) -> List[Tuple[str, str]]:
        """
        分词并标注词性
        
        Args:
            text: 输入文本
            
        Returns:
            [(词语, 词性), ...] 列表
        """
        if not text:
            return []
        
        words = pseg.cut(text)
        return [(word, flag) for word, flag in words]
    
    def filter_by_pos(self, words: List[str] = None, text: str = None) -> List[str]:
        """
        根据词性过滤词语
        
        Args:
            words: 词语列表
            text: 输入文本（如果words为空则对text分词）
            
        Returns:
            过滤后的词语列表
        """
        if words is None and text is None:
            return []
        
        if words is None:
            words = self.segment(text)
        
        # 获取带词性的分词结果
        if text:
            pos_results = self.segment_with_pos(text)
            filtered = [w for w, pos in pos_results if pos in self.allowed_pos]
        else:
            # 根据词语列表进行简单过滤
            filtered = [w for w in words if len(w) > 1]
        
        return filtered
    
    def extract_keywords(self, text: str, top_k: int = 10, method: str = 'tfidf') -> List[str]:
        """
        提取关键词
        
        Args:
            text: 输入文本
            top_k: 返回关键词数量
            method: 提取方法 ('tfidf' 或 'textrank')
            
        Returns:
            关键词列表
        """
        if not text:
            return []
        
        if method == 'textrank':
            keywords = jieba.analyse.textrank(text, topK=top_k)
        else:
            keywords = jieba.analyse.extract_tags(text, topK=top_k)
        
        return keywords
    
    # ==================== 批量处理 ====================
    
    def process_dataframe(self, df: pd.DataFrame, 
                         text_column: str = 'content',
                         title_column: str = 'title',
                         output_prefix: str = '') -> pd.DataFrame:
        """
        批量处理 DataFrame 中的文本
        
        Args:
            df: 输入数据
            text_column: 文本列名
            title_column: 标题列名
            output_prefix: 输出列前缀
            
        Returns:
            处理后的 DataFrame
        """
        if df.empty:
            return df
        
        processed_df = df.copy()
        
        # 确保输出列存在
        seg_col = f'{output_prefix}segmented' if output_prefix else 'segmented_words'
        kw_col = f'{output_prefix}keywords' if output_prefix else 'keywords'
        
        processed_df[seg_col] = ''
        processed_df[kw_col] = ''
        
        # 合并标题和内容用于分析
        for idx, row in processed_df.iterrows():
            # 合并标题和内容
            title = str(row.get(title_column, ''))
            content = str(row.get(text_column, ''))
            combined_text = f"{title} {content}"
            
            # 预处理
            result = self.preprocess_text(combined_text)
            
            # 保存结果
            processed_df.at[idx, seg_col] = ' '.join(result['words'])
            processed_df.at[idx, kw_col] = ','.join(result['keywords'])
        
        logger.info(f"完成处理 {len(processed_df)} 条数据")
        
        return processed_df
    
    # ==================== 特征准备 ====================
    
    def prepare_features(self, texts: List[str], 
                        method: str = 'tfidf',
                        max_features: int = 5000) -> np.ndarray:
        """
        准备文本特征
        
        Args:
            texts: 文本列表
            method: 特征提取方法 ('tfidf' 或 'bow')
            max_features: 最大特征数
            
        Returns:
            特征矩阵 (numpy array)
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
            
            if method == 'bow':
                vectorizer = CountVectorizer(
                    max_features=max_features,
                    token_pattern=r'(?u)\b\w+\b'
                )
            else:
                vectorizer = TfidfVectorizer(
                    max_features=max_features,
                    token_pattern=r'(?u)\b\w+\b'
                )
            
            features = vectorizer.fit_transform(texts)
            
            # 转换为 numpy 数组
            return features.toarray(), vectorizer.get_feature_names_out()
            
        except ImportError:
            logger.warning("sklearn 未安装，返回简单特征")
            return self._simple_features(texts)
    
    def _simple_features(self, texts: List[str]) -> Tuple[np.ndarray, List[str]]:
        """简单特征提取（不使用 sklearn）"""
        # 基于词频的简单特征
        all_words = []
        for text in texts:
            words = self.segment(text)
            all_words.extend(words)
        
        # 统计词频
        word_counts = Counter(all_words)
        vocab = [w for w, _ in word_counts.most_common(1000)]
        
        # 构建特征矩阵
        features = np.zeros((len(texts), len(vocab)))
        
        for i, text in enumerate(texts):
            words = self.segment(text)
            for j, word in enumerate(vocab):
                features[i, j] = words.count(word)
        
        return features, vocab
    
    # ==================== 统计与分析 ====================
    
    def get_statistics(self, df: pd.DataFrame) -> Dict:
        """
        获取数据统计信息

        Args:
            df: 数据 DataFrame

        Returns:
            统计信息字典
        """
        if df.empty:
            return {
                'total_count': 0,
                'duplicate_count': 0,
                'null_count': 0,
                'avg_title_length': 0,
                'avg_content_length': 0,
                'category_distribution': {}
            }

        # 辅助函数：将 numpy 类型转换为 Python 原生类型
        def to_native_type(val):
            """将 numpy/pandas 类型转换为 Python 原生类型"""
            import numbers
            if val is None or pd.isna(val):
                return 0
            if isinstance(val, (np.integer, np.floating, np.bool_)):
                return val.item()
            if isinstance(val, numbers.Number):
                return val
            return val

        stats = {
            'total_count': to_native_type(len(df)),
            'duplicate_count': to_native_type(df.duplicated(subset=['title']).sum() if 'title' in df.columns else 0),
        }

        if 'title' in df.columns:
            stats['avg_title_length'] = to_native_type(df['title'].str.len().mean())

        if 'content' in df.columns:
            stats['avg_content_length'] = to_native_type(df['content'].str.len().mean())

        # 来源分布
        if 'source' in df.columns:
            source_dist = df['source'].value_counts().to_dict()
            stats['source_distribution'] = {str(k): to_native_type(v) for k, v in source_dist.items()}

        # 分类分布（如果有分类标签）
        if 'category' in df.columns:
            cat_dist = df['category'].value_counts().to_dict()
            stats['category_distribution'] = {str(k): to_native_type(v) for k, v in cat_dist.items()}

        return stats
    
    def analyze_word_frequency(self, df: pd.DataFrame, 
                              text_column: str = 'content',
                              top_k: int = 50) -> List[Tuple[str, int]]:
        """
        分析词频
        
        Args:
            df: 数据 DataFrame
            text_column: 文本列名
            top_k: 返回前 k 个高频词
            
        Returns:
            [(词语, 频率), ...] 列表
        """
        all_words = []
        
        for text in df[text_column]:
            words = self.segment(str(text))
            words = self.remove_stopwords(words)
            all_words.extend(words)
        
        word_counts = Counter(all_words)
        return word_counts.most_common(top_k)


class TextVectorizer:
    """文本向量化工具类"""
    
    def __init__(self, method: str = 'tfidf', max_features: int = 5000):
        """
        初始化向量化器
        
        Args:
            method: 向量化方法 ('tfidf', 'bow', 'word2vec')
            max_features: 最大特征数
        """
        self.method = method
        self.max_features = max_features
        self.vectorizer = None
        self.vocabulary = None
        
        if method == 'tfidf':
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.vectorizer = TfidfVectorizer(
                max_features=max_features,
                token_pattern=r'(?u)\b\w+\b',
                min_df=2,
                max_df=0.95
            )
        elif method == 'bow':
            from sklearn.feature_extraction.text import CountVectorizer
            self.vectorizer = CountVectorizer(
                max_features=max_features,
                token_pattern=r'(?u)\b\w+\b',
                min_df=2,
                max_df=0.95
            )
    
    def fit(self, texts: List[str]):
        """拟合模型"""
        if self.vectorizer:
            self.vectorizer.fit(texts)
            self.vocabulary = self.vectorizer.get_feature_names_out()
    
    def transform(self, texts: List[str]) -> np.ndarray:
        """转换文本为向量"""
        if self.vectorizer:
            return self.vectorizer.transform(texts).toarray()
        return np.array([])
    
    def fit_transform(self, texts: List[str]) -> np.ndarray:
        """拟合并转换"""
        if self.vectorizer:
            result = self.vectorizer.fit_transform(texts).toarray()
            self.vocabulary = self.vectorizer.get_feature_names_out()
            return result
        return np.array([])
    
    def get_vocabulary(self) -> List[str]:
        """获取词汇表"""
        return list(self.vocabulary) if self.vocabulary is not None else []


def clean_news_data(input_file: str, output_file: str = None, 
                   config: Dict = None) -> pd.DataFrame:
    """
    清洗新闻数据文件
    
    Args:
        input_file: 输入文件路径 (CSV/JSON)
        output_file: 输出文件路径
        config: 清洗配置
        
    Returns:
        清洗后的 DataFrame
    """
    # 加载数据
    if input_file.endswith('.csv'):
        df = pd.read_csv(input_file, encoding='utf-8')
    elif input_file.endswith('.json'):
        df = pd.read_json(input_file, orient='records')
    else:
        raise ValueError(f"不支持的文件格式: {input_file}")
    
    # 清洗数据
    cleaner = DataCleaner()
    cleaned_df = cleaner.clean_dataframe(df, config)
    
    # 预处理文本
    if config and config.get('preprocess', True):
        cleaned_df = cleaner.process_dataframe(cleaned_df)
    
    # 保存结果
    if output_file:
        if output_file.endswith('.csv'):
            cleaned_df.to_csv(output_file, index=False, encoding='utf-8')
        elif output_file.endswith('.json'):
            cleaned_df.to_json(output_file, orient='records', force_ascii=False, indent=2)
    
    return cleaned_df


if __name__ == '__main__':
    # 测试数据清洗
    cleaner = DataCleaner()
    
    # 测试文本
    test_texts = [
        "新华社北京2024年1月15日电 记者从相关部门获悉，日前召开的国务院常务会议指出，要进一步做好稳就业工作，确保就业大局稳定。",
        "网易体育1月15报道 在今天凌晨结束的比赛中，皇家马德里客场3-1击败巴塞罗那，送给对手联赛首败。",
        "新浪科技讯 1月15日晚间消息，华为公司今日发布新一代旗舰手机，搭载最新处理器和操作系统，性能大幅提升。"
    ]
    
    for text in test_texts:
        result = cleaner.preprocess_text(text)
        print(f"原文: {text[:50]}...")
        print(f"分词: {result['words'][:10]}")
        print(f"关键词: {result['keywords']}")
        print("-" * 50)

