// ==================== 全局状态 ====================
let currentGame = '3d';
let currentPage = 'trend';
let currentFilter = 'all';
let rawHistory = [];
let statsCache = null;
let analysisCache = null;  // 后端智能分析结果缓存
let isDemoData = false;

// ==================== Mulberry32 ====================
function mulberry32(seed) {
    let state = seed | 0;
    return function () {
        state = (state + 0x6D2B79F5) | 0;
        let t = Math.imul(state ^ (state >>> 15), 1 | state);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

// ==================== 号码解析 ====================
function parseNumberToDigits(numStr) {
    const cleaned = numStr.toString().trim();
    if (cleaned.includes(' ')) {
        const parts = cleaned.split(/\s+/);
        if (parts.length === 3) return parts.map(p => parseInt(p, 10));
    }
    if (/^\d{3}$/.test(cleaned)) {
        return cleaned.split('').map(c => parseInt(c, 10));
    }
    return [0, 0, 0];
}

function calcIndicators(digits) {
    const [a, b, c] = digits;
    const sum = a + b + c;
    const span = Math.max(a, b, c) - Math.min(a, b, c);
    const type = a === b && b === c ? '豹子' : (a === b || b === c || a === c ? '组三' : '组六');
    return { sum, span, type };
}

function getTypeClass(type) {
    if (type === '组六') return 'type--zu6';
    if (type === '组三') return 'type--zu3';
    return 'type--bao';
}

function getMissPeriod(position, digit) {
    if (!rawHistory.length) return '-';
    for (let i = 0; i < rawHistory.length; i++) {
        if (rawHistory[i].digits[position] === digit) return i;
    }
    return rawHistory.length;
}

// ==================== 统计计算 ====================
function computeStats(history) {
    const hash = history.length + '|' + (history[0]?.issue || '');
    if (statsCache && statsCache._hash === hash) return statsCache;

    const recent = history.slice(0, 20);

    const freq = [Array(10).fill(0), Array(10).fill(0), Array(10).fill(0)];
    recent.forEach(r => {
        for (let pos = 0; pos < 3; pos++) freq[pos][r.digits[pos]]++;
    });

    const hot = freq.map(f => {
        const max = Math.max(...f);
        return f.reduce((a, v, i) => { if (v === max) a.push(i); return a; }, []);
    });
    const cold = freq.map(f => {
        const min = Math.min(...f.filter(v => v > 0));
        return f.reduce((a, v, i) => { if (v === min && v > 0) a.push(i); return a; }, []);
    });

    // 各位置遗漏
    const miss = [Array(10).fill(0), Array(10).fill(0), Array(10).fill(0)];
    for (let pos = 0; pos < 3; pos++) {
        for (let d = 0; d < 10; d++) {
            miss[pos][d] = getMissPeriod(pos, d);
        }
    }

    // 杀码
    const DECAY = 6;
    const weightedFreq = Array(10).fill(0);
    recent.forEach((r, idx) => {
        const w = Math.exp(-idx / DECAY);
        for (let pos = 0; pos < 3; pos++) weightedFreq[r.digits[pos]] += w;
    });

    const lastSeen = Array(10).fill(recent.length);
    for (let d = 0; d < 10; d++) {
        for (let i = 0; i < recent.length; i++) {
            if (recent[i].digits.includes(d)) { lastSeen[d] = i; break; }
        }
    }

    const coldnessScore = Array(10).fill(0);
    for (let d = 0; d < 10; d++) {
        coldnessScore[d] = weightedFreq[d] * 10 - lastSeen[d];
    }

    const sorted = coldnessScore.map((s, d) => ({ digit: d, score: s }))
        .sort((a, b) => a.score - b.score);
    const killCodes = [sorted[0].digit, sorted[1].digit];
    const killReasons = killCodes.map(k => {
        const ls = lastSeen[k];
        return ls === recent.length ? '近20期未出' : `遗漏${ls}期`;
    });

    // 和值/跨度范围
    const sums = recent.map(r => r.sum).sort((a, b) => a - b);
    const spans = recent.map(r => r.span).sort((a, b) => a - b);
    const p25 = Math.floor(recent.length * 0.25);
    const p75 = Math.floor(recent.length * 0.75);
    const sumRange = [Math.max(0, sums[p25] - 3), Math.min(27, sums[p75] + 3)];
    const spanRange = [Math.max(0, spans[p25] - 1), Math.min(9, spans[p75] + 1)];

    // 形态占比
    const typeCounts = { '组六': 0, '组三': 0, '豹子': 0 };
    recent.forEach(r => typeCounts[r.type]++);
    const typeRatio = {};
    for (const t in typeCounts) typeRatio[t] = typeCounts[t] / recent.length;

    statsCache = {
        freq, hot, cold, miss,
        weightedFreq, lastSeen,
        killCodes, killReasons,
        sumRange, spanRange,
        typeRatio,
        _hash: hash
    };
    return statsCache;
}

function getNumberNote(position, digit, stats) {
    if (stats.hot[position].includes(digit)) return '热号';
    if (stats.cold[position].includes(digit)) return `冷号(遗漏${getMissPeriod(position, digit)}期)`;
    return '常规';
}

// ==================== 页面切换 ====================
function switchPage(pageName) {
    currentPage = pageName;
    document.querySelectorAll('.page').forEach(p => p.classList.remove('page--active'));
    document.getElementById('page-' + pageName).classList.add('page--active');
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.toggle('active', t.dataset.page === pageName));

    // 切换页面时重新渲染（数据已缓存）
    if (pageName === 'trend') renderTrendPage();
    if (pageName === 'recommend') renderRecommendPage();
    if (pageName === 'stats') renderStatsPage();
}

// ==================== 数据刷新 ====================
async function refreshData() {
    showToast('加载中…');
    const [dataObj, analysis] = await Promise.all([
        fetchLotteryData(currentGame),
        fetchAnalysis(currentGame)
    ]);
    isDemoData = !!(dataObj && dataObj._demo);

    if (dataObj && dataObj.data) {
        rawHistory = dataObj.data.map(item => {
            const digits = parseNumberToDigits(item.number);
            const indicators = calcIndicators(digits);
            return { issue: item.issue, date: item.date || '', digits, sum: indicators.sum, span: indicators.span, type: indicators.type };
        }).sort((a, b) => b.issue.localeCompare(a.issue));

        statsCache = null;
        analysisCache = analysis;
        document.getElementById('lastUpdateTime').innerText = new Date().toLocaleString();
        renderDemoBanner();
        updateKillCodeDisplay();
        renderAllPages();
        showToast(isDemoData ? '演示数据已加载' : '数据已刷新');
    } else {
        showToast('数据加载失败，请检查后端');
    }
}

function renderDemoBanner() {
    const banner = document.getElementById('demoBanner');
    if (banner) banner.style.display = isDemoData ? 'block' : 'none';
}

function renderAllPages() {
    if (currentPage === 'trend') renderTrendPage();
    else if (currentPage === 'recommend') renderRecommendPage();
    else if (currentPage === 'stats') renderStatsPage();
}

// ==================== Toast ====================
let toastTimer;
function showToast(msg) {
    let el = document.getElementById('toast');
    if (!el) {
        el = document.createElement('div');
        el.id = 'toast';
        document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.opacity = '1';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.style.opacity = '0'; }, 1500);
}

