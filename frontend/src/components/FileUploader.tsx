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
        className={`relative rounded-2xl p-12 text-center transition-all duration-200 cursor-pointer overflow-hidden
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        style={{
          border: `2px dashed ${dragOver ? '#D4A843' : '#252538'}`,
          background: dragOver
            ? 'linear-gradient(135deg,#D4A84309,#8B7CF606)'
            : 'linear-gradient(145deg,#13131F,#1A1A2E)',
          boxShadow: dragOver ? '0 0 36px 0 #D4A84318, inset 0 0 36px 0 #D4A84308' : 'none',
        }}
      >
        {dragOver && (
          <>
            <span className="absolute top-0 left-0 w-6 h-6 border-t-2 border-l-2 rounded-tl-2xl" style={{ borderColor: '#D4A843' }} />
            <span className="absolute top-0 right-0 w-6 h-6 border-t-2 border-r-2 rounded-tr-2xl" style={{ borderColor: '#D4A843' }} />
            <span className="absolute bottom-0 left-0 w-6 h-6 border-b-2 border-l-2 rounded-bl-2xl" style={{ borderColor: '#D4A843' }} />
            <span className="absolute bottom-0 right-0 w-6 h-6 border-b-2 border-r-2 rounded-br-2xl" style={{ borderColor: '#D4A843' }} />
          </>
        )}

        <UploadCloud
          size={40}
          className={`mx-auto mb-4 transition-all duration-200
            ${dragOver ? 'animate-bounce-subtle scale-110' : ''}`}
          style={{ color: dragOver ? '#D4A843' : '#5C5A72' }}
        />
        <p className="font-medium" style={{ color: dragOver ? '#F0EDE8' : '#A8A4B8' }}>
          {dragOver ? 'Drop to upload' : 'Drag & drop or click to upload'}
        </p>
        <p className="text-sm mt-1" style={{ color: '#5C5A72' }}>MP4, MOV, AVI · Max 10 GB</p>
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
        <p className="text-sm flex items-center gap-1.5" style={{ color: '#F87171' }}>
          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: '#F87171' }} />
          {error}
        </p>
      )}
    </div>
  )
}
