/**
 * 主应用逻辑
 * 新闻数据采集系统 Web 管理平台
 */

// 全局状态
let currentPage = 'dashboard';
let currentNewsType = '';
let currentSource = '';  // 当前选中的媒体来源
let currentArticleId = null;  // 当前查看的文章ID

let analysisSourceShareChart = null;
let analysisInfoDensityChart = null;
let analysisCategoryTrendsChart = null;
let analysisCategoryHourMatrixChart = null;
let analysisCategorySimilarityChart = null;
let analysisDrillSourceShareChart = null;
let analysisDrillKeywordTrendsChart = null;
let analysisDrilldown = null;
let analysisControlsBound = false;
let analysisResizeHandlerBound = false;

let keywordTrendsChart = null;
let keywordTrendsResizeHandlerBound = false;

// 来源类型配置
const sourceTypeConfig = {
    domestic: { name: '国内', class: 'domestic', icon: 'fas fa-home' }
};

// 分页状态管理
let newsState = {
    page: 1,
    limit: 20,
    isLoading: false,
    hasMore: true
};

let logsState = {
    page: 1,
    limit: 20,
    isLoading: false,
    hasMore: true
};

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initSidebarToggle();
    initRouter();  // 初始化路由
    initScrollListeners(); // 初始化滚动监听
    loadDashboard();
});

// ==================== 路由控制 ====================

function initRouter() {
    // 监听 hash 变化
    window.addEventListener('hashchange', handleRoute);

    // 初始路由
    handleRoute();
}

function handleRoute() {
    const hash = window.location.hash;

    if (hash.startsWith('#news/detail/')) {
        const articleId = hash.replace('#news/detail/', '');
        navigateToNewsDetail(articleId);
    } else if (hash.startsWith('#')) {
        const page = hash.substring(1);
        if (['dashboard', 'analysis', 'news', 'logs', 'word-cloud', 'admin'].includes(page)) {
            navigateTo(page);
        } else {
            navigateTo('dashboard');
        }
    } else {
        navigateTo('dashboard');
    }
}

function navigateToNewsDetail(articleId) {
    // 更新导航状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // 更新页面显示
    document.querySelectorAll('.page').forEach(p => {
        p.classList.remove('active');
    });
    document.getElementById('page-news-detail').classList.add('active');

    // 更新面包屑
    document.querySelector('.current-page').textContent = '文章详情';

    currentPage = 'news-detail';
    currentArticleId = articleId;

    // 加载文章详情
    loadNewsDetail(articleId);
}

// ==================== 滚动监听 ====================

function initScrollListeners() {
    // 为新闻列表和分类列表的容器添加滚动监听
    const containers = document.querySelectorAll('.table-container');
    
    containers.forEach(container => {
        container.addEventListener('scroll', debounce((e) => {
            const { scrollTop, scrollHeight, clientHeight } = e.target;
            
            // 距离底部 50px 时触发加载
            if (scrollTop + clientHeight >= scrollHeight - 50) {
                if (currentPage === 'news') {
                    loadNews(true);
                } else if (currentPage === 'logs') {
                    loadClassifiedNews(true);
                }
            }
        }, 200));
    });
}

// ==================== 导航控制 ====================

function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    // 清除 hash 路由
    if (window.location.hash.startsWith('#news/detail/')) {
        window.location.hash = '';
        return;
    }

    // 如果离开仪表盘页面，停止自动刷新
    if (currentPage === 'dashboard' && page !== 'dashboard') {
        stopDashboardAutoRefresh();
    }

    if (currentPage === 'analysis' && page !== 'analysis') {
        disposeAnalysisCharts();
    }

    if (currentPage === 'word-cloud' && page !== 'word-cloud') {
        stopCategoryWordBarrage();
        disposeKeywordTrendsChart();
    }

    // 更新导航状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });

    // 更新页面显示
    document.querySelectorAll('.page').forEach(p => {
        p.classList.remove('active');
    });
    document.getElementById(`page-${page}`).classList.add('active');

    // 更新面包屑
    const pageNames = {
        dashboard: '仪表盘',
        analysis: '新闻分析',
        news: '新闻采集',
        logs: '新闻分类',
        'word-cloud': '词云分析',
        'news-detail': '文章详情',
        admin: '系统管理'
    };
    document.querySelector('.current-page').textContent = pageNames[page] || page;

    currentPage = page;

    // 处理管理员页面侧边栏显示
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebarToggle');
    if (page === 'admin') {
        sidebar.style.display = 'none';
        toggleBtn.style.display = 'none';
        document.querySelector('.main-content').style.marginLeft = '0';
    } else {
        sidebar.style.display = 'block';
        toggleBtn.style.display = 'block';
        document.querySelector('.main-content').style.marginLeft = '';
    }

    // 加载对应页面数据
    switch (page) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'analysis':
            loadAnalysisPage();
            break;
        case 'news':
            loadNews();
            break;
        case 'logs':
            loadCategories().then(() => loadClassifiedNews());
            break;
        case 'word-cloud':
            loadWordCloudPage();
            break;
        case 'admin':
            refreshAdminPage();
            break;
    }
}

// ==================== 侧边栏控制 ====================

function initSidebarToggle() {
    const toggleBtn = document.getElementById('sidebarToggle');
    
    toggleBtn.addEventListener('click', () => {
        toggleSidebar();
    });
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.querySelector('.main-content');
    
    sidebar.classList.toggle('collapsed');
    sidebar.classList.toggle('open');
    mainContent.classList.toggle('expanded');
    
    isSidebarCollapsed = !isSidebarCollapsed;
}

// ==================== 仪表盘页面 ====================

// 仪表盘自动刷新定时器
let dashboardRefreshTimer = null;
const DASHBOARD_REFRESH_INTERVAL = 3000; // 每3秒刷新一次

function startDashboardAutoRefresh() {
    // 停止现有的定时器
    stopDashboardAutoRefresh();
    
    // 启动新的定时器
    dashboardRefreshTimer = setInterval(() => {
        if (currentPage === 'dashboard') {
            // 只在仪表盘页面时刷新
            refreshDashboardData();
        }
    }, DASHBOARD_REFRESH_INTERVAL);
}

function stopDashboardAutoRefresh() {
    if (dashboardRefreshTimer) {
        clearInterval(dashboardRefreshTimer);
        dashboardRefreshTimer = null;
    }
}

// 刷新仪表盘数据（不重新加载整个页面）
async function refreshDashboardData() {
    try {
        const stats = await API.dashboard.stats();
        const logStats = await API.logs.stats();

        if (stats.success) {
            updateDashboardStats(stats.data);
        }

        if (logStats.success) {
            updateTodayStats(logStats.data);
        }
    } catch (error) {
        console.error('刷新仪表盘数据失败:', error);
    }
}

async function loadDashboard() {
    try {
        const stats = await API.dashboard.stats();
        const logStats = await API.logs.stats();

        if (stats.success) {
            updateDashboardStats(stats.data);
        }

        if (logStats.success) {
            updateTodayStats(logStats.data);
        }

        // 加载爬虫列表
        loadSpiderList();

        // 加载最近活动
        loadRecentActivity();

        // 启动自动刷新
        startDashboardAutoRefresh();

    } catch (error) {
        console.error('加载仪表盘数据失败:', error);
        showToast('error', '加载失败', '无法获取仪表盘数据');
    }
}

// ==================== 新闻分析页面 ====================

function ensureAnalysisResizeHandler() {
    if (analysisResizeHandlerBound) return;
    window.addEventListener('resize', () => {
        if (analysisSourceShareChart) analysisSourceShareChart.resize();
        if (analysisInfoDensityChart) analysisInfoDensityChart.resize();
        if (analysisCategoryTrendsChart) analysisCategoryTrendsChart.resize();
        if (analysisCategoryHourMatrixChart) analysisCategoryHourMatrixChart.resize();
        if (analysisCategorySimilarityChart) analysisCategorySimilarityChart.resize();
        if (analysisDrillSourceShareChart) analysisDrillSourceShareChart.resize();
        if (analysisDrillKeywordTrendsChart) analysisDrillKeywordTrendsChart.resize();
    });
    analysisResizeHandlerBound = true;
}

function disposeAnalysisCharts() {
    analysisSourceShareChart = disposeChartInstance(analysisSourceShareChart);
    analysisInfoDensityChart = disposeChartInstance(analysisInfoDensityChart);
    analysisCategoryTrendsChart = disposeChartInstance(analysisCategoryTrendsChart);
    analysisCategoryHourMatrixChart = disposeChartInstance(analysisCategoryHourMatrixChart);
    analysisCategorySimilarityChart = disposeChartInstance(analysisCategorySimilarityChart);
    analysisDrillSourceShareChart = disposeChartInstance(analysisDrillSourceShareChart);
    analysisDrillKeywordTrendsChart = disposeChartInstance(analysisDrillKeywordTrendsChart);
}

function getAnalysisParams() {
    const daysSelect = document.getElementById('analysis-days');
    const topNSelect = document.getElementById('analysis-topn');

    const days = parseInt(daysSelect?.value || '30', 10);
    const topN = parseInt(topNSelect?.value || '8', 10);

    return {
        days: Number.isFinite(days) ? days : 30,
        top_n: Number.isFinite(topN) ? topN : 8
    };
}

function bindAnalysisControls() {
    if (analysisControlsBound) return;

    const daysSelect = document.getElementById('analysis-days');
    const topNSelect = document.getElementById('analysis-topn');
    const refreshBtn = document.getElementById('btn-refresh-analysis');

    if (daysSelect) {
        daysSelect.addEventListener('change', () => {
            loadAnalysisAnalytics();
        });
    }
    if (topNSelect) {
        topNSelect.addEventListener('change', () => {
            loadAnalysisAnalytics();
        });
    }
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadAnalysisAnalytics();
        });
    }

    analysisControlsBound = true;
}

function renderAnalysisSourceShare(data) {
    const container = document.getElementById('analysis-chart-source-share');
    if (!container) return;
    if (!container.offsetWidth || !container.offsetHeight) return;

    const items = (data && data.items) ? data.items : [];
    if (!items.length) {
        analysisSourceShareChart = setChartPlaceholder(container, analysisSourceShareChart, 'fas fa-chart-pie', '暂无数据');
        return;
    }

    analysisSourceShareChart = ensureChart(container, analysisSourceShareChart);
    const option = {
        tooltip: { trigger: 'item' },
        legend: { type: 'scroll', bottom: 0 },
        series: [
            {
                type: 'pie',
                radius: ['45%', '70%'],
                avoidLabelOverlap: true,
                itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
                label: { show: true, formatter: '{b}\n{d}%' },
                labelLine: { show: true },
                data: items
            }
        ]
    };
    analysisSourceShareChart.setOption(option, true);
}

function renderAnalysisInfoDensity(data) {
    const container = document.getElementById('analysis-chart-info-density');
    if (!container) return;
    if (!container.offsetWidth || !container.offsetHeight) return;

    const items = Array.isArray(data?.items) ? data.items : [];
    if (!items.length) {
        analysisInfoDensityChart = setChartPlaceholder(container, analysisInfoDensityChart, 'fas fa-chart-column', '暂无数据');
        return;
    }

    const categories = items.map(i => i.category);
    const values = items.map(i => Number(i.avg_density || 0));
    analysisInfoDensityChart = ensureChart(container, analysisInfoDensityChart);
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter(params) {
                const p = params?.[0];
                const idx = p?.dataIndex ?? 0;
                const raw = items[idx] || {};
                const density = Number(raw.avg_density || 0);
                const count = Number(raw.count || 0);
                const avgTokens = Number(raw.avg_tokens || 0);
                const avgUniqueTokens = Number(raw.avg_unique_tokens || 0);
                const avgChars = Number(raw.avg_chars || 0);
                return [
                    `${escapeHtml(categories[idx] || '')}`,
                    `密度：${(density * 100).toFixed(1)}%`,
                    `样本：${count}`,
                    `平均词数：${avgTokens.toFixed(1)}`,
                    `平均去重词数：${avgUniqueTokens.toFixed(1)}`,
                    `平均字数：${avgChars.toFixed(0)}`
                ].join('<br/>');
            }
        },
        grid: { left: 44, right: 16, top: 16, bottom: 44 },
        xAxis: {
            type: 'category',
            data: categories,
            axisLabel: { rotate: categories.length > 8 ? 30 : 0 }
        },
        yAxis: {
            type: 'value',
            axisLabel: { formatter: (v) => `${(Number(v) * 100).toFixed(0)}%` }
        },
        series: [
            {
                name: '信息密度',
                type: 'bar',
                data: values,
                itemStyle: { color: '#60a5fa' }
            }
        ]
    };
    analysisInfoDensityChart.setOption(option, true);
}

