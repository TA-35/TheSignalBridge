"""Assemble every data source into one modelling table + fixed split + cleaned unlabelled pool."""
import sys, json, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, 'src')
import stanford_politeness_pipeline as P
from politeness_nn import normalize_text
from train_politeness_nn import grouped_split
D = Path('.')  # project root containing the corpus CSVs
df = pd.read_csv(D/'stanford_politeness_features.csv')
assert len(df) == 10956
# --- raw annotator scores -> per-annotator z-scores -> per-item noise estimate
raw = pd.concat([pd.read_csv(D/'wikipedia.annotated.csv'), pd.read_csv(D/'stack-exchange.annotated.csv')], ignore_index=True)
assert (raw['Id'].values == df['Id'].values).all() and np.allclose(raw['Normalized Score'], df['Normalized Score'])
S = raw[[f'Score{i}' for i in range(1,6)]].to_numpy(float)
T = raw[[f'TurkId{i}' for i in range(1,6)]].to_numpy(str)
Z = np.zeros_like(S)
for src_mask in (df['source']=='wikipedia').values, (df['source']=='stack-exchange').values:
    for t in np.unique(T[src_mask]):
        m = (T == t) & src_mask[:, None]
        v = S[m]; Z[m] = (v - v.mean()) / (v.std() + 1e-9)
print('corr(mean z, Normalized Score)=%.4f' % np.corrcoef(Z.mean(1), df['Normalized Score'])[0,1])
df['annot_z_std'] = Z.std(1, ddof=1)
df['annot_sem'] = df['annot_z_std'] / np.sqrt(5)
for i in range(5): df[f'z{i+1}'] = Z[:, i]
rows = df.to_dict('records')
for r in rows: r['Normalized Score'] = str(r['Normalized Score'])
sp = grouped_split(rows, 5120)
df['split'] = ''
for k, idx in sp.items(): df.loc[idx, 'split'] = k
print(df['split'].value_counts().to_dict())
df.to_pickle('data/labelled.pkl')
# --- unlabelled pool, cleaned with the same pipeline functions
w = pd.read_csv(D/'wikipedia.requests.csv', usecols=['Community','Id','Request']); w['source']='wikipedia'
s = pd.read_csv(D/'stack-exchange.requests.csv', usecols=['Community','Id','Request']); s['source']='stack-exchange'
for d in (w, s): d.dropna(subset=['Request'], inplace=True); d['Request'] = d['Request'].astype(str).apply(P.clean_request_text)
w['Request'] = w['Request'].apply(P.clean_wiki_markup).apply(lambda t: P.LEADING_WIKI_TABLE_RE.sub('', t))
s['Request'] = s['Request'].apply(P.clean_se_markup).apply(P.clean_se_markdown)
u = pd.concat([w, s], ignore_index=True)
u['Request'] = u['Request'].apply(P.clean_entities_and_wikilinks).apply(P.clean_request_text)
u['norm'] = u['Request'].apply(normalize_text)
n0 = len(u)
lab_norm = set(df['Request'].apply(normalize_text))
u = u[~u['norm'].isin(lab_norm)]
n1 = len(u)
u = u.drop_duplicates('norm')
wc = u['Request'].str.split().str.len()
u = u[(wc >= 3) & (wc <= 120)].reset_index(drop=True)
print('unlabelled: raw', n0, 'after removing annotated texts', n1, 'after dedupe/length', len(u), u['source'].value_counts().to_dict())
u.drop(columns='norm').to_pickle('data/unlabelled.pkl')
