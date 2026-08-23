/**
 * ClipSense Export Service
 *
 * Global singleton that holds the upload-to-ClipSense function.
 * Set by the ClipSense bridge hook when active, consumed by the export flow
 * to automatically upload the rendered video back to ClipSense after export.
 */

type UploadFn = (blob: Blob) => Promise<{ success: boolean; error?: string }>;

let _uploadFn: UploadFn | null = null;
let _isClipSenseSession = false;
let _jobId: string | null = null;
let _apiBase: string | null = null;

/**
 * Register the ClipSense upload function (called by useClipSenseBridge on init)
 */
export function registerClipSenseExport(
  uploadFn: UploadFn,
  jobId: string,
  apiBase: string,
): void {
  _uploadFn = uploadFn;
  _isClipSenseSession = true;
  _jobId = jobId;
  _apiBase = apiBase;
}

/**
 * Clear the ClipSense session (called on unmount or navigation away)
 */
export function clearClipSenseExport(): void {
  _uploadFn = null;
  _isClipSenseSession = false;
  _jobId = null;
  _apiBase = null;
}

/**
 * Check if this is a ClipSense editing session
 */
export function isClipSenseSession(): boolean {
  return _isClipSenseSession;
}

/**
 * Get the ClipSense job ID
 */
export function getClipSenseJobId(): string | null {
  return _jobId;
}

/**
 * Upload a rendered blob to ClipSense.
 * Returns { success: true } or { success: false, error: "..." }
 * Returns { success: false } if no ClipSense session is active.
 */
export async function uploadToClipSense(
  blob: Blob,
): Promise<{ success: boolean; error?: string }> {
  if (!_uploadFn || !_isClipSenseSession) {
    return { success: false, error: "No ClipSense session active" };
  }
  return _uploadFn(blob);
}