function renderAnalysisCategoryTrends(data) {
    const container = document.getElementById('analysis-chart-category-trends');
    if (!container) return;
    if (!container.offsetWidth || !container.offsetHeight) return;

    const dates = Array.isArray(data?.dates) ? data.dates : [];
    const series = Array.isArray(data?.series) ? data.series : [];
    if (!dates.length || !series.length) {
        analysisCategoryTrendsChart = setChartPlaceholder(container, analysisCategoryTrendsChart, 'fas fa-chart-area', '暂无数据');
        return;
    }

    analysisCategoryTrendsChart = ensureChart(container, analysisCategoryTrendsChart);
    const option = {
        tooltip: { trigger: 'axis' },
        legend: { type: 'scroll', top: 8, left: 'center' },
        grid: { left: 44, right: 16, top: 72, bottom: 44 },
        xAxis: { type: 'category', data: dates, axisLabel: { rotate: dates.length > 12 ? 30 : 0 } },
        yAxis: { type: 'value' },
        series: series.map(s => ({
            name: s.name,
            type: 'line',
            stack: 'total',
            areaStyle: {},
            smooth: true,
            showSymbol: false,
            data: s.data || []
        }))
    };
    analysisCategoryTrendsChart.setOption(option, true);

    analysisCategoryTrendsChart.off('click');
    analysisCategoryTrendsChart.on('click', (params) => {
        const category = params?.seriesName;
        const date = params?.name;
        if (!category || !date) return;
        analysisDrilldown = { category, date };
        updateAnalysisDrillBadge();
        loadAnalysisDrilldown();
    });
}

function updateAnalysisDrillBadge() {
    const badge = document.getElementById('analysis-drill-badge');
    if (!badge) return;
    if (!analysisDrilldown || !analysisDrilldown.category || !analysisDrilldown.date) {
        badge.innerHTML = `<span style="color: var(--text-secondary); font-size: 13px;">未选择</span>`;
        return;
    }
    badge.innerHTML = `
        <span class="keyword-tag">${escapeHtml(String(analysisDrilldown.category))}</span>
        <span class="keyword-tag">${escapeHtml(String(analysisDrilldown.date))}</span>
        <button class="btn btn-outline btn-sm" id="btn-clear-analysis-drilldown"><i class="fas fa-xmark"></i> 清除</button>
    `;
    const btn = document.getElementById('btn-clear-analysis-drilldown');
    if (btn) {
        btn.addEventListener('click', () => {
            analysisDrilldown = null;
            updateAnalysisDrillBadge();
            resetAnalysisDrilldownView();
        });
    }
}

function resetAnalysisDrilldownView() {
    const sourceContainer = document.getElementById('analysis-drill-source-share');
    const trendsContainer = document.getElementById('analysis-drill-keyword-trends');
    const listContainer = document.getElementById('analysis-drill-news-list');

    if (sourceContainer) {
        analysisDrillSourceShareChart = setChartPlaceholder(sourceContainer, analysisDrillSourceShareChart, 'fas fa-chart-pie', '点击趋势图进行下钻');
    }
    if (trendsContainer) {
        analysisDrillKeywordTrendsChart = setChartPlaceholder(trendsContainer, analysisDrillKeywordTrendsChart, 'fas fa-chart-line', '点击趋势图进行下钻');
    }
    if (listContainer) {
        listContainer.innerHTML = `<div class="empty-item" style="margin:0;"><i class="fas fa-hand-pointer"></i> 点击分类趋势中的数据点查看代表新闻</div>`;
    }
}

function renderAnalysisDrillSourceShare(data) {
    const container = document.getElementById('analysis-drill-source-share');
    if (!container) return;
    if (!container.offsetWidth || !container.offsetHeight) return;

    const items = (data && data.items) ? data.items : [];
    if (!items.length) {
        analysisDrillSourceShareChart = setChartPlaceholder(container, analysisDrillSourceShareChart, 'fas fa-chart-pie', '暂无数据');
        return;
    }

    analysisDrillSourceShareChart = ensureChart(container, analysisDrillSourceShareChart);
    const option = {
        tooltip: { trigger: 'item' },
        legend: { type: 'scroll', bottom: 0 },
        series: [
            {
                type: 'pie',
                radius: ['45%', '70%'],
                avoidLabelOverlap: true,
                itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
                label: { show: true, formatter: '{b}\n{d}%' },
                labelLine: { show: true },
                data: items
            }
        ]
    };
    analysisDrillSourceShareChart.setOption(option, true);
}

function renderAnalysisDrillKeywordTrends(data) {
    const container = document.getElementById('analysis-drill-keyword-trends');
    if (!container) return;
    if (!container.offsetWidth || !container.offsetHeight) return;

    const dates = Array.isArray(data?.dates) ? data.dates : [];
    const series = Array.isArray(data?.series) ? data.series : [];
    if (!dates.length || !series.length) {
        analysisDrillKeywordTrendsChart = setChartPlaceholder(container, analysisDrillKeywordTrendsChart, 'fas fa-chart-line', '暂无数据');
        return;
    }

    analysisDrillKeywordTrendsChart = ensureChart(container, analysisDrillKeywordTrendsChart);
    const option = {
        tooltip: { trigger: 'axis' },
        legend: { type: 'scroll', bottom: 0 },
        grid: { left: 44, right: 16, top: 16, bottom: 44 },
        xAxis: { type: 'category', data: dates, axisLabel: { rotate: dates.length > 10 ? 30 : 0 } },
        yAxis: { type: 'value' },
        series: series.map(s => ({
            name: s.name,
            type: 'line',
            smooth: true,
            showSymbol: false,
            data: s.data || []
        }))
    };
    analysisDrillKeywordTrendsChart.setOption(option, true);
}

function renderAnalysisDrillNewsList(items) {
    const container = document.getElementById('analysis-drill-news-list');
    if (!container) return;
    const list = Array.isArray(items) ? items : [];

    if (!list.length) {
        container.innerHTML = `<div class="empty-item" style="margin:0;"><i class="fas fa-inbox"></i> 暂无数据</div>`;
        return;
    }

    container.innerHTML = `
        <div class="table-container" style="max-height: 360px;">
            <table class="data-table" style="font-size: 13px;">
                <thead>
                    <tr>
                        <th>标题</th>
                        <th style="width: 140px;">来源</th>
                        <th style="width: 170px;">时间</th>
                    </tr>
                </thead>
                <tbody>
                    ${list.map(a => {
                        const id = a.id;
                        const title = escapeHtml(a.title || '无标题');
                        const source = escapeHtml(a.source_name || '未知来源');
                        const t = formatDateTime(a.publish_time || a.crawl_time) || '-';
                        return `
                            <tr>
                                <td style="max-width: 560px;">
                                    <a href="#news/detail/${id}" style="color: var(--primary-color); text-decoration: none;">${title}</a>
                                </td>
                                <td>${source}</td>
                                <td>${t}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
}

async function loadAnalysisDrilldown() {
    if (currentPage !== 'analysis') return;
    if (!analysisDrilldown || !analysisDrilldown.category || !analysisDrilldown.date) {
        resetAnalysisDrilldownView();
        return;
    }

    const sourceContainer = document.getElementById('analysis-drill-source-share');
    const trendsContainer = document.getElementById('analysis-drill-keyword-trends');
    const listContainer = document.getElementById('analysis-drill-news-list');
    if (!sourceContainer || !trendsContainer || !listContainer) return;

    analysisDrillSourceShareChart = setChartPlaceholder(sourceContainer, analysisDrillSourceShareChart, 'fas fa-chart-pie', '加载中...');
    analysisDrillKeywordTrendsChart = setChartPlaceholder(trendsContainer, analysisDrillKeywordTrendsChart, 'fas fa-chart-line', '加载中...');
    listContainer.innerHTML = `<div class="loading-item" style="margin:0;"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>`;

    const { days } = getAnalysisParams();
    const { category, date } = analysisDrilldown;

    try {
        const [sourceResp, trendsResp, newsResp] = await Promise.all([
            API.visualize.sourceShare({ days: days, top_n: 8, category: category, date: date }),
            API.visualize.keywordTrends({ days: days, top_k: 5, category: category }),
            API.visualize.representativeNews({ category: category, date: date, limit: 10 })
        ]);

        if (sourceResp?.success) {
            renderAnalysisDrillSourceShare(sourceResp.data);
        } else {
            analysisDrillSourceShareChart = setChartPlaceholder(sourceContainer, analysisDrillSourceShareChart, 'fas fa-chart-pie', sourceResp?.error || '加载失败', true);
        }

        if (trendsResp?.success) {
            renderAnalysisDrillKeywordTrends(trendsResp.data);
        } else {
            analysisDrillKeywordTrendsChart = setChartPlaceholder(trendsContainer, analysisDrillKeywordTrendsChart, 'fas fa-chart-line', trendsResp?.error || '加载失败', true);
        }

        if (newsResp?.success) {
            renderAnalysisDrillNewsList(newsResp.data?.items || []);
        } else {
            listContainer.innerHTML = `<div class="error-item" style="margin:0;"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(newsResp?.error || '加载失败')}</div>`;
        }
    } catch (error) {
        analysisDrillSourceShareChart = setChartPlaceholder(sourceContainer, analysisDrillSourceShareChart, 'fas fa-chart-pie', error.message || '加载失败', true);
        analysisDrillKeywordTrendsChart = setChartPlaceholder(trendsContainer, analysisDrillKeywordTrendsChart, 'fas fa-chart-line', error.message || '加载失败', true);
        listContainer.innerHTML = `<div class="error-item" style="margin:0;"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(error.message || '加载失败')}</div>`;
    }
}

function renderAnalysisCategorySimilarity(data) {
    const container = document.getElementById('analysis-chart-category-similarity');
    if (!container) return;
    if (!container.offsetWidth || !container.offsetHeight) return;

    const categories = Array.isArray(data?.categories) ? data.categories : [];
    const heat = Array.isArray(data?.data) ? data.data : [];
    if (categories.length < 2 || !heat.length) {
        analysisCategorySimilarityChart = setChartPlaceholder(container, analysisCategorySimilarityChart, 'fas fa-table-cells', '暂无数据');
        return;
    }

    analysisCategorySimilarityChart = ensureChart(container, analysisCategorySimilarityChart);
    const option = {
        tooltip: {
            position: 'top',
            formatter(params) {
                const x = params.data?.[0];
                const y = params.data?.[1];
                const v = Number(params.data?.[2] || 0);
                return `${escapeHtml(categories[y] || '')} ↔ ${escapeHtml(categories[x] || '')}<br/>相似度：${v.toFixed(2)}`;
            }
        },
        grid: { left: 120, right: 16, top: 60, bottom: 40 },
        xAxis: {
            type: 'category',
            data: categories,
            splitArea: { show: true },
            axisLabel: { rotate: categories.length > 10 ? 30 : 0 }
        },
        yAxis: {
            type: 'category',
            data: categories,
            splitArea: { show: true },
            axisLabel: { width: 110, overflow: 'truncate' }
        },
        visualMap: {
            min: 0,
            max: 1,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            top: 8,
            inRange: {
                color: ['#fff7ec', '#fee8c8', '#fdd49e', '#fdbb84', '#fc8d59', '#ef6548', '#d7301f', '#b30000', '#7f0000']
            },
            outOfRange: {
                color: '#f3f4f6'
            }
        },
        series: [
            {
                type: 'heatmap',
                data: heat,
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowColor: 'rgba(0,0,0,0.2)'
                    }
                }
            }
        ]
    };
    analysisCategorySimilarityChart.setOption(option, true);
}

function renderAnalysisCategoryHourMatrix(data) {
    const container = document.getElementById('analysis-chart-category-hour-matrix');
    if (!container) return;
    if (!container.offsetWidth || !container.offsetHeight) return;

    const categories = data?.categories || [];
    const hours = data?.hours || [];
    const matrix = data?.data || [];

    if (!categories.length || !hours.length || !matrix.length) {
        analysisCategoryHourMatrixChart = setChartPlaceholder(container, analysisCategoryHourMatrixChart, 'fas fa-border-all', '暂无数据');
        return;
    }

    let maxVal = 0;
    for (const item of matrix) {
        const v = Number(item?.[2] || 0);
        if (v > maxVal) maxVal = v;
    }

    analysisCategoryHourMatrixChart = ensureChart(container, analysisCategoryHourMatrixChart);
    const option = {
        tooltip: {
            position: 'top',
            formatter(params) {
                const cIdx = params.data?.[0];
                const hIdx = params.data?.[1];
                const v = params.data?.[2];
                return `${categories[cIdx] || ''}<br/>小时: ${hours[hIdx]}<br/>数量: ${v}`;
            }
        },
        grid: { left: 120, right: 16, top: 60, bottom: 40 },
        xAxis: {
            type: 'category',
            data: hours.map(h => String(h)),
            splitArea: { show: true }
        },
        yAxis: {
            type: 'category',
            data: categories,
            splitArea: { show: true },
            axisLabel: {
                width: 110,
                overflow: 'truncate'
            }
        },
        visualMap: {
            min: 0,
            max: Math.max(1, maxVal),
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            top: 8,
            inRange: {
                color: ['#fff7ec', '#fee8c8', '#fdd49e', '#fdbb84', '#fc8d59', '#ef6548', '#d7301f', '#b30000', '#7f0000']
            },
            outOfRange: {
                color: '#f3f4f6'
            }
        },
        dataZoom: categories.length > 14 ? [{ type: 'inside', yAxisIndex: 0 }] : [],
        series: [
            {
                type: 'heatmap',
                data: matrix,
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowColor: 'rgba(0,0,0,0.2)'
                    }
                }
            }
        ]
    };
    analysisCategoryHourMatrixChart.setOption(option, true);
}

async function loadAnalysisPage() {
    await loadAnalysisAnalytics();
}

