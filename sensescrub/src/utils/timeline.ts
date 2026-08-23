import type { EditorClip } from '../types'

/** A clip annotated with its percentage offset and width within the timeline. */
export interface ClipOffset {
  clip: EditorClip
  index: number
  /** Left offset as a percentage of total timeline width (0–100). */
  leftPct: number
  /** Width as a percentage of total timeline width (0–100). */
  widthPct: number
}

/**
 * Sum of all clip durations. Returns 0 for empty array — never NaN.
 */
export function totalDuration(clips: EditorClip[]): number {
  return clips.reduce((sum, c) => sum + Math.max(0, c.end_time - c.start_time), 0)
}

/**
 * Convert a time value to a pixel offset within a container of widthPx.
 * Clamps to [0, widthPx].
 */
export function timeToPixel(time: number, total: number, widthPx: number): number {
  if (total <= 0 || widthPx <= 0) return 0
  return Math.max(0, Math.min(widthPx, (time / total) * widthPx))
}

/**
 * Convert a pixel offset within a container of widthPx back to a time value.
 * Clamps to [0, total].
 */
export function pixelToTime(px: number, total: number, widthPx: number): number {
  if (total <= 0 || widthPx <= 0) return 0
  return Math.max(0, Math.min(total, (px / widthPx) * total))
}

/**
 * Convert a raw footage timestamp to assembled trailer time.
 * Returns the position within the assembled trailer (0 → totalDuration).
 * If rawTime falls outside all clips, returns the nearest clip boundary.
 */
export function rawToAssembled(rawTime: number, clips: EditorClip[]): number {
  let cursor = 0
  for (const clip of clips) {
    const dur = Math.max(0, clip.end_time - clip.start_time)
    if (rawTime <= clip.start_time) return cursor
    if (rawTime < clip.end_time)    return cursor + (rawTime - clip.start_time)
    cursor += dur
  }
  return cursor  // past all clips → end of assembled trailer
}

/**
 * Convert an assembled trailer time to a raw footage seek target.
 * Returns the raw footage timestamp to seek to.
 */
export function assembledToRaw(assembledTime: number, clips: EditorClip[]): number {
  let cursor = 0
  for (const clip of clips) {
    const dur = Math.max(0, clip.end_time - clip.start_time)
    if (assembledTime <= cursor + dur) return clip.start_time + (assembledTime - cursor)
    cursor += dur
  }
  // Past end — return last clip's end
  const last = clips[clips.length - 1]
  return last ? last.end_time : 0
}

/**
 * Compute leftPct and widthPct for each clip relative to total trailer duration.
 * Clips are laid out sequentially (cursor-based) — matching how the rendered
 * trailer is assembled, not the original source start_time positions.
 */
export function computeTimelineOffsets(clips: EditorClip[]): ClipOffset[] {
  const total = totalDuration(clips)
  if (total <= 0) return []

  let cursor = 0
  return clips.map((clip, index) => {
    const dur      = Math.max(0, clip.end_time - clip.start_time)
    const leftPct  = (cursor / total) * 100
    const widthPct = (dur    / total) * 100
    cursor += dur
    return { clip, index, leftPct, widthPct }
  })
}
