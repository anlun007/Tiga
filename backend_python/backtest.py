"""
彩票预测回测脚本
- 杀码正确率：杀码数字未出现在下一期开奖号中的比例
- 推荐正确率：5组推荐号码中至少1组完全命中的比例
"""
import json
import math
import sys

# ==================== Mulberry32 伪随机数 ====================
def mulberry32(seed):
    state = seed & 0xFFFFFFFF
    def rand():
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = (state ^ (state >> 15)) * (1 | state)
        t = (t + (t ^ (t >> 7)) * (61 | t)) ^ t
        # >>> 0 等价于 & 0xFFFFFFFF（转无符号32位）
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rand

# ==================== 号码解析 ====================
def parse_digits(num_str):
    s = num_str.strip()
    if ' ' in s:
        parts = s.split()
        if len(parts) == 3:
            return [int(p) for p in parts]
    if len(s) == 3 and s.isdigit():
        return [int(c) for c in s]
    return [0, 0, 0]

# ==================== 统计计算（JS computeStats 的 Python 移植） ====================
def compute_stats(history):
    """ history: list of {issue, digits, sum, span, type} 按时间升序排列 """
    recent = history[-20:]  # 最近20期
    L = len(recent)

    # 频率统计
    freq = [[0]*10, [0]*10, [0]*10]
    for r in recent:
        for pos in range(3):
            freq[pos][r['digits'][pos]] += 1

    # 热号（频率最高）、冷号（频率最低且>0）
    hot = []
    cold = []
    for pos in range(3):
        f = freq[pos]
        max_f = max(f)
        hot.append([i for i, v in enumerate(f) if v == max_f])
        min_f = min(v for v in f if v > 0)
        cold.append([i for i, v in enumerate(f) if v == min_f and v > 0])

    # 杀码：指数衰减加权频率 + 遗漏评分
    DECAY = 6
    weighted_freq = [0]*10
    for idx, r in enumerate(reversed(recent)):
        w = math.exp(-idx / DECAY)
        for pos in range(3):
            weighted_freq[r['digits'][pos]] += w

    last_seen = [L]*10
    for d in range(10):
        for i, r in enumerate(reversed(recent)):
            if d in r['digits']:
                last_seen[d] = i
                break

    coldness = [0]*10
    for d in range(10):
        coldness[d] = weighted_freq[d] * 10 - last_seen[d]

    sorted_cold = sorted([(d, coldness[d]) for d in range(10)], key=lambda x: x[1])
    kill_codes = [sorted_cold[0][0], sorted_cold[1][0]]

    # 和值/跨度范围（25%-75%）
    sums = sorted([r['sum'] for r in recent])
    spans = sorted([r['span'] for r in recent])
    p25 = L // 4
    p75 = L * 3 // 4
    sum_range = [max(0, sums[p25] - 3), min(27, sums[p75] + 3)]
    span_range = [max(0, spans[p25] - 1), min(9, spans[p75] + 1)]

    # 形态占比
    type_counts = {'组六': 0, '组三': 0, '豹子': 0}
    for r in recent:
        type_counts[r['type']] += 1
    type_ratio = {k: v/L for k, v in type_counts.items()}

    return {
        'freq': freq, 'hot': hot, 'cold': cold,
        'kill_codes': kill_codes,
        'sum_range': sum_range, 'span_range': span_range,
        'type_ratio': type_ratio,
    }

# ==================== 分类 ====================
def classify(digits):
    a, b, c = digits
    s = a + b + c
    sp = max(a, b, c) - min(a, b, c)
    if a == b == c:
        t = '豹子'
    elif a == b or b == c or a == c:
        t = '组三'
    else:
        t = '组六'
    return s, sp, t

