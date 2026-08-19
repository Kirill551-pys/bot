import os, sys
import numpy as np
import pandas as pd
from model import (load_matches_data, train_models, calculate_team_metrics,
                   prepare_features_for_match, poisson_over_1_5,
                   predict_goals_markets)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

BINARY = [
    ('total',            'ТБ 2.5',          lambda r: r['home_goals']+r['away_goals'] > 2.5, ['home_goals','away_goals']),
    ('btts',             'ОЗ: да',          lambda r: r['home_goals']>0 and r['away_goals']>0, ['home_goals','away_goals']),
    ('btts_ht',          'ОЗ 1-й тайм',     lambda r: r['ht_home_goals']>0 and r['ht_away_goals']>0, ['ht_home_goals','ht_away_goals']),
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
    return {'n':0,'hit':0,'brier':0.0,'cn':0,'chit':0}

def eval_league(folder):
    path = os.path.join(DATA_DIR, folder, 'matches.csv')
    if not os.path.exists(path): return None
    df = load_matches_data(path)
    if df is None or len(df) < 300: return None
    df = df.sort_values('date').reset_index(drop=True)
    cut = df['date'].quantile(0.75)
    train_df, test_df = df[df['date']<cut], df[df['date']>=cut]
    print(f'[{folder}] train={len(train_df)} test={len(test_df)}...')
    md = train_models(train_df.reset_index(drop=True))
    if not md: return None
    models, scaler, ratings = md['models'], md['scaler'], md['final_ratings']

    S = {k: new_stat() for k,_ ,_,_ in BINARY}
    S['itb'] = new_stat()
    res = new_stat(); ht = new_stat(); book = new_stat()

    for _, r in test_df.iterrows():
        hm = calculate_team_metrics(df, r['home_team'], r['date'])
        am = calculate_team_metrics(df, r['away_team'], r['date'])
        X = scaler.transform(prepare_features_for_match(
            hm, am, ratings.get(r['home_team'],1500), ratings.get(r['away_team'],1500)))

        # --- Исход 1X2 ---
        p = models['result'].predict_proba(X)[0]           # [П2, Х, П1]
        prob = np.array([p[2], p[1], p[0]])                # [П1, Х, П2]
        y = np.array([1,0,0]) if r['home_goals']>r['away_goals'] else \
              np.array([0,0,1]) if r['home_goals']<r['away_goals'] else np.array([0,1,0])
        res['n']+=1; res['hit']+= int(prob.argmax()==y.argmax())
        res['brier'] += float(((prob-y)**2).sum())
        res['cn']+=1 if prob.max()>=0.5 else 0; res['chit']+= int(prob.max()>=0.5 and prob.argmax()==y.argmax())
        # букмекер
        if has_cols(r, ['PSCH','PSCD','PSCA']):
            ih,id_,ia = 1/r['PSCH'],1/r['PSCD'],1/r['PSCA']; s=ih+id_+ia
            imp = np.array([ih/s, id_/s, ia/s])
            book['n']+=1; book['hit'] += int(imp.argmax()==y.argmax())
        # --- 1-й тайм ---
        if 'ht_result' in models and has_cols(r,['ht_result']):
            m = {'H':2,'D':1,'A':0}.get(r['ht_result'])
            if m is not None:
                q = models['ht_result'].predict_proba(X)[0]
                qpr = np.array([q[2],q[1],q[0]])
                yy = np.array([1,0,0]) if m==2 else np.array([0,1,0]) if m==1 else np.array([0,0,1])
                ht['n']+=1; ht['hit']+=int(qpr.argmax()==yy.argmax())

        # --- Бинарные рынки ---
        goals = predict_goals_markets(models, X, hm, am)
        for key, name, fn, cols in BINARY:
            if key in ('total','btts'):
                if key not in goals or not has_cols(r, cols): continue
                p = goals[key]
            else:
                if key not in models or not has_cols(r, cols): continue
                p = models[key].predict_proba(X)[0][1]
            act = 1 if fn(r) else 0
            st = S[key]; st['n']+=1; st['hit']+= int((p>0.5)==act)
            st['brier'] += (p-act)**2
            if p>=0.55: st['cn']+=1; st['chit']+= int(act==1)
        # --- Индив. тотал (Пуассон) ---
        for team_m, gcol in ((hm,'home_goals'),(am,'away_goals')):
            if not has_cols(r,[gcol]): continue
            p = poisson_over_1_5(team_m.get('avg_scored',1.2))
            act = 1 if r[gcol]>=2 else 0
            st=S['itb']; st['n']+=1; st['hit']+=int((p>0.5)==act); st['brier']+=(p-act)**2

    return {'S':S,'res':res,'ht':ht,'book':book}

def pct(a,b): return f"{a/b:.1%}" if b else "—"

if __name__ == '__main__':
    only = sys.argv[1:]
    agg = {}
    for folder in (only or sorted(os.listdir(DATA_DIR))):
        out = eval_league(folder)
        if not out: continue
        for k, st in {**out['S'], '1X2':out['res'], 'HT':out['ht']}.items():
            a = agg.setdefault(k, new_stat())
            for f in a: a[f]+=st[f]
    print('='*78)
    print(f"{'РЫНОК':<18}{'N':>6}{'ACC':>8}{'BRIER':>8}{'CONF≥55%':>10}{'ACC_CONF':>10}")
    order = ['1X2','HT','total','btts','btts_ht','shots_over_22_5','sot_over_8_5',
             'fouls_over_23_5','corners_over_9_5','corners_over_10_5',
             'yellows_over_3_5','yellows_over_4_5','itb']
    names = {k:n for k,n,_,_ in BINARY}; names.update({'1X2':'Исход 1X2','HT':'Исход 1-го тайма','itb':'ИТБ 1.5 (Пуассон)'})
    for k in order:
        if k not in agg: continue
        st = agg[k]
        print(f"{names[k]:<18}{st['n']:>6}{pct(st['hit'],st['n']):>8}"
              f"{st['brier']/max(st['n'],1):>8.3f}{st['cn']:>10}{pct(st['chit'],st['cn']):>10}")