export default function Icon({ name, className = "size-4" }) {
  const paths = {
    arrow: <path d="m5 12 14-7-4 14-3-6-7-1Z" />,
    graph: (
      <>
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="18" cy="7" r="2.5" />
        <circle cx="12" cy="18" r="2.5" />
        <path d="m8.4 6.2 7.1.6M7.4 8.1l3.3 7.5m5.7-6.5-3.1 6.6" />
      </>
    ),
    expand: (
      <>
        <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" />
      </>
    ),
    collapse: (
      <>
        <path d="M3 8h5V3M21 8h-5V3M3 16h5v5M21 16h-5v5" />
      </>
    ),
    refresh: <path d="M20 6v5h-5M4 18v-5h5m9.2-3A7 7 0 0 0 6.1 6.5L4 11m16 2-2.1 4.5A7 7 0 0 1 5.8 14" />,
    stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  };
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}
