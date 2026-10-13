import os
import sys
import numpy as np
import pandas as pd
from model import (load_matches_data, train_models, calculate_team_metrics,
                   prepare_features_for_match, poisson_over_1_5,
                   predict_goals_markets)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# 🔥 Расширенный список рынков для бэктеста
BINARY = [
    ('total',            'ТБ 2.5',          lambda r: r['home_goals']+r['away_goals'] > 2.5, ['home_goals','away_goals']),
    ('btts',             'ОЗ: да',          lambda r: r['home_goals']>0 and r['away_goals']>0, ['home_goals','away_goals']),
    ('btts_ht',          'ОЗ 1-й тайм',     lambda r: float(str(r['ht_home_goals']).replace(',','.')) > 0 and float(str(r['ht_away_goals']).replace(',','.')) > 0, ['ht_home_goals','ht_away_goals']),
    ('shots_over_22_5',  'Удары ТБ 22.5',   lambda r: r['home_shots']+r['away_shots'] > 22.5, ['home_shots','away_shots']),
    ('sot_over_8_5',     'В створ ТБ 8.5',  lambda r: r['home_shots_on_target']+r['away_shots_on_target'] > 8.5, ['home_shots_on_target','away_shots_on_target']),
    ('fouls_over_23_5',  'Фолы ТБ 23.5',    lambda r: r['home_fouls']+r['away_fouls'] > 23.5, ['home_fouls','away_fouls']),
    ('corners_over_9_5', 'Угловые ТБ 9.5',  lambda r: r['home_corners']+r['away_corners'] > 9.5, ['home_corners','away_corners']),
    ('corners_over_10_5','Угловые ТБ 10.5', lambda r: r['home_corners']+r['away_corners'] > 10.5, ['home_corners','away_corners']),
    ('yellows_over_3_5', 'Карт. ТБ 3.5',    lambda r: r['home_yellows']+r['away_yellows'] > 3.5, ['home_yellows','away_yellows']),
    ('yellows_over_4_5', 'Карт. ТБ 4.5',    lambda r: r['home_yellows']+r['away_yellows'] > 4.5, ['home_yellows','away_yellows']),
]

def has_cols(r, cols):
    return all(c in r.index and pd.notna(r[c]) for c in cols)

def new_stat():
    return {'n':0, 'hit':0, 'brier':0.0, 'cn':0, 'chit':0, 
            'stake': 0.0, 'return': 0.0, 'value_bets': 0, 'roi_matches': 0}

def get_calibration_bucket(prob):
    """Определяет бакет калибровки для вероятности"""
    if prob < 0.50: return '<50%'
    elif prob < 0.60: return '50-60%'
    elif prob < 0.70: return '60-70%'
    elif prob < 0.80: return '70-80%'
    else: return '>=80%'

