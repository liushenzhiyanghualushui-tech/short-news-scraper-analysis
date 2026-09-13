package com.news.scraper.strategy;

import okhttp3.*;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;

/**
 * Java HTTP 爬虫抽象基类
 * 
 * 提供 OkHttp 客户端池、Jsoup 解析、重试机制等通用能力。
 * 子类只需实现解析逻辑（parseArticles / parseDetail）。
 */
public abstract class JavaHttpScraper implements ScraperStrategy {

    protected final Logger log = LoggerFactory.getLogger(getClass());

    protected OkHttpClient httpClient;
    protected final RateLimiter rateLimiter = new RateLimiter();
    protected final Random random = new Random();

    /** User-Agent 轮换池 */
    protected static final List<String> USER_AGENTS = List.of(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"
    );

    public JavaHttpScraper() {
        this.httpClient = new OkHttpClient.Builder()
                .connectTimeout(Duration.ofSeconds(10))
                .readTimeout(Duration.ofSeconds(30))
                .writeTimeout(Duration.ofSeconds(10))
                .connectionPool(new ConnectionPool(50, 5, TimeUnit.MINUTES))
                .followRedirects(true)
                .followSslRedirects(true)
                .build();
    }

    /**
     * 获取随机 User-Agent
     */
    protected String randomUA() {
        return USER_AGENTS.get(random.nextInt(USER_AGENTS.size()));
    }

    /**
     * 发起 GET 请求
     */
    protected String fetchUrl(String url) throws IOException {
        Request request = new Request.Builder()
                .url(url)
                .header("User-Agent", randomUA())
                .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
                .header("Accept-Encoding", "gzip, deflate")
                .build();

        try (Response response = httpClient.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("HTTP " + response.code() + " for " + url);
            }
            ResponseBody body = response.body();
            if (body == null) {
                throw new IOException("Empty body for " + url);
            }
            // 自动检测编码
            byte[] bytes = body.bytes();
            String contentType = response.header("Content-Type", "");
            String charset = "UTF-8";
            if (contentType.contains("charset=")) {
                charset = contentType.substring(contentType.indexOf("charset=") + 8).trim();
            }
            return new String(bytes, charset);
        }
    }

    /**
     * 带重试的请求
     */
    protected String fetchWithRetry(String url, int maxRetries) {
        for (int i = 0; i <= maxRetries; i++) {
            try {
                return fetchUrl(url);
            } catch (IOException e) {
                if (i == maxRetries) {
                    log.warn("请求失败 (已重试{}次): {} - {}", maxRetries, url, e.getMessage());
                    return null;
                }
                try {
                    Thread.sleep(1000L * (i + 1)); // 递增退避
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return null;
                }
            }
        }
        return null;
    }

    /**
     * 解析HTML为Document
     */
    protected Document parseHtml(String html) {
        return Jsoup.parse(html);
    }

    /**
     * 随机延迟
     */
    protected void randomDelay(long minMs, long maxMs) {
        try {
            long delay = minMs + random.nextLong(maxMs - minMs);
            Thread.sleep(delay);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * 文本清洗
     */
    protected String cleanText(String text) {
        if (text == null) return "";
        return text.replaceAll("\\s+", " ")
                   .replaceAll("&nbsp;", " ")
                   .replaceAll("&lt;", "<")
                   .replaceAll("&gt;", ">")
                   .replaceAll("&amp;", "&")
                   .replaceAll("&quot;", "\"")
                   .trim();
    }

    // ---- 子类需要实现 ----

    /**
     * 获取新闻列表页URL
     */
    protected abstract String getListPageUrl();

    /**
     * 从列表页解析出文章URL列表
     */
    protected abstract List<String> parseArticleUrls(String html);

    /**
     * 从详情页解析出文章内容
     * @return Map<字段名, 值> 或 null(解析失败)
     */
    protected abstract Map<String, Object> parseArticleDetail(String html, String url);
}
