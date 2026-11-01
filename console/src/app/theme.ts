/** CAVE's colours on Fluent's three themes: light, dark and high contrast. */
import {
  type BrandVariants,
  type Theme,
  createDarkTheme,
  createHighContrastTheme,
  createLightTheme,
} from "@fluentui/react-components";

// deep teal from the mockups (#0B6A8A at 80, the shade Fluent uses for brand backgrounds in light mode)
const cave: BrandVariants = {
  10: "#020D11",
  20: "#041A22",
  30: "#062734",
  40: "#073445",
  50: "#084256",
  60: "#095068",
  70: "#0A5D79",
  80: "#0B6A8A",
  90: "#1D7896",
  100: "#3387A3",
  110: "#4B96B0",
  120: "#64A6BD",
  130: "#7EB6CA",
  140: "#99C6D7",
  150: "#B5D7E4",
  160: "#D3E8F0",
};

const FONT = '"Instrument Sans Variable", "Segoe UI", system-ui, sans-serif';

/**
 * Fills that mean "act" (primary buttons, switches, checkboxes) are near-black, inverted on dark: the teal is
 * kept for data, such as a device that is on, and for links and focus. (taste-skill app rules: colour on data.)
 */
function quietFills(t: Theme, fill: string, hover: string, pressed: string, onFill: string): Theme {
  return {
    ...t,
    fontFamilyBase: FONT,
    colorBrandBackground: fill, colorBrandBackgroundHover: hover, colorBrandBackgroundPressed: pressed,
    colorBrandBackgroundSelected: hover,
    colorCompoundBrandBackground: fill, colorCompoundBrandBackgroundHover: hover,
    colorCompoundBrandBackgroundPressed: pressed, colorCompoundBrandStroke: fill,
    colorCompoundBrandStrokeHover: hover, colorCompoundBrandStrokePressed: pressed,
    colorNeutralForegroundOnBrand: onFill,
  };
}

const light = quietFills(createLightTheme(cave), "#1f201d", "#3a3b37", "#0f100e", "#ffffff");
const dark = quietFills(createDarkTheme(cave), "#f4f4f2", "#d8d8d5", "#ffffff", "#111111");
dark.colorBrandForeground1 = cave[120];
dark.colorBrandForegroundLink = cave[130];
const high = { ...createHighContrastTheme(), fontFamilyBase: FONT };

export const themes: Record<"light" | "dark" | "contrast", Theme> = { light, dark, contrast: high };
export type ThemeName = keyof typeof themes;

function luminance(hex: string): number {
  const v = hex.replace("#", "");
  const full = v.length === 3 ? [...v].map((c) => c + c).join("") : v.slice(0, 6);
  const [r = 0, g = 0, b = 0] = [0, 2, 4].map((i) => {
    const c = parseInt(full.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const [hi = 0, lo = 0] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
