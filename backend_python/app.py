from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import sys

# 确保可以 import smart_analyze
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smart_analyze import analyze, load_params, load_feedback

app = Flask(__name__, static_folder='../frontend')
CORS(app)

# 数据文件路径
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

def read_data(game_type):
    """读取对应的JSON数据文件"""
    file_path = os.path.join(DATA_DIR, f'{game_type}.json')
    if not os.path.exists(file_path):
        default_data = {'gameType': game_type, 'data': []}
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
        return default_data

    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _serialize_result(r):
    """将 analyze() 返回的字典转为 JSON 可序列化格式"""
    trend = r.get('trend', {})
    return {
        'game': r['game'],
        'latest': {
            'issue': r['recent'][-1]['issue'],
            'number': ''.join(map(str, r['recent'][-1]['digits'])),
            'type': r['recent'][-1]['type'],
            'sum': r['recent'][-1]['sum'],
            'span': r['recent'][-1]['span']
        },
        'params': {
            'decay': r['params']['decay'],
            'lookback': r['params']['lookback'],
            'coldness_freq_weight': r['params']['coldness_freq_weight'],
            'cold_rebound_boost': r['params']['cold_rebound_boost'],
            'zusan_min_ratio': r['params'].get('zusan_min_ratio', 0.15),
            'trend_bias_weight': r['params'].get('trend_bias_weight', 0.05)
        },
        'kill': r['kill'],
        'available': r['available'],
        'heat_score': r['heat_score'],
        'cold_digits': r['cold_digits'],
        'hot_digits': r['hot_digits'],
        'gap': r['gap'],
        'gap6': r['gap6'],
        'wf6': [round(x, 2) for x in r['wf6']],
        'sum_range': list(r['sum_range']),
        'span_range': list(r['span_range']),
        'candidates': [{
            'nums': c['nums'],
            'num_str': ''.join(map(str, c['nums'])),
            'score': round(c['score'], 1),
            'sum': c['sum'],
            'span': c['span']
        } for c in sorted(r['candidates'], key=lambda x: -x['score'])[:5]],
        'zusan_ratio': round(r.get('zusan_ratio', 0), 2),
        'trend': {
            'sum_parity': trend.get('sum_parity', {}),
            'odd_even_ratio': trend.get('odd_even_ratio', {}),
            'bias': trend.get('bias', {})
        }
    }

# ========== API 接口 ==========
@app.route('/api/3d', methods=['GET'])
def get_3d_data():
    data = read_data('3d')
    return jsonify(data)

@app.route('/api/pl3', methods=['GET'])
def get_pl3_data():
    data = read_data('pl3')
    return jsonify(data)

@app.route('/api/analyze/<game>', methods=['GET'])
def get_analyze(game):
    """智能分析推荐接口"""
    if game not in ('3d', 'pl3'):
        return jsonify({'error': '无效的游戏类型'}), 400
    result = analyze(game)
    return jsonify(_serialize_result(result))

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """累计统计接口"""
    all_params = load_params()
    feedback_log = load_feedback()
    meta = all_params.get('meta', {})
    return jsonify({
        'meta': meta,
        'params': {
            '3d': all_params.get('3d', {}),
            'pl3': all_params.get('pl3', {})
        },
        'recent_feedback': feedback_log[-5:] if feedback_log else []
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': '后端服务正常运行'})

# ========== 前端页面（重要：让公网能访问） ==========
@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)

# ========== 启动服务 ==========
if __name__ == '__main__':
    print("Lottery backend starting...")
    print("Local: http://127.0.0.1:5000")
    print("Data: backend_python/data/")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)