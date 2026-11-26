/* Small IndexedDB wrapper for offline snapshots and the future answer queue. */
const DB_NAME = 'pli-offline'
const VERSION = 1
const KV = 'kv'
const QUEUE = 'answerQueue'

let dbPromise: Promise<IDBDatabase> | null = null

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) {
      reject(new Error('IndexedDB tidak tersedia'))
      return
    }
    const request = indexedDB.open(DB_NAME, VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(KV)) db.createObjectStore(KV)
      if (!db.objectStoreNames.contains(QUEUE)) {
        const store = db.createObjectStore(QUEUE, { keyPath: 'id' })
        store.createIndex('createdAt', 'createdAt')
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Gagal membuka IndexedDB'))
  })
  return dbPromise
}

function fallbackKey(key: string): string {
  return `pli_offline_${key}`
}

export async function kvSet<T>(key: string, value: T): Promise<void> {
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(KV, 'readwrite')
      tx.objectStore(KV).put(value, key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    localStorage.setItem(fallbackKey(key), JSON.stringify(value))
  }
}

export async function kvGet<T>(key: string): Promise<T | null> {
  try {
    const db = await openDb()
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(KV, 'readonly')
      const request = tx.objectStore(KV).get(key)
      request.onsuccess = () => resolve((request.result as T) ?? null)
      request.onerror = () => reject(request.error)
    })
  } catch {
    const raw = localStorage.getItem(fallbackKey(key))
    return raw ? (JSON.parse(raw) as T) : null
  }
}

export interface QueuedAnswer {
  id: string
  attemptId: string
  questionId: string
  answer: unknown
  createdAt: string
  /** Fase 2 sync fields. Older queue entries remain readable. */
  clientId?: string
  clientUpdatedAt?: string
  timeSpentSec?: number
  changedCount?: number
}

export async function enqueueAnswer(item: QueuedAnswer): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(QUEUE, 'readwrite')
    tx.objectStore(QUEUE).put(item)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function queuedAnswers(): Promise<QueuedAnswer[]> {
  try {
    const db = await openDb()
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(QUEUE, 'readonly')
      const request = tx.objectStore(QUEUE).getAll()
      request.onsuccess = () => resolve(request.result as QueuedAnswer[])
      request.onerror = () => reject(request.error)
    })
  } catch {
    return []
  }
}

export async function clearQueuedAnswer(id: string): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(QUEUE, 'readwrite')
    tx.objectStore(QUEUE).delete(id)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}
