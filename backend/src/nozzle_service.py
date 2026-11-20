import hashlib
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import WashMission
from .operations_models import WorkPermit
from .nozzle_models import (NozzleBatch, NozzleUnit, NozzleIssue,
                            NozzleReturn, NozzleReplacement)
from .field_service import require, audit
from .nozzle_model import judge, train_reference


def _replay(db, model, request_id):
    return db.scalar(select(model).where(model.request_id == request_id))


def _commit_once(db, model, request_id):
    """断线重试不重复入库/补发：同一请求号返回首次结果。"""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _replay(db, model, request_id)
        if existing:
            return existing
        raise


def create_batch(db, body, user):
    batch_code = body.batch_code.strip()
    if db.scalar(select(NozzleBatch).where(NozzleBatch.batch_code == batch_code)):
        raise HTTPException(409, '到货批次编号已存在')
    if len(body.trials) != body.quantity:
        raise HTTPException(409, f'试喷记录须覆盖全部{body.quantity}件喷嘴')
    serials = [t.serial.strip() for t in body.trials]
    if len(set(serials)) != len(serials):
        raise HTTPException(409, '同一批次内喷嘴编号重复')
    for serial in serials:
        if db.scalar(select(NozzleUnit).where(NozzleUnit.serial == serial)):
            raise HTTPException(409, f'喷嘴编号{serial}已登记')
    train_reference()
    batch = NozzleBatch(batch_code=batch_code, nozzle_model=body.nozzle_model.strip(),
                        quantity=body.quantity, arrival_date=body.arrival_date, state='pending')
    db.add(batch)
    db.flush()
    counts = {'pass': 0, 'defect': 0, 'uncertain': 0}
    for trial in body.trials:
        probability, verdict = judge(trial.pressure_kpa, trial.flow_lpm)
        counts[verdict] += 1
        status = {'pass': 'in_stock', 'defect': 'rejected', 'uncertain': 'pending'}[verdict]
        db.add(NozzleUnit(batch_id=batch.id, serial=trial.serial.strip(),
                          pressure_kpa=trial.pressure_kpa, flow_lpm=trial.flow_lpm,
                          defect_probability=probability, model_verdict=verdict, status=status))
    batch.evidence = {
        'nozzle_model': body.nozzle_model,
        'trial_rows': len(body.trials),
        'pass_units': counts['pass'],
        'defect_units': counts['defect'],
        'uncertain_units': counts['uncertain'],
        'judged_at': datetime.utcnow().isoformat() + 'Z',
        'trials_sha256': hashlib.sha256(json.dumps(
            [t.model_dump() for t in body.trials], sort_keys=True,
            ensure_ascii=False, default=str).encode()).hexdigest(),
    }
    audit(db, user, f'登记喷嘴到货批次 {batch.batch_code}，{body.quantity}件，'
                    f'模型判缺陷{counts["defect"]}件，待复核{counts["uncertain"]}件')
    db.commit()
    return batch


def review_unit(db, key, body, user):
    unit = require(db, NozzleUnit, key, True)
    batch = require(db, NozzleBatch, unit.batch_id, True)
    if batch.state == 'void':
        raise HTTPException(409, '批次已撤销放行，不能再复核')
    if batch.state == 'released':
        raise HTTPException(409, '批次已放行，复核结论已冻结')
    if unit.model_verdict != 'uncertain':
        raise HTTPException(409, '仅模型证据不足的喷嘴需要主管复核')
    if unit.status != 'pending':
        raise HTTPException(409, '该喷嘴已复核，不能重复处置')
    unit.review_decision = body.decision
    unit.review_note = body.note.strip()
    unit.reviewed_by = user.email
    unit.status = 'in_stock' if body.decision == 'pass' else 'rejected'
    audit(db, user, f'复核喷嘴 {unit.serial} 为{"可用" if body.decision == "pass" else "缺陷"}')
    db.commit()
    return unit


def release(db, key, user):
    batch = require(db, NozzleBatch, key, True)
    if batch.state == 'void':
        raise HTTPException(409, '批次已撤销放行，须重新到货登记')
    if batch.state == 'released':
        raise HTTPException(409, '批次已放行，不可重复放行')
    pending = db.scalar(select(NozzleUnit).where(
        NozzleUnit.batch_id == batch.id, NozzleUnit.status == 'pending').limit(1))
    if pending:
        raise HTTPException(409, '仍有证据不足的喷嘴未经主管复核，暂不能放行')
    stock = db.scalar(select(NozzleUnit).where(
        NozzleUnit.batch_id == batch.id, NozzleUnit.status == 'in_stock').limit(1))
    if not stock:
        raise HTTPException(409, '该批次没有可放行入库的喷嘴')
    batch.state = 'released'
    batch.released_by = user.email
    batch.released_at = datetime.utcnow()
    audit(db, user, f'放行喷嘴批次 {batch.batch_code}')
    db.commit()
    return batch