async function loadAnalysisAnalytics() {
    if (currentPage !== 'analysis') return;

    bindAnalysisControls();
    ensureAnalysisResizeHandler();

    const container1 = document.getElementById('analysis-chart-source-share');
    const container2 = document.getElementById('analysis-chart-info-density');
    const container3 = document.getElementById('analysis-chart-category-trends');
    const container4 = document.getElementById('analysis-chart-category-hour-matrix');
    const container5 = document.getElementById('analysis-chart-category-similarity');
    if (!container1 || !container2 || !container3 || !container4 || !container5) return;
    if (!container1.offsetWidth || !container2.offsetWidth || !container3.offsetWidth || !container4.offsetWidth || !container5.offsetWidth) return;

    analysisSourceShareChart = setChartPlaceholder(container1, analysisSourceShareChart, 'fas fa-chart-pie', '加载中...');
    analysisInfoDensityChart = setChartPlaceholder(container2, analysisInfoDensityChart, 'fas fa-chart-column', '加载中...');
    analysisCategoryTrendsChart = setChartPlaceholder(container3, analysisCategoryTrendsChart, 'fas fa-chart-area', '加载中...');
    analysisCategoryHourMatrixChart = setChartPlaceholder(container4, analysisCategoryHourMatrixChart, 'fas fa-border-all', '加载中...');
    analysisCategorySimilarityChart = setChartPlaceholder(container5, analysisCategorySimilarityChart, 'fas fa-table-cells', '加载中...');

    const { days, top_n } = getAnalysisParams();

    try {
        const [sourceResp, densityResp, trendsResp, similarityResp, matrixResp] = await Promise.all([
            API.visualize.sourceShare({ days: days, top_n: 8 }),
            API.visualize.infoDensity({ days: days, top_n: top_n }),
            API.visualize.categoryTrends({ days: days, top_n: top_n }),
            API.visualize.categorySimilarity({ days: days, top_words: 80, min_count: 20 }),
            API.visualize.categoryHourMatrix({ days: days })
        ]);

        if (sourceResp?.success) {
            renderAnalysisSourceShare(sourceResp.data);
        } else {
            analysisSourceShareChart = setChartPlaceholder(container1, analysisSourceShareChart, 'fas fa-chart-pie', sourceResp?.error || '加载失败', true);
        }

        if (densityResp?.success) {
            renderAnalysisInfoDensity(densityResp.data);
        } else {
            analysisInfoDensityChart = setChartPlaceholder(container2, analysisInfoDensityChart, 'fas fa-chart-column', densityResp?.error || '加载失败', true);
        }

        if (trendsResp?.success) {
            renderAnalysisCategoryTrends(trendsResp.data);
        } else {
            analysisCategoryTrendsChart = setChartPlaceholder(container3, analysisCategoryTrendsChart, 'fas fa-chart-area', trendsResp?.error || '加载失败', true);
        }

        if (similarityResp?.success) {
            renderAnalysisCategorySimilarity(similarityResp.data);
        } else {
            analysisCategorySimilarityChart = setChartPlaceholder(container5, analysisCategorySimilarityChart, 'fas fa-table-cells', similarityResp?.error || '加载失败', true);
        }

        if (matrixResp?.success) {
            renderAnalysisCategoryHourMatrix(matrixResp.data);
        } else {
            analysisCategoryHourMatrixChart = setChartPlaceholder(container4, analysisCategoryHourMatrixChart, 'fas fa-border-all', matrixResp?.error || '加载失败', true);
        }

        updateAnalysisDrillBadge();
        if (!analysisDrilldown) {
            resetAnalysisDrilldownView();
        } else {
            loadAnalysisDrilldown();
        }
    } catch (error) {
        analysisSourceShareChart = setChartPlaceholder(container1, analysisSourceShareChart, 'fas fa-chart-pie', error.message || '加载失败', true);
        analysisInfoDensityChart = setChartPlaceholder(container2, analysisInfoDensityChart, 'fas fa-chart-column', error.message || '加载失败', true);
        analysisCategoryTrendsChart = setChartPlaceholder(container3, analysisCategoryTrendsChart, 'fas fa-chart-area', error.message || '加载失败', true);
        analysisCategorySimilarityChart = setChartPlaceholder(container5, analysisCategorySimilarityChart, 'fas fa-table-cells', error.message || '加载失败', true);
        analysisCategoryHourMatrixChart = setChartPlaceholder(container4, analysisCategoryHourMatrixChart, 'fas fa-border-all', error.message || '加载失败', true);

        updateAnalysisDrillBadge();
        resetAnalysisDrilldownView();
    }
}

function updateDashboardStats(data) {
    document.getElementById('total-articles').textContent = formatNumber(data.total_articles || 0);
    document.getElementById('domestic-sources').textContent = data.domestic_count || 0;
}

function updateTodayStats(data) {
    document.getElementById('today-runs').textContent = data.total_runs || 0;
    document.getElementById('today-success').textContent = data.success_count || 0;
    document.getElementById('today-failed').textContent = data.failed_count || 0;
    document.getElementById('today-items').textContent = formatNumber(data.total_items || 0);
}

// ==================== 最近活动 ====================

