"""
今日彩票综合分析脚本
整合杀码算法 + 多策略推荐 + 投注建议
"""
import json
import math

# ==================== Mulberry32 伪随机数 ====================
def mulberry32(seed):
    state = seed & 0xFFFFFFFF
    def rand():
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = (state ^ (state >> 15)) * (1 | state)
        t = (t + (t ^ (t >> 7)) * (61 | t)) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rand

def parse_digits(num_str):
    s = num_str.strip()
    if ' ' in s:
        parts = s.split()
        if len(parts) == 3:
            return [int(p) for p in parts]
    if len(s) == 3 and s.isdigit():
        return [int(c) for c in s]
    return [0, 0, 0]

def classify(digits):
    a, b, c = digits
    s = a + b + c
    sp = max(a,b,c) - min(a,b,c)
    if a == b == c: t = '豹子'
    elif a == b or b == c or a == c: t = '组三'
    else: t = '组六'
    return s, sp, t

def compute_stats(history):
    recent = history[-20:]
    L = len(recent)
    freq = [[0]*10, [0]*10, [0]*10]
    for r in recent:
        for pos in range(3):
            freq[pos][r['digits'][pos]] += 1
    hot = []
    cold = []
    for pos in range(3):
        f = freq[pos]
        max_f = max(f)
        hot.append([i for i,v in enumerate(f) if v == max_f])
        min_f = min(v for v in f if v > 0)
        cold.append([i for i,v in enumerate(f) if v == min_f and v > 0])
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
    coldness = [weighted_freq[d] * 10 - last_seen[d] for d in range(10)]
    sorted_cold = sorted([(d, coldness[d]) for d in range(10)], key=lambda x: x[1])
    kill_codes = [sorted_cold[0][0], sorted_cold[1][0]]
    sums = sorted([r['sum'] for r in recent])
    spans = sorted([r['span'] for r in recent])
    p25, p75 = L//4, L*3//4
    sum_range = [max(0, sums[p25]-3), min(27, sums[p75]+3)]
    span_range = [max(0, spans[p25]-1), min(9, spans[p75]+1)]
    type_counts = {'组六':0,'组三':0,'豹子':0}
    for r in recent:
        type_counts[r['type']] += 1
    type_ratio = {k: v/L for k,v in type_counts.items()}
    return {
        'freq': freq, 'hot': hot, 'cold': cold,
        'kill_codes': kill_codes,
        'sum_range': sum_range, 'span_range': span_range,
        'type_ratio': type_ratio, 'weighted_freq': weighted_freq,
        'last_seen': last_seen, 'coldness': coldness, 'sorted_cold': sorted_cold,
    }

def generate_recommendations(stats, last_digits, seed, count=5):
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
    while len(recommendations) < count and attempts < 200:
        attempts += 1
        digits = []
        for pos in range(3):
            weights = [0]*10
            for d in range(10):
                if d == kill1 or d == kill2: weights[d] = 0
                else: weights[d] = freq[pos][d] + 0.3
            total = sum(weights)
            r = rng() * total
            digit = 0
            for d in range(10):
                r -= weights[d]
                if r <= 0: digit = d; break
            digits.append(digit)
        s = sum(digits)
        if s < min_sum or s > max_sum: continue
        sp = max(digits) - min(digits)
        if sp < min_span or sp > max_span: continue
        if last_digits:
            same = sum(1 for i in range(3) if digits[i] == last_digits[i])
            if same >= 2: continue
        key = ''.join(map(str, digits))
        if any(''.join(map(str, r)) == key for r in recommendations): continue
        is_zusan = digits[0]==digits[1] or digits[1]==digits[2] or digits[0]==digits[2]
        if need_sanzu and len(recommendations) == count-1:
            has_zusan = any(r[0]==r[1] or r[1]==r[2] or r[0]==r[2] for r in recommendations)
            if not has_zusan and not is_zusan: continue
        recommendations.append(digits)
    return recommendations

