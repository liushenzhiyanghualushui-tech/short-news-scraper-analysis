package com.news.scraper;

import com.news.entity.ScraperSource;
import com.news.entity.ScraperTask;
import com.news.entity.SpiderLog;
import com.news.repository.ScraperSourceRepository;
import com.news.repository.ScraperTaskRepository;
import com.news.repository.SpiderLogRepository;
import com.news.scraper.strategy.ScraperStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.*;

/**
 * 高并发爬虫编排器 (核心引擎)
 * 
 * 使用 Java 21 虚拟线程实现超高并发爬取。
 * 
 * 架构:
 * ┌──────────────────────────────────────────────────┐
 * │              ScraperOrchestrator                  │
 * │                                                   │
 * │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
 * │  │Java原生爬虫│  │Java原生爬虫│  │FastAPI委托爬虫  │  │
 * │  │ (虚拟线程) │  │ (虚拟线程) │  │ (HTTP调用)    │  │
 * │  │ sina:50   │  │ tencent:40│  │ xinhua/ifeng  │  │
 * │  └──────────┘  └──────────┘  └───────────────┘  │
 * │                                                   │
 * │  所有爬虫并行执行，每个源独立虚拟线程池              │
 * └──────────────────────────────────────────────────┘
 */
@Service
public class ScraperOrchestrator {

    private static final Logger log = LoggerFactory.getLogger(ScraperOrchestrator.class);

    private final ScraperRegistry registry;
    private final FastApiClient fastApiClient;
    private final ScraperSourceRepository sourceRepo;
    private final SpiderLogRepository logRepo;
    private final ScraperTaskRepository taskRepo;
    private final ExecutorService virtualThreadExecutor;

    /** 运行中的任务 */
    private final Map<String, Future<?>> runningTasks = new ConcurrentHashMap<>();

    public ScraperOrchestrator(
            ScraperRegistry registry,
            FastApiClient fastApiClient,
            ScraperSourceRepository sourceRepo,
            SpiderLogRepository logRepo,
            ScraperTaskRepository taskRepo) {
        this.registry = registry;
        this.fastApiClient = fastApiClient;
        this.sourceRepo = sourceRepo;
        this.logRepo = logRepo;
        this.taskRepo = taskRepo;
        this.virtualThreadExecutor = Executors.newVirtualThreadPerTaskExecutor();
    }

    /**
     * 并发执行所有爬虫 (一键全爬)
     * 
     * Java爬虫使用虚拟线程并行执行，
     * Python爬虫通过FastAPI异步调用。
     * 
     * @return 执行结果汇总
     */
    public Map<String, Object> runAllScrapers() {
        log.info("🚀🚀🚀 启动全量爬取任务");
        long startTime = System.currentTimeMillis();

        Map<String, Object> results = new ConcurrentHashMap<>();
        List<CompletableFuture<Void>> allFutures = new ArrayList<>();

        // ---- 阶段1: 并行启动所有Java爬虫 ----
        Set<String> javaSources = registry.getJavaSources();
        for (String sourceCode : javaSources) {
            CompletableFuture<Void> future = CompletableFuture.runAsync(() -> {
                Map<String, Object> result = runSingleJavaScraper(sourceCode);
                results.put(sourceCode, result);
            }, virtualThreadExecutor);
            allFutures.add(future);
        }
        log.info("   Java爬虫已调度: {} 个来源 (虚拟线程)", javaSources.size());

        // ---- 阶段2: 并行启动所有Python爬虫 (异步调用FastAPI) ----
        Set<String> pythonSources = registry.getPythonSources();
        for (String sourceCode : pythonSources) {
            CompletableFuture<Void> future = CompletableFuture.runAsync(() -> {
                Map<String, Object> result = runSinglePythonScraper(sourceCode);
                results.put(sourceCode, result);
            }, virtualThreadExecutor);
            allFutures.add(future);
        }
        log.info("   Python爬虫已调度: {} 个来源 (FastAPI)", pythonSources.size());

        // ---- 等待所有任务完成 ----
        try {
            CompletableFuture.allOf(allFutures.toArray(new CompletableFuture[0]))
                    .get(10, TimeUnit.MINUTES);
        } catch (TimeoutException e) {
            log.warn("部分爬虫超时未完成");
            results.put("_timeout", true);
        } catch (Exception e) {
            log.error("爬虫编排异常: {}", e.getMessage());
            results.put("_error", e.getMessage());
        }

        long duration = (System.currentTimeMillis() - startTime) / 1000;
        long totalItems = results.values().stream()
                .filter(m -> m instanceof Map && ((Map<?, ?>) m).containsKey("items_count"))
                .mapToLong(m -> ((Number) ((Map<?, ?>) m).get("items_count")).longValue())
                .sum();

        results.put("_total_duration_seconds", duration);
        results.put("_total_items", totalItems);
        results.put("_sources_count", javaSources.size() + pythonSources.size());

        log.info("🏁 全量爬取完成: {} 条 / {} 个来源 / {} 秒",
                totalItems, javaSources.size() + pythonSources.size(), duration);

        return results;
    }

