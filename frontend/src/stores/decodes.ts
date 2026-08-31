import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import type { DecodeRecord, DecodeResult, ElementKey } from '@/types/decode'

const STORAGE_KEY = 'readtheroom.decodes'

// Bounded so a long history can't fill the origin's localStorage quota.
// Oldest decodes fall off the end.
const MAX_RECORDS = 100

function load(): DecodeRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as DecodeRecord[]) : []
  } catch {
    return []
  }
}

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `d_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
}

// Decodes the user has run. Message text is written to disk here and nowhere
// else - it is never sent anywhere, and Settings' "clear" wipes it. See the
// data-retention note in docs/api-contract.md.
export const useDecodesStore = defineStore('decodes', () => {
  const records = ref<DecodeRecord[]>(load())

  watch(
    records,
    (value) => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
      } catch {
        // Quota or a privacy mode that blocks writes: keep the session's
        // records in memory rather than breaking the decode flow.
      }
    },
    { deep: true },
  )

  const latest = computed(() => records.value[0] ?? null)

  // How often each element goes unstated across the history. This is the
  // signal a study plan would order by - counts only, no message text.
  const gapCounts = computed(() => {
    const counts: Record<string, number> = {}
    for (const record of records.value) {
      for (const gap of record.missing) {
        counts[gap.field] = (counts[gap.field] ?? 0) + 1
      }
    }
    return counts
  })

  function save(message: string, result: DecodeResult, patternId: string | null): DecodeRecord {
    const record: DecodeRecord = {
      id: newId(),
      createdAt: new Date().toISOString(),
      message,
      tasks: result.tasks ?? [],
      elements: result.elements,
      missing: result.missing,
      asked: [],
      category: result.category,
      patternId,
    }
    records.value.unshift(record)
    if (records.value.length > MAX_RECORDS) {
      records.value = records.value.slice(0, MAX_RECORDS)
    }
    return record
  }

  // The gaps the user ticked - which questions they judged worth asking.
  function setAsked(id: string, asked: ElementKey[]) {
    const record = records.value.find((r) => r.id === id)
    if (record) record.asked = [...asked]
  }

  function find(id: string) {
    return records.value.find((r) => r.id === id) ?? null
  }

  function clear() {
    records.value = []
  }

  return { records, latest, gapCounts, save, setAsked, find, clear }
})