def void_release(db, key, body, user):
    # 与领用/派工共用同一把批次行锁：谁先提交谁生效。
    batch = require(db, NozzleBatch, key, True)
    if batch.state == 'void':
        raise HTTPException(409, '该批次已撤销放行')
    if batch.state != 'released':
        raise HTTPException(409, '仅已放行批次可撤销放行')
    batch.state = 'void'
    batch.voided_by = user.email
    batch.voided_at = datetime.utcnow()
    batch.void_reason = body.reason.strip()
    # 撤销与派工/领用同锁批次行：先撤销则后续领用被拦，已领出的逐件召回。
    units = db.scalars(select(NozzleUnit).where(
        NozzleUnit.batch_id == batch.id).order_by(NozzleUnit.id).with_for_update().execution_options(
        populate_existing=True)).all()
    recalled = sealed = 0
    for unit in units:
        if unit.status == 'in_stock':
            # 已在库未领出的封存件不再发放，与现场退回的隔离件分开标识。
            unit.status = 'voided'
            sealed += 1
        elif unit.status == 'issued':
            unit.status = 'recall_required'
            recalled += 1
    audit(db, user, f'撤销放行批次 {batch.batch_code}，待召回{recalled}件，封存在库{sealed}件，'
                    f'原因{body.reason.strip()}')
    db.commit()
    return batch


def _select_batch(db, batch_id=None):
    """锁读放行批次；与撤销放行共用批次行锁，先撤销则领用被拦。"""
    if batch_id is not None:
        # require(lock=True) 用 FOR UPDATE + populate_existing，锁内读到的是已提交最新状态。
        batch = require(db, NozzleBatch, batch_id, True)
        if batch.state == 'void':
            raise HTTPException(409, '批次已撤销放行，不能领用或补发')
        if batch.state != 'released':
            raise HTTPException(409, '批次尚未放行')
        return batch
    batches = db.scalars(select(NozzleBatch).where(NozzleBatch.state == 'released')
                         .order_by(NozzleBatch.id).with_for_update().execution_options(
                             populate_existing=True)).all()
    for batch in batches:
        if db.scalar(select(NozzleUnit).where(
                NozzleUnit.batch_id == batch.id, NozzleUnit.status == 'in_stock').limit(1)):
            return batch
    raise HTTPException(409, '暂无已放行且有库存的喷嘴批次')


def _pick_units(db, batch, quantity):
    units = db.scalars(select(NozzleUnit).where(
        NozzleUnit.batch_id == batch.id, NozzleUnit.status == 'in_stock'
    ).order_by(NozzleUnit.id).limit(quantity).with_for_update().execution_options(
        populate_existing=True)).all()
    if len(units) < quantity:
        raise HTTPException(409, f'批次{batch.batch_code}可领用喷嘴仅{len(units)}件，不足{quantity}件')
    return units


def issue(db, body, user):
    existing = _replay(db, NozzleIssue, body.request_id)
    if existing:
        return existing
    # 与派工保持同一把锁顺序：任务 → 许可 → 批次，避免与撤销放行/派工交叉死锁。
    permit_ref = require(db, WorkPermit, body.permit_id)
    mission = require(db, WashMission, permit_ref.mission_id, True)
    permit = require(db, WorkPermit, body.permit_id, True)
    # 许可签发后可随派工领用：派工前或派工后都可领，验收后不再发放。
    if permit.state not in ('signed', 'used'):
        raise HTTPException(409, '仅已签发许可可以领用喷嘴')
    if mission.status not in ('draft', 'dispatched', 'retested'):
        raise HTTPException(409, '任务已验收，不能再领用喷嘴')
    batch = _select_batch(db, body.batch_id)
    units = _pick_units(db, batch, body.quantity)
    row = NozzleIssue(permit_id=permit.id, mission_id=mission.id, batch_id=batch.id,
                      quantity=body.quantity, request_id=body.request_id, issued_by=user.email)
    db.add(row)
    db.flush()
    for unit in units:
        unit.status = 'issued'
        unit.issue_id = row.id
        unit.permit_id = permit.id
        unit.mission_id = mission.id
    audit(db, user, f'许可{permit.id}领用喷嘴{body.quantity}件 批次{batch.batch_code}')
    return _commit_once(db, NozzleIssue, body.request_id) or row


def dispatch_guard(db, mission, permit):
    """派工时确认许可下已领喷嘴仍可用；撤销与派工并发以先提交者为准。"""
    units = db.scalars(select(NozzleUnit).where(
        NozzleUnit.permit_id == permit.id
    ).order_by(NozzleUnit.id)).all()
    for unit in units:
        batch = require(db, NozzleBatch, unit.batch_id, True)
        if unit.status in ('issued', 'recall_required') and batch.state != 'released':
            raise HTTPException(409, '喷嘴批次已撤销放行，本任务领用件须召回后再派工')
    if any(u.status == 'recall_required' for u in units):
        raise HTTPException(409, '本任务有喷嘴需召回，请先清点退库')
    # 已领用过的许可，召回件全部退清后须从放行批次重新领用，不能空手派工。
    history = db.scalar(select(NozzleIssue).where(NozzleIssue.permit_id == permit.id).limit(1))
    if history and not any(u.status == 'issued' for u in units):
        raise HTTPException(409, '本任务喷嘴已全部召回，须从放行批次重新领用后再派工')


