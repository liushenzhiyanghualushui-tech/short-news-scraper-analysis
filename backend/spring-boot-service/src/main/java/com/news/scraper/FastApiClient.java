package com.news.scraper;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.news.config.FastApiConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Map;

/**
 * FastAPI 服务调用客户端
 * 调用 Python FastAPI 执行重型爬虫 (xinhua, ifeng, cankaoxiaoxi)
 */
@Component
public class FastApiClient {

    private static final Logger log = LoggerFactory.getLogger(FastApiClient.class);
    private final RestClient restClient;
    private final FastApiConfig config;
    private final ObjectMapper objectMapper;

    public FastApiClient(RestClient restClient, FastApiConfig config, ObjectMapper objectMapper) {
        this.restClient = restClient;
        this.config = config;
        this.objectMapper = objectMapper;
    }

    /** 启动 Python 爬虫 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> startSpider(String spiderName) {
        String url = config.getBaseUrl() + "/api/scraping/start?spider_name=" + spiderName;
        log.info("📡 FastAPI -> POST {}", url);
        try {
            String resp = restClient.post().uri(url).retrieve().body(String.class);
            return objectMapper.readValue(resp, Map.class);
        } catch (Exception e) {
            log.error("FastAPI 调用失败 [{}]: {}", spiderName, e.getMessage());
            return Map.of("status", "failed", "error", e.getMessage());
        }
    }

    /** 查询爬虫状态 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getSpiderStatus(String spiderName) {
        String url = config.getBaseUrl() + "/api/scraping/status/" + spiderName;
        try {
            String resp = restClient.get().uri(url).retrieve().body(String.class);
            return objectMapper.readValue(resp, Map.class);
        } catch (Exception e) {
            return Map.of("status", "error");
        }
    }

    /** 健康检查 */
    public boolean isHealthy() {
        try {
            String resp = restClient.get()
                    .uri(config.getBaseUrl() + "/api/health")
                    .retrieve().body(String.class);
            return resp != null && resp.contains("healthy");
        } catch (Exception e) {
            return false;
        }
    }
}
