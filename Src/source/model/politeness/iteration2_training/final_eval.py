"""Final held-out evaluation. Cut-offs are fixed on validation, then applied to test once."""
import sys, json; sys.path.insert(0,'src')
import numpy as np, pandas as pd
from scipy.stats import spearmanr
df = pd.read_pickle('data/labelled.pkl'); y = df['Normalized Score'].values
S = {k: (df.split==k).values for k in ('train','validation','test')}
cuts_y = np.quantile(y[S['train']], [1/3, 2/3]); qlo, qhi = np.quantile(y[S['train']], [.25, .75])
models = dict(a.split('=') for a in sys.argv[1:])
out = {}
def ev(p, mask, cuts_p, thr):
    yy, pp = y[mask], p[mask]; m = (yy <= qlo) | (yy >= qhi)
    return dict(n=int(mask.sum()), pearson=float(np.corrcoef(yy, pp)[0,1]), spearman=float(spearmanr(yy, pp)[0]), mae=float(np.abs(yy-pp).mean()), rmse=float(np.sqrt(((yy-pp)**2).mean())),
                acc3=float((np.digitize(yy, cuts_y) == np.digitize(pp, cuts_p)).mean()), acc_binary_quartiles=float(((pp[m] > thr) == (yy[m] >= qhi)).mean()), n_binary=int(m.sum()))
for label, name in models.items():
    p = np.load(f'runs/{name}_pred.npy'); cuts_p = np.quantile(p[S['validation']], [1/3, 2/3]); thr = float(np.median(p[S['validation']]))
    r = {k: ev(p, m, cuts_p, thr) for k, m in S.items()}
    for s in ('wikipedia', 'stack-exchange'): r[f'test_{s}'] = ev(p, S['test'] & (df.source==s).values, cuts_p, thr)
    rng = np.random.default_rng(0); ti = np.where(S['test'])[0]; bs = []
    for _ in range(1000):
        b = rng.choice(ti, len(ti)); mk = np.zeros(len(y), bool); mk[b] = True
        yy, pp = y[b], p[b]; bs.append((np.corrcoef(yy, pp)[0,1], (np.digitize(yy, cuts_y) == np.digitize(pp, cuts_p)).mean()))
    bs = np.array(bs); r['test_ci95'] = {'pearson': np.percentile(bs[:,0], [2.5, 97.5]).round(3).tolist(), 'acc3': np.percentile(bs[:,1], [2.5, 97.5]).round(3).tolist()}
    c = np.zeros((3,3), int)
    for a_, b_ in zip(np.digitize(y[S['test']], cuts_y), np.digitize(p[S['test']], cuts_p)): c[a_, b_] += 1
    r['test_confusion_rows_actual_cols_predicted'] = c.tolist(); r['prediction_cutoffs'] = cuts_p.tolist(); r['binary_threshold'] = thr
    out[label] = r
    print(f"{label:22s}" + ' | '.join(f"{k}: r={r[k]['pearson']:.3f} acc3={r[k]['acc3']:.3f} bin={r[k]['acc_binary_quartiles']:.3f} mae={r[k]['mae']:.3f}" for k in ('train','validation','test')))
    print(f"{'':22s}test wiki r={r['test_wikipedia']['pearson']:.3f} acc3={r['test_wikipedia']['acc3']:.3f} bin={r['test_wikipedia']['acc_binary_quartiles']:.3f} | test SE r={r['test_stack-exchange']['pearson']:.3f} acc3={r['test_stack-exchange']['acc3']:.3f} bin={r['test_stack-exchange']['acc_binary_quartiles']:.3f} | CI {r['test_ci95']}")
out['_definitions'] = {'label_tertile_cutoffs_from_train': cuts_y.tolist(), 'quartiles_from_train': [float(qlo), float(qhi)]}
json.dump(out, open('runs/final_eval.json', 'w'), indent=1)