def _lock_unit(db, unit_id):
    """统一按批次→单件顺序加锁，避免与撤销放行交叉死锁。"""
    unit_ref = require(db, NozzleUnit, unit_id)
    require(db, NozzleBatch, unit_ref.batch_id, True)
    return require(db, NozzleUnit, unit_id, True)


def record_return(db, body, user):
    existing = _replay(db, NozzleReturn, body.request_id)
    if existing:
        return existing
    unit = _lock_unit(db, body.unit_id)
    if unit.status not in ('issued', 'recall_required'):
        raise HTTPException(409, '仅已领出或待召回的喷嘴可以清点退回')
    if not unit.issue_id:
        raise HTTPException(409, '该喷嘴没有领用记录，不能退回')
    if unit.installed and body.kind == 'uninstalled':
        raise HTTPException(409, '该喷嘴已登记装用，不能按未装退回清点')
    if body.kind == 'installed':
        unit.installed = True
    item = NozzleReturn(unit_id=unit.id, issue_id=unit.issue_id, kind=body.kind,
                        note=body.note.strip(), request_id=body.request_id,
                        recorded_by=user.email, state='pending_resolution')
    # 未装退回与已装用退回都先隔离，去向核清前不可补发。
    unit.status = 'quarantined'
    db.add(item)
    audit(db, user, f'清点退回喷嘴 {unit.serial}（{"未装" if body.kind == "uninstalled" else "已装用"}），'
                    f'转隔离库存')
    return _commit_once(db, NozzleReturn, body.request_id) or item


def resolve_return(db, key, body, user):
    item = require(db, NozzleReturn, key, True)
    if item.state != 'pending_resolution':
        raise HTTPException(409, '该退回件去向已核清，不能重复处置')
    unit = _lock_unit(db, item.unit_id)
    if body.disposition == 'restock':
        batch = require(db, NozzleBatch, unit.batch_id, True)
        if batch.state != 'released':
            raise HTTPException(409, '所属批次未放行或已撤销，退回件只能报废，不能回库')
        unit.status = 'in_stock'
        item.state = 'restocked'
    else:
        unit.status = 'scrapped'
        item.state = 'scrapped'
    item.resolution = body.resolution.strip()
    item.resolved_by = user.email
    item.resolved_at = datetime.utcnow()
    audit(db, user, f'核清退回喷嘴 {unit.serial} 去向：{"回库" if body.disposition == "restock" else "报废"}')
    db.commit()
    return item


def replacement(db, body, user):
    existing = _replay(db, NozzleReplacement, body.request_id)
    if existing:
        return existing
    item = require(db, NozzleReturn, body.return_id, True)
    if item.state != 'scrapped':
        raise HTTPException(409, '退回件去向未核清或已回库，不能补发')
    if item.kind != 'installed':
        raise HTTPException(409, '仅已装用件报废后需现场补发')
    if db.scalar(select(NozzleReplacement).where(NozzleReplacement.return_id == item.id)):
        raise HTTPException(409, '该退回件已补发，不能重复补发')
    issue = require(db, NozzleIssue, item.issue_id)
    # 原批次被撤销放行时，可指定其他已放行批次补发。
    batch = _select_batch(db, body.batch_id or issue.batch_id)
    units = _pick_units(db, batch, body.quantity)
    row = NozzleReplacement(return_id=item.id, unit_id=units[0].id, batch_id=batch.id,
                            mission_id=issue.mission_id, permit_id=issue.permit_id,
                            quantity=body.quantity, request_id=body.request_id, issued_by=user.email)
    db.add(row)
    db.flush()
    for new_unit in units:
        new_unit.status = 'issued'
        new_unit.permit_id = issue.permit_id
        new_unit.mission_id = issue.mission_id
    audit(db, user, f'补发喷嘴{body.quantity}件 退回件{item.id} 批次{batch.batch_code}')
    return _commit_once(db, NozzleReplacement, body.request_id) or row


def ledger(db):
    return {
        'batches': db.scalars(select(NozzleBatch).order_by(NozzleBatch.id.desc())).all(),
        'units': db.scalars(select(NozzleUnit).order_by(NozzleUnit.id)).all(),
        'issues': db.scalars(select(NozzleIssue).order_by(NozzleIssue.id.desc())).all(),
        'returns': db.scalars(select(NozzleReturn).order_by(NozzleReturn.id.desc())).all(),
        'replacements': db.scalars(select(NozzleReplacement).order_by(NozzleReplacement.id.desc())).all(),
    }
