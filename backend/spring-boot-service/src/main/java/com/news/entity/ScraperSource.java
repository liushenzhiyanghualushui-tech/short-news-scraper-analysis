package com.news.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 新闻来源实体
 * 对应 scraper_sources 表
 */
@Entity
@Table(name = "scraper_sources")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ScraperSource {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(name = "source_type", nullable = false)
    private String sourceType;  // domestic / foreign

    @Column(nullable = false, length = 100)
    private String name;

    @Column(unique = true, nullable = false, length = 50)
    private String code;

    @Column(name = "platform_id")
    private Integer platformId;

    @Column(name = "url_pattern", length = 500)
    private String urlPattern;

    @Column(name = "is_active")
    private Integer isActive = 1;

    /** java=Java原生爬虫, python=FastAPI委托爬虫 */
    @Column(name = "scraper_type", length = 20)
    private String scraperType = "java";

    /** 并发限制 */
    @Column(name = "concurrent_limit")
    private Integer concurrentLimit = 10;

    /** 请求间隔(毫秒) */
    @Column(name = "rate_limit_ms")
    private Integer rateLimitMs = 2000;

    @Column(name = "created_at", insertable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", insertable = false, updatable = false)
    private LocalDateTime updatedAt;
}
