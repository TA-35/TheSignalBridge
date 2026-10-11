// The six pattern categories (the fixed enum in docs/api-contract.md) and the
// calm colour each one is shown in. One hue per category, used on the Pattern
// Library cards and filter pills. No red: these are kinds of phrasing, not
// problems, and nothing here should read as an error.
//
// Only the base hue lives here. The soft background and the text colour are
// mixed from it in CSS against the theme's own surface and text colours, so
// they follow light and dark mode without a second palette.

export const CATEGORY_HUE: Record<string, string> = {
  'Softened request': '#3D7F88', // teal
  'Vague deadline': '#A88442', // honey
  'Unassigned owner': '#7466A8', // lavender
  'Unclear priority': '#4A6FA5', // slate blue
  'Undefined scope': '#737A35', // olive
  'Feedback framing': '#8E6487', // heather
}

// A category the library doesn't know yet still renders, just in a neutral tone.
export const FALLBACK_HUE = '#6B645E'

export function categoryHue(name: string | null | undefined): string {
  return (name && CATEGORY_HUE[name]) || FALLBACK_HUE
}
