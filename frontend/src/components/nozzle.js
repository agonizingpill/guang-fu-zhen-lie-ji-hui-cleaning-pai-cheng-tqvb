import {field} from '../store.js';
import {safe,fixed} from '../utils.js';
import {BATCH_STATES,UNIT_STATES,RETURN_STATES} from '../constants.js';

export const batchState=value=>BATCH_STATES[value]||value;
export const unitState=value=>UNIT_STATES[value]||value;
export const returnState=value=>RETURN_STATES[value]||value;

export const batchOf=id=>field.nozzleBatches.find(b=>b.id===id);
export const unitOf=id=>field.nozzleUnits.find(u=>u.id===id);
export function missionText(id){const m=field.missions.find(m=>m.id===id);return m?`WASH-${m.id}`:`任务${id}`;}
export function batchOption(b){
  const stock=field.nozzleUnits.filter(u=>u.batch_id===b.id&&u.status==='in_stock').length;
  return safe(b.batch_code)+' · '+safe(b.nozzle_model)+' · 在库'+stock+'件';
}
export function batchOptions(selected){return field.nozzleBatches.filter(b=>b.state==='released').map(b=>`<option value="${b.id}" ${b.id===selected?'selected':''}>${batchOption(b)}</option>`).join('');}
export function unitLabel(u){return `${safe(u.serial)}${u.installed?'（已装用）':''}`;}
export function probabilityText(u){return u.defect_probability==null?'—':fixed(u.defect_probability*100,0)+'%';}
export function batchEvidence(b){
  if(!b.evidence)return '<p class="note">尚无判定依据。</p>';
  const ev=b.evidence;
  const rows=`模型判可用 ${ev.pass_units??'—'} 件 · 判缺陷 ${ev.defect_units??'—'} 件 · 证据不足转复核 ${ev.uncertain_units??'—'} 件`;
  return `<p class="note">${rows}<br>试喷记录 ${ev.trial_rows??'—'} 条${ev.trials_sha256?' · 归因哈希 '+safe(String(ev.trials_sha256).slice(0,12)):''}</p>`;
}
export function unitTable(units){
  if(!units.length)return '<div class="empty">该批次没有单件记录</div>';
  return `<div class="tablewrap"><table><thead><tr><th>喷嘴编号</th><th>压力 kPa</th><th>流量 L/min</th><th>缺陷概率</th><th>判定</th><th>复核/领用去向</th></tr></thead><tbody>${units.map(u=>`<tr><td>${safe(u.serial)}</td><td>${fixed(u.pressure_kpa,1)}</td><td>${fixed(u.flow_lpm,2)}</td><td>${probabilityText(u)}</td><td>${safe(unitState(u.status))}${u.reviewed_by?'<br><span class="note">'+safe(u.reviewed_by)+'</span>':''}${u.review_note?'<br><span class="note">'+safe(u.review_note)+'</span>':''}</td><td>${u.issue_id?'领用单 #'+u.issue_id:'—'}${u.mission_id?'<br><span class="note">'+missionText(u.mission_id)+'</span>':''}</td></tr>`).join('')}</tbody></table></div>`;
}
export function issueHistory(){
  if(!field.nozzleIssues.length)return '<div class="empty">尚未领用喷嘴</div>';
  return field.nozzleIssues.map(i=>{
    const units=field.nozzleUnits.filter(u=>u.issue_id===i.id);
    const returns=field.nozzleReturns.filter(r=>r.issue_id===i.id);
    return `<article class="surface nozzle-card"><span class="code">领用 #${i.id} · PERMIT-${i.permit_id} · ${missionText(i.mission_id)}</span><h3>${safe(batchOf(i.batch_id)?.batch_code||'批次'+i.batch_id)} · ${i.quantity} 件</h3><p class="note">领用人 ${safe(i.issued_by)} · 请求号 ${safe(i.request_id)}</p><p class="note">逐件去向：${units.map(u=>unitLabel(u)+' → '+safe(unitState(u.status))).join('；')||'—'}</p>${returns.length?`<p class="note">退回：${returns.map(r=>safe(unitLabel(unitOf(r.unit_id)))+' / '+(r.kind==='installed'?'已装用':'未装')+' / '+safe(returnState(r.state))).join('；')}</p>`:''}</article>`;
  }).join('');
}
export function returnOptions(missionId){
  const issueIds=field.nozzleIssues.filter(i=>!missionId||i.mission_id===missionId).map(i=>i.id);
  return field.nozzleUnits.filter(u=>issueIds.includes(u.issue_id)&&['issued','recall_required'].includes(u.status)&&!field.nozzleReturns.some(r=>r.unit_id===u.id));
}
export const newRequestId=prefix=>prefix+'-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,7);
// 请求号在渲染时固定：页面重试沿用同一号，成功后重渲染才换新号，断线重试不会重复入库或补发。
export const requestField=prefix=>`<input type="hidden" name="request_id" value="${newRequestId(prefix)}">`;
