import { supabase } from './supabase'

function assertQuery(result, label) {
  if (result.error) {
    throw new Error(`${label}: ${result.error.message}`)
  }
  return result.data
}

export async function fetchAccounts() {
  const accessResult = await supabase
    .from('dashboard_account_access')
    .select('account_id')
  const accessRows = assertQuery(accessResult, 'Could not load assigned accounts')
  const accountIds = [...new Set((accessRows ?? []).map((row) => row.account_id))]
  if (!accountIds.length) return []

  const accountResult = await supabase
    .from('trading_accounts')
    .select('account_id,login,server,account_type,currency,balance,auto_trading,updated_at')
    .in('account_id', accountIds)
    .order('updated_at', { ascending: false })
  const accounts = assertQuery(accountResult, 'Could not load trading accounts') ?? []
  return accounts.map((account) => ({
    ...account,
    account_id: String(account.account_id),
  }))
}

export async function fetchAccountDashboard(accountId) {
  const [tradesResult, logsResult, snapshotsResult, metricsResult, scansResult, riskResult, exposureResult, commandResult, rulesResult, reflectionsResult] = await Promise.all([
    supabase
      .from('trades')
      .select(
        'trade_id,ticket,symbol,action,volume,open_price,sl_price,tp_price,profit_loss,status,open_time,close_time,exit_reason',
      )
      .eq('account_id', accountId)
      .order('open_time', { ascending: false })
      .limit(100),
    supabase
      .from('ai_trade_logs')
      .select(
        'log_id,trade_id,symbol,timeframe,indicators_snapshot,ai_reasoning,market_session,created_at,trades!inner(symbol,action,ticket,account_id)',
      )
      .eq('trades.account_id', accountId)
      .order('created_at', { ascending: false })
      .limit(30),
    supabase
      .from('account_equity_snapshots')
      .select('balance,equity,recorded_at')
      .eq('account_id', accountId)
      .order('recorded_at', { ascending: false })
      .limit(500),
    supabase
      .from('dashboard_trade_metrics')
      .select(
        'total_trades,closed_trades,open_trades,winning_trades,realized_pnl,gross_profit,gross_loss',
      )
      .eq('account_id', accountId)
      .maybeSingle(),
    supabase
      .from('dashboard_market_scans')
      .select('symbol,timeframe,last_price,rsi,ema_trend,signal_status,reason,updated_at')
      .eq('account_id', accountId)
      .order('symbol'),
    supabase
      .from('dashboard_risk_metrics')
      .select('free_margin,margin_level,daily_drawdown_percent,max_equity_peak,daily_trade_count')
      .eq('account_id', accountId)
      .maybeSingle(),
    supabase
      .from('dashboard_symbol_exposure')
      .select('symbol,open_positions,total_volume')
      .eq('account_id', accountId)
      .order('symbol'),
    supabase
      .from('bot_commands')
      .select('command_id,command_type,status,result,created_at,processed_at')
      .eq('account_id', accountId)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from('learned_rules')
      .select('rule_id,symbol,category,rule_text,source_trade_id,confidence,supporting_trades,active,created_at,updated_at')
      .eq('account_id', accountId)
      .eq('active', true)
      .order('supporting_trades', { ascending: false })
      .order('confidence', { ascending: false })
      .order('updated_at', { ascending: false })
      .limit(100),
    supabase
      .from('trade_reflections')
      .select('trade_id,symbol,outcome,entry_price,exit_price,profit_loss,holding_seconds,original_ai_reasoning,category,lesson,status,created_at,reflected_at')
      .eq('account_id', accountId)
      .eq('status', 'completed')
      .order('reflected_at', { ascending: false })
      .limit(100),
  ])

  const trades = (assertQuery(tradesResult, 'Could not load trades') ?? []).map((trade) => ({
    ...trade,
    id: trade.trade_id,
    side: trade.action,
    stop_loss: trade.sl_price,
    take_profit: trade.tp_price,
    opened_at: trade.open_time,
    closed_at: trade.close_time,
  }))
  const aiLogs = (assertQuery(logsResult, 'Could not load AI decisions') ?? []).map((log) => ({
    ...log,
    id: log.log_id,
    indicators: log.indicators_snapshot?.indicators ?? {},
    context: log.indicators_snapshot?.context ?? {},
    reasoning: log.ai_reasoning,
    trades: log.trades
      ? { ...log.trades, side: log.trades.action }
      : null,
  }))
  const snapshots = assertQuery(snapshotsResult, 'Could not load equity history') ?? []
  const metrics = assertQuery(metricsResult, 'Could not load trade metrics')
  const scans = assertQuery(scansResult, 'Could not load live market scans') ?? []
  const riskMetrics = assertQuery(riskResult, 'Could not load account risk metrics')
  const exposure = assertQuery(exposureResult, 'Could not load symbol exposure') ?? []
  const latestCommand = assertQuery(commandResult, 'Could not load emergency command status')
  const tradeReflections = (assertQuery(
    reflectionsResult,
    'Could not load trade reflections',
  ) ?? []).map((reflection) => ({
    ...reflection,
    trade_id: String(reflection.trade_id),
  }))
  const reflectionsByTradeId = new Map(
    tradeReflections.map((reflection) => [reflection.trade_id, reflection]),
  )
  const learnedRules = (assertQuery(rulesResult, 'Could not load learned rules') ?? []).map((rule) => ({
    ...rule,
    rule_id: String(rule.rule_id),
    source_trade_id: String(rule.source_trade_id),
    source_outcome: reflectionsByTradeId.get(String(rule.source_trade_id))?.outcome ?? null,
  }))

  return {
    trades,
    aiLogs,
    learnedRules,
    tradeReflections,
    snapshots: snapshots.reverse(),
    scans,
    riskMetrics,
    exposure,
    latestCommand,
    metrics: metrics ?? {
      total_trades: 0,
      closed_trades: 0,
      open_trades: 0,
      winning_trades: 0,
      realized_pnl: 0,
      gross_profit: 0,
      gross_loss: 0,
    },
  }
}

export async function updateAutoTrading(accountId, enabled) {
  const result = await supabase
    .from('trading_accounts')
    .update({ auto_trading: enabled })
    .eq('account_id', accountId)
    .select('account_id,auto_trading')
    .single()
  return assertQuery(result, 'Could not update auto-trading setting')
}

export async function requestEmergencyCloseAll(accountId) {
  const result = await supabase.rpc('request_emergency_close_all', {
    target_account_id: accountId,
  })
  return assertQuery(result, 'Could not queue emergency close command')
}
