import { CheckCircle, Clock, ArrowDown } from 'lucide-react'
import Card from './Card'

interface Stage {
  label: string
  description: string
  status: 'active' | 'future'
}

const STAGES: Stage[] = [
  { label: 'Raw Feedback Ingestion',      description: 'Paste externally collected audience feedback',         status: 'active'  },
  { label: 'Feedback Structuring Agent',  description: 'Converts unstructured text into structured segments',  status: 'active'  },
  { label: 'Structured Dataset',          description: 'Normalised JSON with sentiment, topic & timestamps',   status: 'active'  },
  { label: 'Video Optimization Agent',    description: 'Generates editing recommendations from insights',      status: 'active'  },
  { label: 'Scene Detection',             description: 'Automatic scene boundary detection',                   status: 'future'  },
  { label: 'Transcript Generation',       description: 'Speech-to-text with word-level timestamps (Whisper)', status: 'future'  },
  { label: 'Video Regeneration Agent',    description: 'AI-powered trailer regeneration from editing plan',    status: 'future'  },
  { label: 'Optimized Trailer Output',    description: 'Final optimized trailer delivered to user',            status: 'future'  },
]

export default function PipelineDiagram() {
  return (
    <Card>
      <h3 className="font-semibold text-slate-100 mb-1">AI Pipeline</h3>
      <p className="text-xs text-slate-500 mb-5">
        Current POC stages are active. Future stages are placeholders for upcoming phases.
      </p>

      <div className="space-y-1">
        {STAGES.map((stage, i) => (
          <div key={stage.label}>
            <div className={`flex items-start gap-3 rounded-lg px-3 py-2.5
              ${stage.status === 'active'
                ? 'bg-primary/10 border border-primary/20'
                : 'bg-surface border border-surface-border opacity-50'
              }`}
            >
              {stage.status === 'active' ? (
                <CheckCircle size={15} className="text-primary shrink-0 mt-0.5" />
              ) : (
                <Clock size={15} className="text-slate-500 shrink-0 mt-0.5" />
              )}
              <div className="min-w-0">
                <p className={`text-sm font-medium ${stage.status === 'active' ? 'text-slate-100' : 'text-slate-500'}`}>
                  {stage.label}
                  {stage.status === 'future' && (
                    <span className="ml-2 text-[10px] bg-surface-border text-slate-500 px-1.5 py-0.5 rounded">
                      Future
                    </span>
                  )}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">{stage.description}</p>
              </div>
            </div>

            {i < STAGES.length - 1 && (
              <div className="flex justify-center py-0.5">
                <ArrowDown size={12} className="text-surface-border" />
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}
