"use client";

// One icon per report category, used everywhere a category appears: the map
// beacons, the report form tiles, case lists, status chips, legends and
// timelines. 24×24, stroke-only, drawn in currentColor.

import { categoryHex } from "./labels";

export const CATEGORY_ICONS: Record<string, string> = {
  road_collapse: '<path d="M7 20 9.5 4M17 20 14.5 4"/><path d="M12.5 7l-1.3 2.6 2 1.9-1.4 2.7 1.7 1.8"/>',
  road_blocked: '<path d="M3 8h18v7H3z"/><path d="M6 8l4.5 7M11 8l4.5 7M16 8l4.5 7"/><path d="M6 15v5M18 15v5"/>',
  bridge_damage: '<path d="M3 15c4-6 14-6 18 0M3 15v5M21 15v5M8 11.5V20M16 11.5V20"/><path d="M11 5l2 2.6-2 2.4"/>',
  fallen_tree: '<path d="M4 20 19 11"/><circle cx="16.5" cy="8.5" r="4.2"/><path d="M9 17l-2-4"/>',
  flooding: '<path d="M3 9c2-2.2 4-2.2 6 0s4 2.2 6 0 4-2.2 6 0M3 15c2-2.2 4-2.2 6 0s4 2.2 6 0 4-2.2 6 0"/>',
  embankment_damage: '<path d="M4 20V8h6v12M10 13h4"/><path d="M4 5c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>',
  landslide: '<path d="M2 20 10 7l4.5 6.5L17 11l4 9H2z"/><circle cx="19" cy="4.5" r="1.4" fill="currentColor" stroke="none"/><circle cx="21.5" cy="8.5" r="1.1" fill="currentColor" stroke="none"/>',
  trapped_person: '<circle cx="12" cy="6.5" r="3"/><path d="M6 21v-4.5a6 6 0 0 1 12 0V21"/>',
  medical_need: '<path d="M12 5v14M5 12h14"/>',
  power_outage: '<path d="M13 3 5 13.5h6L10 21l8-10.5h-6z" stroke-linejoin="round"/>',
  water_outage: '<path d="M12 3.5c3 4 5.5 6.8 5.5 10.5a5.5 5.5 0 0 1-11 0C6.5 10.3 9 7.5 12 3.5z"/><path d="M4.5 19.5 19.5 4.5"/>',
  building_damage: '<path d="M4 11l8-7 8 7v9H4z"/><path d="M12 13l-1.4 2.6 1.9 1.8-1.3 2.6"/>',
  fire: '<path d="M12 3c1.2 4 5 5.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2-6 .8 1.2 1.6 2 3-4z"/>',
  gas_leak: '<path d="M7 18h10a4 4 0 0 0 .2-8 5 5 0 0 0-9.6-1A3.6 3.6 0 0 0 7 18z"/>',
  other: '<path d="M12 5v8M12 17.5v.5"/>',
};

// timeline / feed event glyphs, same drawing rules
export const EVENT_ICONS: Record<string, string> = {
  "report.received": '<path d="M4 5h16v10H9l-5 4z"/>',
  threshold_reached: '<circle cx="8.5" cy="8" r="3"/><circle cx="16.5" cy="8" r="3"/><path d="M3 20v-2a5 5 0 0 1 5-5h1M13 20v-2a5 5 0 0 1 5-5h1"/>',
  "case.created": '<path d="M5 21V4h11l-2 4 2 4H5"/>',
  status_changed: '<path d="M5 12h12M13 7l5 5-5 5"/>',
  public_update: '<path d="M4 10v4h3l6 4V6l-6 4H4zM16 9a4 4 0 0 1 0 6"/>',
  internal_note: '<path d="M5 4h10l4 4v12H5z"/><path d="M8 12h8M8 16h6"/>',
  assignment_changed: '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
  dispatch_notified: '<path d="M3 7h10v9H3zM13 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
  "dispatch.created": '<path d="M3 7h10v9H3zM13 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
  "avl.ingested": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>',
  "platform.created": '<path d="M4 5h16v14H4z"/><path d="M4 10h16"/>',
  "platform.published": '<path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
};

export function categoryIcon(category: string): string {
  return CATEGORY_ICONS[category] || CATEGORY_ICONS.other;
}

export function CategoryIcon({ category, size = 16, className = "" }: { category: string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true" dangerouslySetInnerHTML={{ __html: categoryIcon(category) }} />
  );
}

/** Category colour disc with the white icon — the same glyph the map beacons carry. */
export function CategoryBadge({ category, size = 26, color }: { category: string; size?: number; color?: string }) {
  return (
    <span className="inline-grid flex-none place-items-center rounded-full text-white" style={{ width: size, height: size, background: color || categoryHex(category) }}>
      <CategoryIcon category={category} size={Math.round(size * 0.58)} />
    </span>
  );
}

export function EventIcon({ type, size = 12, className = "" }: { type: string; size?: number; className?: string }) {
  const d = EVENT_ICONS[type] || '<circle cx="12" cy="12" r="3"/>';
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true" dangerouslySetInnerHTML={{ __html: d }} />;
}
