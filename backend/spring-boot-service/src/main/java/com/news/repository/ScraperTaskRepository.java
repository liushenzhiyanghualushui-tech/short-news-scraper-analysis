package com.news.repository;

import com.news.entity.ScraperTask;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ScraperTaskRepository extends JpaRepository<ScraperTask, Long> {

    List<ScraperTask> findByStatusOrderByPriorityAscScheduledAtAsc(String status);

    List<ScraperTask> findBySourceCodeOrderByCreatedAtDesc(String sourceCode);
}
