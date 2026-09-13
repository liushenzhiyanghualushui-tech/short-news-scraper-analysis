"""
数据增强模块

为小样本中文新闻分类提供文本级数据增强策略：
1. 同义词替换 (Synonym Replacement) — 基于 jieba 分词 + 内嵌新闻领域同义词表
2. EDA 随机操作 — 随机删除、随机交换、随机插入
3. 类别感知选择性增强 — 仅对低频类别进行增强，平衡类别分布

技术栈：jieba, random, collections
"""

import random
import logging
import math
import jieba
from typing import List, Dict, Tuple, Optional
from collections import Counter

logger = logging.getLogger('data_augmenter')

# ==================== 中文新闻领域同义词表 ====================
# 覆盖14个新闻分类的高频名词、动词、形容词
SYNONYM_DICT = {
    # ---- 政治/国际 ----
    '会议': ['会谈', '峰会', '大会', '座谈会'],
    '政策': ['措施', '方针', '举措', '方案'],
    '改革': ['变革', '革新', '转型', '调整'],
    '政府': ['当局', '官方', '行政部门'],
    '国家': ['国度', '国', '主权国家'],
    '领导': ['带领', '统领', '主导', '引领'],
    '合作': ['协作', '携手', '联合', '配合'],
    '发展': ['进展', '推进', '壮大', '成长'],
    '建设': ['构建', '打造', '搭建', '营建'],
    '推进': ['推动', '促进', '推行', '落实'],
    '总统': ['元首', '总统先生', '领袖'],
    '外交': ['外事', '邦交', '国际关系'],
    '谈判': ['磋商', '协商', '洽谈', '交涉'],
    '签署': ['签订', '缔结', '达成'],
    '声明': ['公告', '通告', '发言', '表态'],
    # ---- 经济/财经 ----
    '市场': ['行情', '市况', '商业环境'],
    '投资': ['注资', '出资', '投入', '布局'],
    '增长': ['上涨', '攀升', '提升', '上扬'],
    '下降': ['下跌', '下滑', '回落', '走低'],
    '企业': ['公司', '集团', '机构', '商家'],
    '利润': ['盈利', '收益', '效益', '利益'],
    '经济': ['经济形势', '经济态势'],
    '金融': ['金融业', '金融领域'],
    '银行': ['金融机构', '银行业'],
    '股价': ['股票价格', '股值', '市值'],
    '消费': ['购买', '消费支出', '开支'],
    '产业': ['行业', '产业链', '业态'],
    '交易': ['买卖', '成交', '出售'],
    '基金': ['资金', '投资基金'],
    # ---- 科技 ----
    '技术': ['科技', '工艺', '方案'],
    '研发': ['研究', '开发', '攻关', '探索'],
    '创新': ['突破', '革新', '革命性进展'],
    '产品': ['商品', '新品', '终端'],
    '芯片': ['处理器', '半导体', '集成电路'],
    '人工智能': ['AI', '智能技术'],
    '互联网': ['网络', '线上', '数字化'],
    '软件': ['程序', '应用', '系统'],
    '发布': ['推出', '上市', '亮相', '面世'],
    '用户': ['使用者', '客户', '消费者'],
    '数据': ['信息', '数据资料'],
    '设备': ['装置', '终端', '器材'],
    '平台': ['系统', '服务平台'],
    # ---- 体育 ----
    '比赛': ['赛事', '竞赛', '对决', '角逐'],
    '冠军': ['桂冠', '第一名', '金牌', '头名'],
    '球员': ['选手', '运动员', '队员'],
    '球队': ['战队', '俱乐部', '队伍'],
    '教练': ['主帅', '执教者', '指导'],
    '胜利': ['获胜', '凯旋', '赢得', '取胜'],
    '失败': ['败北', '落败', '输掉'],
    '训练': ['备战', '集训', '操练'],
    '赛季': ['联赛季', '本赛季'],
    '进球': ['得分', '破门', '建功'],
    # ---- 娱乐 ----
    '电影': ['影片', '大片', '作品'],
    '演员': ['艺人', '明星', '表演者'],
    '导演': ['制片人', '编导'],
    '票房': ['卖座', '收入'],
    '综艺': ['节目', '真人秀', '综艺节目'],
    '歌手': ['歌星', '音乐人', '唱将'],
    '观众': ['粉丝', '受众', '看客'],
    # ---- 军事 ----
    '军队': ['部队', '武装力量', '军方'],
    '武器': ['装备', '军械', '兵器'],
    '演习': ['军演', '联合演习', '实战演练'],
    '导弹': ['飞弹', '弹道武器'],
    '战斗机': ['战机', '歼击机', '军机'],
    '国防': ['防务', '安全防御'],
    # ---- 社会 ----
    '事故': ['事件', '意外', '灾难'],
    '警方': ['公安', '警察', '执法部门'],
    '救援': ['营救', '施救', '抢救'],
    '调查': ['侦查', '排查', '核查'],
    '市民': ['居民', '群众', '百姓', '公众'],
    '案件': ['案子', '刑案', '事件'],
    # ---- 教育 ----
    '学生': ['学子', '考生', '同学'],
    '学校': ['院校', '高校', '学府'],
    '考试': ['测试', '评估', '考核'],
    '教师': ['老师', '教员', '讲师'],
    '招生': ['录取', '纳新'],
    # ---- 文化 ----
    '文化': ['文明', '人文', '文脉'],
    '艺术': ['美术', '创作', '文艺'],
    '展览': ['展出', '展示', '陈列'],
    '历史': ['过往', '史实', '历程'],
    '博物馆': ['纪念馆', '展馆', '陈列馆'],
    # ---- 汽车 ----
    '汽车': ['车辆', '轿车', '座驾'],
    '销量': ['销售量', '出货量', '销售额'],
    '新车': ['新款车型', '全新车型'],
    # ---- 房产 ----
    '房价': ['房屋价格', '楼价', '售价'],
    '楼市': ['房地产市场', '地产行业'],
    '楼盘': ['项目', '住宅项目'],
    # ---- 游戏 ----
    '游戏': ['手游', '端游', '网游'],
    '玩家': ['游戏玩家', '用户', '选手'],
    '版本': ['更新', '迭代', '赛季'],
    # ---- 通用动词 ----
    '表示': ['称', '指出', '透露', '说'],
    '认为': ['觉得', '看来', '以为'],
    '报道': ['消息', '报导', '获悉'],
    '宣布': ['公布', '宣告', '披露'],
    '开展': ['实施', '进行', '展开'],
    '加强': ['强化', '深化', '巩固'],
    '提高': ['提升', '增强', '改善'],
    '完成': ['完毕', '达成', '实现'],
    '参加': ['出席', '参与', '加入'],
    '要求': ['呼吁', '敦促', '号召'],
    '支持': ['援助', '资助', '扶持'],
    '关注': ['聚焦', '瞩目', '留意'],
    '影响': ['波及', '左右', '冲击'],
    '计划': ['规划', '方案', '部署'],
    '目标': ['目的', '愿景', '指标'],
    '成功': ['成就', '成绩', '功绩'],
    '问题': ['难题', '困境', '挑战'],
    '重要': ['关键', '核心', '重大'],
    '积极': ['主动', '正面', '乐观'],
    '显著': ['明显', '突出', '可观'],
    '保障': ['保护', '维护', '守护'],
    '安全': ['安保', '稳定', '平安'],
    '严重': ['严峻', '恶劣', '重大'],
    '丰富': ['充裕', '多元', '充足'],
    '优秀': ['杰出', '卓越', '出色'],
}

