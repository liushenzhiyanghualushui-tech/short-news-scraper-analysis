package com.news.repository;

import com.news.entity.RawArticle;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

@Repository
public interface RawArticleRepository extends JpaRepository<RawArticle, Long> {

    boolean existsByUrl(String url);

    Page<RawArticle> findBySourceCodeOrderByCrawlTimeDesc(String sourceCode, Pageable pageable);

    @Query("SELECT a FROM RawArticle a WHERE " +
           "(:sourceCode IS NULL OR a.sourceCode = :sourceCode) AND " +
           "(:category IS NULL OR a.category = :category) AND " +
           "(:keyword IS NULL OR a.title LIKE %:keyword% OR a.content LIKE %:keyword%) " +
           "ORDER BY a.crawlTime DESC")
    Page<RawArticle> searchArticles(
            @Param("sourceCode") String sourceCode,
            @Param("category") String category,
            @Param("keyword") String keyword,
            Pageable pageable);

    @Query("SELECT COUNT(a) FROM RawArticle a WHERE a.crawlTime >= :since")
    long countSince(@Param("since") LocalDateTime since);

    @Query("SELECT a.sourceCode, COUNT(a) FROM RawArticle a GROUP BY a.sourceCode")
    List<Object[]> countBySource();

    @Query("SELECT a.category, COUNT(a) FROM RawArticle a WHERE a.category IS NOT NULL GROUP BY a.category")
    List<Object[]> countByCategory();
}
