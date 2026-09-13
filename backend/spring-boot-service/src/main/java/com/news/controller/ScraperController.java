package com.news.controller;

import com.news.dto.ApiResponse;
import com.news.dto.ScrapingRequest;
import com.news.entity.ScraperSource;
import com.news.entity.SpiderLog;
import com.news.service.ScraperService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 爬虫管理 API
 */
@RestController
@RequestMapping("/api/spider")
public class ScraperController {

    private final ScraperService scraperService;

    public ScraperController(ScraperService scraperService) {
        this.scraperService = scraperService;
    }

    /** 爬虫列表 */
    @GetMapping("/list")
    public ApiResponse<Map<String, String>> list() {
        return ApiResponse.success(scraperService.listSpiders());
    }

    /** 来源列表 */
    @GetMapping("/sources")
    public ApiResponse<List<ScraperSource>> sources() {
        return ApiResponse.success(scraperService.listSources());
    }

    /** 启动单个爬虫 */
    @PostMapping("/start")
    public ApiResponse<Map<String, Object>> start(@Valid @RequestBody ScrapingRequest request) {
        return ApiResponse.success(scraperService.startSpider(request.getSourceCode()));
    }

    /** 一键全爬 */
    @PostMapping("/run-all")
    public ApiResponse<Map<String, Object>> runAll() {
        return ApiResponse.success(scraperService.runAll());
    }

    /** 爬虫状态 */
    @GetMapping("/status")
    public ApiResponse<Map<String, Object>> status() {
        return ApiResponse.success(scraperService.getStatus());
    }

    /** 日志查询 */
    @GetMapping("/logs")
    public ApiResponse<List<SpiderLog>> logs(
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(scraperService.getLogs(limit));
    }
}
