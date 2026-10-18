package com.news.controller;

import com.news.dto.ApiResponse;
import com.news.entity.RawArticle;
import com.news.service.NewsService;
import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 新闻管理 API
 */
@RestController
@RequestMapping("/api/news")
public class NewsController {

    private final NewsService newsService;

    public NewsController(NewsService newsService) {
        this.newsService = newsService;
    }

    @GetMapping("/list")
    public ApiResponse<List<RawArticle>> listArticles(
            @RequestParam(defaultValue = "") String sourceCode,
            @RequestParam(defaultValue = "") String category,
            @RequestParam(defaultValue = "") String keyword,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        Page<RawArticle> articles = newsService.listArticles(
                sourceCode.isEmpty() ? null : sourceCode,
                category.isEmpty() ? null : category,
                keyword.isEmpty() ? null : keyword,
                page, size);
        return ApiResponse.success(articles.getContent(), articles.getTotalElements());
    }

    @GetMapping("/detail/{id}")
    public ApiResponse<RawArticle> getDetail(@PathVariable Long id) {
        return newsService.getArticle(id)
                .map(ApiResponse::success)
                .orElse(ApiResponse.error(404, "文章不存在"));
    }
}
