package com.news.service;

import com.news.entity.ScraperSource;
import com.news.entity.ScraperTask;
import com.news.entity.SpiderLog;
import com.news.repository.ScraperSourceRepository;
import com.news.repository.ScraperTaskRepository;
import com.news.repository.SpiderLogRepository;
import com.news.scraper.ScraperOrchestrator;
import com.news.scraper.ScraperRegistry;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * 爬虫管理服务
 */
@Service
public class ScraperService {

    private final ScraperOrchestrator orchestrator;
    private final ScraperRegistry registry;
    private final ScraperSourceRepository sourceRepo;
    private final SpiderLogRepository logRepo;
    private final ScraperTaskRepository taskRepo;

    public ScraperService(ScraperOrchestrator orchestrator, ScraperRegistry registry,
                          ScraperSourceRepository sourceRepo, SpiderLogRepository logRepo,
                          ScraperTaskRepository taskRepo) {
        this.orchestrator = orchestrator;
        this.registry = registry;
        this.sourceRepo = sourceRepo;
        this.logRepo = logRepo;
        this.taskRepo = taskRepo;
    }

    /** 获取所有爬虫列表 */
    public Map<String, String> listSpiders() {
        return registry.getAllScrapers();
    }

    /** 获取所有来源配置 */
    public List<ScraperSource> listSources() {
        return sourceRepo.findAll();
    }

    /** 启动单个爬虫 */
    public Map<String, Object> startSpider(String sourceCode) {
        return orchestrator.runSingleSource(sourceCode);
    }

    /** 一键全爬 */
    public Map<String, Object> runAll() {
        return orchestrator.runAllScrapers();
    }

    /** 获取爬虫状态 */
    public Map<String, Object> getStatus() {
        return orchestrator.getStatus();
    }

    /** 查询日志 */
    public List<SpiderLog> getLogs(int limit) {
        return logRepo.findAllByOrderByStartTimeDesc(PageRequest.of(0, limit));
    }

    /** 获取任务队列 */
    public List<ScraperTask> getPendingTasks() {
        return taskRepo.findByStatusOrderByPriorityAscScheduledAtAsc("pending");
    }
}
