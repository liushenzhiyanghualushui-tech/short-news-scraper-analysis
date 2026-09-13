package com.news.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 爬虫执行日志实体
 * 对应 scraper_spider_logs 表
 */
@Entity
@Table(name = "scraper_spider_logs")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SpiderLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(name = "spider_name", nullable = false, length = 100)
    private String spiderName;

    @Column(name = "source_id")
    private Integer sourceId;

    @Column(name = "start_time", nullable = false)
    private LocalDateTime startTime;

    @Column(name = "end_time")
    private LocalDateTime endTime;

    @Column(length = 20)
    private String status;  // running/success/failed

    @Column(name = "items_count")
    private Integer itemsCount = 0;

    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    private Integer duration;  // 秒

    /** 执行引擎: java / python */
    @Column(length = 20)
    private String executor = "java";

    @Column(name = "created_at", insertable = false, updatable = false)
    private LocalDateTime createdAt;
}
