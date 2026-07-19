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
    if (!['mp4', 'mov', 'avi'].includes(ext)) {
      return `Unsupported format ".${ext}". Allowed: MP4, MOV, AVI`
    }
    if (file.size > MAX_FILE_SIZE) {
      return `File too large (${formatFileSize(file.size)}). Max: 10 GB`
    }
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
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer
          ${dragOver ? 'border-primary bg-primary/10' : 'border-surface-border hover:border-primary/50 hover:bg-surface-card'}
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <UploadCloud
          size={40}
          className={`mx-auto mb-4 ${dragOver ? 'text-primary' : 'text-slate-500'}`}
        />
        <p className="text-slate-300 font-medium">Drag & drop or click to upload</p>
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
        <p className="text-red-400 text-sm flex items-center gap-1">⚠ {error}</p>
      )}
    </div>
  )
}