// ==================== 走势页面 ====================
function renderTrendPage() {
    const container = document.getElementById('trendCardList');
    if (!rawHistory.length) {
        container.innerHTML = '<div class="empty-state">暂无数据，请检查后端</div>';
        return;
    }

    const stats = computeStats(rawHistory);
    const { hot, cold } = stats;

    let filtered = rawHistory;
    if (currentFilter !== 'all') {
        filtered = rawHistory.filter(r => r.type === currentFilter);
    }

    if (!filtered.length) {
        container.innerHTML = `<div class="empty-state">暂无「${currentFilter}」形态记录</div>`;
        return;
    }

    container.innerHTML = filtered.slice(0, 50).map((rec, idx) => {
        const digitsHtml = rec.digits.map((d, pos) => {
            let cls = '';
            if (hot[pos].includes(d)) cls = ' trend-card__digit--hot';
            else if (cold[pos].includes(d)) cls = ' trend-card__digit--cold';
            return `<span class="trend-card__digit${cls}">${d}</span>`;
        }).join('');

        return `<div class="trend-card" style="animation-delay:${idx * 0.03}s">
            <span class="trend-card__issue">${rec.issue}</span>
            <div class="trend-card__digits">${digitsHtml}</div>
            <div class="trend-card__meta">
                <span class="trend-card__sumspan">和${rec.sum} 跨${rec.span}</span>
                <span class="trend-card__type ${getTypeClass(rec.type)}">${rec.type}</span>
            </div>
        </div>`;
    }).join('');
}

