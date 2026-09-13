package com.news.scraper;

import com.news.entity.ScraperSource;
import com.news.scraper.strategy.ScraperStrategy;
import com.news.entity.ScraperSource;
import org.springframework.stereotype.Component;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 爬虫注册中心
 * 管理所有爬虫策略实例，区分 Java原生 和 Python委托
 */
@Component
public class ScraperRegistry {

    private final Map<String, ScraperStrategy> javaStrategies = new ConcurrentHashMap<>();
    private final Set<String> pythonScrapers = ConcurrentHashMap.newKeySet();

    public ScraperRegistry(List<ScraperStrategy> strategies) {
        for (ScraperStrategy s : strategies) {
            javaStrategies.put(s.getSourceCode(), s);
        }
        // Python委托爬虫 (重型/浏览器类)
        pythonScrapers.addAll(Set.of("xinhua", "ifeng", "cankaoxiaoxi", "netease_selenium"));
    }

    /** 获取所有已注册的爬虫 */
    public Map<String, String> getAllScrapers() {
        Map<String, String> all = new LinkedHashMap<>();
        javaStrategies.forEach((k, v) -> all.put(k, "java"));
        pythonScrapers.forEach(k -> all.put(k, "python"));
        return all;
    }

    /** 判断爬虫类型 */
    public String getScraperType(String sourceCode) {
        if (javaStrategies.containsKey(sourceCode)) return "java";
        if (pythonScrapers.contains(sourceCode)) return "python";
        return "unknown";
    }

    /** 获取Java爬虫策略 */
    public ScraperStrategy getJavaStrategy(String sourceCode) {
        return javaStrategies.get(sourceCode);
    }

    /** 获取Java爬虫源码列表 */
    public Set<String> getJavaSources() {
        return javaStrategies.keySet();
    }

    /** 获取Python爬虫源码列表 */
    public Set<String> getPythonSources() {
        return pythonScrapers;
    }
}
