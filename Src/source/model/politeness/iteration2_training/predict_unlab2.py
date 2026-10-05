import sys, pickle; sys.path.insert(0,'src')
from common import *
import pandas as pd
from predict_ckpt_model import PolitenessRoberta
torch.set_num_threads(2)
u = pd.read_pickle('data/unlabelled.pkl'); uids = pickle.load(open('data/unlabelled_ids.pkl','rb'))
sel1 = set(np.load('data/unlab_sel.npy').tolist()); rest = np.array([i for i in range(len(u)) if i not in sel1])
sel2 = np.sort(np.random.default_rng(1).choice(rest, 110000, replace=False)); np.save('data/unlab_sel2.npy', sel2)
df = pd.read_pickle('data/labelled.pkl'); y = df['Normalized Score'].values.astype(np.float32); mu, sd = y[df.split=='train'].mean(), y[df.split=='train'].std()
_, _, enc = load_encoder(); model = PolitenessRoberta(enc, 0); model.load_state_dict(torch.load('runs/ftB.pt')); model.eval()
out = np.full(len(sel2), np.nan, dtype=np.float32)
order = np.argsort([len(uids[j]) for j in sel2])
order = np.concatenate([order[i::10] for i in range(10)])   # 10 interleaved length-sorted passes -> any prefix is a random sample
with torch.no_grad():
    for i in range(0, len(order), 64):
        b = order[i:i+64]; b = b[np.argsort([len(uids[sel2[j]]) for j in b])]; x, m = collate([uids[sel2[j]] for j in b])
        out[b] = model(x, m, None).numpy()*sd+mu
        if (i//64) % 100 == 0: np.save('runs/ftB_unlab2_pred.npy', out); print(i, flush=True)
np.save('runs/ftB_unlab2_pred.npy', out); print('ALLDONE', flush=True)
