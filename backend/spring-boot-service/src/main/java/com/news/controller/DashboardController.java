package com.news.controller;

import com.news.dto.ApiResponse;
import com.news.service.NewsService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 仪表盘 API
 */
@RestController
@RequestMapping("/api/dashboard")
public class DashboardController {

    private final NewsService newsService;

    public DashboardController(NewsService newsService) {
        this.newsService = newsService;
    }

    @GetMapping("/stats")
    public ApiResponse<Map<String, Object>> getStats() {
        return ApiResponse.success(newsService.getDashboardStats());
    }
}