// ==================== 推荐页面 ====================
function renderRecommendPage() {
    const container = document.getElementById('recommendList');
    const analysis = analysisCache;

    if (!analysis || !analysis.candidates || analysis.candidates.length === 0) {
        container.innerHTML = '<div class="empty-state">分析数据加载中…<br><small>请确保后端服务已启动</small></div>';
        return;
    }

    let html = '';

    // 最新开奖
    const last = analysis.latest;
    html += `<div class="reco-card--latest">
        <div class="reco-card__header">
            <span>上期 ${last.issue}</span>
            <span>开 <strong>${last.number}</strong> (${last.type}) 和${last.sum} 跨${last.span}</span>
        </div>
    </div>`;

    // 趋势概览
    const trend = analysis.trend;
    if (trend && trend.sum_parity) {
        const sp = trend.sum_parity;
        const oe = trend.odd_even_ratio;
        const n = (sp['奇'] || 0) + (sp['偶'] || 0);
        html += `<div class="reco-card--trend">
            <div class="reco-card__title">趋势概览（近${n}期）</div>
            <div class="trend-bars">
                <div class="trend-row">
                    <span class="trend-label">和值奇偶</span>
                    <span class="trend-val">奇 ${sp['奇']||0}</span>
                    <span class="trend-val">偶 ${sp['偶']||0}</span>
                </div>
                <div class="trend-row">
                    <span class="trend-label">单双比</span>
                    <span class="trend-val">全奇 ${oe['全奇(3:0)']||0}</span>
                    <span class="trend-val">2奇 ${oe['两奇一偶(2:1)']||0}</span>
                    <span class="trend-val">1奇 ${oe['一奇两偶(1:2)']||0}</span>
                    <span class="trend-val">全偶 ${oe['全偶(0:3)']||0}</span>
                </div>
            </div>
        </div>`;
    }

    // 精选推荐
    const maxScore = Math.max(...analysis.candidates.map(c => c.score), 1);
    analysis.candidates.forEach((c, idx) => {
        const isPair = (c.nums[0] === c.nums[1] || c.nums[1] === c.nums[2]);
        const cardClass = isPair ? 'reco-card reco-card--zusan' : 'reco-card';
        const badgeClass = isPair ? 'reco-card__badge reco-card__badge--zusan' : 'reco-card__badge';
        html += `<div class="${cardClass}" style="animation-delay:${idx * 0.06}s">
            <div class="reco-card__header">
                <div class="reco-card__digits">
                    ${c.num_str.split('').map(d => `<span class="reco-digit">${d}</span>`).join('')}
                </div>
                <div class="reco-card__info">
                    <span class="${badgeClass}">#${idx + 1}</span>
                    <span class="reco-card__meta">和${c.sum} 跨${c.span}</span>
                    <span class="reco-card__meta">${c.score}分</span>
                </div>
            </div>
            <div class="reco-card__score-bar">
                <div class="reco-card__score-fill" style="width:${(c.score / maxScore * 100).toFixed(0)}%"></div>
            </div>
        </div>`;
    });

    container.innerHTML = html;
}

