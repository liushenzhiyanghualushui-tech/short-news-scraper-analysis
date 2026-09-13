package com.news.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.util.List;

/**
 * 爬虫请求DTO
 */
@Data
public class ScrapingRequest {

    /** 单个来源编码 */
    @NotBlank(message = "来源编码不能为空")
    private String sourceCode;

    /** 批量来源编码 */
    private List<String> sourceCodes;

    /** 任务类型 */
    private String taskType = "full";  // full / incremental

    /** 优先级 1-10，数字越小优先级越高 */
    private Integer priority = 5;
}
