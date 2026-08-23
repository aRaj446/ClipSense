/**
 * Media Loader — Fetch raw footage as a blob for the engine
 *
 * Downloads the raw footage file from the backend (`GET /editor/{job_id}/raw-video`)
 * into browser memory. The blob is then used by OpenReel's VideoEngine to decode
 * individual frames via WebCodecs.
 *
 * Features:
 *   - Progress tracking for large files
 *   - Metadata extraction via mediabunny (duration, dimensions, codec, frame rate)
 *   - Abort support for cleanup on unmount
 */

import type { MediaMetadata } from '@openreel/core'
import type { MediaLoadProgress } from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface MediaLoadResult {
  blob: Blob
  metadata: MediaMetadata
  url: string // object URL for fallback <video> usage
}

export type ProgressCallback = (progress: MediaLoadProgress) => void

// ── Main loader function ──────────────────────────────────────────────────────

/**
 * Fetch the raw footage file as a blob with progress tracking.
 *
 * @param jobId - The editor job ID to fetch footage for
 * @param onProgress - Optional callback for download progress
 * @param signal - Optional AbortSignal for cancellation
 * @returns The blob, extracted metadata, and an object URL
 */
export async function loadRawFootage(
  jobId: string,
  onProgress?: ProgressCallback,
  signal?: AbortSignal,
): Promise<MediaLoadResult> {
  const url = `${API_BASE}/editor/${jobId}/raw-video`

  // Fetch with progress tracking via ReadableStream
  const response = await fetch(url, { signal })

  if (!response.ok) {
    throw new Error(`Failed to fetch raw footage: ${response.status} ${response.statusText}`)
  }

  const contentLength = parseInt(response.headers.get('content-length') || '0', 10)
  const reader = response.body?.getReader()

  if (!reader) {
    // Fallback: no streaming, just get the blob directly
    const blob = await response.blob()
    const metadata = await extractMetadata(blob)
    return { blob, metadata, url: URL.createObjectURL(blob) }
  }

  // Stream the response and track progress
  const chunks: Uint8Array[] = []
  let loaded = 0

  while (true) {
    if (signal?.aborted) {
      reader.cancel()
      throw new DOMException('Download cancelled', 'AbortError')
    }

    const { done, value } = await reader.read()
    if (done) break

    chunks.push(value)
    loaded += value.length

    onProgress?.({
      loaded,
      total: contentLength || loaded,
      percent: contentLength > 0 ? Math.round((loaded / contentLength) * 100) : 0,
    })
  }

  // Assemble blob from chunks
  const blob = new Blob(chunks, { type: 'video/mp4' })

  onProgress?.({ loaded, total: loaded, percent: 100 })

  // Extract metadata
  const metadata = await extractMetadata(blob)

  return {
    blob,
    metadata,
    url: URL.createObjectURL(blob),
  }
}

// ── Metadata extraction ───────────────────────────────────────────────────────

/**
 * Extract video metadata from a blob using a temporary <video> element.
 * This is a reliable fallback that works even if mediabunny isn't available.
 *
 * For more detailed codec info, we attempt to use mediabunny first and
 * fall back to the video element approach.
 */
async function extractMetadata(blob: Blob): Promise<MediaMetadata> {
  // Try mediabunny first for accurate metadata
  try {
    const metadata = await extractMetadataViaMB(blob)
    if (metadata) return metadata
  } catch {
    // Fall through to video element approach
  }

  // Fallback: use a temporary <video> element
  return extractMetadataViaVideoElement(blob)
}

/**
 * Use mediabunny to extract detailed metadata (codec, exact frame rate, etc.)
 */
async function extractMetadataViaMB(blob: Blob): Promise<MediaMetadata | null> {
  try {
    const mb = await import('mediabunny')
    const source = new mb.BlobSource(blob)
    const input = await mb.Input.fromSource(source)

    const videoTrack = input.videoTracks[0] as any
    const audioTrack = input.audioTracks[0] as any

    if (!videoTrack) return null

    const metadata: MediaMetadata = {
      duration: videoTrack.duration ?? 0,
      width: videoTrack.displayWidth ?? videoTrack.width ?? 1920,
      height: videoTrack.displayHeight ?? videoTrack.height ?? 1080,
      frameRate: videoTrack.frameRate ?? 30,
      codec: videoTrack.codec ?? 'h264',
      sampleRate: audioTrack?.sampleRate ?? 44100,
      channels: audioTrack?.numberOfChannels ?? 2,
      fileSize: blob.size,
      audioTrackCount: input.audioTracks.length,
    }

    // Clean up
    input[Symbol.dispose]?.()

    return metadata
  } catch {
    return null
  }
}

/**
 * Fallback metadata extraction using a temporary <video> element.
 * Less accurate (can't get codec, exact frame rate) but always works.
 */
function extractMetadataViaVideoElement(blob: Blob): Promise<MediaMetadata> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video')
    video.preload = 'metadata'
    const objectUrl = URL.createObjectURL(blob)
    video.src = objectUrl

    const timeout = setTimeout(() => {
      cleanup()
      // Return best-effort defaults if metadata loading times out
      resolve({
        duration: 0,
        width: 1920,
        height: 1080,
        frameRate: 30,
        codec: 'unknown',
        sampleRate: 44100,
        channels: 2,
        fileSize: blob.size,
      })
    }, 10000)

    function cleanup() {
      clearTimeout(timeout)
      URL.revokeObjectURL(objectUrl)
      video.removeEventListener('loadedmetadata', onMeta)
      video.removeEventListener('error', onError)
      video.src = ''
    }

    function onMeta() {
      const metadata: MediaMetadata = {
        duration: video.duration || 0,
        width: video.videoWidth || 1920,
        height: video.videoHeight || 1080,
        frameRate: 30, // Can't get exact FPS from video element
        codec: 'h264', // Assume H.264 for MP4
        sampleRate: 44100,
        channels: 2,
        fileSize: blob.size,
      }
      cleanup()
      resolve(metadata)
    }

    function onError() {
      cleanup()
      reject(new Error('Failed to load video metadata'))
    }

    video.addEventListener('loadedmetadata', onMeta)
    video.addEventListener('error', onError)
  })
}

// ── Cleanup utility ───────────────────────────────────────────────────────────

/**
 * Revoke an object URL created by loadRawFootage.
 * Call on unmount to free memory.
 */
export function releaseMediaUrl(url: string): void {
  try {
    URL.revokeObjectURL(url)
  } catch {
    // Ignore — already revoked or invalid
  }
}