# ==================== 推荐生成 ====================
def generate_recommendations(stats, last_digits, seed):
    freq = stats['freq']
    kill_codes = stats['kill_codes']
    sum_range = stats['sum_range']
    span_range = stats['span_range']
    type_ratio = stats['type_ratio']
    kill1, kill2 = kill_codes
    min_sum, max_sum = sum_range
    min_span, max_span = span_range
    need_sanzu = type_ratio['组三'] >= 0.15

    rng = mulberry32(seed)
    recommendations = []
    attempts = 0
    MAX_ATTEMPTS = 200

    while len(recommendations) < 5 and attempts < MAX_ATTEMPTS:
        attempts += 1
        digits = []
        for pos in range(3):
            weights = [0]*10
            for d in range(10):
                if d == kill1 or d == kill2:
                    weights[d] = 0
                else:
                    weights[d] = freq[pos][d] + 0.3
            total = sum(weights)
            r = rng() * total
            digit = 0
            for d in range(10):
                r -= weights[d]
                if r <= 0:
                    digit = d
                    break
            digits.append(digit)

        s = digits[0] + digits[1] + digits[2]
        if s < min_sum or s > max_sum:
            continue

        sp = max(digits) - min(digits)
        if sp < min_span or sp > max_span:
            continue

        if last_digits:
            same = sum(1 for i in range(3) if digits[i] == last_digits[i])
            if same >= 2:
                continue

        key = ''.join(map(str, digits))
        if any(''.join(map(str, r['numbers'])) == key for r in recommendations):
            continue

        is_zusan = digits[0] == digits[1] or digits[1] == digits[2] or digits[0] == digits[2]
        if need_sanzu and len(recommendations) == 4:
            has_zusan = any(r['_is_zusan'] for r in recommendations)
            if not has_zusan and not is_zusan:
                continue

        recommendations.append({'numbers': digits, '_is_zusan': is_zusan})

    return [r['numbers'] for r in recommendations]

# ==================== 日期转 seed ====================
def date_to_seed(date_str):
    """ '2025-01-01' -> 20250101 """
    return int(date_str.replace('-', ''))

# ==================== 回测主逻辑 ====================
def backtest(data, min_history=30):
    """
    data: list of {issue, number, date}, sorted ascending by issue
    回测：从第 min_history 期开始，用历史预测下一期
    """
    # 预处理所有数据
    all_records = []
    for item in data:
        digits = parse_digits(item['number'])
        s, sp, t = classify(digits)
        all_records.append({
            'issue': item['issue'],
            'date': item.get('date', ''),
            'digits': digits,
            'sum': s,
            'span': sp,
            'type': t,
        })

    kill_total = 0
    kill_correct = 0
    rec_total = 0
    rec_hit = 0
    rec_partial_hit = 0
    rec_any_pos_hit = 0

    # 按形态分类统计
    type_stats = {}
    for t in ['组六', '组三', '豹子']:
        type_stats[t] = {
            'total': 0,
            'kill_total': 0, 'kill_correct': 0,
            'rec_total': 0, 'rec_hit': 0, 'rec_partial_hit': 0, 'rec_any_pos_hit': 0,
        }

    results = []

    for i in range(min_history, len(all_records)):
        history = all_records[:i]
        actual = all_records[i]
        actual_type = actual['type']

        stats = compute_stats(history)

        # ---- 杀码评估 ----
        kill_codes = stats['kill_codes']
        actual_digits_set = set(actual['digits'])
        kill_ok = all(k not in actual_digits_set for k in kill_codes)

        kill_total += 1
        type_stats[actual_type]['total'] += 1
        type_stats[actual_type]['kill_total'] += 1
        if kill_ok:
            kill_correct += 1
            type_stats[actual_type]['kill_correct'] += 1

        # ---- 推荐评估 ----
        last_digits = history[-1]['digits'] if history else None
        seed = date_to_seed(actual['date']) if actual['date'] else int(actual['issue'])
        recs = generate_recommendations(stats, last_digits, seed)

        if recs:
            rec_total += 1
            type_stats[actual_type]['rec_total'] += 1
            actual_tuple = tuple(actual['digits'])
            best_match = 0
            any_pos_match = False
            for rec in recs:
                matched_pos = sum(1 for j in range(3) if rec[j] == actual_tuple[j])
                best_match = max(best_match, matched_pos)
                if set(rec) & actual_digits_set:
                    any_pos_match = True

            if best_match == 3:
                rec_hit += 1
                type_stats[actual_type]['rec_hit'] += 1
            if best_match >= 2:
                rec_partial_hit += 1
                type_stats[actual_type]['rec_partial_hit'] += 1
            if any_pos_match:
                rec_any_pos_hit += 1
                type_stats[actual_type]['rec_any_pos_hit'] += 1

        results.append({
            'issue': actual['issue'],
            'actual': actual['digits'],
            'kill_codes': kill_codes,
            'kill_ok': kill_ok,
        })

    # 输出最后10条详细结果
    print("\nLast 10 results:")
    print(f"{'Issue':<12} {'Actual':<10} {'Kill':<10} {'Result':<10}")
    print("-" * 45)
    for r in results[-10:]:
        status = "OK" if r['kill_ok'] else "FAIL"
        print(f"{r['issue']:<12} {''.join(map(str, r['actual'])):<10} {' '.join(map(str, r['kill_codes'])):<10} {status:<10}")

    return {
        'kill_total': kill_total,
        'kill_correct': kill_correct,
        'rec_total': rec_total,
        'rec_hit': rec_hit,
        'rec_partial_hit': rec_partial_hit,
        'rec_any_pos_hit': rec_any_pos_hit,
        'type_stats': type_stats,
    }

