---
name: Intelligent Education System
colors:
  surface: '#fff8f7'
  surface-dim: '#f0d4d0'
  surface-bright: '#fff8f7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#fff0ef'
  surface-container: '#ffe9e6'
  surface-container-high: '#ffe2de'
  surface-container-highest: '#f9dcd9'
  on-surface: '#271816'
  on-surface-variant: '#5b403d'
  inverse-surface: '#3e2c2a'
  inverse-on-surface: '#ffedea'
  outline: '#8f706c'
  outline-variant: '#e4beba'
  surface-tint: '#b91d20'
  primary: '#a20513'
  on-primary: '#ffffff'
  primary-container: '#c62828'
  on-primary-container: '#ffe0dd'
  inverse-primary: '#ffb4ac'
  secondary: '#005db7'
  on-secondary: '#ffffff'
  secondary-container: '#64a1ff'
  on-secondary-container: '#003670'
  tertiary: '#00557a'
  on-tertiary: '#ffffff'
  tertiary-container: '#006e9d'
  on-tertiary-container: '#d1eaff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdad6'
  primary-fixed-dim: '#ffb4ac'
  on-primary-fixed: '#410003'
  on-primary-fixed-variant: '#93000e'
  secondary-fixed: '#d6e3ff'
  secondary-fixed-dim: '#a9c7ff'
  on-secondary-fixed: '#001b3d'
  on-secondary-fixed-variant: '#00468c'
  tertiary-fixed: '#c8e6ff'
  tertiary-fixed-dim: '#88ceff'
  on-tertiary-fixed: '#001e2f'
  on-tertiary-fixed-variant: '#004c6e'
  background: '#fff8f7'
  on-background: '#271816'
  surface-variant: '#f9dcd9'
typography:
  h1:
    fontFamily: Lexend
    fontSize: 32px
    fontWeight: '700'
    lineHeight: '1.2'
  h2:
    fontFamily: Lexend
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
  h3:
    fontFamily: Lexend
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Manrope
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Manrope
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-bold:
    fontFamily: Manrope
    fontSize: 12px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: 0.05em
  label-sm:
    fontFamily: Manrope
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.2'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  sidebar_width: 260px
  navbar_height: 72px
  gutter: 24px
  card_padding: 20px
  container_max_width: 1440px
---

## Brand & Style

This design system is built for a high-performance CRM environment tailored to the educational sector. The brand personality is **authoritative, clarifying, and supportive**. It balances the rigor required for data management with the approachability needed in academic administration. 

The aesthetic follows a **Corporate Modern** movement, emphasizing a structured card-based UI. This approach organizes complex student and institutional data into digestible modules. The visual language avoids decorative clutter, focusing instead on structural clarity, high-contrast legibility, and a tactile sense of depth through soft shadows. The result is a professional workspace that feels reliable for daily operations while remaining contemporary and fresh.

## Colors

The color palette is engineered for high visibility and semantic clarity. 
- **Primary (Red):** Used for critical actions, brand presence, and primary navigation highlights. It is a deep, professional crimson to ensure accessibility compliance.
- **Secondary (Blue):** Utilized for secondary actions, information callouts, and links. It provides a stable, calming counterpoint to the primary red.
- **Accent (Yellow):** Reserved for notifications, pending statuses, and highlighting specific data insights. It is a warm gold-tone to maintain legibility against white backgrounds.
- **Neutrals:** A sophisticated range of cool grays ensures the interface feels clean. Backgrounds use a very light tint to allow white cards to "pop" effectively.

## Typography

This design system utilizes a dual-font strategy to optimize for both readability and character. 
- **Lexend** is employed for headlines and titles. Its design specifically caters to reading proficiency and clarity, making institutional headers easy to scan.
- **Manrope** is used for all body text, data entries, and UI labels. Its modern, geometric construction remains highly legible at small sizes, which is essential for dense CRM tables and forms.

Priority is given to vertical rhythm and generous line heights to prevent "data fatigue" during prolonged usage.

## Layout & Spacing

The application utilizes a **Fixed Sidebar and Top Navbar** layout model to provide constant access to global navigation and user tools.
- **Grid:** A 12-column fluid grid system is used within the main content area, allowing cards to span various widths (e.g., 4 columns for metrics, 8 columns for lists).
- **Rhythm:** Spacing follows an 8px base unit. All margins and paddings must be multiples of this unit to ensure mathematical harmony.
- **Margins:** Main content containers feature a 24px margin from the screen edges, providing a breathable frame for the card-based interface.
- **Alignment:** Elements are strictly aligned to the left-edge of the grid for a clean vertical scan line.

## Elevation & Depth

Hierarchy in this design system is established through **Tonal Layers** and **Ambient Shadows**. 
- **The Canvas:** The lowest level is the background (#F8F9FA), which acts as a neutral floor.
- **The Cards:** UI elements reside on white surfaces (#FFFFFF). To distinguish these from the background, they utilize a soft, multi-layered shadow (0px 4px 12px rgba(0,0,0,0.05)).
- **Interactive States:** Upon hover, cards and buttons may increase their elevation slightly (0px 8px 20px rgba(0,0,0,0.08)) to provide tactile feedback.
- **Overlays:** Modals and dropdowns use the highest elevation tier with a more pronounced shadow to focus user attention and signify a break in the standard workflow.

## Shapes

The shape language is defined by **Roundedness Level 2**, which instills a friendly yet professional tone.
- **Standard Elements:** Buttons, input fields, and small UI components use a 0.5rem (8px) radius.
- **Containers:** Large cards and the main sidebar utilize a 1rem (16px) radius to soften the overall interface.
- **Strict Rule:** Dotted or dashed borders are strictly prohibited. All containers must be defined by solid lines or subtle shadow-based edges to maintain a premium "production-ready" feel.

## Components

- **Buttons:** Primary buttons use a solid Red background with white text. Secondary buttons use a Blue outline. All buttons feature a 0.5rem corner radius and no gradients.
- **Cards:** The primary vehicle for information. Cards must have a white background, a 1px solid gray border (#DEE2E6), and a soft shadow. They should never be transparent.
- **Inputs:** Text fields use a solid white background with a 1px border. On focus, the border transitions to Blue (Secondary) with a subtle 2px outer glow.
- **Chips/Badges:** Used for status indicators (e.g., "Active", "Graduated"). These use highly desaturated versions of the primary/secondary colors for the background with high-contrast text.
- **Sidebar:** A fixed-width vertical bar on the left. It uses a dark neutral or the primary brand color to ground the application, providing a clear visual anchor.
- **Data Tables:** High-density rows with clear 1px horizontal dividers. No vertical lines. Headers use Lexend in a bold weight to differentiate from the data.