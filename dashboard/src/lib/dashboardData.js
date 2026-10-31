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
    .select('id,login,server,balance,updated_at')
    .in('id', accountIds)
    .order('updated_at', { ascending: false })
  return assertQuery(accountResult, 'Could not load trading accounts') ?? []
}

export async function fetchAccountDashboard(accountId) {
  const [tradesResult, logsResult, snapshotsResult, metricsResult] = await Promise.all([
    supabase
      .from('trades')
      .select(
        'id,ticket,symbol,side,volume,open_price,stop_loss,take_profit,profit_loss,status,opened_at,closed_at,exit_reason,context',
      )
      .eq('account_id', accountId)
      .order('opened_at', { ascending: false })
      .limit(100),
    supabase
      .from('ai_trade_logs')
      .select(
        'id,trade_id,indicators,reasoning,context,timeframe,created_at,trades!inner(symbol,side,ticket,account_id)',
      )
      .eq('trades.account_id', accountId)
      .order('created_at', { ascending: false })
      .limit(30),
    supabase
      .from('account_equity_snapshots')
      .select('balance,equity,margin,free_margin,captured_at')
      .eq('account_id', accountId)
      .order('captured_at', { ascending: false })
      .limit(500),
    supabase
      .from('dashboard_trade_metrics')
      .select(
        'total_trades,closed_trades,open_trades,winning_trades,realized_pnl,gross_profit,gross_loss',
      )
      .eq('account_id', accountId)
      .maybeSingle(),
  ])

  const trades = assertQuery(tradesResult, 'Could not load trades') ?? []
  const aiLogs = assertQuery(logsResult, 'Could not load AI decisions') ?? []
  const snapshots = assertQuery(snapshotsResult, 'Could not load equity history') ?? []
  const metrics = assertQuery(metricsResult, 'Could not load trade metrics')

  return {
    trades,
    aiLogs,
    snapshots: snapshots.reverse(),
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