def analyze_game(game_name, filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    data = raw['data']
    data.sort(key=lambda x: x['issue'])

    all_records = []
    for item in data:
        digits = parse_digits(item['number'])
        s, sp, t = classify(digits)
        all_records.append({'issue': item['issue'], 'date': item.get('date',''), 'digits': digits, 'sum': s, 'span': sp, 'type': t})

    history = all_records
    last = history[-1]
    stats = compute_stats(history)

    print(f'\n{"="*70}')
    print(f'  【{game_name}】综合分析报告 - 2026年5月18日')
    print(f'{"="*70}')

    print(f'\n  [数据概览]')
    print(f'     总期数: {len(data)}')
    print(f'     最新一期: 期号 {last["issue"]}  号码 {"".join(map(str, last["digits"]))}  ({last["type"]})  和值{last["sum"]}  跨度{last["span"]}')

    print(f'\n  [杀码分析 - 今日排除数字]')
    kill = stats['kill_codes']
    print(f'     杀码: [{kill[0]}] 和 [{kill[1]}]')
    print(f'     数字冷度排名 (冷->热):')
    for d, score in stats['sorted_cold']:
        marker = ' <<< 杀码' if d in kill else ''
        print(f'       {d}: 冷度={score:7.2f}  加权频次={stats["weighted_freq"][d]:.3f}  遗漏={stats["last_seen"][d]}期{marker}')

    print(f'\n  [每位热号/冷号]')
    for pos, name in enumerate(['百位', '十位', '个位']):
        print(f'     {name}: 热号={stats["hot"][pos]}  冷号={stats["cold"][pos]}')

    print(f'\n  [和值与跨度范围]')
    print(f'     和值: {stats["sum_range"][0]} ~ {stats["sum_range"][1]}')
    print(f'     跨度: {stats["span_range"][0]} ~ {stats["span_range"][1]}')

    print(f'\n  [近20期形态分布]')
    for t in ['组六', '组三', '豹子']:
        pct = stats['type_ratio'][t] * 100
        bar = '#' * int(pct / 5)
        print(f'     {t}: {pct:5.0f}% {bar}')

    # 今日推荐
    last_digits = last['digits']
    seed = 20260518
    recs = generate_recommendations(stats, last_digits, seed, 5)

    print(f'\n  [今日推荐直选号码] (种子=20260518)')
    for i, rec in enumerate(recs):
        s, sp, t = classify(rec)
        num_str = ''.join(map(str, rec))
        print(f'     #{i+1}: {num_str}  和值={s}  跨度={sp}  形态={t}')

    # 多策略推荐池
    all_recs = set()
    for offset in [0, 1, 7, 13, 42]:
        seed2 = 20260518 + offset
        recs2 = generate_recommendations(stats, last_digits, seed2, 5)
        for r in recs2:
            all_recs.add(''.join(map(str, r)))
    print(f'\n  [多策略推荐池] ({len(all_recs)}组): {sorted(all_recs)}')

    return stats, recs, kill

# ==================== 主分析 ====================
stats_3d, recs_3d, kill_3d = analyze_game('福彩3D', 'backend_python/data/3d.json')
stats_pl3, recs_pl3, kill_pl3 = analyze_game('排列三', 'backend_python/data/pl3.json')

# ==================== 综合投注建议 ====================
print(f'\n{"="*70}')
print(f'  [投注策略建议] 2026年5月18日')
print(f'{"="*70}')

print(f'\n  ┌─────────────────────────────────────────────────────┐')
print(f'  │  福彩3D                                            │')
print(f'  ├─────────────────────────────────────────────────────┤')
print(f'  │  杀码(排除): {kill_3d[0]} 和 {kill_3d[1]}                                    │')
print(f'  │  可用数字: 0-9中去掉 {kill_3d[0]}{kill_3d[1]}                         │')
print(f'  │                                                     │')
print(f'  │  直选推荐:                                         │')
for i, rec in enumerate(recs_3d):
    num_str = ''.join(map(str, rec))
    s, sp, t = classify(rec)
    print(f'  │    {i+1}. {num_str} ({t}, 和值{s}, 跨度{sp})                      │')
print(f'  │                                                     │')
# 组选覆盖
seen = set()
group_nums = []
for rec in recs_3d:
    srt = ''.join(sorted(map(str, rec)))
    if srt not in seen:
        seen.add(srt)
        _, _, t = classify(rec)
        group_nums.append(f'{srt}({t})')
print(f'  │  组选覆盖: {", ".join(group_nums)}        │')
print(f'  └─────────────────────────────────────────────────────┘')

print(f'\n  ┌─────────────────────────────────────────────────────┐')
print(f'  │  排列三                                            │')
print(f'  ├─────────────────────────────────────────────────────┤')
print(f'  │  杀码(排除): {kill_pl3[0]} 和 {kill_pl3[1]}                                    │')
print(f'  │  可用数字: 0-9中去掉 {kill_pl3[0]}{kill_pl3[1]}                         │')
print(f'  │                                                     │')
print(f'  │  直选推荐:                                         │')
for i, rec in enumerate(recs_pl3):
    num_str = ''.join(map(str, rec))
    s, sp, t = classify(rec)
    print(f'  │    {i+1}. {num_str} ({t}, 和值{s}, 跨度{sp})                      │')
print(f'  │                                                     │')
seen = set()
group_nums = []
for rec in recs_pl3:
    srt = ''.join(sorted(map(str, rec)))
    if srt not in seen:
        seen.add(srt)
        _, _, t = classify(rec)
        group_nums.append(f'{srt}({t})')
print(f'  │  组选覆盖: {", ".join(group_nums)}        │')
print(f'  └─────────────────────────────────────────────────────┘')

# 1D/2D 建议
print(f'\n  [1D/2D 投注建议]')
print(f'     3D  热号定位: 百位{stats_3d["hot"][0]} | 十位{stats_3d["hot"][1]} | 个位{stats_3d["hot"][2]}')
print(f'     PL3 热号定位: 百位{stats_pl3["hot"][0]} | 十位{stats_pl3["hot"][1]} | 个位{stats_pl3["hot"][2]}')
print(f'     1D 推荐: 选任意一位的热号中最稳定的数字')
print(f'     2D 推荐: 百位+十位热号组合，或十位+个位热号组合')
print(f'     注意: 避开杀码数字 {set(kill_3d + kill_pl3)}')

# 形态预判
print(f'\n  [形态预判]')
for name, stats in [('3D', stats_3d), ('PL3', stats_pl3)]:
    ratio = stats['type_ratio']
    dominant = max(ratio, key=ratio.get)
    print(f'     {name}: 近期以{dominant}为主({ratio[dominant]*100:.0f}%)', end='')
    if ratio['组三'] >= 0.15:
        print(f'，组三占比偏高(>{15}%)，关注组三回补')
    else:
        print(f'，组三占比偏低，以组六为主')

print(f'\n  [风险提示]')
print(f'     回测杀码正确率: 3D约49.3%, PL3约46.3%')
print(f'     回测推荐Any命中率: 3D约97.0%, PL3约94.5%')
print(f'     回测推荐精确命中率: 3D约2.5%, PL3约0.5%')
print(f'     以上推荐仅供参考，理性购彩!')
