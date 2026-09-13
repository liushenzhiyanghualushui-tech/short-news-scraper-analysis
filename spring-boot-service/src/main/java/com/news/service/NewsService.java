package com.news.service;

import com.news.entity.RawArticle;
import com.news.repository.RawArticleRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.*;

/**
 * 新闻管理服务
 */
@Service
public class NewsService {

    private final RawArticleRepository articleRepo;

    public NewsService(RawArticleRepository articleRepo) {
        this.articleRepo = articleRepo;
    }

    public Page<RawArticle> listArticles(String sourceCode, String category,
                                          String keyword, int page, int size) {
        return articleRepo.searchArticles(
                sourceCode, category, keyword,
                PageRequest.of(page, size));
    }

    public Optional<RawArticle> getArticle(Long id) {
        return articleRepo.findById(id);
    }

    public Map<String, Object> getDashboardStats() {
        Map<String, Object> stats = new LinkedHashMap<>();

        // 总文章数
        stats.put("total_articles", articleRepo.count());

        // 24小时内新增
        long today = articleRepo.countSince(LocalDateTime.now().minusHours(24));
        stats.put("articles_24h", today);

        // 按来源统计
        List<Object[]> bySource = articleRepo.countBySource();
        Map<String, Long> sourceStats = new LinkedHashMap<>();
        for (Object[] row : bySource) {
            sourceStats.put((String) row[0], (Long) row[1]);
        }
        stats.put("by_source", sourceStats);

        // 按分类统计
        List<Object[]> byCategory = articleRepo.countByCategory();
        Map<String, Long> categoryStats = new LinkedHashMap<>();
        for (Object[] row : byCategory) {
            categoryStats.put((String) row[0], (Long) row[1]);
        }
        stats.put("by_category", categoryStats);

        return stats;
    }

    public boolean urlExists(String url) {
        return articleRepo.existsByUrl(url);
    }
}
