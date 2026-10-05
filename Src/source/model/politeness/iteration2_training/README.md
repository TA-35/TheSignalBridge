# Iteration 2 training scripts

These scripts produced `models/politeness_nn_iteration2/`. They were run on a 2-core Linux CPU machine with Python 3.12 and
`torch`, `spacy`, `spacy-curated-transformers`, `scikit-learn`, `pandas`, `scipy`, plus the spaCy `en_core_web_trf` package
(its bundled RoBERTa-base weights are the starting point for fine-tuning). They expect `src/`, `data/` and `runs/` folders
next to the corpus files and import `politeness_nn.py`, `train_politeness_nn.py` and `stanford_politeness_pipeline.py`
from Iteration 1, so adjust paths before re-running. Inference does not need any of this: see `scripts/politeness_v2.py`.

Order of execution:

1. `prep.py` - joins the cleaned corpus, the 21 strategy features and the raw annotator scores; reuses the Iteration 1
   grouped split; cleans the ~409k unlabelled requests with the same pipeline functions and removes every annotated text.
2. `ft.py` - fine-tunes RoBERTa-base for regression (`--feats 0` is the selected teacher, `--feats 1` is the ablation that
   also feeds in the 21 strategy features). Model selection uses validation Pearson only.
3. `predict_unlab2.py` (and the `--predict_unlabelled 1` option of `ft.py`) - scores unlabelled requests with the teacher.
4. `train_student.py` - trains the small text CNN on human labels plus teacher scores and exports NumPy weights.
5. `final_eval.py` - fixes level cut-offs on validation, then scores the test split once.
