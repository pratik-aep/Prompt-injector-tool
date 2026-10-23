import { useCallback, useEffect, useRef, useState } from 'react'

/** Load data on mount / when deps change; exposes reload and a polling option. Errors are surfaced, never swallowed. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs?: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const d = await fnRef.current()
      if (alive.current) { setData(d); setError(null) }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, deps)
  useEffect(() => {
    if (!pollMs) return
    const t = setInterval(() => load(true), pollMs)
    return () => clearInterval(t)
  }, [pollMs, load])
  return { data, error, loading, reload: load, setData }
}
