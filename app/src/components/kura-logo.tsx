/** Kura's mark: three spines on a shelf (蔵, kura, is a storehouse). */
export function KuraLogo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="1" y="1" width="22" height="22" rx="7" className="fill-accent" />
      <rect x="6.4" y="6.5" width="2.8" height="11" rx="1.4" className="fill-on-accent" />
      <rect x="10.6" y="8.5" width="2.8" height="9" rx="1.4" className="fill-on-accent" />
      <rect
        x="14.6"
        y="6.2"
        width="2.8"
        height="11.2"
        rx="1.4"
        transform="rotate(14 16 11.8)"
        className="fill-on-accent"
      />
    </svg>
  );
}