// ==================== 统计页面 ====================
function renderStatsPage() {
    if (rawHistory.length < 10) {
        document.getElementById('hotColdSection').innerHTML = '<div class="stats-section"><div class="empty-state" style="padding:24px">数据不足（需至少10期）</div></div>';
        document.getElementById('missSection').innerHTML = '';
        document.getElementById('summaryGrid').innerHTML = '';
        return;
    }

    const stats = computeStats(rawHistory);
    const { hot, cold, miss } = stats;

    // 热冷号 — 频率柱状图
    const positions = ['百位', '十位', '个位'];
    const maxFreq = Math.max(...stats.freq.flat());
    document.getElementById('hotColdSection').innerHTML = `
        <div class="stats-section">
            <div class="stats-section__title">号码频率分布（近20期）</div>
            <div class="freq-chart">
                ${positions.map((name, i) => `
                    <div class="freq-chart__row">
                        <span class="freq-chart__label">${name}</span>
                        <div class="freq-chart__bars">
                            ${[0,1,2,3,4,5,6,7,8,9].map(d => {
                                const f = stats.freq[i][d];
                                const h = Math.max(8, (f / Math.max(maxFreq, 1)) * 48);
                                let cls = 'freq-bar--warm';
                                if (hot[i].includes(d)) cls = 'freq-bar--hot';
                                else if (cold[i].includes(d)) cls = 'freq-bar--cold';
                                return `<div class="freq-bar ${cls}">
                                    <span class="freq-bar__count">${f}</span>
                                    <div class="freq-bar__fill" style="height:${h}px"></div>
                                    <span class="freq-bar__digit">${d}</span>
                                </div>`;
                            }).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    // 遗漏分析 — 横排圆角方块
    document.getElementById('missSection').innerHTML = `
        <div class="stats-section">
            <div class="stats-section__title">遗漏期数分析</div>
            <div class="miss-row miss-row--header">
                <span class="miss-row__label"></span>
                ${[0,1,2,3,4,5,6,7,8,9].map(d => `<span class="miss-dot miss-dot--header">${d}</span>`).join('')}
            </div>
            ${positions.map((name, i) => `
                <div class="miss-row">
                    <span class="miss-row__label">${name}</span>
                    ${[0,1,2,3,4,5,6,7,8,9].map(d => {
                        const v = miss[i][d];
                        let cls = '';
                        if (v >= 15) cls = ' miss-dot--cold';
                        else if (v <= 2) cls = ' miss-dot--hot';
                        else if (v >= 8) cls = ' miss-dot--warm';
                        return `<span class="miss-dot${cls}" title="${name}数字${d}遗漏${v}期">${v}</span>`;
                    }).join('')}
                </div>
            `).join('')}
        </div>
    `;

    // 汇总统计
    const mode = arr => {
        const freq = {};
        arr.forEach(v => freq[v] = (freq[v] || 0) + 1);
        const max = Math.max(...Object.values(freq));
        return Object.entries(freq).filter(([, v]) => v === max).map(([k]) => k).join(',');
    };
    const sums = rawHistory.map(r => r.sum);
    const spans = rawHistory.map(r => r.span);
    const types = rawHistory.map(r => r.type);
    const typeCounts = { '组六': 0, '组三': 0, '豹子': 0 };
    types.forEach(t => typeCounts[t]++);
    const mainType = Object.entries(typeCounts).sort((a, b) => b[1] - a[1])[0][0];

    document.getElementById('summaryGrid').innerHTML = `
        <div class="stat-card">常见和值<span class="stat-card__value">${mode(sums) || '--'}</span></div>
        <div class="stat-card">常见跨度<span class="stat-card__value">${mode(spans) || '--'}</span></div>
        <div class="stat-card">近期形态<span class="stat-card__value">${mainType}</span></div>
        <div class="stat-card">参考期数<span class="stat-card__value">${rawHistory.length}</span></div>
        <div class="stat-card">形态组六<span class="stat-card__value">${typeCounts['组六']}</span></div>
        <div class="stat-card">形态组三<span class="stat-card__value">${typeCounts['组三']}</span></div>
    `;
}

// ==================== 杀码 ====================
function updateKillCodeDisplay() {
    const el = document.getElementById('killCodeDisplay');
    // 优先使用后端分析结果
    if (analysisCache && analysisCache.kill) {
        const kill = analysisCache.kill;
        el.innerText = kill.join('  ');
        el.title = `杀码: ${kill.join(', ')}（后端智能分析）`;
        return;
    }
    // 降级：前端本地计算
    if (rawHistory.length < 10) {
        el.innerText = '? ?';
        el.title = '需至少10期历史数据';
        return;
    }
    const { killCodes, killReasons } = computeStats(rawHistory);
    el.innerText = `${killCodes[0]}  ${killCodes[1]}`;
    el.title = `杀${killCodes[0]}: ${killReasons[0]} | 杀${killCodes[1]}: ${killReasons[1]}`;
}

// ==================== 玩法切换 ====================
async function switchGame(game) {
    currentGame = game;
    document.querySelectorAll('.game-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.game === game);
    });
    await refreshData();
}

