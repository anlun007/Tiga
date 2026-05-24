const API_CONFIG = {
    BASE_URL: '/api',
    ENDPOINTS: { '3d': '/3d', 'pl3': '/pl3' }
};

async function fetchLotteryData(gameType) {
    const url = `${API_CONFIG.BASE_URL}${API_CONFIG.ENDPOINTS[gameType]}`;
    try {
        console.log('正在请求:', url);
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        console.log('获取数据成功:', data);
        return data;
    } catch (error) {
        console.warn('后端请求失败，使用演示数据:', error.message);
        return getDemoData(gameType);
    }
}

async function fetchAnalysis(gameType) {
    try {
        const url = `${API_CONFIG.BASE_URL}/analyze/${gameType}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        return data;
    } catch (error) {
        console.warn('分析API请求失败:', error.message);
        return null;
    }
}

function getDemoData(gameType) {
    const demo = {
        '3d': {
            gameType: '3d',
            _demo: true,
            data: [
                { issue: "2024030", number: "352", date: "2024-03-01" },
                { issue: "2024031", number: "661", date: "2024-03-02" },
                { issue: "2024032", number: "804", date: "2024-03-03" },
                { issue: "2024033", number: "123", date: "2024-03-04" },
                { issue: "2024034", number: "917", date: "2024-03-05" },
                { issue: "2024035", number: "448", date: "2024-03-06" },
                { issue: "2024036", number: "059", date: "2024-03-07" },
                { issue: "2024037", number: "555", date: "2024-03-08" },
                { issue: "2024038", number: "278", date: "2024-03-09" },
                { issue: "2024039", number: "136", date: "2024-03-10" }
            ]
        },
        'pl3': {
            gameType: 'pl3',
            _demo: true,
            data: [
                { issue: "2024030", number: "120", date: "2024-03-01" },
                { issue: "2024031", number: "349", date: "2024-03-02" },
                { issue: "2024032", number: "567", date: "2024-03-03" },
                { issue: "2024033", number: "008", date: "2024-03-04" },
                { issue: "2024034", number: "222", date: "2024-03-05" },
                { issue: "2024035", number: "451", date: "2024-03-06" },
                { issue: "2024036", number: "789", date: "2024-03-07" },
                { issue: "2024037", number: "303", date: "2024-03-08" }
            ]
        }
    };
    return demo[gameType];
}
