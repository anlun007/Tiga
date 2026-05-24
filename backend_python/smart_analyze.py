"""
智能彩票分析引擎 — 参数可调 + 反馈修正
用法:
  python smart_analyze.py analyze          # 分析今日推荐
  python smart_analyze.py feedback 023     # 录入开奖结果并自动修正参数
  python smart_analyze.py stats            # 查看累计准确率
"""
import json, math, itertools, sys, os
from collections import Counter
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
PARAMS_FILE = os.path.join(BASE, 'params.json')
FEEDBACK_FILE = os.path.join(BASE, 'feedback_log.json')

# ======================== 参数管理 ========================
def load_params():
    with open(PARAMS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_params(p):
    with open(PARAMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(p, f, ensure_ascii=False, indent=2)

def load_feedback():
    if not os.path.exists(FEEDBACK_FILE):
        return []
    with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_feedback(log):
    with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

# ======================== 数据解析 ========================
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
    sp = max(a, b, c) - min(a, b, c)
    if a == b == c: t = '豹子'
    elif a == b or b == c or a == c: t = '组三'
    else: t = '组六'
    return s, sp, t

def load_game_data(game):
    path = os.path.join(BASE, 'data', f'{game}.json')
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    data = raw['data']
    data.sort(key=lambda x: x['issue'])
    records = []
    for item in data:
        d = parse_digits(item['number'])
        s, sp, t = classify(d)
        records.append({
            'issue': item['issue'],
            'date': item.get('date', ''),
            'digits': d, 'sum': s, 'span': sp, 'type': t
        })
    return records

# ======================== 核心分析 ========================
def analyze(game, params=None, exclude_last=0):
    if params is None:
        params = load_params()[game]

    # 新参数默认值（向后兼容旧 params.json）
    params.setdefault('zusan_min_ratio', 0.15)
    params.setdefault('zusan_max_count', 3)
    params.setdefault('trend_bias_weight', 0.05)

    records = load_game_data(game)
    if exclude_last > 0:
        records = records[:-exclude_last]
    recent = records[-params['lookback']:]
    L = len(recent)

    # ========== 类型统计 + 趋势分析 ==========
    type_cnt = Counter(r['type'] for r in recent)
    zusan_ratio = type_cnt.get('组三', 0) / L if L > 0 else 0

    # 和值奇偶 + 单双比
    sum_parity = {'奇': 0, '偶': 0}
    oe_ratio = {'全奇(3:0)': 0, '两奇一偶(2:1)': 0, '一奇两偶(1:2)': 0, '全偶(0:3)': 0}
    for r in recent:
        odd_cnt = sum(1 for d in r['digits'] if d % 2 == 1)
        sum_parity['偶' if r['sum'] % 2 == 0 else '奇'] += 1
        oe_key = {3: '全奇(3:0)', 2: '两奇一偶(2:1)', 1: '一奇两偶(1:2)', 0: '全偶(0:3)'}[odd_cnt]
        oe_ratio[oe_key] += 1

    # 趋势偏向（均值回归假设）
    tb = params['trend_bias_weight']
    trend_bias = {'sum_parity': None, 'odd_even': None}
    if L > 0:
        if sum_parity['奇'] / L >= 0.65:
            trend_bias['sum_parity'] = '偶'
        elif sum_parity['偶'] / L >= 0.65:
            trend_bias['sum_parity'] = '奇'
        if oe_ratio.get('全奇(3:0)', 0) / L >= 0.35:
            trend_bias['odd_even'] = 'less_odd'
        elif oe_ratio.get('全偶(0:3)', 0) / L >= 0.35:
            trend_bias['odd_even'] = 'less_even'

    # 加权频率
    decay = params['decay']
    wf = [0.0] * 10
    for idx, r in enumerate(reversed(recent)):
        w = math.exp(-idx / decay)
        for pos in range(3):
            wf[r['digits'][pos]] += w

    # 遗漏
    gap = [L] * 10
    for d in range(10):
        for i, r in enumerate(reversed(recent)):
            if d in r['digits']:
                gap[d] = i
                break

    # 冷度 = 加权频率 * 系数 - 遗漏
    cw = params['coldness_freq_weight']
    coldness = [wf[d] * cw - gap[d] for d in range(10)]
    sorted_cold = sorted([(d, coldness[d]) for d in range(10)], key=lambda x: x[1])
    kill = [sorted_cold[i][0] for i in range(int(params['kill_count']))]

    # 每位频率
    pos_freq = [Counter() for _ in range(3)]
    for r in recent:
        for pos in range(3):
            pos_freq[pos][r['digits'][pos]] += 1

    # 组六专项
    g6_recent = [r for r in records[-70:] if r['type'] == '组六'][-50:]
    wf6 = [0.0] * 10
    for idx, r in enumerate(reversed(g6_recent)):
        w = math.exp(-idx / 8)
        for d in r['digits']:
            wf6[d] += w
    pos_freq6 = [Counter() for _ in range(3)]
    for r in g6_recent:
        for pos in range(3):
            pos_freq6[pos][r['digits'][pos]] += 1

    # 组六遗漏
    gap6 = [len(g6_recent)] * 10
    for d in range(10):
        for i, r in enumerate(reversed(g6_recent)):
            if d in r['digits']:
                gap6[d] = i
                break

    # 综合热度分: 加权频率(60%) + 近期程度(40%)
    # 两者归一化到0-1后加权
    max_wf6 = max(wf6) if max(wf6) > 0 else 1
    max_gap6 = max(gap6) if max(gap6) > 0 else 1
    heat_score = [0.0] * 10
    for d in range(10):
        freq_norm = wf6[d] / max_wf6
        recency_norm = 1.0 - gap6[d] / max_gap6
        heat_score[d] = freq_norm * 0.6 + recency_norm * 0.4

    # 冷号判定: 热度分 < 0.3 且 遗漏 >= 中位数
    median_gap6 = sorted(gap6)[5]  # 10个数的中位数约在第5位
    cold_digits = [d for d in range(10) if heat_score[d] < 0.3 and gap6[d] >= median_gap6]
    hot_digits = [d for d in range(10) if heat_score[d] > 0.6]

    # 冷号回补加成
    rb = params['cold_rebound_boost']
    for d in range(10):
        if gap[d] >= 4:
            wf6[d] += rb * (gap[d] / 10.0)

    # 和值/跨度 IQR
    g6_sums = sorted([r['sum'] for r in g6_recent])
    g6_spans = sorted([r['span'] for r in g6_recent])
    n = len(g6_sums)
    p25, p75 = n // 4, n * 3 // 4
    ms = params['iqr_margin_sum']
    msp = params['iqr_margin_span']
    sum_range = (max(0, g6_sums[p25] - ms), min(27, g6_sums[p75] + ms))
    span_range = (max(0, g6_spans[p25] - msp), min(9, g6_spans[p75] + msp))

    # 可用数字
    available = [d for d in range(10) if d not in kill]

    # 生成候选
    pw = params['pos_weight']
    cands = []
    for i in range(len(available)):
        for j in range(i + 1, len(available)):
            for k in range(j + 1, len(available)):
                nums = [available[i], available[j], available[k]]
                s = sum(nums)
                sp = max(nums) - min(nums)
                if sum_range[0] <= s <= sum_range[1] and span_range[0] <= sp <= span_range[1]:
                    score = wf6[nums[0]] + wf6[nums[1]] + wf6[nums[2]]
                    pos_score = (pos_freq6[0].get(nums[0], 0) +
                                 pos_freq6[1].get(nums[1], 0) +
                                 pos_freq6[2].get(nums[2], 0))
                    final_score = score + pos_score * pw * 0.3

                    # 趋势偏向加成
                    if trend_bias['sum_parity'] == '偶' and s % 2 == 0:
                        final_score *= (1 + tb)
                    elif trend_bias['sum_parity'] == '奇' and s % 2 == 1:
                        final_score *= (1 + tb)
                    odd_cnt_c = sum(1 for d in nums if d % 2 == 1)
                    if trend_bias['odd_even'] == 'less_odd' and odd_cnt_c <= 1:
                        final_score *= (1 + tb)
                    elif trend_bias['odd_even'] == 'less_even' and odd_cnt_c >= 2:
                        final_score *= (1 + tb)

                    cands.append({
                        'nums': sorted(nums), 'score': final_score,
                        'sum': s, 'span': sp
                    })
    cands.sort(key=lambda x: -x['score'])

    # 多样性选择 — 总共最多5个（组三激活时 3组六+2组三）
    zusan_active = zusan_ratio >= params['zusan_min_ratio'] and len(available) >= 2
    g6_limit = 3 if zusan_active else 5
    max_ol = params['diversity_overlap_max']
    selected = []
    for c in cands:
        if selected:
            if max(len(set(c['nums']) & set(s['nums'])) for s in selected) > max_ol:
                continue
        selected.append(c)
        if len(selected) >= g6_limit:
            break

    # ========== 组三候选生成 ==========
    zusan_cands = []
    if zusan_active:
        for a in available:      # 对子数字
            for b in available:  # 单号数字
                if a == b:
                    continue
                nums = sorted([a, a, b])
                zs = a * 2 + b
                zsp = max(nums) - min(nums)
                if not (sum_range[0] <= zs <= sum_range[1] and span_range[0] <= zsp <= span_range[1]):
                    continue
                base_score = wf6[a] * 2 + wf6[b]
                pos_score = (pos_freq6[0].get(a, 0) +
                             pos_freq6[1].get(a, 0) +
                             pos_freq6[2].get(b, 0))
                final_score = base_score + pos_score * pw * 0.3
                # 趋势偏向
                if trend_bias['sum_parity'] == '偶' and zs % 2 == 0:
                    final_score *= (1 + tb)
                elif trend_bias['sum_parity'] == '奇' and zs % 2 == 1:
                    final_score *= (1 + tb)
                odd_cnt_z = sum(1 for d in nums if d % 2 == 1)
                if trend_bias['odd_even'] == 'less_odd' and odd_cnt_z <= 1:
                    final_score *= (1 + tb)
                elif trend_bias['odd_even'] == 'less_even' and odd_cnt_z >= 2:
                    final_score *= (1 + tb)
                zusan_cands.append({
                    'nums': nums,
                    'pair_digit': a,
                    'single_digit': b,
                    'score': final_score,
                    'sum': zs,
                    'span': zsp
                })

        zusan_cands.sort(key=lambda x: -x['score'])
        zusan_selected = []
        for c in zusan_cands:
            if zusan_selected:
                if max(len(set(c['nums']) & set(s['nums'])) for s in zusan_selected) > max_ol:
                    continue
            zusan_selected.append(c)
            if len(zusan_selected) >= min(params['zusan_max_count'], 5 - len(selected)):
                break
        zusan_cands = zusan_selected

    return {
        'game': game,
        'params': params,
        'records': records,
        'recent': recent,
        'kill': kill,
        'weighted_freq': wf,
        'wf6': wf6,
        'gap': gap,
        'gap6': gap6,
        'heat_score': heat_score,
        'cold_digits': cold_digits,
        'hot_digits': hot_digits,
        'sorted_cold': sorted_cold,
        'sum_range': sum_range,
        'span_range': span_range,
        'pos_freq6': pos_freq6,
        'candidates': selected + zusan_cands,
        'available': available,
        'zusan_ratio': zusan_ratio,
        'trend': {
            'sum_parity': sum_parity,
            'odd_even_ratio': oe_ratio,
            'bias': trend_bias
        }
    }

# ======================== 输出推荐 ========================
def print_recommendations(result):
    print(f"\n{'='*55}")
    print(f"  [{result['game'].upper()}] 智能分析推荐 - {date.today()}")
    print(f"{'='*55}")

    last = result['recent'][-1]
    print(f"  最新期号: {last['issue']}  号码: {''.join(map(str, last['digits']))}  ({last['type']})  和值{last['sum']}  跨度{last['span']}")

    p = result['params']
    print(f"\n  [当前参数] decay={p['decay']} lookback={p['lookback']} "
          f"coldness_w={p['coldness_freq_weight']} "
          f"rebound={p['cold_rebound_boost']}")

    print(f"\n  [杀码] {result['kill']}")
    print(f"  [可用] {result['available']}")

    print(f"\n  [数字热度]  综合分=(频率60% + 近期40%)  杀码={result['kill']}")
    print(f"    热号: {result['hot_digits']}  冷号: {result['cold_digits']}")
    for d in sorted(range(10), key=lambda x: result['heat_score'][x], reverse=True):
        hs = result['heat_score'][d]
        bar = '█' * max(1, int(hs * 15))
        tier = '热' if hs > 0.6 else ('温' if hs >= 0.3 else '冷')
        kill_tag = ' <<< 杀码' if d in result['kill'] else ''
        print(f"    {d}: 综合{hs:.2f} {bar}  频率{result['wf6'][d]:3.1f}  遗漏{result['gap'][d]:2d}期(全)/{result['gap6'][d]:2d}期(组六)  [{tier}]{kill_tag}")

    print(f"\n  [和值 {result['sum_range'][0]}~{result['sum_range'][1]}]  "
          f"[跨度 {result['span_range'][0]}~{result['span_range'][1]}]")

    # ========== 趋势分析 ==========
    trend = result.get('trend', {})
    if trend:
        sp = trend['sum_parity']
        oe = trend['odd_even_ratio']
        n = sum(sp.values())
        if n > 0:
            print(f"\n  [趋势分析 ({n}期)]")
            sp_parts = []
            for k in ('奇', '偶'):
                v = sp.get(k, 0)
                bar = '█' * max(1, int(v / n * 20))
                sp_parts.append(f"{k}: {v}期 {bar} ({v/n*100:.0f}%)")
            print(f"    和值奇偶:  {'  '.join(sp_parts)}")
            oe_parts = []
            for k in ('全奇(3:0)', '两奇一偶(2:1)', '一奇两偶(1:2)', '全偶(0:3)'):
                v = oe.get(k, 0)
                if v == 0:
                    continue
                bar = '█' * max(1, int(v / n * 20))
                oe_parts.append(f"{k}: {v}期 {bar} ({v/n*100:.0f}%)")
            print(f"    单双比:    {'  '.join(oe_parts)}")

    # 合并组六+组三，按得分排序取前5
    combined = sorted(result['candidates'], key=lambda x: -x['score'])[:5]

    print(f"\n  [精选推荐]")
    for i, c in enumerate(combined):
        nums_str = ''.join(map(str, c['nums']))
        direct = [''.join(map(str, p)) for p in list(itertools.permutations(c['nums']))[:2]]
        direct = list(dict.fromkeys(direct))[:2]
        print(f"    #{i+1}: 组选 {nums_str}  例 {'/'.join(direct)}  和值{c['sum']}  跨度{c['span']}  得分{c['score']:.1f}")

    covered = set()
    for c in combined:
        covered.update(c['nums'])
    print(f"\n  覆盖: {sorted(covered)} ({len(covered)}/8个可用数字)")


# ======================== 反馈修正 ========================
def apply_feedback(game, actual_str):
    """录入开奖结果并自动修正参数"""
    actual = parse_digits(actual_str)
    s, sp, t = classify(actual)

    # 检测本期结果是否已在数据中（standalone feedback 场景）
    # 如果已在，排除最后一条后用「预测时」的数据分析
    records = load_game_data(game)
    exclude_last = 0
    if records and records[-1]['digits'] == actual:
        exclude_last = 1

    # 用预测时的数据跑分析（排除本期结果）
    result = analyze(game, exclude_last=exclude_last)
    kill = result['kill']
    cands = result['candidates']

    # 计算命中情况（含组三候选）
    kill_ok = all(k not in actual for k in kill)
    best_match = 0
    best_cand = None
    any_hit = False
    for c in cands:
        matched = sum(1 for d in actual if d in c['nums'])
        if matched >= 1:
            any_hit = True
        if matched > best_match:
            best_match = matched
            best_cand = c['nums']

    # 记录反馈
    feedback_log = load_feedback()
    entry = {
        'date': str(date.today()),
        'game': game,
        'issue': result['recent'][-1]['issue'],
        'actual': actual,
        'actual_type': t,
        'actual_sum': s,
        'actual_span': sp,
        'predicted_kill': kill,
        'predicted_top3': [''.join(map(str, c['nums'])) for c in cands[:3]],
        'kill_correct': kill_ok,
        'any_hit': any_hit,
        'best_match': best_match,
        'best_cand': ''.join(map(str, best_cand)) if best_cand else '',
        'notes': ''
    }

    # 自动修正参数
    all_params = load_params()
    p = all_params[game]
    lr = 0.15  # 学习率

    # 修正1: 杀码失败 → 调整冷度公式
    if not kill_ok:
        p['coldness_freq_weight'] = round(p['coldness_freq_weight'] * (1 - lr), 1)
        p['kill_count'] = max(1, round(p['kill_count'] - 0.5, 1))
        entry['notes'] += f'[杀码失败] 降低coldness_w至{p["coldness_freq_weight"]}; '
    else:
        p['coldness_freq_weight'] = round(p['coldness_freq_weight'] * (1 + lr * 0.3), 1)
        entry['notes'] += f'[杀码正确] 微调coldness_w至{p["coldness_freq_weight"]}; '

    # 修正2: 实际号码含冷号(综合热度<0.3) → 增加回补权重
    cold_in_actual = [d for d in actual if result['heat_score'][d] < 0.3]
    if cold_in_actual:
        p['cold_rebound_boost'] = round(p['cold_rebound_boost'] + lr * 0.5, 2)
        entry['notes'] += f'冷号{cold_in_actual}出现，回补+{lr*0.5:.2f}至{p["cold_rebound_boost"]}; '

    # 修正3: 和值/跨度超范围
    if s < result['sum_range'][0] or s > result['sum_range'][1]:
        p['iqr_margin_sum'] = min(5, p['iqr_margin_sum'] + 1)
        entry['notes'] += f'和值{s}超范围，扩大margin至{p["iqr_margin_sum"]}; '
    if sp < result['span_range'][0] or sp > result['span_range'][1]:
        p['iqr_margin_span'] = min(5, p['iqr_margin_span'] + 1)
        entry['notes'] += f'跨度{sp}超范围，扩大margin至{p["iqr_margin_span"]}; '

    # 修正4: 精确命中 → 奖励当前参数
    if best_match >= 2:
        p['decay'] = round(p['decay'] * (1 + lr * 0.1), 1)
        p['pos_weight'] = round(p['pos_weight'] * (1 + lr * 0.2), 2)
        entry['notes'] += f'命中{best_match}位! 微调decay={p["decay"]} pos_w={p["pos_weight"]}; '

    # 修正6: 组三参数调整
    if t == '组三':
        recent_3 = result['recent']
        zc = sum(1 for r in recent_3 if r['type'] == '组三')
        zr = zc / len(recent_3) if recent_3 else 0
        old_min = p.get('zusan_min_ratio', 0.15)
        # 6a: 实际组三但占比低于阈值 → 降低阈值
        if zr < old_min:
            p['zusan_min_ratio'] = round(old_min * (1 - lr * 0.2), 3)
            entry['notes'] += f'[组三] 占比{zr:.2f}<阈值{old_min:.2f}，阈值降至{p["zusan_min_ratio"]}; '
        # 6b: 实际组三但推荐未命中 → 增加组三推荐数量
        z3_hit = any(len(set(actual) & set(c['nums'])) >= 2 for c in cands)
        if not z3_hit:
            old_max = p.get('zusan_max_count', 3)
            p['zusan_max_count'] = min(5, old_max + 1)
            entry['notes'] += f'[组三] 未命中，zusan_max_count增至{p["zusan_max_count"]}; '
        # 6c: 实际组三但匹配 < 2 位 → 微调趋势权重
        if best_match < 2:
            old_tb = p.get('trend_bias_weight', 0.05)
            p['trend_bias_weight'] = round(old_tb * (1 + lr * 0.1), 4)
            entry['notes'] += f'[组三] 匹配<2位，trend_bias微调至{p["trend_bias_weight"]}; '
    elif t in ('组六', '豹子'):
        # 6d: 非组三但比例高 → 适当提高阈值
        recent_3 = result['recent']
        zc = sum(1 for r in recent_3 if r['type'] == '组三')
        zr = zc / len(recent_3) if recent_3 else 0
        old_min = p.get('zusan_min_ratio', 0.15)
        if zr >= old_min:
            new_val = min(0.40, round(old_min * (1 + lr * 0.15), 3))
            p['zusan_min_ratio'] = new_val
            entry['notes'] += f'[组三] 占比{zr:.2f}但出{t}，阈值微调至{p["zusan_min_ratio"]}; '

    # 修正5: 完全没命中 → 扩大搜索
    if not any_hit:
        p['diversity_overlap_max'] = min(3, p['diversity_overlap_max'] + 0.5)
        p['iqr_margin_sum'] = min(5, p['iqr_margin_sum'] + 1)
        p['iqr_margin_span'] = min(5, p['iqr_margin_span'] + 1)
        entry['notes'] += f'未命中，扩大搜索范围; '

    all_params[game] = p
    all_params['meta']['total_feedback'] += 1
    if kill_ok:
        all_params['meta']['total_kill_correct'] += 1
    if any_hit:
        all_params['meta']['total_any_hit'] += 1

    save_params(all_params)
    feedback_log.append(entry)
    save_feedback(feedback_log)

    # 输出反馈总结
    print(f"\n{'='*55}")
    print(f"  [{game.upper()}] 反馈已记录 - {date.today()}")
    print(f"{'='*55}")
    print(f"  开奖号码: {actual_str}  ({t}, 和值{s}, 跨度{sp})")
    print(f"  杀码 {kill}: {'✓ 正确' if kill_ok else '✗ 失败'}")
    print(f"  推荐命中: {'✓' if any_hit else '✗'}  最佳匹配: {best_match}/3位")
    if best_cand:
        print(f"  最佳匹配号码: {''.join(map(str, best_cand))}")
    print(f"\n  [参数修正]")
    print(f"  {entry['notes']}")
    print(f"\n  [累计] 反馈{all_params['meta']['total_feedback']}次 "
          f"杀码正确率{all_params['meta']['total_kill_correct']/max(1,all_params['meta']['total_feedback'])*100:.1f}% "
          f"Any命中率{all_params['meta']['total_any_hit']/max(1,all_params['meta']['total_feedback'])*100:.1f}%")

    return entry


def show_stats():
    all_params = load_params()
    feedback_log = load_feedback()
    meta = all_params['meta']

    print(f"\n{'='*55}")
    print(f"  累计统计")
    print(f"{'='*55}")
    print(f"  总反馈次数: {meta['total_feedback']}")
    if meta['total_feedback'] > 0:
        print(f"  杀码正确率: {meta['total_kill_correct']/meta['total_feedback']*100:.1f}%")
        print(f"  Any命中率:  {meta['total_any_hit']/meta['total_feedback']*100:.1f}%")

    print(f"\n  [当前参数]")
    for game in ['3d', 'pl3']:
        p = all_params[game]
        print(f"  {game}: decay={p['decay']} lookback={p['lookback']} "
              f"coldness_w={p['coldness_freq_weight']} rebound={p['cold_rebound_boost']} "
              f"margin_sum={p['iqr_margin_sum']} margin_span={p['iqr_margin_span']} "
              f"overlap={p['diversity_overlap_max']} pos_w={p['pos_weight']} "
              f"zusan_r={p.get('zusan_min_ratio', 0.15)} "
              f"zusan_max={p.get('zusan_max_count', 5)} "
              f"trend_w={p.get('trend_bias_weight', 0.05)}")

    if feedback_log:
        print(f"\n  [最近5次反馈]")
        for entry in feedback_log[-5:]:
            actual = ''.join(map(str, entry['actual']))
            k = '✓' if entry['kill_correct'] else '✗'
            h = '✓' if entry['any_hit'] else '✗'
            print(f"  {entry['date']} {entry['game']} 开{actual} 杀码{k} 命中{h} "
                  f"({entry['best_match']}/3) | {entry.get('notes','')[:50]}")


# ======================== 数据更新 ========================
def update_data(game, actual_str):
    """追加新一期数据 + 执行反馈修正"""
    # 先基于当前数据做反馈修正（预测 vs 实际对比）
    print(f"\n  >>> 第1步: 反馈修正（基于现有数据）")
    entry = apply_feedback(game, actual_str)

    # 再追加新数据
    print(f"\n  >>> 第2步: 追加新数据")
    path = os.path.join(BASE, 'data', f'{game}.json')
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    data = raw['data']
    data.sort(key=lambda x: x['issue'])
    last_issue = data[-1]['issue']
    year = int(last_issue[:4])
    period = int(last_issue[4:])
    next_period = period + 1
    next_year = year
    if period >= 358:
        next_period = 1
        next_year = year + 1
    next_issue = f"{next_year}{next_period:03d}"

    if any(item['issue'] == next_issue for item in data):
        print(f"  期号 {next_issue} 已存在，跳过追加")
    else:
        new_entry = {
            "issue": next_issue,
            "number": actual_str,
            "date": str(date.today())
        }
        data.append(new_entry)
        raw['data'] = data
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        print(f"  [{game.upper()}] 期号{next_issue} 号码{actual_str} 已追加")

    print(f"\n  >>> 完成。数据更新 + 参数修正一步到位。")
    return entry


# ======================== 主入口 ========================
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python smart_analyze.py <command> [args]")
        print("  analyze                  分析今日推荐(3D+PL3)")
        print("  analyze 3d               只分析3D")
        print("  update <game> <号码>     追加数据 + 自动修正参数")
        print("  feedback <game> <号码>   仅修正参数(不追加数据)")
        print("  stats                    查看累计统计")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'analyze':
        games = ['3d', 'pl3']
        if len(sys.argv) >= 3:
            games = [sys.argv[2]]
        for g in games:
            r = analyze(g)
            print_recommendations(r)

    elif cmd == 'update':
        if len(sys.argv) < 4:
            print("用法: python smart_analyze.py update 3d 023")
            sys.exit(1)
        game = sys.argv[2]
        number = sys.argv[3]
        update_data(game, number)

    elif cmd == 'feedback':
        if len(sys.argv) < 4:
            print("用法: python smart_analyze.py feedback 3d 023")
            sys.exit(1)
        game = sys.argv[2]
        number = sys.argv[3]
        apply_feedback(game, number)

    elif cmd == 'stats':
        show_stats()
