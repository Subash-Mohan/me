# Me App UI Brand Spec

Source: visual extraction from `mp8nfqs1-Screenshot-2026-05-16-at-11.27.41-PM.png` and `mp8ng1aw-Screenshot-2026-05-16-at-11.27.54-PM.png`.

## Tokens

```css
:root {
  --bg:      oklch(18.2% 0.0000 89.9);
  --surface: oklch(21.8% 0.0000 89.9);
  --fg:      oklch(86.8% 0.0081 106.6);
  --muted:   oklch(64.8% 0.0088 106.6);
  --border:  oklch(28.1% 0.0018 106.5);
  --accent:  oklch(77.4% 0.1189 160.5);

  --font-display: 'Iowan Old Style', 'Charter', Georgia, serif;
  --font-body:    -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Avenir Next', system-ui, sans-serif;
  --font-mono:    'SF Mono', 'JetBrains Mono', ui-monospace, Menlo, monospace;
}
```

## Observed posture

1. Near-black canvas with almost hue-free graphite surfaces; separation comes from 1px outlines and contrast, not glossy fills.
2. The bright surface is the chat bubble itself: a pale linen off-white around `#d4d4ce`, used sparingly as the main moment of emphasis.
3. Accent use is minimal and green-led, not terracotta-led: a mint listening dot and small status glyphs around `#69cd9c`, sometimes anchored by a deeper green around `#285541`.
4. Serif is used sparingly for identity and reflective content; chrome stays in a rounded sans with uppercase micro-labels, timestamps, and low-contrast metadata.
5. A faint top haze / scanline texture sits over the black background, giving the UI a soft cinematic surface without turning into visible noise.
