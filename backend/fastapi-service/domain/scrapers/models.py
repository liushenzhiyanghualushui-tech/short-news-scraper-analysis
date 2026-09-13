"""
统一数据模型定义

本模块定义了国内新闻爬虫的通用数据模型：

国内新闻数据模型 (DomesticNewsItem)

所有数据模型都遵循统一的存储格式，便于后续分类处理。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import json


@dataclass
class DomesticNewsItem:
    """国内新闻数据模型"""
    source_name: str          # 来源名称 (如: 新浪新闻)
    source_code: str = ""     # 来源编码 (如: sina)
    url: str = ""             # 新闻链接
    title: str = ""           # 标题
    keywords: str = ""        # 关键词 (逗号分隔)
    author: str = ""          # 作者
    publish_date: Optional[datetime] = None  # 发布日期
    content: str = ""         # 正文内容
    description: str = ""     # 描述摘要
    crawl_time: datetime = field(default_factory=datetime.now)  # 爬取时间

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "source_code": self.source_code,
            "url": self.url,
            "title": self.title,
            "keywords": self.keywords,
            "author": self.author,
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "content": self.content,
            "description": self.description,
            "crawl_time": self.crawl_time.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DomesticNewsItem":
        pub_date = data.get("publish_date")
        if isinstance(pub_date, str):
            pub_date = datetime.fromisoformat(pub_date).date() if " " not in pub_date else datetime.fromisoformat(pub_date)
        return cls(
            source_name=data["source_name"],
            source_code=data.get("source_code", ""),
            url=data["url"],
            title=data["title"],
            keywords=data.get("keywords", ""),
            author=data.get("author", ""),
            publish_date=pub_date,
            content=data.get("content", ""),
            description=data.get("description", ""),
            crawl_time=datetime.fromisoformat(data["crawl_time"]) if isinstance(data.get("crawl_time"), str) else data.get("crawl_time", datetime.now())
        )


@dataclass
class RawArticleItem:
    """
    统一原始文章数据模型

    整合国内新闻数据为统一格式，存储到 raw_articles 表
    """
    source_type: str          # 来源类型: domestic
    source_name: str          # 来源名称
    source_code: str = ""     # 来源编码
    url: str = ""             # 文章URL
    title: str = ""           # 标题
    title_en: str = ""        # 英文标题
    author: str = ""          # 作者
    content: str = ""         # 正文内容
    description: str = ""     # 描述摘要
    keywords: str = ""        # 关键词 (逗号分隔)
    publish_time: Optional[datetime] = None  # 发布时间
    platform_id: Optional[int] = None  # 平台ID (保留用于兼容性)
    rank: Optional[int] = None  # 排名 (保留用于兼容性)
    crawl_time: datetime = field(default_factory=datetime.now)  # 爬取时间
    raw_data: dict = field(default_factory=dict)  # 原始数据

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_code": self.source_code,
            "url": self.url,
            "title": self.title,
            "title_en": self.title_en,
            "author": self.author,
            "content": self.content,
            "description": self.description,
            "keywords": self.keywords,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "platform_id": self.platform_id,
            "rank": self.rank,
            "crawl_time": self.crawl_time.isoformat(),
            "raw_data": self.raw_data
        }

    @classmethod
    def from_domestic(cls, item: DomesticNewsItem, source_code: str) -> "RawArticleItem":
        # keywords 可能是列表或字符串，需要统一处理
        keywords_str = ""
        if isinstance(item.keywords, list):
            keywords_str = ",".join([str(k) for k in item.keywords if k])
        elif item.keywords:
            keywords_str = str(item.keywords)

        return cls(
            source_type="domestic",
            source_name=item.source_name,
            source_code=source_code,
            url=item.url,
            title=item.title,
            author=item.author,
            keywords=keywords_str,
            content=item.content,
            description=item.description,
            publish_time=item.publish_date,
            crawl_time=item.crawl_time,
            raw_data=item.to_dict()
        )


@dataclass
class XinhuaNewsItem:
    """新华网新闻数据模型"""
    url: str
    title: str
    content: str
    publish_time: Optional[datetime] = None
    subtitle: str = ""
    source: str = "新华网"
    editor: str = ""
    channel: str = ""
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    keywords: str = ""
    status: int = 1
    retry_times: int = 0
    create_time: datetime = field(default_factory=datetime.now)
    update_time: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "subtitle": self.subtitle,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "source": self.source,
            "editor": self.editor,
            "channel": self.channel,
            "content": self.content,
            "images": json.dumps(self.images, ensure_ascii=False),
            "videos": json.dumps(self.videos, ensure_ascii=False),
            "keywords": self.keywords,
            "status": self.status,
            "retry_times": self.retry_times,
            "create_time": self.create_time.isoformat(),
            "update_time": self.update_time.isoformat()
        }



# 数据类型枚举
class DataSourceType:
    DOMESTIC = "domestic"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.DOMESTIC]