async function loadRecentActivity() {
    const list = document.getElementById('recent-activity-list');

    list.innerHTML = `
        <div class="loading-item">
            <i class="fas fa-spinner fa-spin"></i>
            加载数据中...
        </div>
    `;

    try {
        const news = await API.news.list({ limit: 10 });

        const activities = [];

        if (news.success && news.data.items) {
            news.data.items.slice(0, 6).forEach(item => {
                activities.push({
                    type: item.source_type,
                    title: item.title || '未知标题',
                    source: item.source_name,
                    time: formatTime(item.crawl_time)
                });
            });
        }

        if (activities.length > 0) {
            // 按时间排序
            activities.sort((a, b) => new Date(b.time) - new Date(a.time));

            list.innerHTML = activities.slice(0, 6).map(item => {
                const typeConfig = sourceTypeConfig[item.type] || sourceTypeConfig.domestic;
                return `
                    <div class="activity-item">
                        <div class="activity-icon ${typeConfig.class}">
                            <i class="${typeConfig.icon}"></i>
                        </div>
                        <div class="activity-content">
                            <div class="activity-title">${escapeHtml(item.title)}</div>
                            <div class="activity-meta">
                                <span><i class="fas fa-newspaper"></i> ${escapeHtml(item.source)}</span>
                                <span><i class="far fa-clock"></i> ${item.time}</span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            list.innerHTML = '<div class="empty-item"><i class="fas fa-inbox"></i> 暂无数据</div>';
        }
    } catch (error) {
        console.error('加载最近活动失败:', error);
        list.innerHTML = `
            <div class="error-item">
                <i class="fas fa-exclamation-triangle"></i>
                <span>加载失败</span>
                <button class="btn btn-primary btn-sm" onclick="loadRecentActivity()">
                    <i class="fas fa-sync-alt"></i> 重试
                </button>
            </div>
        `;
    }
}

// ==================== 爬虫控制功能 ====================

async function loadSpiderList() {
    const grid = document.getElementById('spider-list');

    grid.innerHTML = `
        <div class="loading-item">
            <i class="fas fa-spinner fa-spin"></i>
            加载爬虫列表中...
        </div>
    `;

    try {
        const result = await API.spider.list();

        if (result.success && result.data && result.data.length > 0) {
            grid.innerHTML = result.data.map(spider => `
                <div class="spider-card">
                    <div class="spider-info">
                        <div class="spider-icon ${spider.type}">
                            <i class="fas fa-spider"></i>
                        </div>
                        <div class="spider-details">
                            <h4>${escapeHtml(spider.description)}</h4>
                            <span class="spider-type-tag">${spider.type_name}</span>
                            <span class="spider-name">${spider.name}</span>
                        </div>
                    </div>
                    <div class="spider-actions">
                        <button class="btn btn-primary btn-sm" onclick="runSpider('${spider.name}', '${spider.type}')">
                            <i class="fas fa-play"></i> 启动
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            grid.innerHTML = '<div class="empty-item"><i class="fas fa-inbox"></i> 暂无爬虫数据</div>';
        }
    } catch (error) {
        console.error('加载爬虫列表失败:', error);
        grid.innerHTML = `
            <div class="error-item">
                <i class="fas fa-exclamation-triangle"></i>
                <span>加载失败</span>
                <button class="btn btn-primary btn-sm" onclick="loadSpiderList()">
                    <i class="fas fa-sync-alt"></i> 重试
                </button>
            </div>
        `;
    }
}

async function runSpider(spiderName, spiderType) {
    try {
        showToast('info', '启动中', '正在启动爬虫: ' + spiderName + '...');

        const result = await API.spider.start(spiderName, spiderType);

        if (result.success) {
            showToast('success', '启动成功', result.message);
            // 刷新日志页面
            if (currentPage === 'logs') {
                loadLogs();
            }
            // 刷新今日统计
            const logStats = await API.logs.stats();
            if (logStats.success) {
                updateTodayStats(logStats.data);
            }
        } else {
            showToast('error', '启动失败', result.error || '未知错误');
        }
    } catch (error) {
        console.error('启动爬虫失败:', error);
        showToast('error', '启动失败', error.message);
    }
}

async function runAllSpiders() {
    try {
        showToast('info', '启动中', '正在依次启动所有爬虫，请稍候...');

        const result = await API.spider.runAll();

        if (result.success) {
            showToast('success', '执行完成', result.message);

            // 刷新日志和统计
            if (currentPage === 'logs') {
                loadLogs();
            }
            const logStats = await API.logs.stats();
            if (logStats.success) {
                updateTodayStats(logStats.data);
            }
        } else {
            showToast('error', '执行失败', result.error || '未知错误');
        }
    } catch (error) {
        console.error('执行所有爬虫失败:', error);
        showToast('error', '执行失败', error.message);
    }
}

// 导出爬虫控制函数
window.loadSpiderList = loadSpiderList;
window.runSpider = runSpider;
window.runAllSpiders = runAllSpiders;

// ==================== 新闻页面 ====================

async function loadNews(isAppend = false) {
    const tbody = document.getElementById('news-table-body');
    const grid = document.getElementById('news-grid');
    const tableCard = document.getElementById('news-table-card');
    
    // 如果不是追加模式，重置状态
    if (!isAppend) {
        newsState.page = 1;
        newsState.hasMore = true;
        newsState.isLoading = false;
        
        // 显示加载状态
        grid.innerHTML = `
            <div class="loading-card">
                <i class="fas fa-spinner fa-spin"></i>
                加载数据中...
            </div>
        `;
        tableCard.style.display = 'none';
        grid.style.display = 'grid';
        tbody.innerHTML = '';
    }
    
    // 检查是否可以加载
    if (newsState.isLoading || (!newsState.hasMore && isAppend)) return;
    
    newsState.isLoading = true;
    
    // 如果是追加模式，显示底部加载指示器
    let loadingRow = null;
    if (isAppend) {
        loadingRow = document.createElement('tr');
        loadingRow.className = 'loading-row';
        loadingRow.innerHTML = '<td colspan="7" style="text-align: center; padding: 20px;"><i class="fas fa-spinner fa-spin"></i> 加载更多...</td>';
        tbody.appendChild(loadingRow);
    }
    
    try {
        const result = await API.news.list({
            type: currentNewsType,
            source: currentSource || null,
            limit: newsState.limit,
            page: newsState.page
        });
        
        // 移除加载指示器
        if (loadingRow) loadingRow.remove();
        
        if (result.success && result.data.items) {
            const items = result.data.items;
            
            // 更新状态
            if (items.length < newsState.limit) {
                newsState.hasMore = false;
            } else {
                newsState.page++;
            }
            
            if (!isAppend) {
                // 隐藏网格视图，显示表格视图
                grid.style.display = 'none';
                tableCard.style.display = 'block';
            }
            
            if (items.length > 0) {
                const html = items.map(item => {
                    const typeConfig = sourceTypeConfig[item.source_type] || sourceTypeConfig.domestic;
                    return `
                        <tr>
                            <td>
                                <span class="source-tag ${typeConfig.class}">
                                    <i class="${typeConfig.icon}"></i>
                                    ${escapeHtml(item.source_name)}
                                </span>
                            </td>
                            <td>${typeConfig.name}</td>
                            <td>${escapeHtml(item.title || '未知标题')}</td>
                            <td>${escapeHtml(item.author || '-')}</td>
                            <td>${formatDateTime(item.publish_time)}</td>
                            <td>${formatTime(item.crawl_time)}</td>
                            <td>
                                <a class="action-link" onclick="showNewsDetail(${item.id})">查看</a>
                            </td>
                        </tr>
                    `;
                }).join('');
                
                if (isAppend) {
                    tbody.insertAdjacentHTML('beforeend', html);
                } else {
                    tbody.innerHTML = html;
                }
            } else {
                if (!isAppend) {
                    tbody.innerHTML = `
                        <tr class="loading-row">
                            <td colspan="7">暂无该媒体的数据</td>
                        </tr>
                    `;
                }
            }
        } else {
            if (!isAppend) {
                grid.innerHTML = '<div class="loading-card">加载失败，请稍后重试</div>';
            }
        }
    } catch (error) {
        console.error('加载新闻数据失败:', error);
        if (loadingRow) loadingRow.remove();
        if (!isAppend) {
            grid.innerHTML = '<div class="loading-card">加载失败，请检查网络连接</div>';
        } else {
            showToast('error', '加载失败', '无法加载更多数据');
        }
    } finally {
        newsState.isLoading = false;
    }
}

function filterBySource(btn, source) {
    // 更新按钮状态
    document.querySelectorAll('.tab-buttons .tab-btn').forEach(b => {
        b.classList.toggle('active', b === btn);
    });
    
    currentSource = source;
    loadNews();
}

function showNewsDetail(id) {
    // 跳转到详情页
    window.location.hash = `news/detail/${id}`;
}

// ==================== 新闻详情页面 ====================

async function loadNewsDetail(articleId) {
    const container = document.getElementById('news-detail-container');

    // 显示加载状态
    container.innerHTML = `
        <div class="loading-card">
            <i class="fas fa-spinner fa-spin"></i>
            <p>正在加载文章内容...</p>
        </div>
    `;

    // 更新面包屑
    document.getElementById('detail-breadcrumb').textContent = `文章 #${articleId}`;

    try {
        const result = await API.news.detail(articleId);

        if (result.success && result.data) {
            const article = result.data;

            // 更新页面标题
            document.getElementById('detail-page-title').textContent = article.title || '无标题';
            document.getElementById('detail-page-desc').textContent = `来源: ${article.source_name || '未知来源'}`;

            // 渲染文章详情
            container.innerHTML = `
                <div class="news-detail-card">
                    <div class="detail-header">
                        <h1 class="detail-title">${escapeHtml(article.title || '无标题')}</h1>
                        <div class="detail-meta">
                            <span class="meta-item">
                                <i class="fas fa-newspaper"></i>
                                ${escapeHtml(article.source_name || '未知来源')}
                            </span>
                            <span class="meta-item">
                                <i class="fas fa-user"></i>
                                ${escapeHtml(article.author || '未知作者')}
                            </span>
                            <span class="meta-item">
                                <i class="fas fa-clock"></i>
                                ${formatDateTime(article.publish_time) || '未知时间'}
                            </span>
                            <span class="meta-item">
                                <i class="fas fa-calendar-alt"></i>
                                采集于 ${formatDateTime(article.crawl_time)}
                            </span>
                        </div>
                        ${article.keywords ? `
                        <div class="detail-keywords">
                            <i class="fas fa-tags"></i>
                            ${String(article.keywords).split(',').filter(k => k.trim()).map(k =>
                                `<span class="keyword-tag">${escapeHtml(k.trim())}</span>`
                            ).join('')}
                        </div>
                        ` : ''}
                    </div>
                    <div class="detail-content">
                        ${article.content ? `
                            <div class="content-text">${formatContent(article.content)}</div>
                        ` : '<p class="empty-content">暂无正文内容</p>'}
                    </div>
                    ${article.url ? `
                    <div class="detail-footer">
                        <a href="${escapeHtml(article.url)}" target="_blank" class="btn btn-outline">
                            <i class="fas fa-external-link-alt"></i>
                            原文链接
                        </a>
                        <button class="btn btn-primary" onclick="window.history.back()">
                            <i class="fas fa-arrow-left"></i>
                            返回列表
                        </button>
                    </div>
                    ` : ''}
                </div>
            `;
        } else {
            container.innerHTML = `
                <div class="error-card">
                    <i class="fas fa-exclamation-circle"></i>
                    <h3>文章不存在</h3>
                    <p>无法找到 ID 为 ${articleId} 的文章</p>
                    <button class="btn btn-primary" onclick="navigateTo('news')">
                        <i class="fas fa-arrow-left"></i>
                        返回列表
                    </button>
                </div>
            `;
        }
    } catch (error) {
        console.error('加载文章详情失败:', error);
        container.innerHTML = `
            <div class="error-card">
                <i class="fas fa-exclamation-triangle"></i>
                <h3>加载失败</h3>
                <p>无法获取文章内容，请检查网络连接</p>
                <button class="btn btn-primary" onclick="loadNewsDetail(${articleId})">
                    <i class="fas fa-sync-alt"></i>
                    重试
                </button>
            </div>
        `;
    }
}

function formatContent(content) {
    // 将内容按段落分割并渲染
    if (!content) return '';

    // 分割段落
    const paragraphs = content.split('\n').filter(p => p.trim());

    return paragraphs.map(p => {
        const trimmed = p.trim();
        if (trimmed) {
            return `<p>${escapeHtml(trimmed)}</p>`;
        }
        return '';
    }).join('');
}

// ==================== 新闻分类页面 (原日志页面) ====================

async function loadCategories() {
    const select = document.getElementById('category-filter');
    if (!select) return;

    try {
        const result = await API.admin.modelStatus();
        if (result.success && result.data && result.data.categories) {
            const categories = result.data.categories;
            const currentVal = select.value;
            
            // 如果分类列表为空，不进行更新
            if (!categories || categories.length === 0) return;

            // 保留"全部分类"选项
            let options = '<option value="">全部分类</option>';
            
            categories.forEach(cat => {
                options += `<option value="${cat}">${cat}</option>`;
            });
            
            select.innerHTML = options;
            
            // 尝试恢复之前的选择
            if (currentVal && categories.includes(currentVal)) {
                select.value = currentVal;
            }
        }
    } catch (error) {
        console.error('加载分类列表失败:', error);
    }
}

function loadLogs() {
    return loadClassifiedNews();
}

async function loadClassifiedNews(isAppend = false) {
    const category = document.getElementById('category-filter').value;
    const tbody = document.getElementById('logs-table-body');
    
    // 如果不是追加模式，重置状态
    if (!isAppend) {
        logsState.page = 1;
        logsState.hasMore = true;
        logsState.isLoading = false;
        
        tbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="5">
                    <i class="fas fa-spinner fa-spin"></i>
                    加载数据中...
                </td>
            </tr>
        `;
    }
    
    // 检查是否可以加载
    if (logsState.isLoading || (!logsState.hasMore && isAppend)) return;
    
    logsState.isLoading = true;
    
    // 如果是追加模式，显示底部加载指示器
    let loadingRow = null;
    if (isAppend) {
        loadingRow = document.createElement('tr');
        loadingRow.className = 'loading-row';
        loadingRow.innerHTML = '<td colspan="5" style="text-align: center; padding: 20px;"><i class="fas fa-spinner fa-spin"></i> 加载更多...</td>';
        tbody.appendChild(loadingRow);
    }
    
    try {
        // 复用新闻列表接口，增加 category 参数
        const result = await API.news.list({
            category: category || null,
            limit: logsState.limit,
            page: logsState.page
        });
        
        // 移除加载指示器
        if (loadingRow) loadingRow.remove();
        
        if (result.success && result.data.items) {
            const items = result.data.items;
            
            // 更新状态
            if (items.length < logsState.limit) {
                logsState.hasMore = false;
            } else {
                logsState.page++;
            }
            
            if (!isAppend) {
                 tbody.innerHTML = '';
            }
            
            if (items.length > 0) {
                const html = items.map(item => {
                    const typeConfig = sourceTypeConfig[item.source_type] || sourceTypeConfig.domestic;
                    return `
                        <tr>
                            <td>
                                <span class="spider-type-tag" style="background: #e3f2fd; color: #1976d2;">
                                    ${escapeHtml(item.category || '未分类')}
                                </span>
                            </td>
                            <td>${escapeHtml(item.title || '无标题')}</td>
                            <td>
                                <span class="source-tag ${typeConfig.class}">
                                    <i class="${typeConfig.icon}"></i>
                                    ${escapeHtml(item.source_name)}
                                </span>
                            </td>
                            <td>${formatDateTime(item.publish_time)}</td>
                            <td>
                                <a class="action-link" onclick="showNewsDetail(${item.id})">查看</a>
                            </td>
                        </tr>
                    `;
                }).join('');
                
                if (isAppend) {
                    tbody.insertAdjacentHTML('beforeend', html);
                } else {
                    tbody.innerHTML = html;
                }
            } else {
                if (!isAppend) {
                    tbody.innerHTML = `
                        <tr class="loading-row">
                            <td colspan="5">暂无该分类的新闻数据</td>
                        </tr>
                    `;
                }
            }
        } else {
            if (!isAppend) {
                tbody.innerHTML = `
                    <tr class="loading-row">
                        <td colspan="5">加载失败，请稍后重试</td>
                    </tr>
                `;
            }
        }
    } catch (error) {
        console.error('加载分类新闻失败:', error);
        if (loadingRow) loadingRow.remove();
        if (!isAppend) {
            tbody.innerHTML = `
                <tr class="loading-row">
                    <td colspan="5">加载失败，请检查网络连接</td>
                </tr>
            `;
        } else {
            showToast('error', '加载失败', '无法加载更多数据');
        }
    } finally {
        logsState.isLoading = false;
    }
}

window.loadClassifiedNews = loadClassifiedNews;

// ==================== 通用功能 ====================

function refreshCurrentPage() {
    switch (currentPage) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'analysis':
            loadAnalysisPage();
            break;
        case 'news':
            loadNews();
            break;
        case 'logs':
            loadLogs();
            break;
        case 'word-cloud':
            loadWordCloudPage();
            break;
    }
    showToast('success', '刷新成功', '数据已更新');
}

function showToast(type, title, message) {
    const container = document.getElementById('toast-container');
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: 'check',
        error: 'times',
        warning: 'exclamation',
        info: 'info'
    };
    
    toast.innerHTML = `
        <div class="toast-icon">
            <i class="fas fa-${icons[type]}"></i>
        </div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;
    
    container.appendChild(toast);
    
    // 3秒后移除
    setTimeout(() => {
        toast.style.animation = 'toastSlideIn 0.3s ease reverse';
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

function closeModal() {
    document.getElementById('detail-modal').classList.remove('active');
}

function openModal(title, bodyHtml) {
    const modal = document.getElementById('detail-modal');
    document.getElementById('modal-title').textContent = title || '详情';
    document.getElementById('modal-body').innerHTML = bodyHtml || '';
    modal.classList.add('active');
}

// ==================== 工具函数 ====================

function formatNumber(num) {
    if (num >= 10000) {
        return (num / 10000).toFixed(1) + 'w';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'k';
    }
    return num.toString();
}

function formatTime(datetime) {
    if (!datetime) return '-';
    
    const date = new Date(datetime);
    const now = new Date();
    const diff = now - date;
    
    // 小于1小时显示分钟
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        if (minutes > 0) {
            return `${minutes}分钟前`;
        }
        return '刚刚';
    }
    
    // 小于24小时显示小时
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours}小时前`;
    }
    
    // 显示日期
    return date.toLocaleDateString('zh-CN');
}

function formatDateTime(datetime) {
    if (!datetime) return '-';
    
    const date = new Date(datetime);
    return date.toLocaleString('zh-CN');
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 导出全局函数
window.navigateTo = navigateTo;
window.refreshCurrentPage = refreshCurrentPage;
window.refreshDashboardData = refreshDashboardData;  // 导出刷新仪表盘数据函数
window.loadDashboard = loadDashboard;  // 导出加载仪表盘函数
window.loadNews = loadNews;
window.loadLogs = loadLogs;
window.loadNewsDetail = loadNewsDetail;
window.filterBySource = filterBySource;
window.closeModal = closeModal;
window.showToast = showToast;
window.loadWordCloudPage = loadWordCloudPage;

// ==================== 管理员页面功能 ====================

// 切换管理员子标签页
function switchAdminTab(btn, tabName) {
    // 更新按钮状态
    document.querySelectorAll('.tab-buttons .tab-btn').forEach(b => {
        b.classList.remove('active');
    });
    btn.classList.add('active');
    
    // 更新标签页显示
    document.querySelectorAll('.admin-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById(`admin-tab-${tabName}`).classList.add('active');
    
    // 加载对应标签数据
    refreshAdminPage();
}

window.switchAdminTab = switchAdminTab;

// 刷新管理员页面（根据当前激活的标签页）
function refreshAdminPage() {
    const activeTab = document.querySelector('.admin-tab.active');
    if (!activeTab) return;
    
    const tabId = activeTab.id;

    if (tabId === 'admin-tab-content-class') {
        loadModelStatus(); // 复用模型状态加载
        refreshModelAnalysisOptions().finally(() => loadModelComparison());
    }
}

// 退出管理员页面
function exitAdminPage() {
    navigateTo('dashboard');
}

window.exitAdminPage = exitAdminPage;

// ==================== 数据清洗功能 ====================

async function runDataClean() {
    const config = {
        format: document.getElementById('clean-format').checked,
        deduplicate: document.getElementById('clean-deduplicate').checked,
        filter_invalid: document.getElementById('clean-filter-invalid').checked,
        missing: document.getElementById('clean-missing').checked,
        llm_filter: document.getElementById('clean-llm-filter').checked
    };
    
    try {
        showToast('info', '处理中', '正在执行数据清洗...');
        if (config.llm_filter) {
            showToast('info', '提示', '大模型筛选耗时较长，请耐心等待...');
        }
        
        // 注意：后端接口可能需要根据新的 config 键名进行适配，或者在这里做映射
        // 这里假设后端接口可以接收这些参数，或者我们保持向后兼容
        const apiConfig = {
            normalize_format: config.format,
            remove_duplicates: config.deduplicate,
            filter_invalid: config.filter_invalid,
            remove_null: config.missing,
            llm_filter: config.llm_filter,
            preprocess: true // 默认开启
        };

        const result = await API.admin.dataClean(apiConfig);
        
        if (result.success) {
            // 显示清洗结果
            document.getElementById('clean-result-card').style.display = 'block';
            
            const statsContainer = document.getElementById('clean-result-stats');
            statsContainer.innerHTML = `
                <div class="stat-card">
                    <div class="stat-icon blue">
                        <i class="fas fa-database"></i>
                    </div>
                    <div class="stat-info">
                        <span class="stat-value">${result.data.original_count}</span>
                        <span class="stat-label">原始数据</span>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon green">
                        <i class="fas fa-check"></i>
                    </div>
                    <div class="stat-info">
                        <span class="stat-value">${result.data.cleaned_count}</span>
                        <span class="stat-label">清洗后数据</span>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon orange">
                        <i class="fas fa-trash"></i>
                    </div>
                    <div class="stat-info">
                        <span class="stat-value">${result.data.removed_count}</span>
                        <span class="stat-label">删除数据</span>
                    </div>
                </div>
            `;
            
            showToast('success', '清洗完成', `处理 ${result.data.cleaned_count} 条数据`);
        } else {
            showToast('error', '清洗失败', result.error || '未知错误');
        }
    } catch (error) {
        console.error('数据清洗失败:', error);
        showToast('error', '清洗失败', error.message);
    }
}

window.runDataClean = runDataClean;

// ==================== 新闻分类与模型功能 ====================

// 更新模型参数显示
function updateModelParams() {
    const modelType = document.getElementById('model-type-select').value;
    // 添加 bert_textcnn 到深度学习模型列表
    const isDeepLearning = ['bert', 'cnn', 'lstm', 'bert_textcnn'].includes(modelType);
    
    const displayStyle = isDeepLearning ? 'block' : 'none';
    
    const epochGroup = document.getElementById('param-epochs');
    const batchGroup = document.getElementById('param-batch');
    const lrGroup = document.getElementById('param-lr');
    
    if (epochGroup) epochGroup.style.display = displayStyle;
    if (batchGroup) batchGroup.style.display = displayStyle;
    if (lrGroup) lrGroup.style.display = displayStyle;

    // 显示或隐藏新模型介绍卡片
    const introCards = document.getElementById('model-intro-cards');
    if (introCards) {
        // 如果是 bert_textcnn，显示介绍卡片
        introCards.style.display = (modelType === 'bert_textcnn') ? 'flex' : 'none';
    }

    // 显示或隐藏训练增强选项（仅 BERT 类模型）
    const enhanceOpts = document.getElementById('training-enhancement-options');
    if (enhanceOpts) {
        enhanceOpts.style.display = ['bert', 'bert_textcnn'].includes(modelType) ? 'block' : 'none';
    }
}
window.updateModelParams = updateModelParams;

function updateNlpTaskParams() {
    const nlpTask = document.getElementById('nlp-task-select')?.value || 'content_classification';
    const showSentiment = nlpTask.startsWith('sentiment_');

    const daysGroup = document.getElementById('param-sentiment-days');
    const limitGroup = document.getElementById('param-sentiment-limit');
    const entitiesGroup = document.getElementById('param-sentiment-entities');
    const displayStyle = showSentiment ? 'block' : 'none';

    if (daysGroup) daysGroup.style.display = displayStyle;
    if (limitGroup) limitGroup.style.display = displayStyle;
    if (entitiesGroup) entitiesGroup.style.display = displayStyle;
}
window.updateNlpTaskParams = updateNlpTaskParams;

// 训练轮询定时器
let trainingPollInterval = null;

function setTrainingControlState(state = 'idle') {
    const startBtn = document.getElementById('btn-start-training');
    const stopBtn = document.getElementById('btn-stop-training');

    if (!startBtn || !stopBtn) {
        return;
    }

    if (state === 'running') {
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 训练中...';
        stopBtn.disabled = false;
        stopBtn.innerHTML = '<i class="fas fa-stop"></i> 停止训练';
        return;
    }

    if (state === 'stopping') {
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 训练中...';
        stopBtn.disabled = true;
        stopBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 停止中...';
        return;
    }

    startBtn.disabled = false;
    startBtn.innerHTML = '<i class="fas fa-play"></i> 开始训练';
    stopBtn.disabled = true;
    stopBtn.innerHTML = '<i class="fas fa-stop"></i> 停止训练';
}

async function startModelTraining() {
    const modelType = document.getElementById('model-type-select').value;
    const nlpTask = document.getElementById('nlp-task-select')?.value || 'content_classification';
    const epochs = document.getElementById('train-epochs').value;
    const batchSize = document.getElementById('train-batch-size').value;
    const learningRate = document.getElementById('train-learning-rate').value;
    const progressBar = document.getElementById('training-progress-bar');
    
    try {
        setTrainingControlState('running');
        if (progressBar) {
            progressBar.classList.remove('bg-success', 'bg-danger');
        }
        
        const enableAug = document.getElementById('enable-augmentation');
        const enableFgm = document.getElementById('enable-fgm');
        const data = {
            model_type: modelType,
            nlp_task: nlpTask,
            epochs: parseInt(epochs),
            batch_size: parseInt(batchSize),
            learning_rate: parseFloat(learningRate),
            enable_augmentation: enableAug ? enableAug.checked : false,
            use_fgm: enableFgm ? enableFgm.checked : false
        };

        if (String(nlpTask).startsWith('sentiment_')) {
            data.sentiment_days = parseInt(document.getElementById('train-sentiment-days')?.value || '3', 10);
            data.sentiment_limit = parseInt(document.getElementById('train-sentiment-limit')?.value || '300', 10);
            data.sentiment_max_entities = parseInt(document.getElementById('train-sentiment-max-entities')?.value || '3', 10);
        }
        
        const result = await API.admin.trainModel(data);
        
        if (result.success) {
            showToast('success', '启动成功', '模型训练已在后台开始');
            startPollingTrainingStatus();
        } else {
            showToast('error', '启动失败', result.error || '未知错误');
            setTrainingControlState('idle');
        }
    } catch (error) {
        console.error('训练启动失败:', error);
        showToast('error', '系统错误', error.message);
        setTrainingControlState('idle');
    }
}
window.startModelTraining = startModelTraining;

async function stopModelTraining() {
    try {
        setTrainingControlState('stopping');
        const result = await API.admin.stopTrainModel();

        if (result.success) {
            showToast('success', '停止请求已发送', '训练任务将尽快安全停止');
        } else {
            showToast('error', '停止失败', result.error || '未知错误');
            setTrainingControlState('running');
        }
    } catch (error) {
        console.error('停止训练失败:', error);
        showToast('error', '系统错误', error.message);
        setTrainingControlState('running');
    }
}
window.stopModelTraining = stopModelTraining;

async function startPollingTrainingStatus() {
    const statusText = document.getElementById('training-status-text');
    const progressText = document.getElementById('training-progress-text');
    const progressBar = document.getElementById('training-progress-bar');
    const logsContainer = document.getElementById('training-logs');
    
    // 清除之前的定时器
    if (trainingPollInterval) clearInterval(trainingPollInterval);
    
    trainingPollInterval = setInterval(async () => {
        try {
            const result = await API.admin.modelStatus();
            
            if (result.success && result.data.training_state) {
                const state = result.data.training_state;
                
                // 更新进度条
                const progress = state.progress || 0;
                progressBar.style.width = `${progress}%`;
                progressText.textContent = `${progress}%`;
                statusText.textContent = state.message || state.status;
                
                // 更新日志
                if (state.logs && state.logs.length > 0) {
                    logsContainer.innerHTML = state.logs.map(log => `<div class="log-line">${log}</div>`).join('');
                    logsContainer.scrollTop = logsContainer.scrollHeight;
                }

                if (state.status === 'training') {
                    setTrainingControlState('running');
                } else if (state.status === 'stopping') {
                    setTrainingControlState('stopping');
                }
                
                // 检查状态
                if (state.status === 'success') {
                    clearInterval(trainingPollInterval);
                    trainingPollInterval = null;
                    setTrainingControlState('idle');
                    showToast('success', '训练完成', '模型已训练完毕');
                    progressBar.classList.add('bg-success');
                    
                    refreshModelAnalysisOptions().finally(() => loadModelComparison());
                    
                } else if (state.status === 'stopped') {
                    clearInterval(trainingPollInterval);
                    trainingPollInterval = null;
                    setTrainingControlState('idle');
                    showToast('success', '训练已停止', state.message || '训练任务已停止');
                } else if (state.status === 'failed') {
                    clearInterval(trainingPollInterval);
                    trainingPollInterval = null;
                    setTrainingControlState('idle');
                    showToast('error', '训练失败', state.message);
                    progressBar.classList.add('bg-danger');
                }
            }
        } catch (error) {
            console.error('获取状态失败:', error);
        }
    }, 1000); // 每秒轮询一次
}

// 初始化页面时检查是否正在训练
document.addEventListener('DOMContentLoaded', () => {
    updateModelParams();
    updateNlpTaskParams();
    // 检查是否有正在进行的训练
    API.admin.modelStatus().then(result => {
        const trainingState = result.success && result.data ? result.data.training_state : null;
        if (trainingState && ['training', 'stopping'].includes(trainingState.status)) {
            setTrainingControlState(trainingState.status === 'stopping' ? 'stopping' : 'running');
            startPollingTrainingStatus();
        } else {
            setTrainingControlState('idle');
        }
    });
    
    if (document.getElementById('model-analysis-select')) {
        refreshModelAnalysisOptions().finally(() => loadModelComparison());
    }
    
    // 检查是否有正在进行的应用模型任务
    API.admin.applyStatus().then(result => {
        if (result.success && result.data && result.data.status === 'processing') {
            document.getElementById('btn-apply-model').disabled = true;
            document.getElementById('btn-apply-model').innerHTML = '<i class="fas fa-spinner fa-spin"></i> 应用中...';
            startPollingApplyStatus();
        }
    });
});

// ==================== 应用模型功能 ====================

let applyPollInterval = null;

async function applyCurrentModel() {
    const btn = document.getElementById('btn-apply-model');
    
    if (!confirm('确定要使用当前模型重新对所有数据进行分类吗？这将覆盖现有的分类结果。')) {
        return;
    }

    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 启动中...';
        
        const result = await API.admin.applyModel();
        
        if (result.success) {
            showToast('success', '启动成功', '模型应用任务已在后台开始');
            startPollingApplyStatus();
        } else {
            showToast('error', '启动失败', result.error || '未知错误');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-magic"></i> 应用当前模型';
        }
    } catch (error) {
        console.error('应用模型失败:', error);
        showToast('error', '系统错误', error.message);
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic"></i> 应用当前模型';
    }
}
window.applyCurrentModel = applyCurrentModel;

async function startPollingApplyStatus() {
    const statusText = document.getElementById('training-status-text');
    const progressText = document.getElementById('training-progress-text');
    const progressBar = document.getElementById('training-progress-bar');
    const logsContainer = document.getElementById('training-logs');
    const btn = document.getElementById('btn-apply-model');
    
    // 停止训练轮询（如果存在）
    if (trainingPollInterval) clearInterval(trainingPollInterval);
    if (applyPollInterval) clearInterval(applyPollInterval);
    
    applyPollInterval = setInterval(async () => {
        try {
            const result = await API.admin.applyStatus();
            
            if (result.success && result.data) {
                const state = result.data;
                
                // 更新进度条
                const progress = state.progress || 0;
                progressBar.style.width = `${progress}%`;
                progressText.textContent = `${progress}%`;
                statusText.textContent = state.message || state.status;
                
                // 更新日志 (追加模式)
                const logMsg = `[Apply] ${state.message}`;
                // 避免重复日志: 简单检查最后一条
                const lastLog = logsContainer.lastElementChild;
                if (!lastLog || lastLog.textContent !== logMsg) {
                    const logLine = document.createElement('div');
                    logLine.className = 'log-line';
                    logLine.textContent = logMsg;
                    logsContainer.appendChild(logLine);
                    logsContainer.scrollTop = logsContainer.scrollHeight;
                }
                
                // 检查状态
                if (state.status === 'success') {
                    clearInterval(applyPollInterval);
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-magic"></i> 应用当前模型';
                    showToast('success', '处理完成', state.message);
                    progressBar.classList.add('bg-success');
                    
                    // 刷新词云和分类
                    loadWordCloudCategories().then(() => loadCategoryWordCloud());
                    
                } else if (state.status === 'failed') {
                    clearInterval(applyPollInterval);
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-magic"></i> 应用当前模型';
                    showToast('error', '处理失败', state.message);
                    progressBar.classList.add('bg-danger');
                }
            }
        } catch (error) {
            console.error('获取应用状态失败:', error);
        }
    }, 1000);
}

// ==================== 模型对比功能 ====================

let modelComparisonChart = null;
let modelComparisonResizeHandlerBound = false;
let modelRadarChart = null;
let modelTrendChart = null;
let modelConfusionChart = null;
let modelClassMetricsChart = null;
let modelDatasetRingChart = null;
let modelAnalysisModels = [];
let currentModelAnalysisSelection = null;

function normalizeModelMetric(value) {
    if (value === null || value === undefined || value === '') {
        return null;
    }

    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : null;
}

function formatModelMetric(value) {
    const numericValue = normalizeModelMetric(value);
    return numericValue === null ? '-' : `${(numericValue * 100).toFixed(2)}%`;
}

function isModelComparisonVisible() {
    const chartContainer = document.getElementById('model-comparison-chart');
    if (!chartContainer) return false;

    const adminTab = chartContainer.closest('.admin-tab');
    return (!adminTab || adminTab.classList.contains('active'))
        && chartContainer.offsetWidth > 0
        && chartContainer.offsetHeight > 0;
}

function disposeModelComparisonChart() {
    if (modelComparisonChart) {
        modelComparisonChart.dispose();
        modelComparisonChart = null;
    }
}

function renderModelComparisonPlaceholder(message, isError = false) {
    const chartContainer = document.getElementById('model-comparison-chart');
    if (!chartContainer) return;

    disposeModelComparisonChart();
    chartContainer.innerHTML = isError
        ? `<div class="error-item"><p>${message}</p></div>`
        : `<div class="empty-state"><i class="fas fa-chart-bar"></i><p>${message}</p></div>`;
}

function ensureModelComparisonChart(chartContainer) {
    if (!modelComparisonChart || modelComparisonChart.getDom() !== chartContainer) {
        disposeModelComparisonChart();
        chartContainer.innerHTML = '';
        modelComparisonChart = echarts.init(chartContainer);
    }

    if (!modelComparisonResizeHandlerBound) {
        window.addEventListener('resize', () => {
            if (modelComparisonChart) {
                modelComparisonChart.resize();
            }
        });
        modelComparisonResizeHandlerBound = true;
    }

    return modelComparisonChart;
}

function disposeChartInstance(chartRef) {
    if (chartRef && !chartRef.isDisposed()) {
        chartRef.dispose();
    }
    return null;
}

function setChartPlaceholder(container, chartRef, iconClass, message, isError = false) {
    if (!container) return null;

    const disposedChart = disposeChartInstance(chartRef);
    container.innerHTML = isError
        ? `<div class="error-item"><p>${message}</p></div>`
        : `<div class="empty-state"><i class="${iconClass}"></i><p>${message}</p></div>`;
    return disposedChart;
}

function getModelHistoryTask(record) {
    if (!record) return 'content_classification';
    if (record.nlp_task) return record.nlp_task;
    if (record.params && record.params.nlp_task) return record.params.nlp_task;
    return 'content_classification';
}

function filterModelHistoryForAnalysis(data) {
    if (!Array.isArray(data)) return [];
    let filtered = data.filter(r => getModelHistoryTask(r) === 'content_classification');
    if (currentModelAnalysisSelection && currentModelAnalysisSelection.model_type) {
        const target = String(currentModelAnalysisSelection.model_type).toLowerCase();
        filtered = filtered.filter(r => String(r.model_type || '').toLowerCase() === target);
    }
    return filtered;
}

function updateModelAnalysisDetailState() {
    const btn = document.getElementById('btn-evaluate-detail');
    if (btn) {
        btn.disabled = !currentModelAnalysisSelection;
    }
}

async function refreshModelAnalysisOptions() {
    const select = document.getElementById('model-analysis-select');
    if (!select) return;

    const prevValue = select.value;
    try {
        const modelsResp = await API.nlp.modelsList();
        const models = modelsResp && modelsResp.success ? (modelsResp.data || []) : [];
        modelAnalysisModels = models
            .filter(m => m && m.task === 'content_classification')
            .filter(m => m && m.capabilities && m.capabilities.can_predict);

        select.innerHTML = '';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '请选择模型进行分析...';
        select.appendChild(placeholder);

        for (const m of modelAnalysisModels) {
            const opt = document.createElement('option');
            opt.value = m.path || '';
            const typeLabel = m.model_type ? String(m.model_type).toUpperCase() : '';
            opt.textContent = `${m.display_name || m.name || m.path || 'model'}${typeLabel ? ` (${typeLabel})` : ''}`;
            select.appendChild(opt);
        }

        if (prevValue && modelAnalysisModels.some(m => m.path === prevValue)) {
            select.value = prevValue;
        } else {
            select.value = '';
        }
    } catch (error) {
        showToast('error', '模型加载失败', error.message);
        modelAnalysisModels = [];
        select.innerHTML = '<option value="">请选择模型进行分析...</option>';
        select.value = '';
    }

    currentModelAnalysisSelection = modelAnalysisModels.find(m => m.path === select.value) || null;
    updateModelAnalysisDetailState();
}

function onModelAnalysisSelectionChange() {
    const select = document.getElementById('model-analysis-select');
    const path = select ? (select.value || '') : '';
    currentModelAnalysisSelection = modelAnalysisModels.find(m => m.path === path) || null;

    const confusionContainer = document.getElementById('model-confusion-matrix');
    const metricsContainer = document.getElementById('model-class-metrics-chart');
    modelConfusionChart = setChartPlaceholder(confusionContainer, modelConfusionChart, 'fas fa-th', '点击"详细评估"按钮生成混淆矩阵');
    modelClassMetricsChart = setChartPlaceholder(metricsContainer, modelClassMetricsChart, 'fas fa-tags', '点击"详细评估"按钮生成类别指标');

    updateModelAnalysisDetailState();
    loadModelComparison();
}
window.onModelAnalysisSelectionChange = onModelAnalysisSelectionChange;

function resetDatasetOverviewCards() {
    const defaults = {
        'ds-total-samples': '-',
        'ds-augmented': '-',
        'ds-auto-labeled': '-',
        'ds-deduplicated': '-',
        'ds-class-count': '-',
        'ds-model-type': '-'
    };

    Object.entries(defaults).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    });
}

function resetModelDeepAnalysisViews() {
    const radarContainer = document.getElementById('model-radar-chart');
    const trendContainer = document.getElementById('model-trend-chart');
    const confusionContainer = document.getElementById('model-confusion-matrix');
    const metricsContainer = document.getElementById('model-class-metrics-chart');
    const datasetContainer = document.getElementById('model-dataset-ring');

    modelRadarChart = setChartPlaceholder(radarContainer, modelRadarChart, 'fas fa-crosshairs', '暂无评估数据');
    modelTrendChart = setChartPlaceholder(trendContainer, modelTrendChart, 'fas fa-chart-line', '暂无历史记录');
    modelConfusionChart = setChartPlaceholder(confusionContainer, modelConfusionChart, 'fas fa-th', '点击"详细评估"按钮生成混淆矩阵');
    modelClassMetricsChart = setChartPlaceholder(metricsContainer, modelClassMetricsChart, 'fas fa-tags', '点击"详细评估"按钮生成类别指标');
    modelDatasetRingChart = setChartPlaceholder(datasetContainer, modelDatasetRingChart, 'fas fa-database', '暂无数据集概况');
    resetDatasetOverviewCards();
}

async function loadModelComparison() {
    try {
        const radarContainer = document.getElementById('model-radar-chart');
        const trendContainer = document.getElementById('model-trend-chart');
        const datasetContainer = document.getElementById('model-dataset-ring');
        if (!radarContainer && !trendContainer && !datasetContainer) return;

        const result = await API.admin.modelHistory();
        if (result.success && result.data && result.data.length > 0) {
            const filtered = filterModelHistoryForAnalysis(result.data);
            if (filtered.length > 0) {
                renderRadarChart(filtered);
                renderTrendChart(filtered);
                renderDatasetOverview(filtered);
            } else {
                resetModelDeepAnalysisViews();
            }
        } else {
            resetModelDeepAnalysisViews();
        }
    } catch (error) {
        console.error('加载模型历史失败:', error);
        resetModelDeepAnalysisViews();
    }
}
window.loadModelComparison = loadModelComparison;

function renderComparisonChart(data) {
    const chartContainer = document.getElementById('model-comparison-chart');
    if (!chartContainer || !isModelComparisonVisible()) return;

    const displayData = data
        .filter(item => item.is_ranked)
        .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
        .slice(-10);

    if (displayData.length === 0) {
        renderModelComparisonPlaceholder('暂无测试集/验证集评估记录，请先训练或评估模型');
        return;
    }

    const chart = ensureModelComparisonChart(chartContainer);
    
    const xLabels = displayData.map(item => {
        const time = new Date(item.timestamp).toLocaleTimeString('zh-CN', {hour: '2-digit', minute:'2-digit'});
        return `${item.model_type}\n${time}`;
    });
    
    const accuracyData = displayData.map(item => {
        const metric = normalizeModelMetric(item.accuracy);
        return metric === null ? null : Number((metric * 100).toFixed(2));
    });
    const f1Data = displayData.map(item => {
        const metric = normalizeModelMetric(item.f1_score);
        return metric === null ? null : Number((metric * 100).toFixed(2));
    });
    
    const option = {
        title: {
            text: '模型性能排行榜 (最近10次评估)',
            left: 'center',
            textStyle: { fontSize: 14, fontWeight: 'normal' }
        },
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter(params) {
                const lines = [params[0]?.axisValueLabel?.replace('\n', ' ') || ''];
                params.forEach(param => {
                    const value = param.value === null || param.value === undefined ? '-' : `${param.value}%`;
                    lines.push(`${param.marker}${param.seriesName}: ${value}`);
                });
                return lines.join('<br/>');
            }
        },
        legend: {
            data: ['准确率 (Accuracy)', 'F1 分数'],
            bottom: 0
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '10%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: xLabels,
            axisLabel: { interval: 0, rotate: 0 }
        },
        yAxis: {
            type: 'value',
            max: 100,
            name: '百分比 (%)'
        },
        series: [
            {
                name: '准确率 (Accuracy)',
                type: 'bar',
                data: accuracyData,
                itemStyle: { color: '#3b82f6' },
                label: {
                    show: true,
                    position: 'top',
                    formatter(params) {
                        return params.value === null || params.value === undefined ? '' : `${params.value}%`;
                    }
                }
            },
            {
                name: 'F1 分数',
                type: 'bar',
                data: f1Data,
                itemStyle: { color: '#10b981' },
                label: {
                    show: true,
                    position: 'top',
                    formatter(params) {
                        return params.value === null || params.value === undefined ? '' : `${params.value}%`;
                    }
                }
            }
        ]
    };
    
    chart.setOption(option, true);
    requestAnimationFrame(() => {
        if (modelComparisonChart) {
            modelComparisonChart.resize();
        }
    });
}

function renderComparisonTable(data) {
    const tbody = document.getElementById('model-history-table-body');
    if (!tbody) return;
    
    // 按时间倒序
    const sortedData = [...data].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    tbody.innerHTML = sortedData.map(item => `
        <tr>
            <td>${new Date(item.timestamp).toLocaleString('zh-CN')}</td>
            <td><span class="badge badge-blue">${item.model_type}</span></td>
            <td>${item.type === 'train' ? '训练' : '评估'} / ${item.scope_label || '-'}</td>
            <td><b>${formatModelMetric(item.accuracy)}</b></td>
            <td>${formatModelMetric(item.f1_score)}</td>
            <td>${item.samples}</td>
        </tr>
    `).join('');
}

// ==================== 模型性能深度分析图表 ====================

const MODEL_COLORS = {
    bert: '#3b82f6',
    bert_textcnn: '#8b5cf6',
    lstm: '#f59e0b',
    cnn: '#ef4444',
    svm: '#10b981',
    nb: '#06b6d4',
    rf: '#ec4899',
    lr: '#f97316',
    knn: '#14b8a6'
};

function getModelColor(modelType) {
    return MODEL_COLORS[modelType] || '#64748b';
}

function ensureChart(container, chartRef) {
    if (chartRef && chartRef.getDom() === container) return chartRef;
    if (chartRef) chartRef.dispose();
    container.innerHTML = '';
    return echarts.init(container);
}

// --- 图表1: 多维指标雷达图 ---
function renderRadarChart(data) {
    const container = document.getElementById('model-radar-chart');
    if (!container) return;

    const ranked = data.filter(item => item.is_ranked);
    if (ranked.length === 0) {
        modelRadarChart = setChartPlaceholder(container, modelRadarChart, 'fas fa-crosshairs', '暂无评估数据');
        return;
    }

    // 按 model_type 分组，取每个模型最新的记录
    const latestByModel = {};
    ranked.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    ranked.forEach(item => {
        latestByModel[item.model_type] = item;
    });

    const models = Object.values(latestByModel);
    const indicators = [
        { name: '准确率', max: 100 },
        { name: '精确率', max: 100 },
        { name: '召回率', max: 100 },
        { name: 'F1 分数', max: 100 }
    ];

    const seriesData = models.map(item => {
        const acc = normalizeModelMetric(item.accuracy);
        const prec = normalizeModelMetric(item.precision);
        const rec = normalizeModelMetric(item.recall);
        const f1 = normalizeModelMetric(item.f1_score);
        return {
            value: [
                acc !== null ? parseFloat((acc * 100).toFixed(2)) : 0,
                prec !== null ? parseFloat((prec * 100).toFixed(2)) : 0,
                rec !== null ? parseFloat((rec * 100).toFixed(2)) : 0,
                f1 !== null ? parseFloat((f1 * 100).toFixed(2)) : 0
            ],
            name: item.model_type,
            areaStyle: { opacity: 0.15 },
            lineStyle: { width: 2 },
            itemStyle: { color: getModelColor(item.model_type) }
        };
    });

    modelRadarChart = ensureChart(container, modelRadarChart);

    const option = {
        tooltip: {
            trigger: 'item',
            formatter(params) {
                const d = params.data;
                return `<b>${d.name}</b><br/>` +
                    `准确率: ${d.value[0]}%<br/>` +
                    `精确率: ${d.value[1] > 0 ? d.value[1] + '%' : '暂无'}<br/>` +
                    `召回率: ${d.value[2] > 0 ? d.value[2] + '%' : '暂无'}<br/>` +
                    `F1 分数: ${d.value[3] > 0 ? d.value[3] + '%' : '暂无'}`;
            }
        },
        legend: {
            data: models.map(m => m.model_type),
            bottom: 0,
            textStyle: { fontSize: 12 }
        },
        radar: {
            indicator: indicators,
            shape: 'polygon',
            splitNumber: 5,
            center: ['50%', '48%'],
            radius: '65%',
            name: {
                textStyle: { fontSize: 12, color: '#475569' }
            },
            splitArea: {
                areaStyle: {
                    color: ['rgba(79,70,229,0.02)', 'rgba(79,70,229,0.04)', 'rgba(79,70,229,0.06)', 'rgba(79,70,229,0.08)', 'rgba(79,70,229,0.1)']
                }
            },
            axisLine: { lineStyle: { color: '#cbd5e1' } },
            splitLine: { lineStyle: { color: '#e2e8f0' } }
        },
        series: [{
            type: 'radar',
            data: seriesData,
            emphasis: {
                lineStyle: { width: 3 }
            }
        }]
    };

    modelRadarChart.setOption(option, true);
}

// --- 图表2: 训练趋势折线图 ---
function renderTrendChart(data) {
    const container = document.getElementById('model-trend-chart');
    if (!container) return;

    if (!data || data.length === 0) {
        modelTrendChart = setChartPlaceholder(container, modelTrendChart, 'fas fa-chart-line', '暂无历史记录');
        return;
    }

    const sorted = [...data].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    // 分离 train 和 evaluate 记录
    const trainRecords = sorted.filter(r => r.type === 'train');
    const evalRecords = sorted.filter(r => r.type === 'evaluate' || r.is_ranked);

    const formatTime = ts => {
        const d = new Date(ts);
        return `${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
    };

    // 合并所有时间轴
    const allTimestamps = sorted.map(r => r.timestamp);
    const xData = allTimestamps.map(formatTime);

    // 构建 train accuracy 系列
    const trainAccData = sorted.map(r => {
        if (r.type === 'train') {
            const v = normalizeModelMetric(r.train_accuracy || r.accuracy);
            return v !== null ? Number((v * 100).toFixed(2)) : null;
        }
        return null;
    });

    // 构建 evaluate accuracy 系列
    const evalAccData = sorted.map(r => {
        if (r.type === 'evaluate' || r.is_ranked) {
            const v = normalizeModelMetric(r.accuracy);
            return v !== null ? Number((v * 100).toFixed(2)) : null;
        }
        return null;
    });

    // 构建 scatter 数据（使用索引作为x坐标）
    const scatterByModel = {};
    sorted.forEach((r, idx) => {
        const v = normalizeModelMetric(r.accuracy);
        if (v === null) return;
        if (!scatterByModel[r.model_type]) scatterByModel[r.model_type] = [];
        scatterByModel[r.model_type].push([idx, Number((v * 100).toFixed(2))]);
    });

    const scatterSeries = Object.entries(scatterByModel).map(([mt, pts]) => ({
        name: mt,
        type: 'scatter',
        data: pts,
        symbolSize: 10,
        itemStyle: { color: getModelColor(mt) },
        z: 10
    }));

    modelTrendChart = ensureChart(container, modelTrendChart);

    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            formatter(params) {
                let lines = [params[0]?.axisValueLabel || ''];
                params.forEach(p => {
                    if (p.value !== null && p.value !== undefined) {
                        const val = Array.isArray(p.value) ? p.value[1] : p.value;
                        if (val !== null) {
                            lines.push(`${p.marker}${p.seriesName}: ${val}%`);
                        }
                    }
                });
                return lines.join('<br/>');
            }
        },
        legend: {
            data: ['训练准确率', '测试准确率', ...Object.keys(scatterByModel)],
            bottom: 0,
            textStyle: { fontSize: 11 }
        },
        grid: {
            left: '3%', right: '4%', bottom: '14%', top: '8%', containLabel: true
        },
        xAxis: {
            type: 'category',
            data: xData,
            axisLabel: { rotate: 30, fontSize: 10 },
            boundaryGap: false
        },
        yAxis: {
            type: 'value',
            max: 100,
            name: '准确率 (%)',
            nameTextStyle: { fontSize: 11 }
        },
        series: [
            {
                name: '训练准确率',
                type: 'line',
                data: trainAccData,
                lineStyle: { type: 'dashed', width: 2, color: '#94a3b8' },
                itemStyle: { color: '#94a3b8' },
                symbol: 'none',
                connectNulls: true
            },
            {
                name: '测试准确率',
                type: 'line',
                data: evalAccData,
                lineStyle: { width: 2.5, color: '#4f46e5' },
                itemStyle: { color: '#4f46e5' },
                symbol: 'none',
                connectNulls: true,
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(79,70,229,0.15)' },
                        { offset: 1, color: 'rgba(79,70,229,0.01)' }
                    ])
                }
            },
            ...scatterSeries
        ]
    };

    modelTrendChart.setOption(option, true);
}

