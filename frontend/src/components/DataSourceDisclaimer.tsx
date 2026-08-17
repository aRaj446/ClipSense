import { Info } from 'lucide-react'

/**
 * DataSourceDisclaimer
 *
 * Reusable notice displayed on comment/feedback upload screens.
 * Uses project design-system colours exclusively (inline styles) so it
 * renders correctly in both Tailwind-class contexts (UploadPage) and
 * inline-style contexts (SmartTrailerPanel).
 *
 * Responsive: stacks icon + text on all viewport widths.
 * Typography: 11px — visible without dominating the upload experience.
 */
export default function DataSourceDisclaimer() {
  return (
    <div
      role="note"
      aria-label="Data source information"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '8px',
        padding: '8px 12px',
        borderRadius: '10px',
        background: '#D4A84309',
        border: '1px solid #D4A84328',
      }}
    >
      <Info
        size={12}
        aria-hidden="true"
        style={{ color: '#D4A843', flexShrink: 0, marginTop: '1px' }}
      />
      <p style={{ fontSize: '11px', lineHeight: '1.5', color: '#A8A4B8', margin: 0 }}>
        ClipSense analyses publicly available comments. No personal data is
        stored. All processing is local.
      </p>
    </div>
  )
}
