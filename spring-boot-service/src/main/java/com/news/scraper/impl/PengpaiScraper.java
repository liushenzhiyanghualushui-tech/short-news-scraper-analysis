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
 * 澎湃新闻爬虫 (Java高并发版)
 */
@Component
public class PengpaiScraper extends JavaHttpScraper {

    private static final String SOURCE_CODE = "pengpai";
    private static final String LIST_URL = "https://www.thepaper.cn/";
    private static final Pattern DATE_PATTERN = Pattern.compile(
            "(\\d{4})[年/-](\\d{1,2})[月/-](\\d{1,2})[日]?\\s*(\\d{1,2}):(\\d{2})");

    @Override
    public String getName() { return "澎湃新闻"; }

    @Override
    public String getSourceCode() { return SOURCE_CODE; }

    @Override
    public List<Map<String, Object>> scrape(ScraperSource source) {
        List<Map<String, Object>> results = Collections.synchronizedList(new ArrayList<>());
        int concurrentLimit = source.getConcurrentLimit() != null ? 
                source.getConcurrentLimit() : 30;

        log.info("🕷 [澎湃] 开始抓取，并发数={}", concurrentLimit);

        String listHtml = fetchWithRetry(LIST_URL, 3);
        if (listHtml == null) return results;

        List<String> articleUrls = parseArticleUrls(listHtml);
        log.info("[澎湃] 从列表页解析到 {} 个候选链接", articleUrls.size());

        try (var executor = java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = new ArrayList<java.util.concurrent.Future<?>>();
            for (String url : articleUrls) {
                if (url == null || url.isBlank()) continue;
                futures.add(executor.submit(() -> {
                    try {
                        rateLimiter.acquire(SOURCE_CODE);
                        randomDelay(400, 1500);
                        String html = fetchWithRetry(url, 2);
                        if (html == null) return;
                        Map<String, Object> article = parseArticleDetail(html, url);
                        if (article != null) results.add(article);
                    } catch (Exception ignored) {}
                }));
            }
            for (var f : futures) {
                try { f.get(25, java.util.concurrent.TimeUnit.SECONDS); } 
                catch (Exception ignored) {}
            }
        }

        log.info("✅ [澎湃] 完成: 采集 {} 条新闻", results.size());
        return results;
    }

    @Override
    protected String getListPageUrl() { return LIST_URL; }

    @Override
    protected List<String> parseArticleUrls(String html) {
        Set<String> urls = new LinkedHashSet<>();
        Document doc = parseHtml(html);
        Elements links = doc.select("a[href]");
        for (Element link : links) {
            String href = link.absUrl("href");
            if (href.contains("thepaper.cn") && 
                href.matches(".*newsDetail_forward_\\d+.*")) {
                urls.add(href);
            }
        }
        return urls.stream().limit(120).toList();
    }

    @Override
    protected Map<String, Object> parseArticleDetail(String html, String url) {
        try {
            Document doc = parseHtml(html);
            String title = "";
            Element titleEl = doc.selectFirst("h1, .news_title, .index_title");
            if (titleEl != null) title = cleanText(titleEl.text());
            if (title.isEmpty()) return null;

            LocalDateTime publishTime = null;
            Element timeEl = doc.selectFirst(".news_about time, .pubtime, .index_date");
            if (timeEl != null) {
                Matcher m = DATE_PATTERN.matcher(cleanText(timeEl.text()));
                if (m.find()) {
                    try {
                        publishTime = LocalDateTime.of(
                                Integer.parseInt(m.group(1)), Integer.parseInt(m.group(2)),
                                Integer.parseInt(m.group(3)), Integer.parseInt(m.group(4)),
                                Integer.parseInt(m.group(5)));
                    } catch (Exception ignored) {}
                }
            }

            StringBuilder content = new StringBuilder();
            Elements contentEls = doc.select(".news_txt p, .index_cent p, .news_content p");
            for (Element p : contentEls) {
                String text = cleanText(p.text());
                if (!text.isEmpty() && text.length() > 5) content.append(text).append("\n");
            }

            Map<String, Object> article = new HashMap<>();
            article.put("url", url);
            article.put("title", title);
            article.put("content", content.toString());
            article.put("source_name", "澎湃新闻");
            article.put("source_code", SOURCE_CODE);
            article.put("publish_time", Objects.requireNonNullElseGet(publishTime, LocalDateTime::now));
            article.put("crawl_time", LocalDateTime.now());
            return article;
        } catch (Exception e) { return null; }
    }
}
