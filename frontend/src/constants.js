export const ROLES={admin:'运维主管',planner:'清洗计划员',viewer:'电站观察员'};
export const SURVEY_STATES={recorded:'待评估',evaluating:'评估中',assessed:'已评估',scheduled:'清洗中',retested:'已复测',closed:'已闭环',blocked:'需重试',stale:'清洗前旧读数'};
export const MISSION_STATES={draft:'待派工',dispatched:'执行中',retested:'待验收',accepted:'已验收',superseded:'旧计划已失效'};
export const BATCH_STATES={pending:'待复核放行',released:'已放行可领用',void:'已撤销放行'};
export const UNIT_STATES={pending:'证据不足待复核',rejected:'模型判缺陷',in_stock:'在库可领用',issued:'已领出',installed:'已装用',recall_required:'需召回',quarantined:'隔离库存待核清',scrapped:'已报废',voided:'封存不发放'};
export const RETURN_STATES={pending_resolution:'待核清去向',restocked:'已回库',scrapped:'已报废待补发'};