# 停用词集合（增强时跳过这些词不替换）
_STOPWORDS = {
    '的', '是', '了', '在', '和', '有', '就', '不', '这', '也', '都',
    '被', '与', '着', '为', '到', '把', '从', '向', '又', '要', '会',
    '能', '可', '对', '而', '但', '或', '而且', '因为', '所以',
    '如果', '那么', '或者', '虽然', '但是', '然而',
    '我', '你', '他', '她', '它', '我们', '你们', '他们',
    '这个', '那个', '什么', '怎么', '如何',
    '啊', '吧', '呢', '吗', '哦', '嗯', '哈', '呀',
    '日', '月', '年', '时', '分', '秒', '已', '已经',
    '上', '下', '中', '内', '外', '前', '后',
    '很', '非常', '十分', '特别', '相当', '最', '更',
}

# 构建反向同义词索引（word -> group of synonyms），加速查找
_WORD_TO_SYNONYMS = {}
for _key, _values in SYNONYM_DICT.items():
    _group = [_key] + _values
    for _word in _group:
        _WORD_TO_SYNONYMS[_word] = _group


class TextAugmenter:
    """中文新闻文本数据增强器"""

    def __init__(self, alpha_sr: float = 0.15, alpha_rd: float = 0.1, alpha_rs: float = 0.1):
        """
        Args:
            alpha_sr: 同义词替换比例（替换 alpha_sr * n 个词）
            alpha_rd: 随机删除概率（每个词以 alpha_rd 概率被删除）
            alpha_rs: 随机交换比例（交换 alpha_rs * n 对词）
        """
        self.alpha_sr = alpha_sr
        self.alpha_rd = alpha_rd
        self.alpha_rs = alpha_rs

    # ==================== 单文本增强方法 ====================

    def synonym_replace(self, text: str, n: int = None) -> str:
        """同义词替换：随机选择 n 个可替换词，替换为同义词"""
        words = list(jieba.cut(text))
        if not words:
            return text

        # 找出可替换位置（非停用词 + 在同义词表中）
        replaceable = [(i, w) for i, w in enumerate(words) if w in _WORD_TO_SYNONYMS and w not in _STOPWORDS]
        if not replaceable:
            return text

        if n is None:
            n = max(1, int(self.alpha_sr * len(words)))
        n = min(n, len(replaceable))

        chosen = random.sample(replaceable, n)
        new_words = words.copy()
        for idx, word in chosen:
            synonyms = [s for s in _WORD_TO_SYNONYMS[word] if s != word]
            if synonyms:
                new_words[idx] = random.choice(synonyms)

        return ''.join(new_words)

    def random_delete(self, text: str) -> str:
        """随机删除：以概率 alpha_rd 删除每个词"""
        words = list(jieba.cut(text))
        if len(words) <= 2:
            return text
        remaining = [w for w in words if random.random() > self.alpha_rd]
        if not remaining:
            remaining = [random.choice(words)]
        return ''.join(remaining)

    def random_swap(self, text: str, n: int = None) -> str:
        """随机交换：随机交换 n 对词的位置"""
        words = list(jieba.cut(text))
        if len(words) < 3:
            return text
        if n is None:
            n = max(1, int(self.alpha_rs * len(words)))
        new_words = words.copy()
        for _ in range(n):
            i, j = random.sample(range(len(new_words)), 2)
            new_words[i], new_words[j] = new_words[j], new_words[i]
        return ''.join(new_words)

    def random_insert(self, text: str, n: int = None) -> str:
        """随机插入：随机选一个词的同义词，插入到随机位置"""
        words = list(jieba.cut(text))
        if not words:
            return text

        replaceable = [w for w in words if w in _WORD_TO_SYNONYMS and w not in _STOPWORDS]
        if not replaceable:
            return text

        if n is None:
            n = max(1, int(self.alpha_sr * len(words)))
        new_words = words.copy()
        for _ in range(n):
            word = random.choice(replaceable)
            synonyms = [s for s in _WORD_TO_SYNONYMS[word] if s != word]
            if synonyms:
                insert_pos = random.randint(0, len(new_words))
                new_words.insert(insert_pos, random.choice(synonyms))
        return ''.join(new_words)

    def augment_one(self, text: str, method: str = 'random') -> str:
        """对单条文本执行一次增强

        Args:
            text: 原始文本
            method: 'synonym' | 'delete' | 'swap' | 'insert' | 'random'（随机选一种）
        """
        if method == 'random':
            method = random.choice(['synonym', 'delete', 'swap', 'insert'])

        if method == 'synonym':
            return self.synonym_replace(text)
        elif method == 'delete':
            return self.random_delete(text)
        elif method == 'swap':
            return self.random_swap(text)
        elif method == 'insert':
            return self.random_insert(text)
        return text


