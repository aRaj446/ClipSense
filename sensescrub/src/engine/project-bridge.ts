/**
 * Project Bridge — SenseScrub EditorClip[] → OpenReel Project
 *
 * Converts SenseScrub's flat clip list (segments of a single raw footage file)
 * into OpenReel's full Project structure so the VideoEngine can render frames.
 *
 * Key mapping:
 *   - All clips reference a single MediaItem (the raw footage blob)
 *   - Clips are placed sequentially on a single video track (assembled timeline)
 *   - Each clip's `inPoint`/`outPoint` maps to source footage offsets
 *   - `startTime` on the OpenReel Clip = assembled position (cumulative offset)
 *   - Muted clips have volume=0
 *
 * This bridge is recalculated whenever clips change (trim, reorder, delete, add).
 */

import type { EditorClip } from '../types'
import type {
  Project,
  ProjectSettings,
  MediaLibrary,
  MediaItem,
  MediaMetadata,
} from '@openreel/core'
import type {
  Timeline,
  Track,
  Clip,
  Transform,
} from '@openreel/core'

// ── Constants ─────────────────────────────────────────────────────────────────

const MEDIA_ID = 'raw-footage'
const TRACK_ID = 'main-video'
const TRACK_NAME = 'Video'

// ── Default transform — identity (full-frame, centered) ─────────────────────

const DEFAULT_TRANSFORM: Transform = {
  position: { x: 0, y: 0 },
  scale: { x: 1, y: 1 },
  rotation: 0,
  anchor: { x: 0.5, y: 0.5 },
  opacity: 1,
}

// ── Project settings (1080p @ 30fps — matches backend compose pipeline) ─────

const DEFAULT_SETTINGS: ProjectSettings = {
  width: 1920,
  height: 1080,
  frameRate: 30,
  sampleRate: 44100,
  channels: 2,
}

// ── Bridge interface ──────────────────────────────────────────────────────────

export interface ProjectBridgeOptions {
  /** Override project resolution if raw footage has different dimensions */
  width?: number
  height?: number
  /** Override frame rate */
  frameRate?: number
}

export interface ProjectBridgeResult {
  /** The OpenReel Project ready for VideoEngine.renderFrame() */
  project: Project
  /** Total assembled duration in seconds */
  totalDuration: number
  /** Map from SenseScrub clip ID → OpenReel clip ID (same value) */
  clipIdMap: Map<string, string>
}

// ── Core bridge function ──────────────────────────────────────────────────────

/**
 * Convert SenseScrub's clip list + raw footage metadata into an OpenReel Project.
 *
 * @param clips - The current ordered clip list from useEditorState
 * @param mediaBlob - The raw footage file blob (fetched from /editor/{id}/raw-video)
 * @param mediaMetadata - Metadata about the raw footage (duration, dimensions, codec)
 * @param options - Optional overrides for project settings
 */
export function buildProject(
  clips: EditorClip[],
  mediaBlob: Blob,
  mediaMetadata: MediaMetadata,
  options: ProjectBridgeOptions = {},
): ProjectBridgeResult {

  const settings: ProjectSettings = {
    ...DEFAULT_SETTINGS,
    width: options.width ?? mediaMetadata.width ?? DEFAULT_SETTINGS.width,
    height: options.height ?? mediaMetadata.height ?? DEFAULT_SETTINGS.height,
    frameRate: options.frameRate ?? mediaMetadata.frameRate ?? DEFAULT_SETTINGS.frameRate,
  }

  // Build the media library with a single entry — the raw footage
  const mediaItem: MediaItem = {
    id: MEDIA_ID,
    name: 'Raw Footage',
    type: 'video',
    fileHandle: null,
    blob: mediaBlob,
    metadata: mediaMetadata,
    thumbnailUrl: null,
    waveformData: null,
  }

  const mediaLibrary: MediaLibrary = {
    items: [mediaItem],
  }

  // Build timeline clips — sequential assembly from the clip list
  const clipIdMap = new Map<string, string>()
  const timelineClips: Clip[] = []
  let assembledOffset = 0

  for (const editorClip of clips) {
    const duration = Math.max(0, editorClip.end_time - editorClip.start_time)
    if (duration <= 0) continue

    // Speed affects assembled duration: faster = shorter, slower = longer
    const speed = editorClip.speed ?? 1
    const assembledDuration = duration / speed

    const openreelClip: Clip = {
      id: editorClip.id,
      mediaId: MEDIA_ID,
      trackId: TRACK_ID,
      startTime: assembledOffset,
      duration: assembledDuration,
      inPoint: editorClip.start_time,   // source footage start
      outPoint: editorClip.end_time,     // source footage end
      effects: [],
      audioEffects: [],
      transform: DEFAULT_TRANSFORM,
      volume: editorClip.muted ? 0 : 1,
      keyframes: [],
      speed: editorClip.speed ?? 1,
    }

    timelineClips.push(openreelClip)
    clipIdMap.set(editorClip.id, editorClip.id)
    assembledOffset += assembledDuration
  }

  // Build the track
  const videoTrack: Track = {
    id: TRACK_ID,
    type: 'video',
    name: TRACK_NAME,
    clips: timelineClips,
    transitions: [],
    locked: false,
    hidden: false,
    muted: false,
    solo: false,
  }

  // Build the timeline
  const timeline: Timeline = {
    tracks: [videoTrack],
    subtitles: [],
    duration: assembledOffset,
    markers: [],
  }

  // Build the project
  const project: Project = {
    id: 'sensescrub-project',
    name: 'SenseScrub Edit',
    createdAt: Date.now(),
    modifiedAt: Date.now(),
    settings,
    mediaLibrary,
    timeline,
  }

  return {
    project,
    totalDuration: assembledOffset,
    clipIdMap,
  }
}

// ── Utility: update project when clips change ─────────────────────────────────

/**
 * Rebuild the project with a new clip list while reusing the same media blob.
 * This is called on every clip mutation (trim, reorder, delete, add, mute toggle).
 *
 * @param prevProject - The current project (to reuse mediaLibrary.items[0].blob)
 * @param clips - The new clip list
 * @param options - Optional overrides
 */
export function rebuildProject(
  prevProject: Project,
  clips: EditorClip[],
  options: ProjectBridgeOptions = {},
): ProjectBridgeResult {
  const mediaItem = prevProject.mediaLibrary.items[0]
  if (!mediaItem || !mediaItem.blob) {
    throw new Error('[ProjectBridge] Cannot rebuild — no media blob in project')
  }

  return buildProject(clips, mediaItem.blob, mediaItem.metadata, options)
}

// ── Utility: compute assembled time for a given clip ──────────────────────────

/**
 * Get the assembled start time of a specific clip by ID.
 */
export function getClipAssembledStart(clips: EditorClip[], clipId: string): number {
  let offset = 0
  for (const clip of clips) {
    if (clip.id === clipId) return offset
    offset += Math.max(0, clip.end_time - clip.start_time)
  }
  return offset
}

/**
 * Find which clip is active at a given assembled timeline position.
 * Returns the clip and its index, or null if past all clips.
 */
export function getClipAtAssembledTime(
  clips: EditorClip[],
  assembledTime: number,
): { clip: EditorClip; index: number } | null {
  let offset = 0
  for (let i = 0; i < clips.length; i++) {
    const clip = clips[i]
    const duration = Math.max(0, clip.end_time - clip.start_time)
    if (assembledTime < offset + duration) {
      return { clip, index: i }
    }
    offset += duration
  }
  return null
}
