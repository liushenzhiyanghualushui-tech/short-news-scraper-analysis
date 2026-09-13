package com.news.scraper.impl;

import com.news.entity.ScraperSource;
import com.news.scraper.strategy.JavaHttpScraper;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 腾讯新闻爬虫 (Java高并发版)
 * 
 * 策略特点:
 * - 并发数: 40
 * - 速率限制: 2000ms/请求
 * - 解析: API类JSON数据 + HTML内容提取
 */
@Component
public class TencentNewsScraper extends JavaHttpScraper {

    private static final String SOURCE_CODE = "tencent";
    private static final String LIST_URL = "https://news.qq.com/";
    private static final Pattern DATE_PATTERN = Pattern.compile(
            "(\\d{4})[年/-](\\d{1,2})[月/-](\\d{1,2})[日]?\\s*(\\d{1,2}):(\\d{2})");

    @Override
    public String getName() {
        return "腾讯新闻";
    }

    @Override
    public String getSourceCode() {
        return SOURCE_CODE;
    }

    @Override
    public List<Map<String, Object>> scrape(ScraperSource source) {
        List<Map<String, Object>> results = Collections.synchronizedList(new ArrayList<>());
        int concurrentLimit = source.getConcurrentLimit() != null ? 
                source.getConcurrentLimit() : 40;

        log.info("🕷 [腾讯] 开始抓取，并发数={}", concurrentLimit);

        String listHtml = fetchWithRetry(LIST_URL, 3);
        if (listHtml == null) {
            log.warn("[腾讯] 列表页获取失败");
            return results;
        }

        List<String> articleUrls = parseArticleUrls(listHtml);
        log.info("[腾讯] 从列表页解析到 {} 个候选链接", articleUrls.size());

        try (var executor = java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = new ArrayList<java.util.concurrent.Future<?>>();

            for (String url : articleUrls) {
                if (url == null || url.isBlank()) continue;
                futures.add(executor.submit(() -> {
                    try {
                        rateLimiter.acquire(SOURCE_CODE);
                        randomDelay(300, 1000);
                        String detailHtml = fetchWithRetry(url, 2);
                        if (detailHtml == null) return;
                        Map<String, Object> article = parseArticleDetail(detailHtml, url);
                        if (article != null && !article.isEmpty()) {
                            results.add(article);
                        }
                    } catch (Exception e) {
                        log.debug("[腾讯] 抓取详情失败: {} - {}", url, e.getMessage());
                    }
                }));
            }

            for (var f : futures) {
                try { f.get(25, java.util.concurrent.TimeUnit.SECONDS); } 
                catch (Exception ignored) {}
            }
        }

        log.info("✅ [腾讯] 完成: 采集 {} 条新闻", results.size());
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

        Elements links = doc.select("a[href]");
        for (Element link : links) {
            String href = link.absUrl("href");
            if (href.contains("new.qq.com") && href.contains("/rain/a/")) {
                urls.add(href);
            }
        }
        return urls.stream().limit(150).toList();
    }

    @Override
    protected Map<String, Object> parseArticleDetail(String html, String url) {
        try {
            Document doc = parseHtml(html);

            String title = "";
            Element titleEl = doc.selectFirst("h1, .content-article h1, .title");
            if (titleEl != null) title = cleanText(titleEl.text());
            if (title.isEmpty()) return null;

            LocalDateTime publishTime = null;
            Element timeEl = doc.selectFirst(".content-article .time, .article-time, .pub-time");
            if (timeEl != null) publishTime = parseDate(cleanText(timeEl.text()));

            StringBuilder content = new StringBuilder();
            Elements contentEls = doc.select(".content-article p, .article-content p");
            for (Element p : contentEls) {
                String text = cleanText(p.text());
                if (!text.isEmpty() && text.length() > 5) {
                    content.append(text).append("\n");
                }
            }

            Map<String, Object> article = new HashMap<>();
            article.put("url", url);
            article.put("title", title);
            article.put("content", content.toString());
            article.put("source_name", "腾讯新闻");
            article.put("source_code", SOURCE_CODE);
            article.put("publish_time", publishTime);
            article.put("crawl_time", LocalDateTime.now());
            return article;
        } catch (Exception e) {
            return null;
        }
    }

    private LocalDateTime parseDate(String text) {
        if (text == null) return null;
        Matcher m = DATE_PATTERN.matcher(text);
        if (m.find()) {
            try {
                return LocalDateTime.of(
                        Integer.parseInt(m.group(1)), Integer.parseInt(m.group(2)),
                        Integer.parseInt(m.group(3)), Integer.parseInt(m.group(4)),
                        Integer.parseInt(m.group(5)));
            } catch (Exception ignored) {}
        }
        return LocalDateTime.now();
    }
}
