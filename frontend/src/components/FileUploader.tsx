import { useRef, DragEvent, ChangeEvent, useState } from 'react'
import { UploadCloud } from 'lucide-react'
import { ACCEPTED_MIME, MAX_FILE_SIZE, formatFileSize } from '../utils/format'

interface Props {
  onFile: (file: File) => void
  disabled?: boolean
}

export default function FileUploader({ onFile, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function validate(file: File): string | null {
    const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (!['mp4', 'mov', 'avi'].includes(ext))
      return `Unsupported format ".${ext}". Allowed: MP4, MOV, AVI`
    if (file.size > MAX_FILE_SIZE)
      return `File too large (${formatFileSize(file.size)}). Max: 10 GB`
    return null
  }

  function handleFile(file: File) {
    const err = validate(file)
    if (err) { setError(err); return }
    setError(null)
    onFile(file)
  }

  function onInputChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  return (
    <div className="space-y-2">
      <div
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`relative rounded-xl p-12 text-center transition-all duration-200 cursor-pointer overflow-hidden
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        style={{
          border: `2px dashed ${dragOver ? '#2563EB' : '#1C2A3F'}`,
          background: dragOver
            ? 'linear-gradient(135deg,#2563EB0A,#7C3AED08)'
            : 'linear-gradient(145deg,#0E1525,#141E30)',
          boxShadow: dragOver ? '0 0 32px 0 #2563EB18, inset 0 0 32px 0 #2563EB08' : 'none',
        }}
      >
        {/* Animated corner accents when dragging */}
        {dragOver && (
          <>
            <span className="absolute top-0 left-0 w-6 h-6 border-t-2 border-l-2 border-primary rounded-tl-xl" />
            <span className="absolute top-0 right-0 w-6 h-6 border-t-2 border-r-2 border-primary rounded-tr-xl" />
            <span className="absolute bottom-0 left-0 w-6 h-6 border-b-2 border-l-2 border-primary rounded-bl-xl" />
            <span className="absolute bottom-0 right-0 w-6 h-6 border-b-2 border-r-2 border-primary rounded-br-xl" />
          </>
        )}

        <UploadCloud
          size={40}
          className={`mx-auto mb-4 transition-all duration-200
            ${dragOver ? 'text-primary animate-bounce-subtle scale-110' : 'text-slate-500'}`}
        />
        <p className="text-slate-300 font-medium">
          {dragOver ? 'Drop to upload' : 'Drag & drop or click to upload'}
        </p>
        <p className="text-slate-500 text-sm mt-1">MP4, MOV, AVI · Max 10 GB</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_MIME}
          className="hidden"
          onChange={onInputChange}
          disabled={disabled}
        />
      </div>
      {error && (
        <p className="text-red-400 text-sm flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
          {error}
        </p>
      )}
    </div>
  )
}
