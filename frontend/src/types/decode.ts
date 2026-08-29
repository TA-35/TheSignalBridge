// Define response type: Mirrors docs/api-contract.md POST /api/decode.

export type ElementKey = 'time' | 'task' | 'deadline' | 'for_whom'

export const ELEMENT_LABELS: Record<ElementKey, string> = {
  time: 'Time',
  task: 'Task-To-Do',
  deadline: 'Deadline',
  for_whom: 'For whom',
}

export const NOT_SPECIFIED = 'Not specified'

export interface MissingElement {
  field: ElementKey
  prompt: string
}

export interface DecodeResult {
  elements: Record<ElementKey, string>
  covered: ElementKey[]
  missing: MissingElement[]
  category: string | null
}
