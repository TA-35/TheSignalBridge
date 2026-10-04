"""Distil the fine-tuned RoBERTa teacher into a small text CNN that runs on NumPy alone."""
import sys, json, argparse, time, collections; sys.path.insert(0,'src')
import numpy as np, pandas as pd, torch, torch.nn as nn
from politeness_v2 import tokenize, PAD, UNK, PolitenessCNN, encode
ap = argparse.ArgumentParser()
ap.add_argument('--name', default='stu'); ap.add_argument('--teachers', default='ftB'); ap.add_argument('--n_unlab', type=int, default=10**9)
ap.add_argument('--emb', type=int, default=128); ap.add_argument('--filters', type=int, default=160); ap.add_argument('--epochs', type=int, default=12)
ap.add_argument('--alpha', type=float, default=0.5, help='weight of the human label vs teacher on labelled train rows')
ap.add_argument('--lr', type=float, default=1e-3); ap.add_argument('--seed', type=int, default=0); ap.add_argument('--dropout', type=float, default=0.3)
ap.add_argument('--min_count', type=int, default=3); ap.add_argument('--pool2', type=int, default=0); ap.add_argument('--no_unlab', type=int, default=0)
a = ap.parse_args(); torch.manual_seed(a.seed); rng = np.random.default_rng(a.seed); torch.set_num_threads(2)
WIDTHS = [1, 2, 3, 4]
df = pd.read_pickle('data/labelled.pkl'); y = df['Normalized Score'].values.astype(np.float32)
tr = np.where(df.split=='train')[0]; va = np.where(df.split=='validation')[0]
mu, sd = float(y[tr].mean()), float(y[tr].std())
T = a.teachers.split('+')
t_lab = np.mean([np.load(f'runs/{t}_pred.npy') for t in T], 0)
texts = list(df.Request[tr]); targ = list(a.alpha*y[tr] + (1-a.alpha)*t_lab[tr]); wts = [1.0]*len(tr)
if not a.no_unlab:
    u = pd.read_pickle('data/unlabelled.pkl'); sel = np.load('data/unlab_sel.npy')
    t_un = np.mean([np.load(f'runs/{t}_unlab_pred.npy') for t in T], 0)
    if a.pool2:   # second batch of teacher-labelled requests
        sel = np.concatenate([sel, np.load('data/unlab_sel2.npy')]); t_un = np.concatenate([t_un, np.load(f'runs/{T[0]}_unlab2_pred.npy')])
        ok = ~np.isnan(t_un); sel, t_un = sel[ok], t_un[ok]
    k = min(a.n_unlab, len(sel)); pick = rng.choice(len(sel), k, replace=False)
    texts += list(u.Request.values[sel[pick]]); targ += list(t_un[pick]); wts += [1.0]*k
targ = (np.array(targ, np.float32)-mu)/sd
toks = [tokenize(t) for t in texts]
cnt = collections.Counter(w for t in toks for w in set(t))
vocab = {'<pad>': PAD, '<unk>': UNK}
for w, c in cnt.most_common():
    if c >= a.min_count: vocab[w] = len(vocab)
print('train docs', len(texts), 'vocab', len(vocab), flush=True)
enc_ = lambda ts: [np.array([vocab.get(w, UNK) for w in t] or [UNK], np.int64) for t in ts]
X = enc_(toks); Xva = enc_([tokenize(t) for t in df.Request[va]])

class CNN(nn.Module):
    def __init__(s):
        super().__init__()
        s.emb = nn.Embedding(len(vocab), a.emb, padding_idx=0)
        s.convs = nn.ModuleList([nn.Conv1d(a.emb, a.filters, k) for k in WIDTHS])
        s.drop = nn.Dropout(a.dropout); s.fc1 = nn.Linear(2*a.filters*len(WIDTHS), 256); s.fc2 = nn.Linear(256, 1)
    def forward(s, ids, lens):
        pad = max(WIDTHS)-1
        x = s.emb(nn.functional.pad(ids, (pad, pad))).transpose(1, 2)   # (B,E,T+2pad)
        out = []
        for k, c in zip(WIDTHS, s.convs):
            h = torch.relu(c(x))                                          # (B,F,T+2pad-k+1)
            n = (lens + 2*pad - k + 1).view(-1, 1, 1)
            m = (torch.arange(h.shape[2]).view(1, 1, -1) < n)
            out += [h.masked_fill(~m, -1e9).max(2).values, (h*m).sum(2)/n.squeeze(2)]
        return s.fc2(s.drop(torch.tanh(s.fc1(s.drop(torch.cat(out, 1)))))).squeeze(-1)
