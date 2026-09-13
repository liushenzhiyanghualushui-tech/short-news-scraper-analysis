/**
 * API 模块
 * 处理与后端 API 的通信
 */

const API_BASE = '/api';

// 通用请求配置
const requestConfig = {
    timeout: 300000,  // 5分钟超时，因为顺序执行爬虫可能需要较长时间
    headers: {
        'Content-Type': 'application/json'
    }
};

// 封装 fetch 请求
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    
    const config = {
        ...requestConfig,
        ...options,
        headers: {
            ...requestConfig.headers,
            ...options.headers
        }
    };

    try {
        const response = await fetch(url, config);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || '请求失败');
        }
        
        return data;
    } catch (error) {
        console.error('API 请求错误:', error);
        throw error;
    }
}

// ==================== 仪表盘 API ====================

async function getDashboardStats() {
    return apiRequest('/dashboard/stats');
}

// ==================== 新闻 API ====================

async function getNewsList(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.type) queryParams.append('type', params.type);
    if (params.source) queryParams.append('source', params.source);
    if (params.category) queryParams.append('category', params.category);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.page) queryParams.append('page', params.page);
    
    const query = queryParams.toString();
    return apiRequest(`/news/list${query ? '?' + query : ''}`);
}

async function getNewsDetail(articleId) {
    return apiRequest(`/news/detail/${articleId}`);
}

// ==================== 来源 API ====================

async function getSources(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.type) queryParams.append('type', params.type);
    
    const query = queryParams.toString();
    return apiRequest(`/sources${query ? '?' + query : ''}`);
}

// ==================== 日志 API ====================

async function getLogs(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.status) queryParams.append('status', params.status);
    
    const query = queryParams.toString();
    return apiRequest(`/logs${query ? '?' + query : ''}`);
}

async function getLogStats() {
    return apiRequest('/logs/stats');
}

// ==================== 爬虫控制 API ====================

async function getSpiderList() {
    return apiRequest('/spider/list');
}

async function startSpider(spiderName, spiderType = 'domestic') {
    return apiRequest('/spider/start', {
        method: 'POST',
        body: JSON.stringify({ spider_name: spiderName, spider_type: spiderType })
    });
}

async function stopSpider(spiderName) {
    return apiRequest('/spider/stop', {
        method: 'POST',
        body: JSON.stringify({ spider_name: spiderName })
    });
}

async function runAllSpiders(spiderNames = []) {
    return apiRequest('/spider/run-all', {
        method: 'POST',
        body: JSON.stringify({ spider_names: spiderNames })
    });
}

// ==================== 系统 API ====================

async function healthCheck() {
    return apiRequest('/health');
}

// ==================== 管理员 API ====================

// 数据管理
async function getAdminDataStats() {
    return apiRequest('/admin/data/stats');
}

async function postAdminDataClean(config = {}) {
    return apiRequest('/admin/data/clean', {
        method: 'POST',
        body: JSON.stringify(config)
    });
}

async function getAdminWordFrequency(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.top_k) queryParams.append('top_k', params.top_k);
    if (params.category) queryParams.append('category', params.category);
    const query = queryParams.toString();
    return apiRequest(`/admin/data/word-frequency${query ? '?' + query : ''}`);
}

// 模型管理
async function getAdminModelStatus() {
    return apiRequest('/admin/model/status');
}

async function getAdminModelHistory() {
    return apiRequest('/admin/model/history');
}

async function deleteAdminModelHistory() {
    return apiRequest('/admin/model/history', {
        method: 'DELETE'
    });
}

async function postAdminTrainModel(config = {}) {
    return apiRequest('/admin/model/train', {
        method: 'POST',
        body: JSON.stringify(config)
    });
}

async function postAdminStopTrainModel() {
    return apiRequest('/admin/model/stop', {
        method: 'POST'
    });
}

async function postAdminEvaluateModel() {
    return apiRequest('/admin/model/evaluate', {
        method: 'POST'
    });
}

