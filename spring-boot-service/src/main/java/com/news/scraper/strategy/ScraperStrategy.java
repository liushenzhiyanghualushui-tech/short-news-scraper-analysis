package com.news.scraper.strategy;

import com.news.entity.ScraperSource;
import java.util.List;
import java.util.Map;

/**
 * 爬虫策略接口
 * 
 * 每个新闻来源实现各自的抓取策略。
 * 不同来源的HTML结构、反爬策略、解析逻辑完全不同。
 */
public interface ScraperStrategy {

    /**
     * 获取策略名称
     */
    String getName();

    /**
     * 获取该策略适用的来源编码
     */
    String getSourceCode();

    /**
     * 执行爬取任务
     *
     * @param source 来源配置（含并发限制、速率限制）
     * @return 采集到的新闻条目列表，每条为 Map 格式
     */
    List<Map<String, Object>> scrape(ScraperSource source);

    /**
     * 该爬虫是否支持并发执行
     * Java原生HTTP爬虫返回true，Selenium类返回false
     */
    default boolean supportsConcurrency() {
        return true;
    }

    /**
     * 获取推荐并发数
     */
    default int getRecommendedConcurrency() {
        return 20;
    }
}
