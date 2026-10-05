"""Fine-tune RoBERTa-base (+ optional strategy-feature fusion) for politeness regression."""
import sys, pickle, time, json, argparse, math; sys.path.insert(0,'src')
from common import *
import pandas as pd
from curated_transformers.models.attention import AttentionMask
ap = argparse.ArgumentParser()
ap.add_argument('--name', required=True); ap.add_argument('--seed', type=int, default=0)
ap.add_argument('--epochs', type=float, default=4); ap.add_argument('--lr', type=float, default=2e-5)
ap.add_argument('--bs', type=int, default=16); ap.add_argument('--feats', type=int, default=1)
ap.add_argument('--weighting', default='sem'); ap.add_argument('--dropout', type=float, default=0.1)
ap.add_argument('--wd', type=float, default=0.01); ap.add_argument('--train_on', default='train')
ap.add_argument('--predict_unlabelled', type=int, default=0)
a = ap.parse_args()
torch.manual_seed(a.seed); np.random.seed(a.seed); torch.set_num_threads(2)

class PolitenessRoberta(nn.Module):
    def __init__(self, enc, n_feat, dropout):
        super().__init__()
        self.enc = enc; self.drop = nn.Dropout(dropout); self.n_feat = n_feat
        if n_feat: self.fproj = nn.Sequential(nn.Linear(n_feat, 32), nn.Tanh())
        self.head = nn.Sequential(nn.Linear(768 + (32 if n_feat else 0), 256), nn.Tanh(), nn.Dropout(dropout), nn.Linear(256, 1))
    def forward(self, ids, mask, feats=None):
        h = self.enc(ids, AttentionMask(mask)).all_outputs[-1]
        mm = mask.unsqueeze(-1).float(); pooled = self.drop((h*mm).sum(1)/mm.sum(1))
        if self.n_feat: pooled = torch.cat([pooled, self.fproj(feats)], 1)
        return self.head(pooled).squeeze(-1)

df = pd.read_pickle('data/labelled.pkl'); ids = pickle.load(open('data/labelled_ids.pkl','rb'))
y = df['Normalized Score'].values.astype(np.float32)
F = np.hstack([df[FEATS].values.astype(np.float32), (df.source=='wikipedia').values[:,None].astype(np.float32)])
tr = np.where(df.split.isin(a.train_on.split('+')))[0]; va = np.where(df.split=='validation')[0]
mu, sd = y[df.split=='train'].mean(), y[df.split=='train'].std(); ys = (y-mu)/sd
if a.weighting == 'sem':   # inverse-variance style weight from the 5 annotators' spread
    s = df['annot_sem'].values; w = 1.0/(1.0 + (s/np.median(s))**2); w = w/w[tr].mean()
else: w = np.ones(len(df))
w = w.astype(np.float32)
_, _, enc = load_encoder()
model = PolitenessRoberta(enc, F.shape[1] if a.feats else 0, a.dropout)
nd = [p for n,p in model.enc.named_parameters() if 'bias' in n or 'norm' in n.lower()]
dc = [p for n,p in model.enc.named_parameters() if not ('bias' in n or 'norm' in n.lower())]
hp = [p for n,p in model.named_parameters() if not n.startswith('enc.')]
opt = torch.optim.AdamW([{'params': dc, 'lr': a.lr, 'weight_decay': a.wd}, {'params': nd, 'lr': a.lr, 'weight_decay': 0.0}, {'params': hp, 'lr': 1e-3, 'weight_decay': a.wd}])
steps_per_epoch = math.ceil(len(tr)/a.bs); total = int(steps_per_epoch*a.epochs); warm = int(0.06*total)
sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: (s+1)/warm if s < warm else max(0.0, (total-s)/(total-warm)))

def predict(idx_ids, feats, bs=64):
    model.eval(); order = np.argsort([len(x) for x in idx_ids]); out = np.zeros(len(idx_ids), dtype=np.float32)
    with torch.no_grad():
        for i in range(0, len(order), bs):
            b = order[i:i+bs]; x, m = collate([idx_ids[j] for j in b])
            out[b] = model(x, m, torch.from_numpy(feats[b]) if a.feats else None).numpy()
    model.train(); return out*sd + mu

rng = np.random.default_rng(a.seed); step = 0; best = -1; hist = []; t0 = time.time(); model.train()
eval_every = steps_per_epoch//2; done = False
while not done:
    # length-bucketed shuffling: sort chunks of 50 batches by length to cut padding
    perm = rng.permutation(tr); chunks = [perm[i:i+a.bs*50] for i in range(0, len(perm), a.bs*50)]
    batches = []
    for c in chunks:
        c = c[np.argsort([len(ids[j]) for j in c])]; batches += [c[i:i+a.bs] for i in range(0, len(c), a.bs)]
    rng.shuffle(batches)
    for b in batches:
        x, m = collate([ids[j] for j in b])
        pred = model(x, m, torch.from_numpy(F[b]) if a.feats else None)
        loss = (torch.from_numpy(w[b]) * nn.functional.huber_loss(pred, torch.from_numpy(ys[b]), delta=1.0, reduction='none')).mean()
        loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step(); opt.zero_grad(); step += 1
        if step % eval_every == 0 or step == total:
            if a.train_on == 'train':
                pv = predict([ids[j] for j in va], F[va]); r = float(np.corrcoef(pv, y[va])[0,1])
                hist.append({'step': step, 'epoch': step/steps_per_epoch, 'val_pearson': r, 'val_mae': float(np.abs(pv-y[va]).mean()), 'min': (time.time()-t0)/60})
                print(json.dumps(hist[-1]), flush=True)
                if r > best: best = r; torch.save(model.state_dict(), f'runs/{a.name}.pt')
            elif step == total: torch.save(model.state_dict(), f'runs/{a.name}.pt')
        if step >= total: done = True; break
model.load_state_dict(torch.load(f'runs/{a.name}.pt'))
p = predict(ids, F); np.save(f'runs/{a.name}_pred.npy', p)
json.dump({'args': vars(a), 'history': hist, 'best_val_pearson': best, 'train_mean': float(mu), 'train_std': float(sd)}, open(f'runs/{a.name}.json','w'), indent=1)
print('DONE best', best, flush=True)
if a.predict_unlabelled:
    uids = pickle.load(open('data/unlabelled_ids.pkl','rb')); sel = np.load('data/unlab_sel.npy'); UF = np.load('data/unlab_feats.npy')
    np.save(f'runs/{a.name}_unlab_pred.npy', predict([uids[j] for j in sel], UF)); print('UNLAB DONE', flush=True)