// --- 图表3: 混淆矩阵热力图 ---
function renderConfusionMatrix(cmData) {
    const container = document.getElementById('model-confusion-matrix');
    if (!container) return;

    if (!cmData || !cmData.matrix || !cmData.labels) {
        modelConfusionChart = setChartPlaceholder(container, modelConfusionChart, 'fas fa-th', '无混淆矩阵数据');
        return;
    }

    const labels = cmData.labels;
    const matrix = cmData.matrix;

    // 构建 heatmap data: [x, y, value]
    const heatmapData = [];
    let maxVal = 0;
    for (let i = 0; i < matrix.length; i++) {
        for (let j = 0; j < matrix[i].length; j++) {
            heatmapData.push([j, i, matrix[i][j]]);
            if (matrix[i][j] > maxVal) maxVal = matrix[i][j];
        }
    }

    modelConfusionChart = ensureChart(container, modelConfusionChart);

    const option = {
        tooltip: {
            position: 'top',
            formatter(params) {
                return `真实: <b>${labels[params.value[1]]}</b><br/>` +
                       `预测: <b>${labels[params.value[0]]}</b><br/>` +
                       `数量: <b>${params.value[2]}</b>`;
            }
        },
        grid: {
            left: '18%', right: '12%', bottom: '18%', top: '4%'
        },
        xAxis: {
            type: 'category',
            data: labels,
            name: '预测类别',
            nameLocation: 'center',
            nameGap: 40,
            axisLabel: { rotate: 45, fontSize: 10, interval: 0 },
            splitArea: { show: true }
        },
        yAxis: {
            type: 'category',
            data: labels,
            name: '真实类别',
            nameLocation: 'center',
            nameGap: 70,
            axisLabel: { fontSize: 10, interval: 0 },
            splitArea: { show: true }
        },
        visualMap: {
            min: 0,
            max: maxVal || 1,
            calculable: true,
            orient: 'vertical',
            right: '2%',
            top: 'center',
            itemHeight: 200,
            inRange: {
                color: ['#fff7ec', '#fee8c8', '#fdd49e', '#fdbb84', '#fc8d59', '#ef6548', '#d7301f', '#b30000', '#7f0000']
            },
            outOfRange: {
                color: '#f3f4f6'
            }
        },
        series: [{
            type: 'heatmap',
            data: heatmapData,
            label: {
                show: labels.length <= 10,
                fontSize: 10,
                color: '#1e293b',
                textBorderColor: '#ffffff',
                textBorderWidth: 2,
                formatter(params) {
                    return params.value[2] > 0 ? params.value[2] : '';
                }
            },
            emphasis: {
                itemStyle: {
                    shadowBlur: 10,
                    shadowColor: 'rgba(0, 0, 0, 0.3)'
                }
            }
        }]
    };

    modelConfusionChart.setOption(option, true);
}

