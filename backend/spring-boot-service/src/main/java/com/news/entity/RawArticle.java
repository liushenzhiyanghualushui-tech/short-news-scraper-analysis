package com.news.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 原始文章实体
 * 对应 scraper_raw_articles 表
 */
@Entity
@Table(name = "scraper_raw_articles")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RawArticle {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "source_id", nullable = false)
    private Integer sourceId;

    @Column(name = "source_type", nullable = false)
    private String sourceType;

    @Column(name = "source_name", length = 100)
    private String sourceName;

    @Column(name = "source_code", length = 50)
    private String sourceCode;

    @Column(length = 2000)
    private String url;

    @Column(length = 500)
    private String title;

    @Column(name = "title_en", length = 500)
    private String titleEn;

    @Column(length = 200)
    private String author;

    @Lob
    @Column(columnDefinition = "LONGTEXT")
    private String content;

    @Column(columnDefinition = "TEXT")
    private String description;

    @Column(columnDefinition = "TEXT")
    private String keywords;

    @Column(length = 50)
    private String category;

    @Column(name = "publish_time")
    private LocalDateTime publishTime;

    @Column(name = "platform_id")
    private Integer platformId;

    @Column(name = "rank")
    private Integer rank;

    @Column(name = "crawl_time", nullable = false)
    private LocalDateTime crawlTime;

    @Column(columnDefinition = "JSON")
    private String rawData;

    @Column(length = 20)
    private String status = "pending";

    @Column(name = "created_at", insertable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", insertable = false, updatable = false)
    private LocalDateTime updatedAt;
}