def batch(seqs):
    L = max(len(q) for q in seqs); ids = np.zeros((len(seqs), L), np.int64)
    for i, q in enumerate(seqs): ids[i, :len(q)] = q
    return torch.from_numpy(ids), torch.tensor([len(q) for q in seqs])
def predict(m, seqs):
    m.eval(); o = np.zeros(len(seqs), np.float32); order = np.argsort([len(q) for q in seqs])
    with torch.no_grad():
        for i in range(0, len(order), 512):
            b = order[i:i+512]; o[b] = m(*batch([seqs[j] for j in b])).numpy()
    m.train(); return o*sd+mu
m = CNN(); opt = torch.optim.AdamW(m.parameters(), lr=a.lr, weight_decay=1e-4)
n = len(X); bs = 128; total = a.epochs*(n//bs); sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=total, pct_start=0.1)
best = -1; hist = []; t0 = time.time(); step = 0
for ep in range(a.epochs):
    perm = rng.permutation(n)
    for i in range(0, n - bs + 1, bs):
        b = perm[i:i+bs]; ids, lens = batch([X[j] for j in b])
        # word dropout: randomly replace 5% of tokens by <unk> so rare words are not memorised
        drop = (torch.rand(ids.shape) < 0.05) & (ids != 0); ids = ids.masked_fill(drop, UNK)
        loss = nn.functional.huber_loss(m(ids, lens), torch.from_numpy(targ[b])); loss.backward()
        nn.utils.clip_grad_norm_(m.parameters(), 1.0); opt.step(); sched.step(); opt.zero_grad(); step += 1
        if step >= total: break
    pv = predict(m, Xva); r = float(np.corrcoef(pv, y[va])[0, 1]); rt = float(np.corrcoef(pv, t_lab[va])[0, 1])
    hist.append({'epoch': ep+1, 'val_pearson_vs_human': r, 'val_pearson_vs_teacher': rt, 'min': (time.time()-t0)/60}); print(json.dumps(hist[-1]), flush=True)
    if r > best: best = r; torch.save(m.state_dict(), f'runs/{a.name}.pt')
m.load_state_dict(torch.load(f'runs/{a.name}.pt')); m.eval()
sd_ = m.state_dict(); arrays = {'emb': sd_['emb.weight'].numpy(), 'fc1_w': sd_['fc1.weight'].numpy(), 'fc1_b': sd_['fc1.bias'].numpy(), 'fc2_w': sd_['fc2.weight'].numpy(), 'fc2_b': sd_['fc2.bias'].numpy()}
for k, c in zip(WIDTHS, m.convs):   # torch conv weight (F,E,k) -> (F, k*E) matching the NumPy window layout
    arrays[f'conv{k}_w'] = c.weight.detach().permute(0, 2, 1).reshape(a.filters, -1).numpy(); arrays[f'conv{k}_b'] = c.bias.detach().numpy()
np.savez_compressed(f'runs/{a.name}.npz', **{k: v.astype(np.float16) for k, v in arrays.items()})
json.dump(vocab, open(f'runs/{a.name}_vocab.json', 'w'))
# all-labelled predictions through the *NumPy* path with the float16 weights that will ship
npm = PolitenessCNN(dict(np.load(f'runs/{a.name}.npz')), WIDTHS)
p = np.array([npm.score_standardized(encode(t, vocab))*sd+mu for t in df.Request]); np.save(f'runs/{a.name}_pred.npy', p)
pt = predict(m, enc_([tokenize(t) for t in df.Request])); print('numpy-vs-torch max abs diff', float(np.abs(p-pt).max()))
json.dump({'args': vars(a), 'history': hist, 'best_val_pearson': best, 'vocab': len(vocab), 'train_docs': len(texts), 'widths': WIDTHS, 'train_mean': mu, 'train_std': sd}, open(f'runs/{a.name}.json', 'w'), indent=1)
print('DONE best', best)
