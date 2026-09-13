package com.news.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.Map;

@RestController
public class HealthController {

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of(
                "status", "healthy",
                "service", "spring-boot-business",
                "version", "2.0.0",
                "timestamp", LocalDateTime.now().toString()
        );
    }
}
