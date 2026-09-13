package com.news.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 爬虫任务队列实体
 * 对应 scraper_task_queue 表
 * 由 Spring Boot 调度器管理
 */
@Entity
@Table(name = "scraper_task_queue")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ScraperTask {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "source_code", nullable = false, length = 50)
    private String sourceCode;

    @Column(name = "task_type", length = 20)
    private String taskType = "full";  // full / incremental

    @Column(name = "priority")
    private Integer priority = 5;

    @Column(length = 20)
    private String status = "pending";  // pending/running/completed/failed/cancelled

    @Column(name = "scheduled_at")
    private LocalDateTime scheduledAt;

    @Column(name = "started_at")
    private LocalDateTime startedAt;

    @Column(name = "completed_at")
    private LocalDateTime completedAt;

    @Column(name = "items_collected")
    private Integer itemsCollected = 0;

    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    @Column(name = "retry_count")
    private Integer retryCount = 0;

    @Column(name = "max_retries")
    private Integer maxRetries = 3;

    @Column(name = "created_at", insertable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", insertable = false, updatable = false)
    private LocalDateTime updatedAt;
}
