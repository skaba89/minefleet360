export type IconName = "dashboard" | "truck" | "gps" | "users" | "assignment" | "mission" | "tool" | "calendar" | "scale" | "chart" | "settings" | "menu" | "shield" | "phone" | "fuel";

const paths: Record<IconName, string> = {
  dashboard: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  truck: "M3 6h11v11H3z M14 10h4l3 4v3h-7 M5 17a2 2 0 1 0 4 0 M16 17a2 2 0 1 0 4 0",
  gps: "M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0z M15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  users: "M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3 M13 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M18 3a4 4 0 0 1 0 8 M22 21v-3a4 4 0 0 0-3-4",
  assignment: "M7 3H3v18h18v-4 M8 7h13 M17 3l4 4-4 4 M16 17H7 M11 13l-4 4 4 4",
  mission: "M3 5h6l3 3h9v13H3z M3 5V3h6l3 3",
  tool: "M14 6a5 5 0 0 0-6 6L2 18l4 4 6-6a5 5 0 0 0 6-6l-4 2-2-2z",
  calendar: "M3 5h18v16H3z M7 2v6 M17 2v6 M3 11h18 M7 15h3 M14 15h3",
  scale: "M5 3h14v18H5z M8 6h8v5H8z M9 16h6 M12 6l2 3",
  chart: "M3 3v18h18 M7 16v-5 M12 16V7 M17 16V4",
  settings: "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z",
  menu: "M3 6h18 M3 12h18 M3 18h18",
  shield: "M12 2l9 4v6c0 6-9 10-9 10S3 18 3 12V6z M8 12l3 3 5-6",
  phone: "M7 2h10v20H7z M10 18h4",
  fuel: "M3 21h12 M5 21V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v16 M5 8h8 M14 10h2l3 3v5a2 2 0 0 0 4 0v-6l-3-3",
};

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  return <svg className={`icon ${className}`} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
