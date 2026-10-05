import torch, torch.nn as nn
from curated_transformers.models.attention import AttentionMask
class PolitenessRoberta(nn.Module):
    def __init__(self, enc, n_feat, dropout=0.1):
        super().__init__()
        self.enc = enc; self.drop = nn.Dropout(dropout); self.n_feat = n_feat
        if n_feat: self.fproj = nn.Sequential(nn.Linear(n_feat, 32), nn.Tanh())
        self.head = nn.Sequential(nn.Linear(768 + (32 if n_feat else 0), 256), nn.Tanh(), nn.Dropout(dropout), nn.Linear(256, 1))
    def forward(self, ids, mask, feats=None):
        h = self.enc(ids, AttentionMask(mask)).all_outputs[-1]
        mm = mask.unsqueeze(-1).float(); pooled = self.drop((h*mm).sum(1)/mm.sum(1))
        if self.n_feat: pooled = torch.cat([pooled, self.fproj(feats)], 1)
        return self.head(pooled).squeeze(-1)