// --- 图表4: 各类别 F1/Precision/Recall 分组柱状图 ---
function renderClassMetricsChart(reportData) {
    const container = document.getElementById('model-class-metrics-chart');
    if (!container) return;

    if (!reportData) {
        modelClassMetricsChart = setChartPlaceholder(container, modelClassMetricsChart, 'fas fa-tags', '无分类报告数据');
        return;
    }

    // 过滤掉 macro avg / weighted avg / accuracy 等汇总行
    const skipKeys = ['accuracy', 'macro avg', 'weighted avg', 'micro avg'];
    const categories = Object.keys(reportData).filter(k => !skipKeys.includes(k));

    if (categories.length === 0) {
        modelClassMetricsChart = setChartPlaceholder(container, modelClassMetricsChart, 'fas fa-tags', '无分类详情数据');
        return;
    }

    const precisionData = categories.map(c => Number(((reportData[c].precision || 0) * 100).toFixed(2)));
    const recallData = categories.map(c => Number(((reportData[c].recall || 0) * 100).toFixed(2)));
    const f1Data = categories.map(c => Number((((reportData[c]['f1-score'] || reportData[c].f1_score || 0)) * 100).toFixed(2)));

    modelClassMetricsChart = ensureChart(container, modelClassMetricsChart);

    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter(params) {
                let lines = [`<b>${params[0].axisValueLabel}</b>`];
                params.forEach(p => {
                    lines.push(`${p.marker}${p.seriesName}: ${p.value}%`);
                });
                // 附加 support 数量
                const cat = params[0].axisValueLabel;
                const support = reportData[cat] && reportData[cat].support;
                if (support !== undefined) {
                    lines.push(`样本数: ${support}`);
                }
                return lines.join('<br/>');
            }
        },
        legend: {
            data: ['精确率', '召回率', 'F1 分数'],
            bottom: 0,
            textStyle: { fontSize: 11 }
        },
        grid: {
            left: '3%', right: '4%', bottom: '12%', top: '6%', containLabel: true
        },
        xAxis: {
            type: 'category',
            data: categories,
            axisLabel: { rotate: 35, fontSize: 10, interval: 0 }
        },
        yAxis: {
            type: 'value',
            max: 100,
            name: '%',
            nameTextStyle: { fontSize: 11 }
        },
        series: [
            {
                name: '精确率',
                type: 'bar',
                data: precisionData,
                itemStyle: { color: '#3b82f6' },
                barMaxWidth: 20
            },
            {
                name: '召回率',
                type: 'bar',
                data: recallData,
                itemStyle: { color: '#f59e0b' },
                barMaxWidth: 20
            },
            {
                name: 'F1 分数',
                type: 'bar',
                data: f1Data,
                itemStyle: { color: '#10b981' },
                barMaxWidth: 20
            }
        ]
    };

    modelClassMetricsChart.setOption(option, true);
}

