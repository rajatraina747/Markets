import { useEffect, useState } from 'react'
import { get } from './api'

export function useApi<T>(path: string | null): { data: T | null; error: string | null; loading: boolean } {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null, error: null, loading: !!path,
  })
  useEffect(() => {
    if (!path) { setState({ data: null, error: null, loading: false }); return }
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    get<T>(path).then(
      (data) => live && setState({ data, error: null, loading: false }),
      (e: Error) => live && setState({ data: null, error: e.message, loading: false }),
    )
    return () => { live = false }
  }, [path])
  return state
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return v
}

export function useLocal<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const s = localStorage.getItem('markets:' + key)
      return s === null ? initial : (JSON.parse(s) as T)
    } catch { return initial }
  })
  const set = (nv: T) => {
    setV(nv)
    try { localStorage.setItem('markets:' + key, JSON.stringify(nv)) } catch { /* private mode */ }
  }
  return [v, set]
}