async function postAdminEvaluateSavedModel(filepath) {
    return apiRequest('/admin/model/evaluate/saved', {
        method: 'POST',
        body: JSON.stringify({ filepath: filepath })
    });
}

async function postAdminPredict(texts) {
    return apiRequest('/admin/model/predict', {
        method: 'POST',
        body: JSON.stringify({ texts: texts })
    });
}

async function postAdminSaveModel(filename) {
    return apiRequest('/admin/model/save', {
        method: 'POST',
        body: JSON.stringify({ filename: filename })
    });
}

async function postAdminLoadModel(filepath) {
    return apiRequest('/admin/model/load', {
        method: 'POST',
        body: JSON.stringify({ filepath: filepath })
    });
}

async function postAdminApplyModel() {
    return apiRequest('/admin/model/apply', {
        method: 'POST'
    });
}

async function getAdminApplyStatus() {
    return apiRequest('/admin/model/apply/status');
}

async function deleteAdminModelClear(options = {}) {
    const includePretrained = !!(options && options.includePretrained);
    const query = includePretrained ? '?include_pretrained=1' : '';
    return apiRequest(`/admin/model/clear${query}`, {
        method: 'DELETE'
    });
}

// 可视化
async function getAdminVisualizeDataQuality() {
    return apiRequest('/admin/visualize/data-quality');
}

async function getAdminVisualizeCollectionStats() {
    return apiRequest('/admin/visualize/collection-stats');
}

// ==================== 前台可视化 API ====================

async function getVisualizeCategoryHourMatrix(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append('days', params.days);
    const query = queryParams.toString();
    return apiRequest(`/visualize/category-hour-matrix${query ? '?' + query : ''}`);
}

async function getVisualizeContentLengthRatio(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append('days', params.days);
    if (params.threshold) queryParams.append('threshold', params.threshold);
    const query = queryParams.toString();
    return apiRequest(`/visualize/content-length-ratio${query ? '?' + query : ''}`);
}

async function getVisualizeSourceShare(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append('days', params.days);
    if (params.top_n) queryParams.append('top_n', params.top_n);
    if (params.category) queryParams.append('category', params.category);
    if (params.date) queryParams.append('date', params.date);
    const query = queryParams.toString();
    return apiRequest(`/visualize/source-share${query ? '?' + query : ''}`);
}

async function getVisualizeKeywordTrends(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append('days', params.days);
    if (params.category) queryParams.append('category', params.category);
    if (params.top_k) queryParams.append('top_k', params.top_k);
    const query = queryParams.toString();
    return apiRequest(`/visualize/keyword-trends${query ? '?' + query : ''}`);
}

async function getVisualizeCategoryTrends(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append('days', params.days);
    if (params.top_n) queryParams.append('top_n', params.top_n);
    const query = queryParams.toString();
    return apiRequest(`/visualize/category-trends${query ? '?' + query : ''}`);
}

async function getVisualizeInfoDensity(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append('days', params.days);
    if (params.top_n) queryParams.append('top_n', params.top_n);
    const query = queryParams.toString();
    return apiRequest(`/visualize/info-density${query ? '?' + query : ''}`);
}

async function getVisualizeRepresentativeNews(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.category) queryParams.append('category', params.category);
    if (params.date) queryParams.append('date', params.date);
    if (params.limit) queryParams.append('limit', params.limit);
    const query = queryParams.toString();
    return apiRequest(`/visualize/representative-news${query ? '?' + query : ''}`);
}

async function getVisualizeCategorySimilarity(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append('days', params.days);
    if (params.top_words) queryParams.append('top_words', params.top_words);
    if (params.min_count) queryParams.append('min_count', params.min_count);
    const query = queryParams.toString();
    return apiRequest(`/visualize/category-similarity${query ? '?' + query : ''}`);
}

// ==================== NLP API ====================

async function getNlpModels() {
    return apiRequest('/admin/nlp/models');
}

async function getNlpSettings() {
    return apiRequest('/admin/nlp/settings');
}

