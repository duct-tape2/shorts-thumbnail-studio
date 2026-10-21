# Thumbnail studio UI

Direction: a quiet desktop production workspace for a Korean thumbnail editor.
The finished vertical thumbnail is the focal point, not chrome or metrics.

Palette: navy #142B46, paper #FFFFFF, workspace #F0F3F7, ink #172B43,
muted #607084, brand orange #F58220. Orange is reserved for importing files.
Typeface: bundled SUIT; title 24px, section 17px, body 14px, hints 12px.

Layout: left aligned labels and actions; portrait preview centered on a neutral
canvas. A narrow navy rail contains the queue. White editor on the right has
stacked labels so Korean fields are not squeezed. Settings stay collapsed.

    file queue | large result / original tabs | wording editor
    import     | empty state gives one action | disabled until ready
    capture    | progress and next action     | regenerate

Review: keep brand continuity without turning every region into a card. Use
one workspace rather than a dashboard. No decorative metrics, gradients,
or engine/font-size details in the main user flow. Color always accompanied
by status text. Keyboard focus visible. Check empty/processing/completed/error
states at 1280×850 and 1024×720, including packaged Windows Qt rendering.

Reference: https://github.com/anthropics/skills/tree/main/skills/frontend-design
Read from work/design-skills/frontend-design/SKILL.md; design advice adapted to Qt.
