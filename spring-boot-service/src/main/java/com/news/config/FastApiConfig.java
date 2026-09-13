package com.news.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/**
 * FastAPI 服务连接配置
 */
@Data
@Configuration
@ConfigurationProperties(prefix = "fastapi")
public class FastApiConfig {
    private String baseUrl = "http://localhost:8000";
    private Duration connectTimeout = Duration.ofSeconds(10);
    private Duration readTimeout = Duration.ofSeconds(600);
}