// --- 图表5: 数据集概况环形图 + 统计卡片 ---
function renderDatasetOverview(data) {
    if (!data || data.length === 0) {
        resetModelDeepAnalysisViews();
        return;
    }

    // 取最新一条记录
    const sorted = [...data].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    const latest = sorted[0];

    const samples = latest.samples || 0;
    const augmented = latest.augmented_samples || 0;
    const autoLabeled = latest.auto_labeled_samples || 0;
    const deduplicated = latest.deduplicated_samples || 0;
    const classCount = latest.class_count || 0;
    const modelType = latest.model_type || '-';

    // 更新统计卡片
    const setEl = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };
    setEl('ds-total-samples', samples.toLocaleString());
    setEl('ds-augmented', augmented.toLocaleString());
    setEl('ds-auto-labeled', autoLabeled.toLocaleString());
    setEl('ds-deduplicated', deduplicated.toLocaleString());
    setEl('ds-class-count', classCount);
    setEl('ds-model-type', modelType.toUpperCase());

    // 环形图
    const container = document.getElementById('model-dataset-ring');
    if (!container) return;

    const originalSamples = Math.max(0, samples - augmented);

    modelDatasetRingChart = ensureChart(container, modelDatasetRingChart);

    const option = {
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c} ({d}%)'
        },
        legend: {
            orient: 'vertical',
            right: 0,
            top: 'center',
            textStyle: { fontSize: 11 },
            itemWidth: 12,
            itemHeight: 12
        },
        series: [{
            type: 'pie',
            radius: ['42%', '70%'],
            center: ['40%', '50%'],
            avoidLabelOverlap: true,
            padAngle: 2,
            itemStyle: {
                borderRadius: 6,
                borderColor: '#fff',
                borderWidth: 2
            },
            label: {
                show: false
            },
            emphasis: {
                label: {
                    show: true,
                    fontSize: 14,
                    fontWeight: 'bold'
                }
            },
            data: [
                { value: originalSamples, name: '原始样本', itemStyle: { color: '#4f46e5' } },
                { value: augmented, name: '增强样本', itemStyle: { color: '#8b5cf6' } },
                { value: autoLabeled, name: '自动标注', itemStyle: { color: '#06b6d4' } },
                { value: deduplicated, name: '去重删除', itemStyle: { color: '#ef4444' } }
            ].filter(d => d.value > 0)
        }]
    };

    modelDatasetRingChart.setOption(option, true);
}

