package com.news.repository;

import com.news.entity.ScraperSource;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface ScraperSourceRepository extends JpaRepository<ScraperSource, Integer> {

    Optional<ScraperSource> findByCode(String code);

    List<ScraperSource> findBySourceTypeAndIsActive(String sourceType, Integer isActive);

    List<ScraperSource> findByIsActiveAndScraperType(Integer isActive, String scraperType);
}