    /**
     * 执行单个来源爬虫 (路由到Java或Python)
     */
    public Map<String, Object> runSingleSource(String sourceCode) {
        String type = registry.getScraperType(sourceCode);
        return switch (type) {
            case "java" -> runSingleJavaScraper(sourceCode);
            case "python" -> runSinglePythonScraper(sourceCode);
            default -> Map.of("success", false, "error", "未知来源: " + sourceCode);
        };
    }

    /**
     * 执行 Java 原生爬虫
     */
    private Map<String, Object> runSingleJavaScraper(String sourceCode) {
        long startTime = System.currentTimeMillis();
        Optional<ScraperSource> sourceOpt = sourceRepo.findByCode(sourceCode);

        if (sourceOpt.isEmpty()) {
            return Map.of("success", false, "error", "来源配置不存在: " + sourceCode);
        }

        ScraperSource source = sourceOpt.get();
        ScraperStrategy strategy = registry.getJavaStrategy(sourceCode);
        if (strategy == null) {
            return Map.of("success", false, "error", "无Java策略: " + sourceCode);
        }

        // 记录日志
        SpiderLog spiderLog = SpiderLog.builder()
                .spiderName(strategy.getName())
                .sourceId(source.getId())
                .startTime(LocalDateTime.now())
                .status("running")
                .executor("java")
                .build();
        spiderLog = logRepo.save(spiderLog);

        try {
            List<Map<String, Object>> items = strategy.scrape(source);
            long duration = (System.currentTimeMillis() - startTime) / 1000;

            // 更新日志
            spiderLog.setEndTime(LocalDateTime.now());
            spiderLog.setStatus("success");
            spiderLog.setItemsCount(items.size());
            spiderLog.setDuration((int) duration);
            logRepo.save(spiderLog);

            log.info("✅ [JAVA] {} : {} 条 / {} 秒", sourceCode, items.size(), duration);

            return Map.of(
                    "success", true,
                    "source_code", sourceCode,
                    "items_count", items.size(),
                    "duration_seconds", duration,
                    "executor", "java"
            );
        } catch (Exception e) {
            long duration = (System.currentTimeMillis() - startTime) / 1000;
            spiderLog.setEndTime(LocalDateTime.now());
            spiderLog.setStatus("failed");
            spiderLog.setErrorMessage(e.getMessage());
            spiderLog.setDuration((int) duration);
            logRepo.save(spiderLog);

            log.error("❌ [JAVA] {} 失败: {}", sourceCode, e.getMessage());
            return Map.of("success", false, "error", e.getMessage(), "duration_seconds", duration);
        }
    }

    /**
     * 执行 Python 爬虫 (委托 FastAPI)
     */
    private Map<String, Object> runSinglePythonScraper(String sourceCode) {
        long startTime = System.currentTimeMillis();

        log.info("🐍 [Python] 委托 FastAPI 执行爬虫: {}", sourceCode);

        // 记录日志
        SpiderLog spiderLog = SpiderLog.builder()
                .spiderName(sourceCode)
                .startTime(LocalDateTime.now())
                .status("running")
                .executor("python")
                .build();
        spiderLog = logRepo.save(spiderLog);

        try {
            Map<String, Object> fastApiResult = fastApiClient.startSpider(sourceCode);
            long duration = (System.currentTimeMillis() - startTime) / 1000;

            spiderLog.setEndTime(LocalDateTime.now());
            if ("completed".equals(fastApiResult.get("status"))) {
                spiderLog.setStatus("success");
                spiderLog.setItemsCount(
                        fastApiResult.containsKey("result") ? 
                        extractItemCount(fastApiResult.get("result")) : 0);
            } else {
                spiderLog.setStatus("failed");
            }
            spiderLog.setDuration((int) duration);
            logRepo.save(spiderLog);

            log.info("🐍 [Python] {} 完成: {} / {} 秒", sourceCode, 
                    fastApiResult.getOrDefault("status", "unknown"), duration);

            Map<String, Object> result = new HashMap<>(fastApiResult);
            result.put("source_code", sourceCode);
            result.put("duration_seconds", duration);
            result.put("executor", "python");
            return result;

        } catch (Exception e) {
            long duration = (System.currentTimeMillis() - startTime) / 1000;
            spiderLog.setEndTime(LocalDateTime.now());
            spiderLog.setStatus("failed");
            spiderLog.setErrorMessage(e.getMessage());
            spiderLog.setDuration((int) duration);
            logRepo.save(spiderLog);

            return Map.of("success", false, "error", e.getMessage(), "duration_seconds", duration);
        }
    }

    @SuppressWarnings("unchecked")
    private int extractItemCount(Object result) {
        if (result instanceof Map) {
            Object count = ((Map<String, Object>) result).get("items_count");
            if (count instanceof Number) return ((Number) count).intValue();
        }
        return 0;
    }

    /** 获取运行状态 */
    public Map<String, Object> getStatus() {
        Map<String, Object> status = new LinkedHashMap<>();
        status.put("running_tasks", runningTasks.size());
        status.put("java_sources", registry.getJavaSources());
        status.put("python_sources", registry.getPythonSources());
        status.put("fastapi_healthy", fastApiClient.isHealthy());
        return status;
    }
}
