/**
 * Vietnam flag as an inline SVG.
 *
 * The regional-indicator emoji 🇻🇳 renders as a real flag on macOS / iOS / Android,
 * but Windows ships no flag glyphs, so Chrome/Edge on Windows fall back to the
 * letters "VN". This component renders identically on every platform with no font
 * dependency and no extra network request (so it can never be a deploy-asset 404).
 *
 * `size` sets the rendered height in px; width follows the flag's 3:2 ratio.
 */
export default function VnFlag({
  size = 20,
  className,
  style,
  title = 'Vietnam',
}: {
  size?: number
  className?: string
  style?: React.CSSProperties
  title?: string
}) {
  return (
    <svg
      className={className}
      width={(size * 3) / 2}
      height={size}
      viewBox="0 0 30 20"
      role="img"
      aria-label={title}
      style={{ display: 'inline-block', verticalAlign: 'middle', borderRadius: 2, ...style }}
    >
      <title>{title}</title>
      <rect width="30" height="20" fill="#DA251D" />
      {/* Centered yellow five-pointed star (outer r=6, inner r=2.29, centred at 15,10) */}
      <path
        fill="#FF0"
        d="M15 4 16.35 8.15 20.71 8.15 17.18 10.71 18.53 14.85 15 12.29 11.47 14.85 12.82 10.71 9.29 8.15 13.65 8.15Z"
      />
    </svg>
  )
}
