import { useState } from 'react'
import { AlertTriangle, Power, ShieldAlert } from 'lucide-react'
import { requestEmergencyCloseAll, updateAutoTrading } from '../lib/dashboardData'

export default function BotControls({
  account,
  latestCommand,
  onAccountUpdated,
  onRefresh,
}) {
  const [dialog, setDialog] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const demoAccount = account.account_type?.toLowerCase() === 'demo'

  async function confirmAction() {
    if (!dialog || busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      if (dialog === 'enable' || dialog === 'disable') {
        const updated = await updateAutoTrading(account.account_id, dialog === 'enable')
        onAccountUpdated(updated)
        setNotice(`Auto-trading ${updated.auto_trading ? 'enabled' : 'disabled'} for this account.`)
      } else {
        const commandId = await requestEmergencyCloseAll(account.account_id)
        onAccountUpdated({
          account_id: account.account_id,
          auto_trading: false,
        })
        setNotice(`Emergency close queued (command #${commandId}). Auto-trading has been disabled.`)
        await onRefresh()
      }
      setDialog(null)
    } catch (actionError) {
      setError(actionError.message)
    } finally {
      setBusy(false)
    }
  }

  const autoTradingEnabled = account.auto_trading === true

  return (
    <section className="rounded-2xl border border-[#202c32] bg-[#10171b] p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[#604040] bg-[#302020] text-[#ffaaa0]">
            <ShieldAlert size={17} />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-[#e8efec]">Bot controls</h2>
            <p className="mt-1 max-w-2xl text-[10px] leading-5 text-[#78888d]">
              Account switch is an additional gate. The engine environment gate must also be enabled; trade actions are restricted to Demo accounts.
            </p>
            {!demoAccount && (
              <p className="mt-1 text-[10px] font-medium text-[#ff988a]">
                Controls are locked because this account is not marked Demo.
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            aria-checked={autoTradingEnabled}
            className={`inline-flex h-10 items-center gap-2 rounded-xl border px-3 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
              autoTradingEnabled
                ? 'border-[#4b673c] bg-[#20301d] text-[#c4f18f]'
                : 'border-[#344047] bg-[#182126] text-[#a7b3b4]'
            }`}
            disabled={!demoAccount}
            onClick={() => setDialog(autoTradingEnabled ? 'disable' : 'enable')}
            role="switch"
            type="button"
          >
            <Power size={14} />
            Auto-trading {autoTradingEnabled ? 'On' : 'Off'}
            <span className={`h-2 w-2 rounded-full ${autoTradingEnabled ? 'bg-[#b6f36b]' : 'bg-[#728187]'}`} />
          </button>
          <button
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-[#704040] bg-[#351f20] px-3 text-xs font-semibold text-[#ffaaa0] transition hover:bg-[#452526] disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!demoAccount}
            onClick={() => setDialog('close_all')}
            type="button"
          >
            <AlertTriangle size={14} /> Emergency stop &amp; close all
          </button>
        </div>
      </div>

      {(notice || error) && (
        <p className={`mt-4 rounded-lg border px-3 py-2 text-[10px] ${error ? 'border-[#604040] bg-[#302020] text-[#ffaaa0]' : 'border-[#344b36] bg-[#19251a] text-[#b7ed83]'}`}>
          {error || notice}
        </p>
      )}
      {latestCommand && (
        <p className="mt-3 text-[10px] text-[#7d8d90]">
          Latest emergency command: <span className="font-semibold uppercase text-[#b7c3c0]">{latestCommand.status}</span>
          {latestCommand.result && <span> · {latestCommand.result}</span>}
        </p>
      )}

      {dialog && (
        <div
          aria-labelledby="bot-control-title"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#05080b]/80 p-4 backdrop-blur-sm"
          role="dialog"
        >
          <div className="w-full max-w-md rounded-2xl border border-[#3b4548] bg-[#11191d] p-5 shadow-2xl">
            <div className="flex items-start gap-3">
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${dialog === 'close_all' ? 'bg-[#351f20] text-[#ffaaa0]' : 'bg-[#242117] text-[#e2bd72]'}`}>
                {dialog === 'close_all' ? <AlertTriangle size={17} /> : <Power size={17} />}
              </span>
              <div>
                <h3 className="text-sm font-semibold text-[#e8efec]" id="bot-control-title">
                  {dialog === 'close_all'
                    ? 'Emergency stop and close all?'
                    : `Turn auto-trading ${dialog === 'enable' ? 'on' : 'off'}?`}
                </h3>
                <p className="mt-2 text-xs leading-6 text-[#9aa8a8]">
                  {dialog === 'close_all'
                    ? `This immediately disables new entries and queues the MT5 engine to close every position on Demo account #${account.login}. It will not execute from this browser.`
                    : dialog === 'enable'
                      ? 'The engine may open new positions after this change only if its server-side environment gate is also enabled.'
                      : 'The engine will stop opening new positions. Existing positions are not closed by this action.'}
                </p>
                {dialog === 'close_all' && (
                  <p className="mt-3 rounded-lg border border-[#674142] bg-[#2d1d1d] px-3 py-2 text-[10px] leading-5 text-[#ffb8ad]">
                    Closing at market can realize a loss and execution depends on the MT5 terminal and broker connectivity.
                  </p>
                )}
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                className="h-9 rounded-lg border border-[#344047] px-3 text-xs font-medium text-[#aab7b7] hover:bg-[#1b2529] disabled:opacity-50"
                disabled={busy}
                onClick={() => setDialog(null)}
                type="button"
              >
                Cancel
              </button>
              <button
                className={`h-9 rounded-lg px-3 text-xs font-semibold disabled:opacity-50 ${dialog === 'close_all' ? 'bg-[#c45e54] text-white hover:bg-[#d36e64]' : 'bg-[#b6f36b] text-[#10170c] hover:bg-[#c8ff82]'}`}
                disabled={busy}
                onClick={confirmAction}
                type="button"
              >
                {busy ? 'Working…' : dialog === 'close_all' ? 'Disable & queue close' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
