package com.news;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 短新闻爬取与分析 - Spring Boot 主应用
 * 
 * 核心特性:
 * - 虚拟线程支持的并发爬虫编排 (Java 21)
 * - REST API 业务中台
 * - 定时任务调度
 */
@SpringBootApplication
@EnableScheduling
public class NewsApplication {

    public static void main(String[] args) {
        SpringApplication.run(NewsApplication.class, args);
    }
}
