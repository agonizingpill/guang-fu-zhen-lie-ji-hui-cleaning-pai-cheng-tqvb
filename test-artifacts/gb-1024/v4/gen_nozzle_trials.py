"""生成喷嘴试喷参考数据（固定 seed，模拟数据，非真实出厂记录）。

确认批次：24 件/批，缺陷件全部表现为“压力正常但流量偏低”，
少量缺陷件因供水压力不足同时呈现低压；另有约10%合格件落在
压力/流量边界附近，用于验证证据不足时的主管复核。

到货批次：NZ-2605 12件（3件缺陷）、NZ-2606 8件（2件明显缺陷
+1件边界读数）。到货批次不参与训练，只用于运行时判定。
"""
import json
import random
from pathlib import Path

rnd = random.Random(4211)


def good():
    if rnd.random() < 0.1:
        return {"pressure_kpa": round(rnd.uniform(240, 266), 1),
                "flow_lpm": round(rnd.uniform(2.88, 3.16), 2)}
    return {"pressure_kpa": round(rnd.uniform(255, 345), 1),
            "flow_lpm": round(rnd.uniform(3.32, 4.9), 2)}


def bad():
    return {"pressure_kpa": round(rnd.uniform(252, 340), 1),
            "flow_lpm": round(rnd.uniform(1.15, 2.55), 2)}


def confirmed(code, model, quantity, bad_count, arrival):
    picks = list(range(1, quantity + 1))
    rnd.shuffle(picks)
    badset = set(picks[:bad_count])
    trials = []
    for i in range(1, quantity + 1):
        row = bad() if i in badset else good()
        trials.append({"serial": f"{code}-{i:02d}", **row,
                       "verdict": "bad" if i in badset else "good"})
    return {"batch_code": code, "nozzle_model": model, "quantity": quantity,
            "arrival_date": arrival, "trials": trials}


def arrival(code, model, quantity, date, defects, gray=None):
    trials = []
    for i in range(1, quantity + 1):
        if gray and i == gray[0]:
            row = {"pressure_kpa": gray[1], "flow_lpm": gray[2]}
        elif i in defects:
            row = bad()
        else:
            row = good()
        trials.append({"serial": f"{code}-{i:02d}", **row})
    return {"batch_code": code, "nozzle_model": model, "quantity": quantity,
            "arrival_date": date, "trials": trials}


data = {
    "note": "模拟试喷记录；confirmed_batches 为已确认好坏的历史批次，arrivals 为待判定到货批次。",
    "generated_seed": 4211,
    "confirmed_batches": [
        confirmed("NZ-2601", "NL-SF-15 扇形喷嘴", 24, 8, "2026-10-06"),
        confirmed("NZ-2602", "NL-SF-15 扇形喷嘴", 24, 7, "2026-10-18"),
        confirmed("NZ-2603", "NL-TJ-08 锥形喷嘴", 24, 8, "2026-11-02"),
        confirmed("NZ-2604", "NL-TJ-08 锥形喷嘴", 24, 8, "2026-11-10"),
    ],
    "arrivals": [
        arrival("NZ-2605", "NL-SF-15 扇形喷嘴", 12, "2026-11-16", {3, 7, 10}),
        arrival("NZ-2606", "NL-SF-15 扇形喷嘴", 8, "2026-11-19", {2, 4}, gray=(6, 300.0, 2.8)),
    ],
}
target = Path('/workspace/backend/fixtures/nozzle_trials.json')
target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
print('wrote', target, 'confirmed', sum(len(b['trials']) for b in data['confirmed_batches']),
      'arrivals', sum(len(b['trials']) for b in data['arrivals']))