async function postNlpSettings(config = {}) {
    return apiRequest('/admin/nlp/settings', {
        method: 'POST',
        body: JSON.stringify(config)
    });
}

async function postNlpSentimentRun(config = {}) {
    return apiRequest('/admin/nlp/sentiment/run', {
        method: 'POST',
        body: JSON.stringify(config)
    });
}

async function getNlpSentimentStatus() {
    return apiRequest('/admin/nlp/sentiment/status');
}

async function getArticleSentiment(articleId) {
    return apiRequest(`/articles/${articleId}/sentiment`);
}

async function postArticleSentimentAnalyze(articleId, payload = {}) {
    return apiRequest(`/articles/${articleId}/sentiment/analyze`, {
        method: 'POST',
        body: JSON.stringify(payload || {})
    });
}

async function postNlpEventsRun(config = {}) {
    return apiRequest('/admin/nlp/events/run', {
        method: 'POST',
        body: JSON.stringify(config)
    });
}

async function getNlpEventsStatus() {
    return apiRequest('/admin/nlp/events/status');
}

async function getEventsList(params = {}) {
    const queryParams = new URLSearchParams();
    if (params.days) queryParams.append('days', params.days);
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.min_article_count) queryParams.append('min_article_count', params.min_article_count);
    const query = queryParams.toString();
    return apiRequest(`/events${query ? '?' + query : ''}`);
}

async function getEventDetail(eventId) {
    return apiRequest(`/events/${eventId}`);
}

// 导出 API 模块
window.API = {
    dashboard: {
        stats: getDashboardStats
    },
    visualize: {
        categoryHourMatrix: getVisualizeCategoryHourMatrix,
        contentLengthRatio: getVisualizeContentLengthRatio,
        sourceShare: getVisualizeSourceShare,
        keywordTrends: getVisualizeKeywordTrends,
        categoryTrends: getVisualizeCategoryTrends,
        infoDensity: getVisualizeInfoDensity,
        representativeNews: getVisualizeRepresentativeNews,
        categorySimilarity: getVisualizeCategorySimilarity
    },
    news: {
        list: getNewsList,
        detail: getNewsDetail
    },
    sources: {
        get: getSources
    },
    logs: {
        list: getLogs,
        stats: getLogStats
    },
    spider: {
        list: getSpiderList,
        start: startSpider,
        stop: stopSpider,
        runAll: runAllSpiders
    },
    system: {
        health: healthCheck
    },
    nlp: {
        modelsList: getNlpModels,
        settingsGet: getNlpSettings,
        settingsUpdate: postNlpSettings,
        sentimentRun: postNlpSentimentRun,
        sentimentStatus: getNlpSentimentStatus,
        articleSentiment: getArticleSentiment,
        articleSentimentAnalyze: postArticleSentimentAnalyze,
        eventsRun: postNlpEventsRun,
        eventsStatus: getNlpEventsStatus,
        eventsList: getEventsList,
        eventDetail: getEventDetail
    },
    admin: {
        // 数据管理
        dataStats: getAdminDataStats,
        dataClean: postAdminDataClean,
        wordFrequency: getAdminWordFrequency,
        // 模型管理
        modelStatus: getAdminModelStatus,
        modelHistory: getAdminModelHistory,
        clearModelHistory: deleteAdminModelHistory,
        trainModel: postAdminTrainModel,
        stopTrainModel: postAdminStopTrainModel,
        evaluateModel: postAdminEvaluateModel,
        evaluateSavedModel: postAdminEvaluateSavedModel,
        predict: postAdminPredict,
        saveModel: postAdminSaveModel,
        loadModel: postAdminLoadModel,
        applyModel: postAdminApplyModel,
        applyStatus: getAdminApplyStatus,
        clearModel: deleteAdminModelClear,
        // 可视化
        visualizeDataQuality: getAdminVisualizeDataQuality,
        visualizeCollectionStats: getAdminVisualizeCollectionStats
    }
};