# ==================== 主程序 ====================
def main():
    games = ['3d', 'pl3']
    for game in games:
        path = f'backend_python/data/{game}.json'
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        data = raw['data']
        # 按期号排序（升序）
        data.sort(key=lambda x: x['issue'])

        print(f"\n{'='*60}")
        print(f"  {game.upper()} Backtest Report ({len(data)} records, 30 warmup)")
        print(f"{'='*60}")

        result = backtest(data, min_history=30)

        kill_rate = result['kill_correct'] / result['kill_total'] * 100 if result['kill_total'] else 0
        exact_rate = result['rec_hit'] / result['rec_total'] * 100 if result['rec_total'] else 0
        partial_rate = result['rec_partial_hit'] / result['rec_total'] * 100 if result['rec_total'] else 0
        any_rate = result['rec_any_pos_hit'] / result['rec_total'] * 100 if result['rec_total'] else 0

        print(f"\n  === Overall ===")
        print(f"  Kill Code Accuracy: {kill_rate:.1f}% ({result['kill_correct']}/{result['kill_total']})")
        print(f"  Rec Exact(3pos):    {exact_rate:.1f}% ({result['rec_hit']}/{result['rec_total']})")
        print(f"  Rec Match 2pos:    {partial_rate:.1f}% ({result['rec_partial_hit']}/{result['rec_total']})")
        print(f"  Rec Any match:     {any_rate:.1f}% ({result['rec_any_pos_hit']}/{result['rec_total']})")

        print(f"\n  === By Type ===")
        for t in ['组六', '组三', '豹子']:
            ts = result['type_stats'][t]
            if ts['total'] == 0:
                continue
            k_rate = ts['kill_correct'] / ts['kill_total'] * 100 if ts['kill_total'] else 0
            e_rate = ts['rec_hit'] / ts['rec_total'] * 100 if ts['rec_total'] else 0
            p_rate = ts['rec_partial_hit'] / ts['rec_total'] * 100 if ts['rec_total'] else 0
            a_rate = ts['rec_any_pos_hit'] / ts['rec_total'] * 100 if ts['rec_total'] else 0
            print(f"  [{t}] count={ts['total']:>3}  Kill:{k_rate:5.1f}%  Exact:{e_rate:5.1f}%  2pos:{p_rate:5.1f}%  Any:{a_rate:5.1f}%")

if __name__ == '__main__':
    main()
