import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score

FEATURES = ['pressure_kpa', 'flow_lpm']
# 概率落在两条界线之间视为证据不足，交主管现场复核。
DEFECT_THRESHOLD = 0.65
PASS_THRESHOLD = 0.35


def _reference():
    source = Path(__file__).resolve().parents[1] / 'fixtures/nozzle_trials.json'
    raw = source.read_bytes()
    return raw, json.loads(raw)


def _rows(batch):
    return [(t['pressure_kpa'], t['flow_lpm'], 1 if t['verdict'] == 'bad' else 0)
            for t in batch['trials'] if t['verdict'] in ('good', 'bad')]


def _new_model():
    return RandomForestClassifier(
        n_estimators=100, max_depth=6, min_samples_leaf=2,
        class_weight='balanced', random_state=42, n_jobs=1)


def _score(y_true, y_pred):
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    if len(y_true) == 0:
        return {'rows': 0, 'accuracy': None, 'precision': None, 'recall': None}
    # 只有单一类别时 precision/recall 无定义，保留 None 而不是伪装成 1。
    both = len(set(y_true.tolist())) > 1
    return {
        'rows': int(len(y_true)),
        'accuracy': round(float(accuracy_score(y_true, y_pred)), 4),
        'precision': round(float(precision_score(y_true, y_pred, zero_division=0)), 4) if both else None,
        'recall': round(float(recall_score(y_true, y_pred, zero_division=0)), 4) if both else None,
    }


@lru_cache(maxsize=1)
def train_reference():
    """用已确认好坏的试喷记录训练，并按到货批次留出评估泛化。"""
    raw, root = _reference()
    batches = [b for b in root['confirmed_batches'] if _rows(b)]
    rows = [r for b in batches for r in _rows(b)]
    if not rows:
        raise ValueError('缺少已确认好坏的试喷记录')
    x = np.array([[a, b] for a, b, _ in rows])
    y = np.array([c for _, _, c in rows])

    model = _new_model()
    model.fit(x, y)
    in_sample_pred = model.predict(x)

    # 按到货批次留一：留出的整批不参与训练，再把各批预测汇总。
    holdout_true, holdout_pred, per_batch = [], [], []
    for batch in batches:
        train = [r for b in batches if b is not batch for r in _rows(b)]
        test = _rows(batch)
        if not train:
            continue
        held = _new_model()
        held.fit(np.array([[a, b] for a, b, _ in train]), np.array([c for _, _, c in train]))
        pred = (held.predict_proba(np.array([[a, b] for a, b, _ in test]))[:, 1] >= 0.5).astype(int)
        holdout_true.extend([c for _, _, c in test])
        holdout_pred.extend(pred.tolist())
        per_batch.append({'batch_code': batch['batch_code'], 'rows': len(test), 'recall': _score([c for _, _, c in test], pred)['recall']})

    evidence = {
        'method': 'RandomForestClassifier / 100 trees / max_depth 6 / balanced',
        'features': FEATURES,
        'reference_batches': [b['batch_code'] for b in batches],
        'reference_rows': len(rows),
        'defect_rows': int(y.sum()),
        'feature_importance': dict(zip(FEATURES, [round(float(v), 4) for v in model.feature_importances_])),
        'train': _score(y, in_sample_pred),
        'group_holdout': {
            'strategy': '按到货批次留一（LeaveOneGroupOut）',
            **_score(holdout_true, holdout_pred),
            'per_batch': per_batch,
        },
        'thresholds': {'defect_at_least': DEFECT_THRESHOLD, 'pass_at_most': PASS_THRESHOLD,
                       'between': 'uncertain / 主管复核'},
        'random_state': 42,
        'sha256': hashlib.sha256(raw).hexdigest(),
    }
    return model, evidence


def judge(pressure_kpa, flow_lpm):
    """返回 (缺陷概率, 自动判定)。证据不足时不代替主管下结论。"""
    model, _ = train_reference()
    probability = float(model.predict_proba([[pressure_kpa, flow_lpm]])[0, 1])
    if probability >= DEFECT_THRESHOLD:
        verdict = 'defect'
    elif probability <= PASS_THRESHOLD:
        verdict = 'pass'
    else:
        verdict = 'uncertain'
    return round(probability, 4), verdict