def eval_league(folder):
    path = os.path.join(DATA_DIR, folder, 'matches.csv')
    if not os.path.exists(path): return None
    
    df = load_matches_data(path)
    if df is None or len(df) < 300: return None
    
    # 🔥 ЗАЩИТА: Если датасет аномально большой (больше 10 000 матчей),
    # берем только последние 10 000, чтобы не ждать часами.
    MAX_MATCHES = 10000
    if len(df) > MAX_MATCHES:
        print(f'⚠️ [{folder}] Слишком большой датасет ({len(df)} матчей). Берем только последние {MAX_MATCHES}.')
        df = df.tail(MAX_MATCHES).reset_index(drop=True)
    
    df = df.sort_values('date').reset_index(drop=True)
    cut = df['date'].quantile(0.75)
    train_df, test_df = df[df['date']<cut], df[df['date']>=cut]
    print(f'[{folder}] train={len(train_df)} test={len(test_df)}...')
    
    md = train_models(train_df.reset_index(drop=True))
    if not md: return None
    models, scaler, ratings = md['models'], md['scaler'], md['final_ratings']

    S = {k: new_stat() for k,_,_,_ in BINARY}
    S['itb'] = new_stat()
    
    # 🔥 НОВЫЕ МЕТРИКИ ДЛЯ 1X2 (основной рынок для ROI)
    res = new_stat()
    calibration_tracker = {'<50%': {'n':0, 'hit':0}, '50-60%': {'n':0, 'hit':0}, 
                           '60-70%': {'n':0, 'hit':0}, '70-80%': {'n':0, 'hit':0}, '>=80%': {'n':0, 'hit':0}}
    
    # 🔥 СПИСОК ДЛЯ АНАЛИЗА ПОРОГОВ — ИНИЦИАЛИЗИРУЕМ ДО ЦИКЛА!
    all_predictions_list = []
    
    # 🔥 НОВОЕ: Собираем прогнозы по ВСЕМ рынкам
    all_markets_predictions = {
        'result': [],
        'total': [],
        'btts': [],
        'btts_ht': [],
        'shots_over_22_5': [],
        'sot_over_8_5': [],
        'fouls_over_23_5': [],
        'corners_over_9_5': [],
        'corners_over_10_5': [],
        'yellows_over_3_5': [],
        'yellows_over_4_5': [],
    }

    for _, r in test_df.iterrows():
        hm = calculate_team_metrics(df, r['home_team'], r['date'])
        am = calculate_team_metrics(df, r['away_team'], r['date'])
        X = scaler.transform(prepare_features_for_match(
            hm, am, ratings.get(r['home_team'],1500), ratings.get(r['away_team'],1500)))

        # --- Исход 1X2 и расчет ROI ---
        p = models['result'].predict_proba(X)[0]           # [П2, Х, П1]
        prob = np.array([p[2], p[1], p[0]])                # [П1, Х, П2]
        y = np.array([1,0,0]) if r['home_goals']>r['away_goals'] else \
              np.array([0,0,1]) if r['home_goals']<r['away_goals'] else np.array([0,1,0])
        
        pred_idx = prob.argmax()
        model_prob = float(prob[pred_idx])
        is_hit = 1 if pred_idx == y.argmax() else 0
        
        res['n'] += 1
        res['hit'] += is_hit
        res['brier'] += float(((prob-y)**2).sum())
        
        # 🔥 Сохраняем данные каждого прогноза для анализа по порогам
        pred_data = {
            'model_prob': model_prob,
            'is_hit': is_hit,
            'stake': 1.0,
            'actual_odds': None,
            'is_value': False
        }
        
        # 🔥 Расчет ROI (только если есть реальные коэффициенты)
        psch = r.get('PSCH', None)
        pscd = r.get('PSCD', None)
        psca = r.get('PSCA', None)
        
        if pd.notna(psch) and pd.notna(pscd) and pd.notna(psca):
            # Реальные коэффициенты есть
            odds_arr = [float(psca), float(pscd), float(psch)]  # [П2, Х, П1]
            actual_odds = odds_arr[pred_idx]
            
            # 🔥 КРИТИЧЕСКИ ВАЖНЫЙ ФИЛЬТР: Работаем только с адекватными коэффициентами
            # Отсекаем "лотерейные" исходы с кэфом > 3.50 и слишком низкие < 1.40
            if 1.40 <= actual_odds <= 3.50:
                stake = 1.0
                res['stake'] += stake
                res['return'] += stake * actual_odds * is_hit
                res['roi_matches'] += 1
                pred_data['actual_odds'] = actual_odds
                
                # Расчет Value только для адекватных кэфов
                expected_value = (model_prob * actual_odds) - 1.0
                if expected_value > 0.05:  # 🔥 Требую минимум 5% математического преимущества
                    res['value_bets'] += 1
                    pred_data['is_value'] = True

        # 🔥 Калибровка: отслеживаем реальную частоту попаданий для предсказанных вероятностей
        bucket = get_calibration_bucket(model_prob)
        calibration_tracker[bucket]['n'] += 1
        calibration_tracker[bucket]['hit'] += is_hit
        
        # 🔥 Сохраняем прогноз для 1X2
        all_markets_predictions['result'].append(pred_data.copy())

        # --- Бинарные рынки ---
        goals = predict_goals_markets(models, X, hm, am)
        for key, name, fn, cols in BINARY:
            if key in ('total','btts'):
                if key not in goals or not has_cols(r, cols): continue
                p_bin = goals[key]
            else:
                if key not in models or not has_cols(r, cols): continue
                
                # 🔥 ЗАЩИТА: безопасно получаем вероятность класса 1
                probs = models[key].predict_proba(X)[0]
                if len(probs) == 2:
                    p_bin = probs[1]
                else:
                    # Если модель обучилась только на 1 классе, проверяем, был ли это класс "1"
                    p_bin = probs[0] if 1 in getattr(models[key], 'classes_', [0]) else 0.0
            
            act = 1 if fn(r) else 0
            st = S[key]
            st['n'] += 1
            st['hit'] += int((p_bin > 0.5) == act)
            st['brier'] += (p_bin - act) ** 2
            if p_bin >= 0.55: 
                st['cn'] += 1
                st['chit'] += int(act == 1)
            
            # 🔥 Сохраняем прогноз для этого рынка
            market_pred = {
                'model_prob': p_bin,
                'is_hit': act,
                'stake': 1.0,
                'actual_odds': None,
                'is_value': False
            }
            all_markets_predictions[key].append(market_pred)
        
        # 🔥 ДОБАВЛЯЕМ ПРОГНОЗ В СПИСОК (внутри цикла, но НЕ return!)
        all_predictions_list.append(pred_data)
    
    # 🔥 RETURN ДОЛЖЕН БЫТЬ ПОСЛЕ ЦИКЛА (с правильным отступом!)
    return {
        'S': S, 
        'res': res, 
        'calibration': calibration_tracker, 
        'predictions': all_predictions_list,
        'markets_predictions': all_markets_predictions
    }