// ==================== 筛选 ====================
function setupFilters() {
    document.getElementById('typeFilter').addEventListener('click', (e) => {
        if (!e.target.classList.contains('filter-chip')) return;
        currentFilter = e.target.dataset.filter;
        document.querySelectorAll('.filter-chip').forEach(c => c.classList.toggle('active', c.dataset.filter === currentFilter));
        renderTrendPage();
    });
}

// ==================== 触摸滑动手势 ====================
function setupSwipeGesture() {
    const container = document.getElementById('pageContainer');
    let startX = 0, startY = 0;
    const pageOrder = ['trend', 'recommend', 'stats'];

    container.addEventListener('touchstart', (e) => {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
    }, { passive: true });

    container.addEventListener('touchend', (e) => {
        const deltaX = e.changedTouches[0].clientX - startX;
        const deltaY = e.changedTouches[0].clientY - startY;

        // 必须是水平滑动：水平位移 > 垂直位移，且超过阈值
        if (Math.abs(deltaX) < 60 || Math.abs(deltaX) < Math.abs(deltaY)) return;

        const currentIdx = pageOrder.indexOf(currentPage);
        if (deltaX < -60 && currentIdx < 2) {
            switchPage(pageOrder[currentIdx + 1]);
        } else if (deltaX > 60 && currentIdx > 0) {
            switchPage(pageOrder[currentIdx - 1]);
        }
    });
}

// ==================== 键盘快捷键 ====================
function setupKeyboard() {
    document.addEventListener('keydown', (e) => {
        if (document.activeElement !== document.body) return;
        if (e.key === '1') switchGame('3d');
        if (e.key === '2') switchGame('pl3');
        if (e.key === '3') switchPage('trend');
        if (e.key === '4') switchPage('recommend');
        if (e.key === '5') switchPage('stats');
        if (e.key === 'r' && e.ctrlKey) { e.preventDefault(); refreshData(); }
    });
}

// ==================== 初始化 ====================
async function init() {
    // 玩法切换
    document.querySelectorAll('.game-btn').forEach(btn => {
        btn.addEventListener('click', () => switchGame(btn.dataset.game));
    });

    // 刷新按钮
    document.getElementById('refreshDataBtn').addEventListener('click', refreshData);

    // 底部导航
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => switchPage(tab.dataset.page));
    });

    setupFilters();
    setupSwipeGesture();
    setupKeyboard();

    // 初始加载
    await refreshData();
}

init();