// --- 触发详细评估 (混淆矩阵 + 类别指标) ---
async function evaluateAndRenderDetails() {
    const btn = document.getElementById('btn-evaluate-detail');
    if (!btn) return;

    if (!currentModelAnalysisSelection || !currentModelAnalysisSelection.path) {
        showToast('warning', '请选择模型', '请先在右上角选择要分析的模型');
        return;
    }

    btn.classList.add('loading');
    btn.innerHTML = '<i class="fas fa-spinner"></i> 评估中...';

    try {
        const result = await API.admin.evaluateSavedModel(currentModelAnalysisSelection.path);
        if (result.success && result.data) {
            const { metrics, confusion_matrix: cmData } = result.data;
            if (cmData) renderConfusionMatrix(cmData);
            if (metrics && metrics.classification_report) {
                renderClassMetricsChart(metrics.classification_report);
            }
            const acc = metrics && typeof metrics.accuracy === 'number' ? (metrics.accuracy * 100).toFixed(2) : '-';
            const f1 = metrics && typeof metrics.f1_score === 'number' ? (metrics.f1_score * 100).toFixed(2) : '-';
            showToast('success', '评估完成', `Accuracy ${acc}%, F1 ${f1}%`);
        } else {
            showToast('error', '评估失败', result.error || '未知错误');
        }
    } catch (error) {
        showToast('error', '评估出错', error.message);
    } finally {
        btn.classList.remove('loading');
        btn.innerHTML = '<i class="fas fa-microscope"></i> 详细评估';
    }
}
window.evaluateAndRenderDetails = evaluateAndRenderDetails;

// --- 统一 resize 所有新增图表 ---
function resizeAllModelCharts() {
    [modelRadarChart, modelTrendChart, modelConfusionChart, modelClassMetricsChart, modelDatasetRingChart].forEach(chart => {
        if (chart && !chart.isDisposed()) chart.resize();
    });
}

if (!modelComparisonResizeHandlerBound) {
    // resize handler 由 ensureModelComparisonChart 绑定，这里补充新图表
} else {
    // 如果已绑定，追加新图表的 resize
}
window.addEventListener('resize', resizeAllModelCharts);

async function clearModelHistory() {
    if (!confirm('确定要清空所有模型历史记录吗？')) return;
    
    try {
        const result = await API.admin.clearModelHistory();
        if (result.success) {
            showToast('success', '成功', '历史记录已清空');
            resetModelDeepAnalysisViews();
            loadModelComparison();
        } else {
            showToast('error', '失败', result.error);
        }
    } catch (error) {
        showToast('error', '错误', error.message);
    }
}
window.clearModelHistory = clearModelHistory;

async function clearSavedModel() {
    if (!confirm('确定要清除训练模型吗？\n这将重置当前内存中的模型，并删除 saved_models 下除 pretrained（预训练权重缓存）外的模型存档。')) return;

    try {
        const result = await API.admin.clearModel();
        if (result.success) {
            showToast('success', '成功', result.message || '模型已清除');
            loadModelComparison();
        } else {
            showToast('error', '失败', result.error);
        }
    } catch (error) {
        showToast('error', '错误', error.message);
    }
}
window.clearSavedModel = clearSavedModel;

function loadWordCloudPage() {
    loadWordCloudCategories().then(() => loadWordCloudInsights());
}

// ==================== 分类词云功能 ====================

let categoryWordBarrageController = null;
const CATEGORY_WORD_CLOUD_MODE = 'static';

function stopCategoryWordBarrage() {
    if (categoryWordBarrageController) {
        categoryWordBarrageController.stop();
        categoryWordBarrageController = null;
    }
}

function hashStringToHue(input) {
    let hash = 0;
    for (let i = 0; i < input.length; i++) {
        hash = ((hash << 5) - hash) + input.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash) % 360;
}

function renderStaticWordCloud(container, words) {
    const maxCount = words && words.length > 0 ? words[0].count : 1;
    container.innerHTML = `
        <div class="word-cloud-tags">
            ${words.map((item) => {
                const normalized = maxCount > 0 ? (item.count / maxCount) : 0;
                const size = Math.max(1, Math.min(5, Math.ceil(normalized * 5)));
                const hue = hashStringToHue(item.word);
                return `
                    <span class="word-tag size-${size}" style="--tag-hue: ${hue};" title="${escapeHtml(item.word)} (${item.count})">
                        <span class="word-text">${escapeHtml(item.word)}</span>
                        <span class="word-count">(${item.count})</span>
                    </span>
                `;
            }).join('')}
        </div>
    `;
}

function createCategoryWordBarrage(container, words) {
    const stage = document.createElement('div');
    stage.className = 'barrage-stage';
    container.innerHTML = '';
    container.appendChild(stage);

    const colors = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#06b6d4', '#3b82f6', '#8b5cf6', '#ec4899'];
    const maxCount = Math.max(...words.map(w => w.count));
    const weights = words.map(w => Math.max(1, w.count));
    const totalWeight = weights.reduce((a, b) => a + b, 0);

    let laneCount = 6;
    let laneHeight = 30;
    let laneAvailableAt = new Array(laneCount).fill(0);
    let spawnTimer = null;
    let stopped = false;
    let visibilityHandler = null;

    function updateLanes() {
        const rect = stage.getBoundingClientRect();
        const height = rect.height || 0;
        laneCount = Math.max(5, Math.min(12, Math.floor(height / laneHeight) || 6));
        laneAvailableAt = new Array(laneCount).fill(0);
    }

    function pickWord() {
        let r = Math.random() * totalWeight;
        for (let i = 0; i < words.length; i++) {
            r -= weights[i];
            if (r <= 0) return words[i];
        }
        return words[words.length - 1];
    }

    function pickLane(now) {
        let bestIdx = 0;
        let bestTime = laneAvailableAt[0] || 0;
        for (let i = 1; i < laneAvailableAt.length; i++) {
            if (laneAvailableAt[i] < bestTime) {
                bestTime = laneAvailableAt[i];
                bestIdx = i;
            }
        }
        if (bestTime <= now) return bestIdx;

        const available = [];
        for (let i = 0; i < laneAvailableAt.length; i++) {
            if (laneAvailableAt[i] <= now) available.push(i);
        }
        if (available.length > 0) return available[Math.floor(Math.random() * available.length)];
        return bestIdx;
    }

    function spawnOnce() {
        if (stopped) return;
        if (document.hidden) return;

        const rect = stage.getBoundingClientRect();
        const width = rect.width || 0;
        const height = rect.height || 0;
        if (width <= 0 || height <= 0) return;

        const now = Date.now();
        const laneIndex = pickLane(now);
        const item = pickWord();
        const normalized = maxCount > 0 ? (item.count / maxCount) : 0;

        const el = document.createElement('span');
        el.className = 'barrage-item';
        el.title = `${item.word} (${item.count})`;
        el.style.color = colors[Math.floor(Math.random() * colors.length)];
        el.style.fontSize = `${13 + normalized * 18}px`;
        el.style.opacity = `${0.85 + normalized * 0.15}`;

        const duration = 9 + normalized * 7;
        el.style.animationDuration = `${duration}s`;
        el.style.animationDelay = `${Math.random() * 0.6}s`;
        el.style.animationIterationCount = '1';

        const topJitter = Math.max(0, laneHeight - 24);
        el.style.top = `${laneIndex * laneHeight + Math.random() * topJitter}px`;

        const textNode = document.createTextNode(item.word);
        const countNode = document.createElement('span');
        countNode.className = 'barrage-count';
        countNode.textContent = `(${item.count})`;
        el.appendChild(textNode);
        el.appendChild(countNode);

        el.addEventListener('animationend', () => {
            if (el.parentNode) el.parentNode.removeChild(el);
        });

        stage.appendChild(el);

        if (stage.childElementCount > 140) {
            while (stage.childElementCount > 120) {
                stage.removeChild(stage.firstElementChild);
            }
        }

        const elWidth = el.getBoundingClientRect().width || 0;
        const speed = (width + elWidth + 80) / duration;
        const gap = 18;
        laneAvailableAt[laneIndex] = now + ((elWidth + gap) / Math.max(1, speed)) * 1000;
    }

    function start() {
        stopped = false;
        updateLanes();
        spawnOnce();
        spawnTimer = setInterval(spawnOnce, 200);
        window.addEventListener('resize', updateLanes);
        visibilityHandler = () => {
            if (!document.hidden) spawnOnce();
        };
        document.addEventListener('visibilitychange', visibilityHandler);
    }

    function stop() {
        stopped = true;
        if (spawnTimer) clearInterval(spawnTimer);
        spawnTimer = null;
        window.removeEventListener('resize', updateLanes);
        if (visibilityHandler) {
            document.removeEventListener('visibilitychange', visibilityHandler);
            visibilityHandler = null;
        }
        if (container.contains(stage)) {
            container.innerHTML = '';
        }
    }

    return { start, stop };
}

async function loadWordCloudCategories() {
    const select = document.getElementById('cloud-category-select');
    if (!select) return;

    try {
        const result = await API.admin.modelStatus();
        if (result.success && result.data && result.data.categories) {
            const categories = result.data.categories;
            const currentVal = select.value;
            
            // 如果分类列表为空，不进行更新
            if (!categories || categories.length === 0) return;

            // 保留"全部分类"选项
            let options = '<option value="all">全部分类</option>';
            
            categories.forEach(cat => {
                options += `<option value="${cat}">${cat}</option>`;
            });
            
            select.innerHTML = options;
            
            // 尝试恢复之前的选择
            if (currentVal && (currentVal === 'all' || categories.includes(currentVal))) {
                select.value = currentVal;
            }
        }
    } catch (error) {
        console.error('加载词云分类列表失败:', error);
    }
}

async function loadCategoryWordCloud() {
    const category = document.getElementById('cloud-category-select').value;
    const container = document.getElementById('category-word-cloud-container');
    
    stopCategoryWordBarrage();
    container.innerHTML = `
        <div class="loading-item">
            <i class="fas fa-spinner fa-spin"></i>
            正在生成 ${category === 'all' ? '全部' : category} 词云...
        </div>
    `;
    
    try {
        const result = await API.admin.wordFrequency({ 
            top_k: 50,
            category: category === 'all' ? null : category
        });
        
        if (result.success && result.data.word_frequency) {
            const words = result.data.word_frequency;
            
            if (words.length === 0) {
                container.innerHTML = '<div class="empty-state"><i class="fas fa-font"></i><p>该分类下暂无数据</p></div>';
                return;
            }

            const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (prefersReducedMotion || CATEGORY_WORD_CLOUD_MODE === 'static') {
                renderStaticWordCloud(container, words);
                return;
            }

            categoryWordBarrageController = createCategoryWordBarrage(container, words);
            categoryWordBarrageController.start();
        } else {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-font"></i><p>暂无词频数据</p></div>';
        }
    } catch (error) {
        console.error('加载词云失败:', error);
        container.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>加载失败</p></div>';
    }
}

window.loadCategoryWordCloud = loadCategoryWordCloud;

function ensureKeywordTrendsResizeHandler() {
    if (keywordTrendsResizeHandlerBound) return;
    window.addEventListener('resize', () => {
        if (keywordTrendsChart) keywordTrendsChart.resize();
    });
    keywordTrendsResizeHandlerBound = true;
}

function disposeKeywordTrendsChart() {
    keywordTrendsChart = disposeChartInstance(keywordTrendsChart);
}

async function loadKeywordTrends() {
    const container = document.getElementById('chart-keyword-trends');
    if (!container) return;
    if (!container.offsetWidth || !container.offsetHeight) return;

    ensureKeywordTrendsResizeHandler();

    const categoryVal = document.getElementById('cloud-category-select')?.value || 'all';
    const days = parseInt(document.getElementById('trend-days-select')?.value || '14', 10);
    const topK = parseInt(document.getElementById('trend-topk-select')?.value || '5', 10);
    const category = categoryVal === 'all' ? null : categoryVal;

    keywordTrendsChart = setChartPlaceholder(container, keywordTrendsChart, 'fas fa-chart-line', '加载中...');

    try {
        const resp = await API.visualize.keywordTrends({
            days: Number.isFinite(days) ? days : 14,
            top_k: Number.isFinite(topK) ? topK : 5,
            category: category || undefined
        });

        if (!resp?.success) {
            keywordTrendsChart = setChartPlaceholder(container, keywordTrendsChart, 'fas fa-chart-line', resp?.error || '加载失败', true);
            return;
        }

        const data = resp.data || {};
        const dates = data.dates || [];
        const series = data.series || [];

        if (!dates.length || !series.length) {
            keywordTrendsChart = setChartPlaceholder(container, keywordTrendsChart, 'fas fa-chart-line', '暂无数据');
            return;
        }

        keywordTrendsChart = ensureChart(container, keywordTrendsChart);
        const option = {
            tooltip: { trigger: 'axis' },
            legend: { type: 'scroll', bottom: 0 },
            grid: { left: 44, right: 16, top: 16, bottom: 44 },
            xAxis: {
                type: 'category',
                data: dates,
                axisLabel: { rotate: dates.length > 10 ? 30 : 0 }
            },
            yAxis: { type: 'value' },
            series: series.map(s => ({
                name: s.name,
                type: 'line',
                smooth: true,
                showSymbol: false,
                data: s.data || []
            }))
        };
        keywordTrendsChart.setOption(option, true);
    } catch (error) {
        keywordTrendsChart = setChartPlaceholder(container, keywordTrendsChart, 'fas fa-chart-line', error.message || '加载失败', true);
    }
}

async function loadWordCloudInsights() {
    await Promise.all([
        loadKeywordTrends(),
        loadCategoryWordCloud()
    ]);
}

window.loadWordCloudInsights = loadWordCloudInsights;

