import logging
import os
import time

from scrapers.config import load_config
from scrapers.domestic.ifeng import IfengScraper


class FakeDB:
    def __init__(self):
        self._seen = set()

    def url_exists(self, url):
        return url in self._seen

    def insert_raw_article(self, item, source_id):
        self._seen.add(item.url)
        return True

    def get_source_by_code(self, code):
        return {"id": 1}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    config = load_config()

    target_max_items = int(os.environ.get("IFENG_MAX_ITEMS", "3000"))
    target_concurrency = int(os.environ.get("IFENG_CONCURRENCY", "2"))
    only_list = os.environ.get("IFENG_ONLY_LIST", "0") == "1"

    domestic = config.get("domestic_news", {})
    if isinstance(domestic, dict):
        for s in domestic.get("sources", []) or []:
            if isinstance(s, dict) and s.get("name") == "ifeng":
                s["max_items"] = target_max_items
                s["concurrency"] = target_concurrency
                break

    spider = IfengScraper(config, FakeDB())

    start = time.time()
    if only_list:
        urls = spider.fetch_article_list()
        print("LIST_DONE", "urls", len(urls), "duration_s", round(time.time() - start, 2))
        return

    count = spider.run()
    print("RUN_DONE", count, "duration_s", round(time.time() - start, 2))


if __name__ == "__main__":
    main()

