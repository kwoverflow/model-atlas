# Frozen Research Comparison 1

Registered before running the new ranker on 2026-09-12.

Question: does a trained query/passage scorer solve the measured selection bottleneck more
effectively and cheaply than the 1.5B generative selector?

## Fixed Inputs

- Approved revision 1.0.5; no case, source, label, top-k or approval edits.
- Previous report SHA-256: 7f7536daba6baf4c20ba2a0d30a1856f2b4d854a7a3f614ecb9f84a69c5be15a.
- Reuse its guarded English translations and public top-50 candidate lists exactly.
- Evaluate all 48 RAG cases; apply candidates only to 22 ordinary cases, retaining 26 fallbacks.
- Known development set only, not an independent holdout.
- Never provide expected IDs, facts, grades or review data to the scorer.

## Two Candidates Only

1. Trained Cross-Encoder: cross-encoder/ms-marco-MiniLM-L6-v2, official FP32 ONNX model,
   revision 233902d25c440f23af6f7d6e94d2946bac0bee0a. Score each English-query/full-passage pair;
   stable descending score, then chunk ID. Return five. English checkpoint is appropriate to
   the translated-query/English-handbook experiment, not evidence of Korean-language support.
2. The same scores with Maximal Marginal Relevance. Relevance = sigmoid of raw score (not a
   calibrated probability), redundancy = cosine similarity of L2-normalized word unigram/bigram
   TF-IDF over the fixed public candidate corpus. Lambda = 0.7; choose five greedily with stable
   chunk-ID ties. This is a particular MMR adaptation, not a reproduction of the 1998 experiment.

Use Hugging Face Tokenizers and ONNX Runtime CPU, at most four intra-op threads, batch size eight.
Maximum sequence length 512; query capped at 128 tokens. Use all overlapping passage windows
(64-token overlap, at most eight per passage), aggregate with MaxP. Reject excess rather than
silently truncate. Record window count, raw scores, input hashes, model/file hashes and timing.
At most 1,100 pairs, no new translation/answer generation, no cloud inference or training.
Wall-clock scoring budget 15 minutes, checked between cases; each case is one bounded CPU batch loop.

## Decision And Stop

- Promising development candidate: at least 12/22 ordinary and 3/5 critical, zero regressions
  against both default lexical and guarded RRF, no processing failures, and measured scoring
  time below 10 seconds per ordinary case on average (translation/model loading excluded).
- Answer-diagnostic eligibility still requires all five critical retrieval contracts and zero
  regressions/failures. Neither condition authorizes production or official Gate promotion.
- Run this comparison once. No lambda sweep, new prompts, alternate model cascade or cherry-picking.
- If both miss the promising threshold, stop this retrieval-tuning line. Keep the product scope
  as an EvalOps MVP and require a separately scoped data/model decision instead of another phase.
- Even if a candidate is promising, preserve the default and require independent held-out queries
  and fresh answer/citation evaluation before claiming general quality.

## Basis

- Nogueira and Cho (2019), https://arxiv.org/abs/1901.04085: query/passage cross-encoding.
- Carbonell and Goldstein (1998), https://doi.org/10.1145/290941.291025: relevance/novelty MMR.
- Dai and Callan (2019), https://arxiv.org/abs/1905.09217: passage-level scoring and MaxP.
- Sun et al., https://arxiv.org/abs/2304.09542: specialized ranking versus general generation;
  the previous hierarchical source deletion was not the paper's sliding-window permutation.
- Liu et al., https://arxiv.org/abs/2307.03172: context-position sensitivity is a risk, not a
  proven diagnosis of our exact run.

The model card and publication benchmark numbers are not Model Atlas quality estimates.
