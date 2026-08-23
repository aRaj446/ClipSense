/**
 * useClipSenseBridge — Integration hook for ClipSense → OpenReel flow
 *
 * When OpenReel is opened with the `#/clipsense?projectId=X&jobId=Y` hash:
 *   1. Creates a new project in OpenReel
 *   2. Fetches the raw footage video from ClipSense backend
 *   3. Imports it into OpenReel's media library
 *   4. Places it on the timeline
 *   5. Navigates to the editor
 *
 * After the user edits and exports:
 *   - Uploads the rendered file back to ClipSense
 *   - Registers it as a new trailer with "Edited using SenseScrub" tag
 *
 * URL format: http://localhost:5176/#/clipsense?projectId=UUID&jobId=UUID&apiBase=http://localhost:8000
 */

import { useState, useCallback, useRef } from "react";
import { useProjectStore } from "../stores/project-store";
import { registerClipSenseExport } from "../services/clipsense-export";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ClipSenseBridgeState {
  /** Whether the bridge is actively loading/importing */
  loading: boolean;
  /** Current phase of the loading process */
  phase: string;
  /** Download progress (0-100) */
  progress: number;
  /** Error message if something went wrong */
  error: string | null;
  /** Whether the bridge successfully completed initialization */
  ready: boolean;
  /** The ClipSense project ID (for export-back) */
  projectId: string | null;
  /** The ClipSense job ID (for export-back) */
  jobId: string | null;
  /** The ClipSense API base URL */
  apiBase: string | null;
}

export interface ClipSenseBridgeActions {
  /** Start the import process — called once when the clipsense route is detected */
  startImport: (projectId: string, jobId: string, apiBase?: string) => Promise<void>;
  /** Upload a rendered video back to ClipSense after export */
  uploadToClipSense: (blob: Blob) => Promise<{ success: boolean; error?: string }>;
}

