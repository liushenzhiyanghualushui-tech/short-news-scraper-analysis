package com.news.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.Map;

/**
 * 爬虫全局配置
 */
@Data
@Configuration
@ConfigurationProperties(prefix = "scraper")
public class ScraperProperties {
    private int maxConcurrentScrapers = 20;
    private int defaultTimeout = 300;
    private int maxRetries = 3;
    private long baseDelayMs = 1000;
    private Map<String, SourceConfig> sources;

    @Data
    public static class SourceConfig {
        private int concurrentLimit = 20;
        private long rateLimitMs = 2000;
    }
}
