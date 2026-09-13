package com.news.repository;

import com.news.entity.SpiderLog;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SpiderLogRepository extends JpaRepository<SpiderLog, Integer> {

    List<SpiderLog> findAllByOrderByStartTimeDesc(Pageable pageable);

    List<SpiderLog> findBySpiderNameOrderByStartTimeDesc(String spiderName, Pageable pageable);
}
