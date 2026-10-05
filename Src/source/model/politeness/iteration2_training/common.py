import warnings; warnings.filterwarnings("ignore")
import numpy as np, torch, torch.nn as nn
FEATS = ['gratitude','deference','greeting','positive_lexicon','negative_lexicon','apologizing','please','please_start','indirect_btw','direct_question','direct_start','counterfactual_modal','indicative_modal','first_person_start','first_person_pl','first_person','second_person','second_person_start','factuality','hedge_wordlist','hedge_dependency']
MAXLEN = 96

def load_encoder():
    import spacy
    from curated_transformers.models.attention import AttentionMask  # noqa
    nlp = spacy.load("en_core_web_trf", exclude=["tagger","parser","attribute_ruler","lemmatizer","ner"])
    tr = nlp.get_pipe("transformer")
    enc = [n for n in tr.model.walk() if n.name == 'byte_bpe_encoder'][0]
    mod = [n for n in tr.model.walk() if n.name == 'pytorch'][0].shims[0]._model
    return nlp, enc, mod

def tokenize(texts, nlp, enc, bs=2000):
    out = []
    for i in range(0, len(texts), bs):
        docs = [nlp.make_doc(t) for t in texts[i:i+bs]]
        for r in enc.predict(docs):
            ids = np.asarray(r.dataXd).ravel().astype(np.int64)
            if len(ids) > MAXLEN: ids = np.concatenate([ids[:MAXLEN-1], ids[-1:]])
            out.append(ids)
    return out

def collate(id_list):
    L = max(len(x) for x in id_list)
    ids = np.full((len(id_list), L), 1, dtype=np.int64); mask = np.zeros((len(id_list), L), dtype=bool)
    for i, x in enumerate(id_list): ids[i, :len(x)] = x; mask[i, :len(x)] = True
    return torch.from_numpy(ids), torch.from_numpy(mask)

def metrics(y, p, cuts_y, cuts_p=None):
    """cuts_y: label tertile cut-offs (from train labels). cuts_p: cut-offs applied to predictions."""
    from scipy.stats import spearmanr
    cuts_p = cuts_y if cuts_p is None else cuts_p
    yc, pc = np.digitize(y, cuts_y), np.digitize(p, cuts_p)
    return dict(pearson=float(np.corrcoef(y, p)[0,1]), spearman=float(spearmanr(y, p)[0]),
                mae=float(np.abs(y-p).mean()), acc3=float((yc == pc).mean()))

def binary_quartile_acc(y, p, q_lo, q_hi, thr):
    m = (y <= q_lo) | (y >= q_hi)
    return float(((p[m] > thr) == (y[m] >= q_hi)).mean()), int(m.sum())
