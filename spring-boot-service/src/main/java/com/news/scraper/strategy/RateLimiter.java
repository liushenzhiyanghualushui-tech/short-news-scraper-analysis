package com.news.scraper.strategy;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 速率限制器
 * 
 * 每个域名独立的速率控制，防止触发反爬机制。
 * 使用令牌桶算法。
 */
public class RateLimiter {

    private final Map<String, AtomicLong> lastRequestTime = new ConcurrentHashMap<>();
    private final Map<String, Long> rateLimits = new ConcurrentHashMap<>();

    /**
     * 注册域名速率限制
     */
    public void registerDomain(String domain, long minIntervalMs) {
        rateLimits.put(domain, minIntervalMs);
        lastRequestTime.putIfAbsent(domain, new AtomicLong(0));
    }

    /**
     * 获取令牌（阻塞等待直到可以发起请求）
     */
    public void acquire(String domain) {
        Long minInterval = rateLimits.get(domain);
        if (minInterval == null) {
            return; // 无限制
        }

        AtomicLong lastTime = lastRequestTime.computeIfAbsent(
                domain, k -> new AtomicLong(0));

        long now = System.currentTimeMillis();
        long elapsed = now - lastTime.get();

        if (elapsed < minInterval) {
            try {
                Thread.sleep(minInterval - elapsed);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        lastTime.set(System.currentTimeMillis());
    }

    /**
     * 尝试获取令牌（非阻塞）
     * @return true=可以请求，false=需要等待
     */
    public boolean tryAcquire(String domain) {
        Long minInterval = rateLimits.get(domain);
        if (minInterval == null) return true;

        AtomicLong lastTime = lastRequestTime.computeIfAbsent(
                domain, k -> new AtomicLong(0));

        long now = System.currentTimeMillis();
        return (now - lastTime.get()) >= minInterval;
    }
}
