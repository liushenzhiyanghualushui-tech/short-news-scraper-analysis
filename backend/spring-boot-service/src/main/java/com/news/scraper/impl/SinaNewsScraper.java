package com.news.scraper.impl;

import com.news.entity.ScraperSource;
import com.news.scraper.strategy.JavaHttpScraper;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 新浪新闻爬虫 (Java高并发版)
 * 
 * 策略特点:
 * - 并发数: 50 (高并发，新浪服务器承载能力强)
 * - 速率限制: 1500ms/请求
 * - 解析: 首页链接提取 + 详情页内容解析
 * - 反爬: User-Agent轮换 + 随机延迟
 */
@Component
public class SinaNewsScraper extends JavaHttpScraper {

    private static final String SOURCE_CODE = "sina";
    private static final String LIST_URL = "https://news.sina.com.cn/";
    private static final Pattern DATE_PATTERN = Pattern.compile(
            "(\\d{4})[年/-](\\d{1,2})[月/-](\\d{1,2})[日]?\\s*(\\d{1,2}):(\\d{2})");

    @Override
    public String getName() {
        return "新浪新闻";
    }

    @Override
    public String getSourceCode() {
        return SOURCE_CODE;
    }

    @Override
    public List<Map<String, Object>> scrape(ScraperSource source) {
        List<Map<String, Object>> results = Collections.synchronizedList(new ArrayList<>());
        int concurrentLimit = source.getConcurrentLimit() != null ? 
                source.getConcurrentLimit() : 50;

        log.info("🕷 [新浪] 开始抓取，并发数={}", concurrentLimit);

        // 步骤1: 获取列表页
        String listHtml = fetchWithRetry(LIST_URL, 3);
        if (listHtml == null) {
            log.warn("[新浪] 列表页获取失败");
            return results;
        }

        // 步骤2: 解析文章URL
        List<String> articleUrls = parseArticleUrls(listHtml);
        log.info("[新浪] 从列表页解析到 {} 个候选链接", articleUrls.size());

        // 步骤3: 虚拟线程并发抓取详情页
        try (var executor = java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = new ArrayList<java.util.concurrent.Future<?>>();

            for (String url : articleUrls) {
                if (url == null || url.isBlank()) continue;

                futures.add(executor.submit(() -> {
                    try {
                        rateLimiter.acquire(SOURCE_CODE);
                        randomDelay(200, 800);

                        String detailHtml = fetchWithRetry(url, 2);
                        if (detailHtml == null) return;

                        Map<String, Object> article = parseArticleDetail(detailHtml, url);
                        if (article != null && !article.isEmpty()) {
                            results.add(article);
                        }
                    } catch (Exception e) {
                        log.debug("[新浪] 抓取详情失败: {} - {}", url, e.getMessage());
                    }
                }));
            }

            // 等待所有任务完成（带超时）
            for (var f : futures) {
                try {
                    f.get(30, java.util.concurrent.TimeUnit.SECONDS);
                } catch (Exception ignored) {}
            }
        }

        log.info("✅ [新浪] 完成: 采集 {} 条新闻", results.size());
        return results;
    }

    @Override
    protected String getListPageUrl() {
        return LIST_URL;
    }

    @Override
    protected List<String> parseArticleUrls(String html) {
        Set<String> urls = new LinkedHashSet<>();
        Document doc = parseHtml(html);

        // 新浪新闻首页链接模式
        Elements links = doc.select("a[href]");
        for (Element link : links) {
            String href = link.absUrl("href");
            if (href.contains("news.sina.com.cn") && 
                href.matches(".*/(doc-[a-z]+|\\d{4}-\\d{2}-\\d{2})/.*\\.s?html.*")) {
                urls.add(href);
            }
        }

        // 限制数量
        return urls.stream().limit(200).toList();
    }

    @Override
    protected Map<String, Object> parseArticleDetail(String html, String url) {
        try {
            Document doc = parseHtml(html);

            // 标题
            String title = "";
            Element titleEl = doc.selectFirst("h1.main-title, h1.article-title, h1");
            if (titleEl != null) {
                title = cleanText(titleEl.text());
            }
            if (title.isEmpty()) return null;

            // 时间
            LocalDateTime publishTime = null;
            Element timeEl = doc.selectFirst(".date, .time, .pub-time, .article-time");
            if (timeEl != null) {
                publishTime = parseDate(cleanText(timeEl.text()));
            }

            // 来源
            String source = "";
            Element sourceEl = doc.selectFirst(".source, .article-source");
            if (sourceEl != null) {
                source = cleanText(sourceEl.text());
            }

            // 正文
            StringBuilder content = new StringBuilder();
            Elements contentEls = doc.select("#article p, .article-content p, #artibody p");
            for (Element p : contentEls) {
                String text = cleanText(p.text());
                if (!text.isEmpty()) {
                    content.append(text).append("\n");
                }
            }

            Map<String, Object> article = new HashMap<>();
            article.put("url", url);
            article.put("title", title);
            article.put("content", content.toString());
            article.put("source_name", "新浪新闻");
            article.put("source_code", SOURCE_CODE);
            article.put("author", source);
            article.put("publish_time", publishTime);
            article.put("crawl_time", LocalDateTime.now());

            return article;
        } catch (Exception e) {
            log.debug("[新浪] 解析详情失败: {}", e.getMessage());
            return null;
        }
    }

    private LocalDateTime parseDate(String text) {
        if (text == null) return null;
        Matcher m = DATE_PATTERN.matcher(text);
        if (m.find()) {
            try {
                return LocalDateTime.of(
                        Integer.parseInt(m.group(1)),
                        Integer.parseInt(m.group(2)),
                        Integer.parseInt(m.group(3)),
                        Integer.parseInt(m.group(4)),
                        Integer.parseInt(m.group(5))
                );
            } catch (Exception ignored) {}
        }
        return LocalDateTime.now();
    }
}