const DEFAULT_API_BASE = "http://localhost:8000";

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useClipSenseBridge(): [ClipSenseBridgeState, ClipSenseBridgeActions] {
  const [state, setState] = useState<ClipSenseBridgeState>({
    loading: false,
    phase: "",
    progress: 0,
    error: null,
    ready: false,
    projectId: null,
    jobId: null,
    apiBase: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  const createNewProject = useProjectStore((s) => s.createNewProject);
  const importMedia = useProjectStore((s) => s.importMedia);
  const addClipToNewTrack = useProjectStore((s) => s.addClipToNewTrack);

  // ── Start import flow ───────────────────────────────────────────────────

  const startImport = useCallback(
    async (projectId: string, jobId: string, apiBase?: string) => {
      const api = apiBase || DEFAULT_API_BASE;

      setState({
        loading: true,
        phase: "Connecting to ClipSense...",
        progress: 0,
        error: null,
        ready: false,
        projectId,
        jobId,
        apiBase: api,
      });

      const abortController = new AbortController();
      abortRef.current = abortController;

      try {
        // Step 1: Fetch editor state from ClipSense to get project name + output URL
        setState((s) => ({ ...s, phase: "Fetching project info..." }));

        let projectName = "ClipSense Edit";
        let trailerOutputUrl: string | null = null;
        try {
          const editorRes = await fetch(`${api}/editor/${jobId}`, {
            signal: abortController.signal,
          });
          if (editorRes.ok) {
            const editorData = await editorRes.json();
            // Get the generated trailer output URL
            if (editorData.output_url) {
              trailerOutputUrl = editorData.output_url;
            }
            // Try to get the project name
            if (editorData.project_id) {
              const projRes = await fetch(`${api}/project/${editorData.project_id}`, {
                signal: abortController.signal,
              });
              if (projRes.ok) {
                const projData = await projRes.json();
                projectName = projData.name || projData.filename || "ClipSense Edit";
              }
            }
          }
        } catch {
          // Non-critical — use default name
        }

        // Step 2: Create a new project in OpenReel
        setState((s) => ({ ...s, phase: "Creating project...", progress: 5 }));
        createNewProject(projectName, { width: 1920, height: 1080, frameRate: 30 });

        // Step 3: Fetch the generated trailer from ClipSense
        setState((s) => ({ ...s, phase: "Downloading generated trailer...", progress: 8 }));

        let trailerImported = false;
        if (trailerOutputUrl) {
          try {
            const trailerUrl = `${api}${trailerOutputUrl}`;
            const trailerRes = await fetch(trailerUrl, { signal: abortController.signal });

            if (trailerRes.ok) {
              const trailerBlob = await trailerRes.blob();
              const trailerFile = new File([trailerBlob], `${projectName} - Generated Trailer.mp4`, { type: "video/mp4" });

              setState((s) => ({ ...s, phase: "Importing generated trailer...", progress: 30 }));
              const trailerImportResult = await importMedia(trailerFile);

              if (trailerImportResult.success && trailerImportResult.actionId) {
                // Place the generated trailer on the timeline
                await addClipToNewTrack(trailerImportResult.actionId, 0);
                trailerImported = true;
              }
            }
          } catch (err) {
            console.warn("[ClipSenseBridge] Failed to fetch generated trailer, continuing with raw footage:", err);
          }
        }

        // Step 4: Fetch the raw footage video from ClipSense
        setState((s) => ({ ...s, phase: "Downloading raw footage...", progress: trailerImported ? 40 : 15 }));

        const videoUrl = `${api}/editor/${jobId}/raw-video`;
        const videoRes = await fetch(videoUrl, { signal: abortController.signal });

        if (!videoRes.ok) {
          throw new Error(`Failed to fetch video: ${videoRes.status} ${videoRes.statusText}`);
        }

        // Stream download with progress
        const contentLength = parseInt(videoRes.headers.get("content-length") || "0", 10);
        const reader = videoRes.body?.getReader();

        let videoBlob: Blob;

        if (reader && contentLength > 0) {
          const chunks: Uint8Array[] = [];
          let loaded = 0;
          const progressBase = trailerImported ? 40 : 15;
          const progressRange = trailerImported ? 45 : 70;

          while (true) {
            if (abortController.signal.aborted) throw new DOMException("Aborted", "AbortError");
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
            loaded += value.length;
            const pct = Math.round((loaded / contentLength) * progressRange) + progressBase;
            setState((s) => ({
              ...s,
              progress: pct,
              phase: `Downloading raw footage... ${Math.round((loaded / 1024 / 1024) * 10) / 10}MB`,
            }));
          }
          videoBlob = new Blob(chunks, { type: "video/mp4" });
        } else {
          // Fallback: no streaming
          videoBlob = await videoRes.blob();
        }

        setState((s) => ({ ...s, phase: "Importing raw footage...", progress: 87 }));

        // Step 5: Import raw footage into OpenReel's media library
        const videoFile = new File([videoBlob], `${projectName} - Raw Footage.mp4`, { type: "video/mp4" });
        const importResult = await importMedia(videoFile);

        if (!importResult.success || !importResult.actionId) {
          throw new Error(importResult.error?.message || "Media import failed");
        }

        // Only place raw footage on timeline if trailer wasn't imported
        if (!trailerImported) {
          setState((s) => ({ ...s, phase: "Placing on timeline...", progress: 93 }));
          const mediaId = importResult.actionId;
          const clipResult = await addClipToNewTrack(mediaId, 0);

          if (!clipResult.success) {
            console.warn("[ClipSenseBridge] Failed to place on timeline:", clipResult.error);
          }
        }

        setState((s) => ({
          ...s,
          loading: false,
          phase: "",
          progress: 100,
          ready: true,
        }));

        // Register the upload function for the export flow
        registerClipSenseExport(
          async (blob: Blob) => {
            const formData = new FormData();
            formData.append("file", blob, `sensescrub-export-${Date.now()}.mp4`);
            const res = await fetch(`${api}/editor/${jobId}/upload-render`, {
              method: "POST",
              body: formData,
            });
            if (!res.ok) {
              const errData = await res.json().catch(() => ({}));
              return { success: false, error: errData.detail || `Upload failed: ${res.status}` };
            }
            return { success: true };
          },
          jobId,
          api,
        );
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        const message = err instanceof Error ? err.message : String(err);
        setState((s) => ({
          ...s,
          loading: false,
          phase: "",
          error: `Import failed: ${message}`,
        }));
      }
    },
    [createNewProject, importMedia, addClipToNewTrack],
  );

  // ── Upload exported video back to ClipSense ─────────────────────────────

  const uploadToClipSense = useCallback(
    async (blob: Blob): Promise<{ success: boolean; error?: string }> => {
      const { jobId, apiBase } = state;
      if (!jobId || !apiBase) {
        return { success: false, error: "No ClipSense session active" };
      }

      try {
        const formData = new FormData();
        formData.append("file", blob, `sensescrub-export-${Date.now()}.mp4`);

        const res = await fetch(`${apiBase}/editor/${jobId}/upload-render`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          return {
            success: false,
            error: errData.detail || `Upload failed: ${res.status}`,
          };
        }

        return { success: true };
      } catch (err) {
        return {
          success: false,
          error: err instanceof Error ? err.message : "Upload failed",
        };
      }
    },
    [state],
  );

  return [state, { startImport, uploadToClipSense }];
}
