"""澎湃新闻爬虫 - 适配 short_new 的 MySQL"""

import logging
import asyncio
import time
import json
import random
from typing import Dict, List, Optional
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from ..base import BaseScraper
from ..models import DomesticNewsItem, RawArticleItem


class PengpaiScraper(BaseScraper):
    """澎湃新闻爬虫 (重构版 - 基于 asyncio 和 httpx)"""

    def __init__(self, config: dict, db_handler):
        super().__init__(config, db_handler)
        self.source_name = "澎湃新闻"
        self.source_code = "pengpai"
        self.seed_url = "https://www.thepaper.cn/"
        
        # 配置
        self.target_count = self.config.get("max_items", 10000)
        self.per_channel_limit = 3000
        self.concurrency = 10
        self.list_api = "https://api.thepaper.cn/contentapi/nodeCont/getByChannelId"
        
        # 频道列表：时事、财经、热点、思想、生活、推荐
        self.channel_ids = ["25950", "25951", "25949", "25952", "25953", ""]
        
        # Headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://www.thepaper.cn",
            "Referer": "https://www.thepaper.cn/"
        }

    def run(self) -> int:
        """执行爬取"""
        self.logger.info(f"开始爬取 {self.source_name}，目标: {self.target_count} 条")
        try:
            return asyncio.run(self.async_run())
        except Exception as e:
            self.logger.error(f"爬取过程中发生未捕获异常: {e}")
            import traceback
            traceback.print_exc()
            return 0

    async def async_run(self) -> int:
        """异步执行主逻辑"""
        queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(self.concurrency)
        total_saved = 0
        
        async with httpx.AsyncClient(headers=self.headers, timeout=15) as client:
            # 启动消费者
            consumers = [asyncio.create_task(self.worker(queue, semaphore, client)) for _ in range(self.concurrency)]
            
            total_fetched = 0
            
            self.logger.info(f"开始获取列表...")
            
            for channel_id in self.channel_ids:
                channel_name = channel_id if channel_id else "推荐"
                self.logger.info(f"切换到频道: {channel_name}")
                current_start_time = ""
                page_num = 0
                channel_fetched = 0
                
                while channel_fetched < self.per_channel_limit:
                    if total_fetched >= self.target_count:
                        self.logger.info(f"已达到全局最大抓取量 {self.target_count}，停止抓取")
                        break
                        
                    page_num += 1
                    self.logger.info(f"正在获取 {channel_name} 列表第 {page_num} 页... 本频道已获取: {channel_fetched}, 总获取: {total_fetched}")
                    
                    try:
                        payload = {
                            "channelId": channel_id,
                            "excludeContIds": [],
                            "listRecommendIds": [],
                            "pageSize": 20, # 每次取20条
                            "startTime": current_start_time
                        }
                        if not current_start_time:
                            del payload['startTime']
                            if not channel_id:
                                payload['channelId'] = "" # 首页推荐
                        
                        resp = await client.post(self.list_api, json=payload)
                        data = resp.json()
                        
                        if data['code'] != 200:
                            self.logger.error(f"API Error: {data}")
                            break
                            
                        news_list = data.get('data', {}).get('list', [])
                        if not news_list:
                            self.logger.info(f"频道 {channel_name} 没有更多新闻了")
                            break
                            
                        for item in news_list:
                            # 构造完整的 skipUrl
                            if 'skipUrl' not in item and 'contId' in item:
                                item['skipUrl'] = f"https://www.thepaper.cn/newsDetail_forward_{item['contId']}"
                            queue.put_nowait(item)
                        
                        count = len(news_list)
                        total_fetched += count
                        channel_fetched += count
                        
                        # 更新游标
                        last_item = news_list[-1]
                        # 优先使用 pubTimeLong，如果没有则尝试 publishTime，最后尝试 pubTime
                        current_start_time = last_item.get('pubTimeLong') or last_item.get('publishTime') or last_item.get('pubTime')
                        
                        # 稍微等待，避免请求过快
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        self.logger.error(f"获取列表失败: {e}")
                        await asyncio.sleep(2)
                        # 如果连续失败，可以考虑跳出当前频道
                        break
                
                if total_fetched >= self.target_count:
                    break
            
            self.logger.info("所有频道列表获取完毕，等待正文抓取完成...")
            # 发送结束信号
            for _ in range(self.concurrency):
                queue.put_nowait(None)
                
            results = await asyncio.gather(*consumers)
            total_saved = sum(results)
            
        self.logger.info(f"抓取完成，共保存 {total_saved} 条")
        return total_saved

    async def worker(self, queue, semaphore, client):
        """消费者：抓取内容并入库"""
        count = 0
        loop = asyncio.get_running_loop()
        
        while True:
            item = await queue.get()
            if item is None:
                break
                
            async with semaphore:
                url = item.get('skipUrl', '')
                if not url:
                    queue.task_done()
                    continue

                # 异步获取内容
                content = await self.fetch_article_content(client, url)
                
            if content:
                # 构造数据
                article_data = {
                    "title": item.get('name', ''),
                    "publish_date": item.get('pubTime', ''),
                    "url": url,
                    "content": content,
                    "author": "澎湃新闻"
                }
                
                # 在线程池中执行同步的数据库操作
                saved = await loop.run_in_executor(None, self.save_article_sync, article_data)
                if saved:
                    count += 1
            
            queue.task_done()
        return count

    async def fetch_article_content(self, client, url):
        """抓取新闻详情页并提取正文"""
        if not url:
            return ""
        try:
            # 简单的重试机制
            for attempt in range(3):
                try:
                    resp = await client.get(url, follow_redirects=True)
                    resp.raise_for_status()
                    break
                except httpx.HTTPError:
                    if attempt == 2: return ""
                    await asyncio.sleep(1)

            soup = BeautifulSoup(resp.text, "lxml")
            
            # 策略1：寻找包含最多段落文本的 div
            max_p_len = 0
            best_div = None
            
            for div in soup.find_all('div'):
                current_len = sum(len(t) for t in [p.get_text(strip=True) for p in div.find_all('p')])
                if current_len > max_p_len:
                    max_p_len = current_len
                    best_div = div
            
            if best_div and max_p_len > 100:
                 return "\n".join([p.get_text(strip=True) for p in best_div.find_all('p')])

            # 策略2：尝试通过特定类名
            content_div = soup.select_one('.news_txt') or \
                          soup.select_one('.index_centent_wrap__Jv8jK') or \
                          soup.select_one('[class*="news_txt"]') or \
                          soup.select_one('article')
                          
            if content_div:
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    return "\n".join([p.get_text(strip=True) for p in paragraphs])
                else:
                    return content_div.get_text(strip=True)
            return ""
        except Exception:
            return ""

    def save_article_sync(self, article: Dict) -> bool:
        """同步保存文章到数据库"""
        url = article.get('url', '')
        if self.url_exists(url):
            return False

        item = DomesticNewsItem(
            source_name=self.source_name,
            source_code=self.source_code,
            url=url,
            title=article.get('title', ''),
            author=article.get('author', ''),
            content=article.get('content', ''),
            publish_date=self.try_parse_date(article.get('publish_date')),
            keywords="",
            description=""
        )

        raw_item = RawArticleItem.from_domestic(item, self.source_code)
        return self.db.insert_raw_article(raw_item, self._get_source_id())

    def _get_source_id(self) -> int:
        """获取来源ID"""
        source = self.db.get_source_by_code(self.source_code)
        return source["id"] if source else 0

    def get_source_config(self) -> Dict:
        """获取源配置"""
        return {
            "name": self.source_name,
            "code": self.source_code,
            "type": "domestic",
            "seed_url": self.seed_url
        }