def pct(a, b): 
    return f"{(a/b)*100:.1f}%" if b else "—"

if __name__ == '__main__':
    only = sys.argv[1:]
    agg = {'res': new_stat(), 'calibration': {'<50%': {'n':0, 'hit':0}, '50-60%': {'n':0, 'hit':0}, '60-70%': {'n':0, 'hit':0}, '70-80%': {'n':0, 'hit':0}, '>=80%': {'n':0, 'hit':0}}}
    all_predictions = []  # 🔥 Глобальный список всех прогнозов
    
    # 🔥 НОВОЕ: Агрегируем прогнозы по всем рынкам
    all_markets_predictions = {
        'result': [],
        'total': [],
        'btts': [],
        'btts_ht': [],
        'shots_over_22_5': [],
        'sot_over_8_5': [],
        'fouls_over_23_5': [],
        'corners_over_9_5': [],
        'corners_over_10_5': [],
        'yellows_over_3_5': [],
        'yellows_over_4_5': [],
    }
    
    for folder in (only or sorted(os.listdir(DATA_DIR))):
        out = eval_league(folder)
        if not out: continue
        
        # Агрегируем 1X2
        for f in agg['res']:
            agg['res'][f] += out['res'][f]
        
        # Агрегируем калибровку
        for bucket in agg['calibration']:
            agg['calibration'][bucket]['n'] += out['calibration'][bucket]['n']
            agg['calibration'][bucket]['hit'] += out['calibration'][bucket]['hit']
        
        # 🔥 Агрегируем прогнозы
        all_predictions.extend(out.get('predictions', []))
        
        # 🔥 Агрегируем прогнозы по рынкам
        for market_key in all_markets_predictions:
            all_markets_predictions[market_key].extend(out.get('markets_predictions', {}).get(market_key, []))

    print('='*90)
    print(f"{'РЫНОК':<18}{'N':>6}{'ACC':>8}{'ROI':>8}{'VALUE':>8}{'BRIER':>8}{'CONF≥55% ACC':>12}")
    
    st = agg['res']
    
    if st['roi_matches'] > 0:
        roi = ((st['return'] - st['stake']) / st['stake']) * 100
        roi_str = f"{roi:>7.1f}%"
    else:
        roi_str = "  N/A"
    
    print(f"{'1X2 (Основной)':<18}{st['n']:>6}{pct(st['hit'], st['n']):>8}{roi_str}{st['value_bets']:>8}{st['brier']/max(st['n'],1):>8.3f}{pct(st['chit'], st['cn']):>12}")
    
    print(f"\n📊 Статистика ROI: матчей с реальными кэфами: {st['roi_matches']} из {st['n']}")
    
    # 🔥 НОВЫЙ БЛОК: Анализ ROI по уровням уверенности для 1X2
    print('\n📊 ROI ПО УРОВНЯМ УВЕРЕННОСТИ МОДЕЛИ (1X2):')
    print(f"{'Порог уверенности':<20}{'N':>6}{'ACC':>8}{'ROI':>10}{'Value':>8}")
    
    thresholds = [0.45, 0.50, 0.55, 0.60, 0.65]
    for threshold in thresholds:
        # Фильтруем прогнозы с уверенностью >= threshold
        filtered = [p for p in all_predictions if p['model_prob'] >= threshold]
        if not filtered:
            print(f"{'≥' + str(int(threshold*100)) + '%':<20}{0:>6}{'—':>8}{'—':>10}{'—':>8}")
            continue
        
        f_n = len(filtered)
        f_hits = sum(1 for p in filtered if p['is_hit'] == 1)
        f_acc = (f_hits / f_n) * 100
        
        # ROI только для ставок с реальными кэфами
        f_roi_matches = [p for p in filtered if p.get('actual_odds') is not None]
        if f_roi_matches:
            f_stake = sum(p['stake'] for p in f_roi_matches)
            f_return = sum(p['stake'] * p['actual_odds'] * p['is_hit'] for p in f_roi_matches)
            f_roi = ((f_return - f_stake) / f_stake) * 100 if f_stake > 0 else 0
            f_roi_str = f"{f_roi:>9.1f}%"
        else:
            f_roi_str = "      N/A"
        
        f_value = sum(1 for p in filtered if p.get('is_value', False))
        
        print(f"{'≥' + str(int(threshold*100)) + '%':<20}{f_n:>6}{f_acc:>7.1f}%{f_roi_str}{f_value:>8}")
    
    # 🔥 НОВОЕ: Анализ по ВСЕМ рынкам
    print('\n' + '='*90)
    print('📊 АНАЛИЗ ПО ВСЕМ РЫНКАМ:')
    print('='*90)
    
    market_names = {
        'result': 'Исход 1X2',
        'total': 'ТБ 2.5',
        'btts': 'ОЗ: Да',
        'btts_ht': 'ОЗ 1-й тайм',
        'shots_over_22_5': 'Удары ТБ 22.5',
        'sot_over_8_5': 'Удары в створ ТБ 8.5',
        'fouls_over_23_5': 'Фолы ТБ 23.5',
        'corners_over_9_5': 'Угловые ТБ 9.5',
        'corners_over_10_5': 'Угловые ТБ 10.5',
        'yellows_over_3_5': 'Карточки ТБ 3.5',
        'yellows_over_4_5': 'Карточки ТБ 4.5',
    }
    
    for market_key, market_name in market_names.items():
        market_preds = all_markets_predictions.get(market_key, [])
        if not market_preds:
            continue
        
        print(f'\n🎯 {market_name}:')
        print(f"{'Порог':<15}{'N':>8}{'ACC':>10}{'Статус':>15}")
        
        for threshold in [0.45, 0.50, 0.55, 0.60, 0.65]:
            filtered = [p for p in market_preds if p['model_prob'] >= threshold]
            if not filtered:
                print(f"{'≥' + str(int(threshold*100)) + '%':<15}{0:>8}{'—':>10}{'—':>15}")
                continue
            
            f_n = len(filtered)
            f_hits = sum(1 for p in filtered if p['is_hit'] == 1)
            f_acc = (f_hits / f_n) * 100
            
            # Определяем статус
            if f_acc >= 65:
                status = "✅ ОТЛИЧНО"
            elif f_acc >= 60:
                status = "✅ ХОРОШО"
            elif f_acc >= 55:
                status = "⚠️ СРЕДНЕ"
            else:
                status = "❌ СЛАБО"
            
            print(f"{'≥' + str(int(threshold*100)) + '%':<15}{f_n:>8}{f_acc:>9.1f}%{status:>15}")
    
    print('\n📊 КАЛИБРОВКА МОДЕЛИ (Предсказанная вероятность vs Реальная частота):')
    print(f"{'Бакет вероятности':<20}{'N':>6}{'Реальный Hit Rate':>18}{'Статус':>15}")
    
    # 🔥 Исправленный маппинг бакетов к их серединам
    bucket_midpoints = {
        '<50%': 0.45,
        '50-60%': 0.55,
        '60-70%': 0.65,
        '70-80%': 0.75,
        '>=80%': 0.85
    }
    
    for bucket in ['<50%', '50-60%', '60-70%', '70-80%', '>=80%']:
        data = agg['calibration'][bucket]
        if data['n'] > 0:
            real_hr = data['hit'] / data['n']
            midpoint = bucket_midpoints[bucket]
            # Если реальная частота близка к середине бакета (±15%), модель хорошо калибрована
            status = "✅ ОК" if abs(real_hr - midpoint) < 0.15 else "⚠️ Смещение"
            print(f"{bucket:<20}{data['n']:>6}{real_hr:>17.1%}{status:>15}")
        else:
            print(f"{bucket:<20}{0:>6}{'N/A':>18}{'—':>15}")