def augment_dataset(
    texts: List[str],
    labels: List[str],
    target_ratio: float = 0.75,
    max_aug_factor: int = 4,
    alpha_sr: float = 0.15,
    alpha_rd: float = 0.1,
    callback=None,
) -> Tuple[List[str], List[str], Dict]:
    """类别感知的选择性数据增强

    仅对样本数低于目标值的类别进行增强，使类别分布趋向均衡。
    增强后始终保留全部原始样本，新增样本附加在末尾。

    Args:
        texts: 原始训练文本列表
        labels: 原始训练标签列表
        target_ratio: 增强目标 = 中位数 * target_ratio 到 中位数之间
        max_aug_factor: 单条文本最多复制倍数上限（防止过增强）
        alpha_sr: 同义词替换比例
        alpha_rd: 随机删除概率
        callback: 进度回调 (progress: int, message: str)

    Returns:
        (augmented_texts, augmented_labels, summary)
    """
    counter = Counter(labels)
    class_counts = sorted(counter.values())
    median_count = int(class_counts[len(class_counts) // 2])
    target_count = max(median_count, 10)  # 至少增强到 10 条

    augmenter = TextAugmenter(alpha_sr=alpha_sr, alpha_rd=alpha_rd)

    # 按类别分桶
    class_texts: Dict[str, List[str]] = {}
    for text, label in zip(texts, labels):
        class_texts.setdefault(label, []).append(text)

    aug_texts = []
    aug_labels = []
    total_augmented = 0
    aug_details = {}

    classes_to_augment = {cls for cls, cnt in counter.items() if cnt < target_count}

    if callback:
        callback(0, f"数据增强: 目标样本数 {target_count}，需增强 {len(classes_to_augment)}/{len(counter)} 个类别")

    for cls in classes_to_augment:
        cls_samples = class_texts[cls]
        current_count = len(cls_samples)
        need = target_count - current_count
        # 限制最大增强倍数
        need = min(need, current_count * max_aug_factor)
        if need <= 0:
            continue

        cls_aug_texts = []
        for i in range(need):
            src_text = cls_samples[i % current_count]
            aug_text = augmenter.augment_one(src_text, method='random')
            # 质量控制：增强文本长度不低于原文 40%
            if len(aug_text) >= len(src_text) * 0.4:
                cls_aug_texts.append(aug_text)

        aug_texts.extend(cls_aug_texts)
        aug_labels.extend([cls] * len(cls_aug_texts))
        total_augmented += len(cls_aug_texts)
        aug_details[cls] = {'original': current_count, 'augmented': len(cls_aug_texts)}

    # 合并：原始 + 增强
    all_texts = list(texts) + aug_texts
    all_labels = list(labels) + aug_labels

    summary = {
        'original_samples': len(texts),
        'augmented_samples': total_augmented,
        'total_samples': len(all_texts),
        'target_count': target_count,
        'classes_augmented': len(classes_to_augment),
        'details': aug_details,
    }

    if callback:
        callback(100, f"数据增强完成: 原始 {len(texts)} → 增强后 {len(all_texts)} 条 (+{total_augmented})")

    logger.info(f"数据增强完成: {len(texts)} → {len(all_texts)} 条 (增加 {total_augmented} 条, 覆盖 {len(classes_to_augment)} 个低频类别)")

    return all_texts, all_labels, summary
